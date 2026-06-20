---
id: backstage-plugins
title: Phase 24 — Backstage Plugins (custom image)
sidebar_position: 2
---

# Phase 24 — Backstage Plugins (custom image build)

Phase 18 shipped a minimal Backstage catalog — read-only inventory of 5 GitHub repos via the off-the-shelf `ghcr.io/backstage/backstage` image. This phase converts Backstage from "directory of repos" into a real Internal Developer Portal by:

1. **Fixing the broken UI** — the upstream off-the-shelf frontend bundle includes the notifications plugin without the matching `apiRef` factory in `packages/app/src/apis.ts`, throwing `NotImplementedError` on every page load. This is structural; no version pin or chart-values change can resolve it. Only a custom build can.
2. **Adding the four plugins that make Backstage actually useful** — Kubernetes (live pod state per Component), ArgoCD (sync/health per Component), Grafana (embedded dashboards), TechDocs (in-portal Markdown rendering).
3. **Wiring Authentik OIDC** (assumes Phase 23 has shipped) — replaces guest auth with the same SSO every other app uses.

End state: Backstage transforms from "I can look up the platform-demo repo" into "I can see live cluster state, deployment health, observability dashboards, and rendered docs — all for any Component, all in one UI, gated by Authentik."

---

## Why this phase requires a custom image (and Phase 18 didn't)

Phase 18 deliberately deferred this work with explicit reasoning. CLAUDE.md and the Phase 18 doc note:

> Off-the-shelf image `ghcr.io/backstage/backstage:latest` — avoids 3+ hours of Node.js scaffold + Docker build for marginal portfolio gain at Phase 18's catalog-only scope.

That trade-off no longer holds at Phase 24 scope. The plugins ARE the value. Each one (`@backstage/plugin-kubernetes`, etc.) is a separate npm package that must be:
- Added to `packages/app/package.json` (frontend) and `packages/backend/package.json` (backend)
- Registered in `packages/app/src/App.tsx` (route mounting) and `packages/app/src/apis.ts` (API client registration)
- Backend-equivalent registered in `packages/backend/src/index.ts`
- Configured in `app-config.yaml` (per-plugin auth / endpoint config)

None of those changes are possible without rebuilding the image. The off-the-shelf image is a frozen demo build; customization happens *inside* the build pipeline. This is Spotify's intentional design — Backstage is *meant* to be a framework you build on, not a turnkey app you `helm install`.

The notifications bug becomes incidental: when you rebuild `packages/app/src/apis.ts` to add the plugins you want, you also remove the broken notifications import (or register a no-op fallback). The UI fix comes free.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backstage version | **`@backstage/create-app` latest** (single decisive pull, immutable) | The off-the-shelf `:latest` drift problem disappears the moment we own the image — every build produces a SHA-tagged immutable artifact pushed to Harbor. |
| Plugins (Day 1) | Kubernetes + ArgoCD + Grafana + TechDocs | Highest-value-per-effort. Each one targets a workload we already run on the cluster, so they have something real to show. |
| Plugins (Day 2 / deferred) | Software Templates (scaffolder), GitHub Actions, Notifications backend, Search | Each adds substantial config + auth surface area; can layer in after foundation is solid. |
| Auth | Authentik OIDC (assumes Phase 23 has shipped) | Replaces guest auth. Same OIDC client pattern as ArgoCD + Grafana. |
| Image registry | `harbor.10.0.0.200.nip.io/library/backstage:<git-sha>` | Phase 7 + Phase 16 give us a proper home for custom images. Tagged by git SHA — same pattern as `platform-demo` (Phase 13). |
| Build location | Locally on Mac (`yarn build-image`), then `crane copy` to Harbor | Avoids needing a Backstage-specific GHA workflow; Mac builds are fast (~3-5 min) and Harbor accepts the push. |
| GitOps | Helm release stays managed via direct `helm upgrade` (same as today); `backstage-values.yaml` mirrored to `minicloud-ansible/helm-values/` (Phase 18 pattern) | Postgres StatefulSet + 1 GiB PVC migration through ArgoCD is high-risk; deferred to a separate "Backstage GitOps" phase if ever needed. |
| Catalog content | Same 5 catalog-info.yaml URLs as Phase 18 | No regression in what the catalog ingests; only the UI rendering changes. |

---

## What's deliberately deferred

| Component | Reason | Future home |
|---|---|---|
| **Software Templates ("Golden Paths")** | The single most valuable Backstage feature, but needs scaffolder backend + at least 2-3 well-designed templates to be useful. Quick-start templates without good design hurt more than they help. | Future "Backstage Templates" phase, after Day 1 plugins prove themselves |
| **GitHub Actions plugin** | Needs a GitHub App (vs PAT) for least-privileged scoping. Worth adding in a paired "GitHub integration" phase | Future phase |
| **Notifications backend** | Once the notifications-API mismatch is fixed via no-op fallback in `apis.ts`, the bell icon goes away. Wiring an actual notifications backend (email / Slack / webhook) is its own substantial feature | Future phase |
| **Search plugin** | The default search backend works fine for the 5 Components we have; tuning becomes valuable once there are ~50+ entities | When catalog grows past ~20 entities |
| **Vault for OIDC client secret** | Vault itself is deferred (Phase 15 honest scope note) | Pair with future Vault phase |

---

## Pre-flight

```bash
# 1. Phase 23 (Authentik) is shipped and Stage 1+3 are green
curl -sIf --cacert ~/minicloud-ca.crt https://auth.10.0.0.200.nip.io/ | head -1
# Expected: HTTP/1.1 200 OK

# 2. Harbor `library` project exists and we can push to it
curl -s --cacert ~/minicloud-ca.crt -u "admin:$(cat ~/.harbor-admin)" \
  https://harbor.10.0.0.200.nip.io/api/v2.0/projects/library | jq -r .name
# Expected: library

# 3. Node.js + Yarn available on the build machine (Mac)
node --version    # need >= 20.x
yarn --version    # need >= 1.22 (Classic) or modern Berry
crane version     # for pushing the built image

# 4. The current Backstage catalog API is working (sanity check)
bs_catalog | head -3
# Expected: 3 Components listed
```

All four must be green before starting.

---

## Stage 1 — Scaffold the custom app (~30 min)

On the **Mac** (the build machine — the controller doesn't have Node.js per CLAUDE.md):

```bash
mkdir -p ~/code
cd ~/code
npx @backstage/create-app@latest minicloud-backstage
# Prompts:
#   - Database: PostgreSQL (matches our deployed Postgres)
cd minicloud-backstage
git init && git add -A && git commit -m "initial scaffold from @backstage/create-app"
gh repo create andrelair-platform/minicloud-backstage --private --source=. --remote=origin
git push -u origin main
```

You now own the source. Every subsequent change is `git commit + push + build`.

### Stage 1 acceptance

```bash
yarn install
yarn dev   # local dev server at http://localhost:3000
# Browse to localhost:3000 → see the default Backstage app
# Verify: catalog loads with the demo components (we'll replace these)
```

---

## Stage 2 — Fix `apis.ts` and remove the notifications bug (~15 min)

Edit `packages/app/src/apis.ts`. Find the section that imports `@backstage/plugin-notifications` (added by recent scaffold versions). Two options:

**Option A — Remove it entirely** (cleanest if you don't want notifications):

```typescript
// DELETE these imports:
// import { notificationsApiRef } from '@backstage/plugin-notifications-react';
// DELETE the corresponding createApiFactory({...}) entry
```

Also delete the notifications-related entry in `packages/app/src/App.tsx` (the `<NotificationsPage>` route mount and the `<NotificationsSidebarItem>` in the Sidebar).

**Option B — No-op fallback** (cleaner if you might want notifications later):

```typescript
import { createApiFactory } from '@backstage/core-plugin-api';
import { notificationsApiRef } from '@backstage/plugin-notifications-react';

createApiFactory({
  api: notificationsApiRef,
  deps: {},
  factory: () => ({
    getNotifications: async () => [],
    getStatus: async () => ({ unread: 0, total: 0 }),
    updateStatus: async () => {},
    updateNotifications: async () => {},
  }),
}),
```

This wires a stub implementation: bell icon renders but always shows "0 notifications", no errors thrown.

### Stage 2 acceptance

```bash
yarn dev
# Browse to localhost:3000
# NO MORE NotImplementedError overlay on page load
# Catalog renders fully
```

---

## Stage 3 — Add Kubernetes plugin (~45 min)

Adds live pod/Service state to each Component's "Kubernetes" tab.

```bash
yarn --cwd packages/app add @backstage/plugin-kubernetes
yarn --cwd packages/backend add @backstage/plugin-kubernetes-backend
```

### 3.1 — Backend wiring

`packages/backend/src/index.ts`:

```typescript
backend.add(import('@backstage/plugin-kubernetes-backend'));
```

### 3.2 — Frontend wiring

`packages/app/src/App.tsx` — add the `<EntityKubernetesContent>` to the Component catalog page:

```typescript
import { EntityKubernetesContent } from '@backstage/plugin-kubernetes';

// Inside <EntityLayout> for kind:component
<EntityLayout.Route path="/kubernetes" title="Kubernetes">
  <EntityKubernetesContent refreshIntervalMs={30000} />
</EntityLayout.Route>
```

### 3.3 — Cluster locator config in `app-config.yaml`

```yaml
kubernetes:
  serviceLocatorMethod:
    type: 'multiTenant'
  clusterLocatorMethods:
    - type: 'config'
      clusters:
        - name: minicloud
          url: https://10.0.0.2:6443
          authProvider: 'serviceAccount'
          serviceAccountToken: ${K8S_SA_TOKEN}
          caData: ${K8S_CA_DATA}   # base64 of /etc/rancher/k3s/k3s.yaml's CA
          skipTLSVerify: false
          skipMetricsLookup: false
```

### 3.4 — Cluster-side ServiceAccount

In the cluster (apply via gitops or `kubectl apply -f`):

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backstage-k8s-viewer
  namespace: backstage
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: backstage-k8s-viewer
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: view   # read-only across all namespaces
subjects:
  - kind: ServiceAccount
    name: backstage-k8s-viewer
    namespace: backstage
---
apiVersion: v1
kind: Secret
metadata:
  name: backstage-k8s-viewer-token
  namespace: backstage
  annotations:
    kubernetes.io/service-account.name: backstage-k8s-viewer
type: kubernetes.io/service-account-token
```

```bash
# Extract token + CA into Backstage's Secret
K8S_SA_TOKEN=$(kubectl get secret backstage-k8s-viewer-token -n backstage -o jsonpath='{.data.token}' | base64 -d)
K8S_CA_DATA=$(kubectl get secret backstage-k8s-viewer-token -n backstage -o jsonpath='{.data.ca\.crt}')
```

Inject both into `backstage-values.yaml` via `extraEnvVars` (matches the existing Postgres pattern).

### 3.5 — Per-Component annotations

In each repo's `catalog-info.yaml`, add the annotation that tells the plugin which k8s resources belong to which Component:

```yaml
metadata:
  annotations:
    'backstage.io/kubernetes-id': platform-demo   # matches the label on Deployment/Service
```

And label the k8s resources accordingly:

```bash
kubectl label deploy platform-demo -n gitops-demo backstage.io/kubernetes-id=platform-demo --overwrite
```

### Stage 3 acceptance

```text
✔ Browse to Component page for platform-demo
✔ "Kubernetes" tab appears
✔ Shows current Deployment, ReplicaSet, Pod, Service, Ingress for platform-demo
✔ Live state (status, restarts, events) refreshes every 30s
```

---

## Stage 4 — Add ArgoCD plugin (~30 min)

Adds the "ArgoCD" tab to each Component, showing live sync/health status.

We'll use [`roadiehq/backstage-plugin-argo-cd`](https://github.com/RoadieHQ/backstage-plugin-argo-cd) — the community plugin (the official `@backstage/plugin-argo-cd` was deprecated in 2024).

```bash
yarn --cwd packages/app add @roadiehq/backstage-plugin-argo-cd
yarn --cwd packages/backend add @roadiehq/backstage-plugin-argo-cd-backend
```

### 4.1 — `app-config.yaml`

```yaml
argocd:
  username: ${ARGOCD_USERNAME}
  password: ${ARGOCD_PASSWORD}
  appLocatorMethods:
    - type: 'config'
      instances:
        - name: minicloud
          url: https://argocd.10.0.0.200.nip.io
```

### 4.2 — Per-Component annotations

```yaml
metadata:
  annotations:
    'argocd/app-name': platform-demo   # matches the ArgoCD Application name
```

### Stage 4 acceptance

```text
✔ Component page → "ArgoCD" tab → live sync/health status visible
✔ Click through to https://argocd.10.0.0.200.nip.io/applications/platform-demo
```

---

## Stage 5 — Add Grafana plugin (~30 min)

Adds embedded dashboard cards on each Component page.

```bash
yarn --cwd packages/app add @k-phoen/backstage-plugin-grafana
yarn --cwd packages/backend add @k-phoen/backstage-plugin-grafana-backend
```

### 5.1 — `app-config.yaml`

```yaml
grafana:
  domain: https://grafana.10.0.0.200.nip.io
  unifiedAlerting: true
```

### 5.2 — Per-Component annotations

```yaml
metadata:
  annotations:
    'grafana/dashboard-selector': "tags @> '\"platform-demo\"'"
```

### Stage 5 acceptance

```text
✔ Component page → "Grafana" overview shows linked dashboards
✔ Click-through to Grafana works (already shares Authentik SSO from Phase 23)
```

---

## Stage 6 — Add TechDocs (~45 min)

Renders Markdown from each repo's `docs/` folder inside Backstage.

```bash
yarn --cwd packages/app add @backstage/plugin-techdocs
yarn --cwd packages/backend add @backstage/plugin-techdocs-backend
```

### 6.1 — `app-config.yaml`

```yaml
techdocs:
  builder: 'local'   # build on Backstage backend; production would use s3/cache
  generator:
    runIn: 'docker'  # mkdocs in a sidecar
  publisher:
    type: 'local'    # or 'awsS3' / similar
```

### 6.2 — Per-repo `mkdocs.yml`

In each repo that has docs (start with `minicloud-platform-docs` — but it's Docusaurus, not MkDocs; either convert OR use `'minicloud-ansible'` as the first TechDocs example since it has README + module docs):

```yaml
site_name: minicloud-ansible
nav:
  - Home: index.md
  - Roles:
      - common: roles/common.md
      - longhorn-prereq: roles/longhorn-prereq.md
      # ...
```

### Stage 6 acceptance

```text
✔ Component page → "TechDocs" tab → renders Markdown
✔ Sidebar navigation works
✔ Mermaid diagrams render
```

---

## Stage 7 — Wire Authentik OIDC (~30 min, assumes Phase 23 shipped)

Replace guest auth with the same Authentik SSO every other app uses.

### 7.1 — In Authentik

Create a new OAuth2/OpenID Provider + Application named `backstage`. Redirect URI: `https://backstage.10.0.0.200.nip.io/api/auth/authentik/handler/frame`.

### 7.2 — Backstage `app-config.yaml`

```yaml
auth:
  environment: production
  providers:
    authentik:
      production:
        metadataUrl: https://auth.10.0.0.200.nip.io/application/o/backstage/.well-known/openid-configuration
        clientId: backstage
        clientSecret: ${AUTH_AUTHENTIK_CLIENT_SECRET}
        callbackUrl: https://backstage.10.0.0.200.nip.io/api/auth/authentik/handler/frame
        signIn:
          resolvers:
            - resolver: emailMatchingUserEntityProfileEmail
```

### 7.3 — Sign-in page

`packages/app/src/App.tsx`:

```typescript
import { authentikAuthApiRef } from '@backstage/plugin-auth-backend-module-authentik-provider';

const app = createApp({
  components: {
    SignInPage: props => (
      <SignInPage
        {...props}
        auto
        provider={{
          id: 'authentik',
          title: 'Authentik',
          message: 'Sign in with the Authentik SSO',
          apiRef: authentikAuthApiRef,
        }}
      />
    ),
  },
});
```

### 7.4 — Delete the guest provider

Remove `providers.guest` from `app-config.yaml`. Bookmark the emergency-fallback recovery path (Authentik admin → user impersonation) in CLAUDE.md.

### Stage 7 acceptance

```text
✔ Visiting backstage.10.0.0.200.nip.io 302s to auth.10.0.0.200.nip.io
✔ After Authentik login, lands in Backstage as authenticated user
✔ Component pages show user identity in header
```

---

## Stage 8 — Build, push to Harbor, ship (~20 min)

Locally on Mac:

```bash
cd ~/code/minicloud-backstage
yarn install
yarn tsc
yarn build:backend
yarn build-image --tag harbor.10.0.0.200.nip.io/library/backstage:$(git rev-parse --short HEAD)
```

This produces an image tagged with the current git SHA. Push to Harbor:

```bash
SHA=$(git rev-parse --short HEAD)
crane copy --insecure \
  ghcr.io/your-local-cache/backstage:${SHA} \
  harbor.10.0.0.200.nip.io/library/backstage:${SHA}
```

### 8.1 — Update `backstage-values.yaml` on the controller

```diff
   image:
     registry: harbor.10.0.0.200.nip.io
     repository: library/backstage
-    tag: "1.51.2"
+    tag: "<short-git-sha>"
```

```bash
helm upgrade backstage backstage/backstage -n backstage -f backstage-values.yaml
kubectl rollout status deploy/backstage -n backstage --timeout=180s
```

### 8.2 — Mirror to ansible repo

Same pattern as Phase 18:

```bash
cp backstage-values.yaml ansible/helm-values/backstage-values.yaml
cd ansible && git add helm-values/backstage-values.yaml && \
  git commit -m "chore(helm-values): bump backstage to custom image <sha>" && \
  git push origin main
```

### Stage 8 acceptance

```text
✔ kubectl get pods -n backstage shows new pod Running
✔ kubectl get pod -n backstage -o jsonpath='{.items[0].spec.containers[0].image}'
  shows harbor.10.0.0.200.nip.io/library/backstage:<sha> (NOT ghcr.io)
✔ Browse https://backstage.10.0.0.200.nip.io — no error overlay
✔ pin_audit still returns empty (no :latest regression)
✔ All 7 prior stages' acceptance criteria still hold
```

---

## Two predicted install gotchas

### Gotcha 1: `yarn build-image` needs a local Docker daemon

Backstage's `yarn build-image` shells out to `docker build`. If Docker Desktop isn't running on the Mac, the build fails with a cryptic socket error. Make sure Docker Desktop is running before Stage 8.

### Gotcha 2: TechDocs `runIn: 'docker'` inside the cluster needs DinD or a sidecar build container

The TechDocs generator spawns an MkDocs Docker container to build each repo's docs. Inside a Kubernetes pod, you don't have a Docker daemon. Options:
- `runIn: 'local'` and rely on the Backstage container having MkDocs pre-installed (requires custom Dockerfile)
- Use a separate `techdocs-builder` workflow that pre-builds docs and pushes to S3/MinIO, then Backstage just serves them

The simplest path for Phase 24 Day 1: skip the in-cluster build (Stage 6 deferred) and add it as Day 2 work once the foundation is solid.

---

## Done When

```text
Stage 1 ✔ Custom Backstage repo scaffolded, pushed to andrelair-platform/minicloud-backstage
Stage 2 ✔ apis.ts fixed; yarn dev shows NO NotImplementedError
Stage 3 ✔ Kubernetes plugin live on Component pages
Stage 4 ✔ ArgoCD plugin shows sync/health
Stage 5 ✔ Grafana plugin shows embedded dashboards
Stage 6 ✔ TechDocs renders Markdown (or deferred to Day 2 — documented)
Stage 7 ✔ Authentik OIDC working; guest auth removed
Stage 8 ✔ Custom image in Harbor; cluster running it; values mirrored to ansible
        ✔ pin_audit returns empty
        ✔ bs_catalog still works (Backstage API unchanged)
        ✔ Phase 24 marked Done in CLAUDE.md + intro.md
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Building a Backstage custom image from create-app** | The canonical path — Spotify's official guidance. Every shop running Backstage at scale does this. |
| **Fixing an upstream apiRef registration gap** | Real platform-engineering work — understanding the plugin lifecycle, the `createApiFactory` pattern, what registration means. The kind of thing interviewers love. |
| **Wiring k8s ServiceAccount + ClusterRoleBinding for read-only catalog observation** | Same pattern every monitoring/observability tool needs — Backstage just happens to be the consumer. |
| **OIDC integration with redirect URI + signin resolver design** | RBAC-derived identity flow that distinguishes "user authenticated" from "user authorized for this Component". |
| **Per-Component annotation strategy** | The Backstage opinion: catalog-info.yaml IS the source-of-truth, every integration reads from it. Generalizes to GitHub Actions discovery, CI/CD attestations, SLO definitions. |
| **Image immutability via git SHA tags** | Same discipline as Phase 13's platform-demo: every build produces an immutable, traceable artifact. |
| **Honest deferrals** (Software Templates, GitHub Actions plugin, TechDocs in-cluster build) | Same pattern as Phase 11 (Crossplane), Phase 13 (GitLab), Phase 15 (Vault), Phase 16 (n8n), Phase 18 (plugins — exactly this phase's predecessor), Phase 19 (MLflow/Kubeflow), Phase 23 (LDAP/SCIM/PAM). Senior engineers ship the foundation first. |


---

## Execution gotchas (real, hit during Phase 24)

### Gotcha 3: `yarn build-image` produces an ARM64 image on Apple Silicon

`yarn build-image` calls `docker build` without a `--platform` flag. On a Mac (ARM64), the resulting image is `linux/arm64`. The k3s ThinkPads are `x86_64`. Deploying the ARM64 image causes an `exec format error` (exit code 255) in CrashLoopBackOff.

**Fix:** set `DOCKER_DEFAULT_PLATFORM` before the build:
```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 yarn build-image --tag "backstage:<sha>-amd64"
```

Tag the image with `-amd64` suffix so it is distinguishable from any ARM64 artifact under the same SHA. Use a new tag (not overwrite the old one) to bypass kubelet `IfNotPresent` cache — if the same tag exists on the node, kubelet will not re-pull even if Harbor has new content.

### Gotcha 4: `crane push` for Harbor, not `docker push`

Docker Desktop on macOS uses a Linux VM that does not trust macOS System Keychain, so `docker push` to Harbor fails with `certificate signed by unknown authority` even after adding the minicloud CA via `~/.docker/certs.d/`.

**Fix:** Use `crane` (Google container tool), which uses Go native TLS and respects the macOS System Keychain where the minicloud CA was already trusted:
```bash
docker save "backstage:<sha>-amd64" -o /tmp/backstage-amd64.tar
crane push /tmp/backstage-amd64.tar "harbor.10.0.0.200.nip.io/library/backstage:<sha>-amd64"
rm /tmp/backstage-amd64.tar
```

### Gotcha 5: `@k-phoen/backstage-plugin-grafana` requires `grafana.domain` in config schema

The Grafana community plugin ships a config schema that marks `grafana.domain` as **required**. Even if the plugin is not actively registered in `App.tsx`, its JSON schema is compiled into the app bundle during `yarn build`. The `plugin-app-backend` validates the full schema at startup, causing this fatal error:

```
Config validation failed, Config must have required property 'grafana'
```

**Fix:** Add to `appConfig` in `backstage-values.yaml` (no rebuild needed — this is runtime config):
```yaml
grafana:
  domain: https://grafana.10.0.0.200.nip.io
```

### Gotcha 6: `scope` option removed from OIDC provider in Backstage 1.52+

The `@backstage/plugin-auth-backend-module-oidc-provider` in Backstage 1.52 removed the `scope` config key. Using it causes:

```
Failed to initialize oidc auth provider, The oidc provider no longer supports the "scope" configuration option. Please use the "additionalScopes" option instead.
```

**Fix:** Replace in `appConfig.auth.providers.oidc.production`:
```yaml
# Old (broken):
scope: 'openid profile email'

# New:
additionalScopes: []  # openid, profile, email are included by default
```

---

## Phase complete

- **Image:** `harbor.10.0.0.200.nip.io/library/backstage:bcec03f-amd64`
- **Built:** 2026-06-20 (linux/amd64 on Apple Silicon Mac with DOCKER_DEFAULT_PLATFORM override)
- **Helm revision:** 11
- **Health:** `readiness 200 OK`, `liveness 200 OK`
- **Auth:** Authentik OIDC (guest mode removed)
- **Plugins live:** Kubernetes, ArgoCD, TechDocs (local), Grafana
- **Deferred:** TechDocs in-cluster builder (DinD), Software Templates
