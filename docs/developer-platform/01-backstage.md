---
id: backstage
title: Phase 18 — Backstage (minimal IDP)
sidebar_position: 1
---

# Phase 18 — Backstage (Internal Developer Portal)

Backstage is Spotify's open-source developer-portal framework. Its core
value is the **Software Catalog** — a unified registry of services, APIs,
docs, and ownership metadata — plus a plugin system for embedding
Kubernetes/ArgoCD/Grafana/etc. dashboards per service.

For a single-operator homelab like this one, Backstage is **honestly
portfolio-only — not operationally needed**. Homer + the live docs site
already do 90% of what a developer portal would. Same architectural
question we asked at every "do we need this?" decision: GitLab in Phase
13, Crossplane in Phase 11, Vault in Phase 15, Backstage here.

The skill of installing, configuring, and reasoning about an IDP is real
and recruiter-recognizable. So Phase 18 ships **a focused minimal
Backstage** — catalog-only, no plugins, no SSO — that demonstrates the
architecture without burning a weekend on plugins nobody will use.

---

## Architecture

```text
                          ┌───────────────────────────────────────────┐
   Browser                │  backstage namespace                       │
       │ HTTPS            │                                            │
       │ + guest auth     │  ┌──────────────────────────┐              │
       ▼                  │  │ Backstage Pod (1 replica)│              │
  cert-manager TLS        │  │  off-the-shelf image:    │              │
  + NGINX Ingress  ──────▶│  │  ghcr.io/backstage/      │              │
                          │  │    backstage:1.51.2       │              │
                          │  │  pulled through Harbor's  │              │
                          │  │   ghcr proxy (Phase 16)   │              │
                          │  └─────────┬────────────────┘              │
                          │            │                                │
                          │            ▼                                │
                          │  ┌──────────────────────────┐               │
                          │  │ PostgreSQL (StatefulSet) │               │
                          │  │ bitnami/postgresql 18.x  │               │
                          │  │ standalone, Longhorn 1Gi │               │
                          │  └──────────────────────────┘               │
                          │                                             │
                          │  Catalog refresh every 100s:                │
                          │   pulls 5 catalog-info.yaml from            │
                          │   raw.githubusercontent.com/...             │
                          └─────────────────────────────────────────────┘
```

After this phase: `https://backstage.10.0.0.200.nip.io` shows a
**Software Catalog** with 1 System (`minicloud-platform`) and 5
Components (one per repo in `andrelair-platform`).

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Install method | Helm chart `backstage/backstage` v2.7.0 | Standard install path; bundles Postgres subchart |
| Image | **Off-the-shelf `ghcr.io/backstage/backstage:1.51.2`** (pulled through Harbor `ghcr` proxy cache, **pinned 2026-06-15** — see "Image tag pinning" section) | Avoids 3+ hours of Node.js scaffold + Docker build for marginal portfolio gain. Custom build deferred. |
| Database | **PostgreSQL** (bitnami subchart, standalone), 1 GiB on Longhorn | SQLite is documented as "for development only"; Postgres is the right shape for portfolio even at this scale |
| Authentication | **Guest auth** (no SSO) with `dangerouslyAllowOutsideDevelopment: true` | GitHub OAuth requires GitHub App + browser setup; SSO requires Keycloak (future phase). Guest gets us to "logged in" instantly. |
| Plugins | **Catalog-only** (chart's default — no Kubernetes/ArgoCD/Grafana plugins) | Each plugin requires custom-build with its node module. Deferred. |
| Catalog source | **5 `catalog-info.yaml` files**, one per repo, fetched via `raw.githubusercontent.com` URLs | Avoids needing a GitHub integration token (anonymous reads of public raw URLs work) |
| Hostname | `backstage.10.0.0.200.nip.io` via NGINX Ingress + cert-manager TLS | Same single-IP host-routing pattern |
| Resource budget | Backstage 384Mi req / 1 GiB limit; Postgres 128Mi / 512 MiB | Conservative; cluster has ~30 GiB headroom |

---

## What's deferred (with future homes)

Same scope-reduction pattern as Phase 11 (Crossplane), Phase 13
(GitLab), Phase 15 (Vault), Phase 16 (n8n/Temporal/Airflow).

| Component | Reason | Future home |
|---|---|---|
| **Custom Backstage image build** | 3+ hours of Node.js scaffold + Docker build for marginal gain over off-the-shelf | Future "Backstage Plugins" phase, when we wire Kubernetes/ArgoCD/Grafana plugins |
| **GitHub OAuth / SSO** | Requires GitHub App + Keycloak as backbone | Future phase pairing with Keycloak |
| **Kubernetes / ArgoCD / Grafana plugins** | Each requires the custom-build pipeline; the off-the-shelf image doesn't include them | Future "Backstage Plugins" phase |
| **Software Templates ("Golden Paths")** | Most valuable feature, needs scaffolder backend + template repos. ~6 hours focused work. | Dedicated future phase, after SSO |
| **Vault** | Same reasons as Phase 15 — single-control-plane SPOF, no current workload needs dynamic creds | Future phase pairing with external-DB-credentials need |
| **Crossplane** | Promised "alongside Phase 18" in Phase 11's deferral; still no compelling external-infra use case | Future phase when there's a real cloud account or self-service template need |

This means Phase 18 ships ~30% of "real Backstage" — the catalog. Honest
about what's missing and why.

---

## Image tag pinning (2026-06-15)

### The incident

Six weeks after install, opening Backstage from a browser surfaced this React error overlay:

```text
NotImplementedError
Message: No implementation available for apiRef{plugin.notifications.service}
```

The catalog still worked — dismissing the overlay or hard-refreshing the page got past it — but the error reappeared on every fresh load. Root cause: the `:latest` tag is a rolling reference that points at whatever the Backstage team most recently published from the off-the-shelf example app, and over those six weeks the frontend bundle started including a Notifications-plugin UI component that calls a backend API client that the example app's backend doesn't actually wire up. Spotify's own off-the-shelf image is a *demonstration of plugin capability*, not a production deployment — the frontend/backend can drift out of sync on any new build.

### What pinning did and didn't fix

Edited `backstage-values.yaml`:

```diff
   image:
     registry: ghcr.io
     repository: backstage/backstage
-    tag: latest
+    tag: "1.51.2"
```

Applied with `helm upgrade backstage backstage/backstage -n backstage -f backstage-values.yaml`. Rollout took ~24 s (336 MB image, pulled through Harbor's `ghcr` proxy cache).

**What the pin DID fix:** silent drift on every pod restart. Previously, any random pod reschedule could land on a new `:latest` image with subtly different behavior. Now the image identity is frozen — pod restarts, node reboots, full cluster wipes all converge on the exact same byte-for-byte image.

**What the pin DID NOT fix:** the `NotImplementedError` overlay itself. Verification after the pin took effect:

```bash
# pod confirmed at 1.51.2:
kubectl get pod -n backstage -o jsonpath='{.items[0].spec.containers[0].image}'
# → ghcr.io/backstage/backstage:1.51.2

# bundle hash served by 1.51.2:
curl -s https://backstage.10.0.0.200.nip.io/ | grep -oE 'module-backstage\.[a-f0-9]+\.js'
# → module-backstage.5c25c313.js

# This is the SAME hash as the original error stack trace, meaning :latest
# at audit time was already 1.51.2 — the pin was a no-op in functional terms.
```

The off-the-shelf image at 1.51.2 still ships the same `apiRef{plugin.notifications.service}` registration gap. An early version of this section claimed "1.49.0 shipped a no-op fallback" — that was wishful inference, not verified upstream behavior. Corrected here for honesty.

### Why the off-the-shelf image carries this bug at every version (so far)

The image is built from `packages/app` and `packages/backend` in the Backstage repo — the example app the maintainers ship to *demonstrate* what's possible, not a turnkey production deployment. Over the past ~18 months they added the notifications plugin's UI components to `packages/app/src/App.tsx` (the bell icon in the header) without registering the matching `notificationsApiRef` factory in `packages/app/src/apis.ts`. Frontend imports the plugin → plugin code runs on every page load → tries to resolve its API client → no implementation registered → `NotImplementedError` overlay.

This is a structural issue with running the upstream example app, not a per-version bug that can be pinned around. Every tag from when the notifications UI was added until someone wires the API factory in `packages/app/src/apis.ts` exhibits this.

### Working with the bug today — what actually works

**What does NOT work** (and the doc said it would — corrected here):

- "Dismiss the error overlay" — the overlay rendering is React's `ErrorBoundary` catching the failed apiRef lookup, but the lookup re-fires on every route render because the notifications plugin is registered globally in the Header component. There's no dismissable state; the overlay re-appears immediately on any navigation.
- Hard-refresh, incognito mode, different browsers, direct URL navigation to `/catalog` — none of these bypass the error, because the failing component is in the always-rendered Header tree.

**Also tried (2026-06-15) — downgrade to `1.25.0`** (a tag that likely predates the notifications-plugin-in-frontend era):

```bash
sed -i 's|tag: "1.51.2"|tag: "1.25.0"|' backstage-values.yaml
helm upgrade backstage backstage/backstage -n backstage -f backstage-values.yaml
# Result: CrashLoopBackOff on backstage-77745c54d-5przd
# Logs: error in BackendInitializer.start at backend-app-api/dist/index.cjs.js:1486
```

The backend config schema between 1.25.0 and the chart `backstage-2.7.0` is incompatible. The pod can't even reach the point where the frontend would be served. Reverted to `1.51.2` via `helm upgrade`; old pod kept running throughout (rolling deploy preserved availability). Net result: pinning experiments are exhausted in both directions — neither newer nor older off-the-shelf tags resolve the UI issue.

**What actually works — use the catalog via API, not the UI.**

At Phase 18's scope, Backstage is a read-only catalog. The catalog data is served cleanly by the API regardless of UI state. A shell function gives equivalent functionality without the broken UI:

```bash
bs_catalog() {
  local CA="${BS_CA:-$HOME/minicloud-ca.crt}"
  local TOKEN
  TOKEN=$(curl -sf --cacert "$CA" -X POST https://backstage.10.0.0.200.nip.io/api/auth/guest/refresh | jq -r '.backstageIdentity.token')
  curl -sf --cacert "$CA" -H "Authorization: Bearer $TOKEN" \
    "https://backstage.10.0.0.200.nip.io/api/catalog/entities?filter=kind=${1:-component}" \
  | jq -r '.[] | "\(.metadata.name) [\(.kind)] (\(.spec.type // "n/a")) — owner: \(.spec.owner // "n/a") — \(.metadata.description // "no description")"'
}
```

Usage:

```bash
bs_catalog              # all Components
bs_catalog system       # all Systems
bs_catalog api          # all APIs
bs_catalog location     # all catalog Locations
```

The function is stashed durably in [`minicloud-ansible/scripts/bs-catalog.sh`](https://github.com/andrelair-platform/minicloud-ansible/blob/main/scripts/bs-catalog.sh) so it survives a controller wipe and is usable from any machine with the CA cert.

**The pin to `1.51.2` is kept** because the drift-control value is real and orthogonal to the visible UI error. The pinning lesson generalizes (and uncovered 2 more `:latest` references in Phase 3 + Phase 19). What was wrong was the specific claim that a tag-level fix exists for this bug.

### Real fix (Option 3 — deferred to a future "Backstage Plugins" phase)

The proper resolution is to stop running the off-the-shelf example app and ship a custom image:

1. `npx @backstage/create-app minicloud-backstage` — scaffolds the TypeScript monorepo locally
2. Edit `packages/app/src/apis.ts` — either remove the notifications-plugin import OR register a no-op `notificationsApiRef` factory
3. Add the plugins we actually want (`@backstage/plugin-kubernetes`, `@backstage/plugin-argocd`, `@backstage/plugin-grafana`, `@backstage/plugin-techdocs`)
4. `yarn build-image` → custom Docker image
5. `crane copy` to `harbor.10.0.0.200.nip.io/library/backstage:<sha>`
6. Point `backstage-values.yaml` at the custom image, ship via Helm upgrade

Realistic effort: one focused 3-4 hour session. The notifications mismatch gets fixed for free because you control `apis.ts`. Same session unlocks Kubernetes/ArgoCD/Grafana plugins — converting Backstage from a read-only catalog into a true Internal Developer Portal.

### Why the pinning section still belongs in this doc

The visible bug is the trigger that uncovered a broader anti-pattern: `:latest` on a long-running cluster is a time bomb regardless of whether a specific symptom is visible. The cluster-wide audit one-liner that came out of this work found 2 more `:latest` references (Phase 3 Homer, Phase 19 Ollama), both of which were pinned the same day for the same drift-control reason. **The lesson holds even though the specific Backstage symptom didn't go away.**

### Lessons for future workloads

This is a generic anti-pattern, not Backstage-specific. **Any off-the-shelf image pulled with `:latest` is a time bomb on a long-running cluster** — silently drifts on every pod restart, until it suddenly doesn't work. Audit other workloads for `:latest` references:

```bash
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: {range .spec.containers[*]}{.image}{"\n"}{end}{end}' | grep ':latest$'
```

Pin every result to a specific version. Use a renovate-bot or Dependabot equivalent to surface upgrade PRs rather than hoping `:latest` does the right thing.

### Where the pinned values file lives

The `backstage-values.yaml` is **not** in `minicloud-gitops` (Backstage is Helm-installed, not yet ArgoCD-managed). To survive a controller wipe, the file is mirrored into the [`minicloud-ansible` repo](https://github.com/andrelair-platform/minicloud-ansible) under `helm-values/backstage-values.yaml`. Migration to ArgoCD-managed Helm is a future phase — it requires preserving the live Postgres StatefulSet + 1 GiB PVC through the cut-over, which is non-trivial and deserves its own focused work block.

---

## Pre-flight

```bash
helm repo add backstage https://backstage.github.io/charts
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Generate Postgres password (mode 600, never committed)
openssl rand -base64 24 > ~/.backstage-postgres
chmod 600 ~/.backstage-postgres
```

---

## Out-of-band Postgres Secret

The bitnami chart's `existingSecret` mechanism expects a Secret with
specific keys. We pre-create it in the chart's expected format:

```bash
kubectl create namespace backstage

PG_PW=$(cat ~/.backstage-postgres)
kubectl create secret generic backstage-postgres-secret \
  -n backstage \
  --from-literal=postgres-password="$PG_PW" \
  --from-literal=password="$PG_PW"
```

---

## `backstage-values.yaml`

```yaml
backstage:
  replicas: 1
  image:
    registry: ghcr.io
    repository: backstage/backstage
    # Pinned 2026-06-15 (see "Image tag pinning" section below)
    tag: "1.51.2"
    # ghcr.io is routed through Harbor's ghcr proxy via the Phase 16
    # mirror config in /etc/rancher/k3s/registries.yaml — no override needed

  resources:
    requests: { cpu: 100m, memory: 384Mi }
    limits:   { cpu: 1000m, memory: 1Gi }

  containerPorts:
    backend: 7007

  appConfig:
    app:
      title: minicloud platform
      baseUrl: https://backstage.10.0.0.200.nip.io
    organization:
      name: andrelair-platform
    backend:
      baseUrl: https://backstage.10.0.0.200.nip.io
      listen: { port: 7007 }
      cors:
        origin: https://backstage.10.0.0.200.nip.io
        methods: [GET, POST, PUT, DELETE]
        credentials: true
      # URL whitelist — without this, raw.githubusercontent.com reads
      # are blocked by Backstage's default policy.
      reading:
        allow:
          - host: raw.githubusercontent.com
          - host: github.com
      database:
        client: pg
        connection:
          host: ${POSTGRES_HOST}
          port: ${POSTGRES_PORT}
          user: ${POSTGRES_USER}
          password: ${POSTGRES_PASSWORD}
    auth:
      providers:
        guest:
          # Required when NODE_ENV=production (off-the-shelf image runs
          # in production mode); without this, /api/auth/guest/refresh
          # returns 403 NotAllowedError. Acceptable here: internal-only
          # via Tailscale + cluster network, no sensitive catalog data.
          dangerouslyAllowOutsideDevelopment: true
    catalog:
      rules:
        - allow: [Component, System, API, Resource, Location]
      locations:
        - type: url
          target: https://raw.githubusercontent.com/andrelair-platform/minicloud-platform-docs/main/catalog-info.yaml
        - type: url
          target: https://raw.githubusercontent.com/andrelair-platform/minicloud-ansible/main/catalog-info.yaml
        - type: url
          target: https://raw.githubusercontent.com/andrelair-platform/minicloud-opentofu/main/catalog-info.yaml
        - type: url
          target: https://raw.githubusercontent.com/andrelair-platform/minicloud-gitops/main/catalog-info.yaml
        - type: url
          target: https://raw.githubusercontent.com/andrelair-platform/platform-demo/main/catalog-info.yaml

  extraEnvVars:
    - name: POSTGRES_HOST
      value: backstage-postgresql
    - name: POSTGRES_PORT
      value: "5432"
    - name: POSTGRES_USER
      value: bn_backstage
    - name: POSTGRES_PASSWORD
      valueFrom:
        secretKeyRef:
          name: backstage-postgres-secret
          key: password

ingress:
  enabled: false   # we add our own with cert-manager TLS

postgresql:
  enabled: true
  image:
    registry: docker.io
    repository: bitnamilegacy/postgresql
  architecture: standalone
  auth:
    username: bn_backstage
    database: backstage_plugin_catalog
    existingSecret: backstage-postgres-secret
    secretKeys:
      adminPasswordKey: postgres-password
      userPasswordKey: password
  primary:
    persistence:
      enabled: true
      storageClass: longhorn
      size: 1Gi
    resources:
      requests: { cpu: 50m, memory: 128Mi }
      limits:   { cpu: 500m, memory: 512Mi }
```

---

## Install + bootstrap order trap

```bash
helm install backstage backstage/backstage -n backstage \
  -f backstage-values.yaml \
  --wait --timeout 10m
```

**Likely first failure:** `Backend startup failed... ECONNREFUSED 5432`.

Postgres needs ~5 min to first-boot (init scripts, schema setup,
checkpoint). Backstage's startup happens in parallel and tries to
connect immediately. **Backstage 1.x doesn't retry on startup-time DB
connection failures** — it logs `BackendStartupError` and stays broken.

Fix: restart the Backstage pod once Postgres is fully Ready.

```bash
kubectl rollout restart deployment/backstage -n backstage
kubectl rollout status deployment/backstage -n backstage --timeout=120s
```

This is a real production gotcha — even with `helm install --wait`, the
chart's readiness probes wait for Backstage's HTTP server to be alive,
which can succeed before Backstage's database connection is. The
`--wait` then times out at 10min on the readiness probe, but the helm
install itself reports `STATUS: deployed`. Restart the pod and you're
fine.

---

## TLS Ingress

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: backstage-tls
  namespace: backstage
spec:
  secretName: backstage-tls
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
  dnsNames: [backstage.10.0.0.200.nip.io]
  duration: 2160h
  renewBefore: 720h
  privateKey: { algorithm: ECDSA, size: 256 }
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: backstage
  namespace: backstage
  annotations:
    nginx.org/redirect-to-https: "true"
spec:
  ingressClassName: nginx
  tls:
    - hosts: [backstage.10.0.0.200.nip.io]
      secretName: backstage-tls
  rules:
    - host: backstage.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: backstage
                port: { number: 7007 }
```

---

## The 5 `catalog-info.yaml` files

One per repo, at the repo's root. Components reference the umbrella
System (`spec.system: minicloud-platform`) for tree-view navigation.

### `minicloud-platform-docs/catalog-info.yaml` — System + Component

```yaml
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: minicloud-platform
  description: 3-node bare-metal Kubernetes platform on ThinkPads
  tags: [homelab, bare-metal, portfolio]
spec:
  owner: andrelair-platform
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: minicloud-platform-docs
  description: Docusaurus 3 documentation site
  annotations:
    backstage.io/source-location: url:https://github.com/andrelair-platform/minicloud-platform-docs
    github.com/project-slug: andrelair-platform/minicloud-platform-docs
  tags: [documentation, docusaurus]
  links:
    - { url: https://andrelair-platform.github.io/minicloud-platform-docs/, title: Live docs site }
spec:
  type: documentation
  lifecycle: production
  owner: andrelair-platform
  system: minicloud-platform
```

### `platform-demo/catalog-info.yaml` (most-decorated example)

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: platform-demo
  description: Phase 13 — tiny Go HTTP service end-to-end CI/CD demo
  annotations:
    backstage.io/source-location: url:https://github.com/andrelair-platform/platform-demo
    github.com/project-slug: andrelair-platform/platform-demo
    argocd/app-name: platform-demo
    prometheus.io/rule: http_request_duration_seconds_count{namespace="gitops-demo"}
    grafana/dashboard-selector: namespace=gitops-demo
  tags: [go, service, demo, phase-13, cicd]
  links:
    - { url: https://platform-demo.10.0.0.200.nip.io/, title: Live service }
    - { url: https://argocd.10.0.0.200.nip.io/applications/platform-demo, title: ArgoCD Application }
spec:
  type: service
  lifecycle: production
  owner: andrelair-platform
  system: minicloud-platform
```

The other three (ansible / opentofu / gitops) follow the same shape with
appropriate `type` (tool), tags, and links.

The `argocd/app-name`, `prometheus.io/rule`, `grafana/dashboard-selector`
annotations don't do anything yet — but they're the right metadata for
when we add the corresponding plugins. Future-proofing.

---

## Verification

```bash
# Pods
kubectl get pods -n backstage
# Expected: backstage-... (1/1 Running) + backstage-postgresql-0 (1/1 Running)

# UI reachable
curl -sIL --cacert ~/minicloud-ca.crt https://backstage.10.0.0.200.nip.io/

# Page title
curl -s --cacert ~/minicloud-ca.crt https://backstage.10.0.0.200.nip.io/ \
  | grep -oE "<title>[^<]+</title>"
# <title>minicloud platform</title>

# Catalog query (with guest auth)
TOKEN=$(curl -s --cacert ~/minicloud-ca.crt -X POST \
  https://backstage.10.0.0.200.nip.io/api/auth/guest/refresh \
  | jq -r '.backstageIdentity.token')

curl -s --cacert ~/minicloud-ca.crt \
  -H "Authorization: Bearer $TOKEN" \
  "https://backstage.10.0.0.200.nip.io/api/catalog/entities?filter=kind=component" \
  | jq -r '.[] | "\(.metadata.name) — \(.spec.type)"'
# minicloud-ansible — tool
# minicloud-gitops — tool
# minicloud-opentofu — tool
# minicloud-platform-docs — documentation
# platform-demo — service
```

In the browser at `https://backstage.10.0.0.200.nip.io`:

1. Click **"Sign in as Guest"**
2. Catalog page → switch from "OWNER" to "ALL" filter
3. See 5 Components + 1 System with descriptions, tags, owner, links

---

## Three real install gotchas

### 1. Postgres race on first install
`helm install --wait` reports `STATUS: deployed` even when Backstage's
DB connection failed. Always restart the Backstage pod manually if logs
show `ECONNREFUSED`.

### 2. Default URL reading whitelist blocks `raw.githubusercontent.com`
Without `backend.reading.allow: [{host: raw.githubusercontent.com}]`,
catalog refresh logs:
```
Unable to read url, Reading from 'https://raw.githubusercontent.com/...'
is not allowed.
```

### 3. Guest auth gated in production-mode
The off-the-shelf image runs `NODE_ENV=production`. Without
`auth.providers.guest.dangerouslyAllowOutsideDevelopment: true`, every
guest sign-in returns:
```
NotAllowedError: The guest provider cannot be used outside of a development environment
```

---

## Done When

```text
✔ 2 pods Running in backstage namespace (backstage + backstage-postgresql-0)
✔ 1 PVC Bound on Longhorn (backstage-postgresql)
✔ Cert + Ingress for backstage.10.0.0.200.nip.io
✔ HTTP→HTTPS 301 redirect; HTTPS returns 200 with title "minicloud platform"
✔ Guest auth issues a JWT (~514 chars)
✔ /api/catalog/entities returns 6 entities: 1 System + 5 Components
✔ Each Component has its system: minicloud-platform link
✔ Homer has a Backstage tile
```

---

## Phase 24 — Custom Image + Authentik OIDC SSO (2026-07-10)

Phase 18 ran the off-the-shelf Backstage image with guest auth. Phase 24 replaced both:

- **Custom image** built from `andrelair-platform/minicloud-backstage` — TypeScript monorepo compiled on CI, pushed to Harbor, cosign-signed, auto-bumped via GPG-signed gitops commit.
- **Authentik OIDC** — replaces guest auth. User signs in via the platform's central SSO; identity is resolved against a real catalog User entity.

---

### Authentik provider setup

In Authentik: **Applications → Providers → Create → OAuth2/OpenID Connect Provider**

| Field | Value |
|---|---|
| Name | `backstage` |
| Client type | Confidential |
| Client ID | (auto-generated) |
| Client Secret | (auto-generated) |
| Grant types | **Authorization Code + Refresh Token** ← mandatory, defaults to empty |
| Signing Key | `authentik Self-signed Certificate` |
| Property Mappings | Select all OpenID mappings |
| Redirect URIs | `https://backstage.devandre.sbs/api/auth/oidc/handler/frame` |
| Sub mode | Based on hashed User ID |

:::danger Grant types — the most commonly missed field
The Authentik provider form defaults `grant_types` to an **empty list** when accessed via the API. If you create the provider via API (as Terraform/IaC tools do), authorization_code is never enabled. Symptom in Backstage logs: `invalid_request (The request is otherwise malformed)`. Fix: open the provider in Authentik UI → edit → enable **Authorization Code** + **Refresh Token**.
:::

**Authorization flow:** use `default-provider-authorization-implicit-consent` (NOT explicit-consent). Explicit-consent rejects `prompt=none` — Backstage's silent token refresh uses `prompt=none` and will always fail with `login_required` on explicit-consent flows.

---

### Backstage Helm values — OIDC config

Key additions in `minicloud-gitops/helm-values/backstage-values.yaml`:

```yaml
backstage:
  appConfig:
    app:
      baseUrl: https://backstage.devandre.sbs
      extensions:
        - page:catalog:
            config:
              path: /        # ← catalog page at root; see "Root route" gotcha below
    backend:
      baseUrl: https://backstage.devandre.sbs
      cors:
        origin: https://backstage.devandre.sbs
    auth:
      environment: production
      providers:
        oidc:
          production:
            metadataUrl: https://auth.devandre.sbs/application/o/backstage/.well-known/openid-configuration
            clientId: ${AUTH_OIDC_CLIENT_ID}
            clientSecret: ${AUTH_OIDC_CLIENT_SECRET}
            callbackUrl: https://backstage.devandre.sbs/api/auth/oidc/handler/frame
            additionalScopes: []
            signIn:
              resolvers:
                - resolver: emailMatchingUserEntityProfileEmail
                - resolver: emailLocalPartMatchingUserEntityName
    catalog:
      rules:
        - allow: [Component, System, API, Resource, Location, User, Group]
      locations:
        - type: url
          target: https://raw.githubusercontent.com/andrelair-platform/minicloud-gitops/main/catalog-info.yaml
        # ... (one entry per repo)
```

---

### Frontend auth module (auth.tsx)

The new Backstage frontend system (`@backstage/frontend-defaults`) requires an explicit `ApiBlueprint` for the OIDC provider. Guest auth is removed entirely.

```typescript
// packages/app/src/modules/auth.tsx
import { createFrontendModule } from '@backstage/frontend-plugin-api';
import {
  ApiBlueprint, createApiRef, configApiRef,
  discoveryApiRef, oauthRequestApiRef,
} from '@backstage/frontend-plugin-api';
import { SignInPageBlueprint } from '@backstage/plugin-app-react';
import { OAuth2 } from '@backstage/core-app-api';
import { SignInPage } from '@backstage/core-components';

export const oidcAuthApiRef = createApiRef<...>({ id: 'auth.oidc' });

export const authModule = createFrontendModule({
  pluginId: 'app',
  extensions: [
    ApiBlueprint.make({
      name: 'oidc',
      params: defineParams => defineParams({
        api: oidcAuthApiRef,
        deps: { configApi: configApiRef, discoveryApi: discoveryApiRef, oauthRequestApi: oauthRequestApiRef },
        factory: ({ configApi, discoveryApi, oauthRequestApi }) =>
          OAuth2.create({
            configApi,          // ← required in new system; omitting causes 404 on /api/config
            discoveryApi, oauthRequestApi,
            environment: 'production',
            provider: { id: 'oidc', title: 'Authentik', icon: () => null },
            defaultScopes: ['openid', 'email', 'profile'],
          }),
      }),
    }),
    SignInPageBlueprint.make({
      params: {
        loader: async () => (props: any) => (
          <SignInPage {...props} providers={[{
            id: 'oidc-auth-provider',
            title: 'Login with Authentik',
            message: 'Sign in using your Authentik SSO account',
            apiRef: oidcAuthApiRef,
          }]} />
          // ← 'guest' removed: causes 404 on /api/auth/guest/refresh in production
        ),
      },
    }),
  ],
});
```

---

### Catalog User + Group entities

The sign-in resolver (`emailMatchingUserEntityProfileEmail`) looks for a `User` entity with matching email in the catalog. The catalog must have the User entity before login can complete.

Add to `minicloud-gitops/catalog-info.yaml`:

```yaml
---
apiVersion: backstage.io/v1alpha1
kind: Group
metadata:
  name: andrelair-platform
  annotations:
    backstage.io/source-location: url:https://github.com/andrelair-platform/minicloud-gitops
spec:
  type: team
  profile:
    displayName: andrelair-platform
  children: []
---
apiVersion: backstage.io/v1alpha1
kind: User
metadata:
  name: kanmegnea
  annotations:
    backstage.io/source-location: url:https://github.com/andrelair-platform/minicloud-gitops
spec:
  profile:
    displayName: AndreLair
    email: kanmegnea@gmail.com
  memberOf:
    - andrelair-platform
```

Also add `User` and `Group` to `catalog.rules.allow` in the Helm values — without this, these kinds are silently rejected even if the entity is present in the source file.

---

### OIDC debug chain — 6 errors fixed in sequence

#### Error 1: `invalid_request (The request is otherwise malformed)`

**Cause:** Authentik provider `grant_types: []` — authorization_code was never enabled.  
**Symptom in Authentik logs:** `"Invalid grant_type for provider", "grant_type": "authorization_code"`  
**Fix:** Edit provider in Authentik UI → enable Authorization Code + Refresh Token.

#### Error 2: `Failed to sign-in, unable to resolve user identity`

**Cause:** No `User` entity in the catalog with matching email.  
**Fix:** Add `User` entity to `catalog-info.yaml` AND add `User, Group` to `catalog.rules.allow`.

#### Error 3: `404` on `/api/auth/guest/refresh`

**Cause:** `'guest'` provider left in `SignInPage.providers` array; the production Backstage image doesn't register the guest endpoint.  
**Fix:** Remove `'guest'` from the providers array.

#### Error 4: `login_required` on every Sign In attempt

**Root cause:** `metadataUrl` pointed at `auth.10.0.0.200.nip.io`. The OIDC discovery document's `authorization_endpoint` therefore used that hostname. The login popup opened at `auth.10.0.0.200.nip.io`. The user's Authentik session cookie was scoped to `auth.devandre.sbs` (different hostname). Browser didn't send the cookie → no active session → Authentik rejected `prompt=none` → `login_required`.

**Fix:** Change `metadataUrl` to `https://auth.devandre.sbs/application/o/backstage/.well-known/openid-configuration`. The discovery document then returns `authorization_endpoint: auth.devandre.sbs/...` — matching the hostname where the user's session cookie lives.

**Key insight:** the domain in `metadataUrl` must be the SAME domain where users authenticate in their browser. Backstage uses the OIDC discovery document to determine where to send the popup.

#### Error 5: `Page Not Found` after successful login

**Cause:** `app-config.yaml` (baked into the image) contains `app.extensions.page:catalog.config.path: /`. But the Backstage pod only loads the Helm-injected ConfigMap at runtime — the base config is NOT loaded. Without the extension config, the catalog page is at `/catalog`, not `/`. After login, the main window was at `https://backstage.devandre.sbs/` with no route registered there → "Page Not Found".

**Fix:** Add the extension config explicitly to the Helm values `appConfig`:
```yaml
app:
  extensions:
    - page:catalog:
        config:
          path: /
```

**Key insight:** in the new Backstage frontend system, the pod only loads the configs listed in the startup `--config` args. The base `app-config.yaml` is NOT auto-loaded in production unless explicitly included. Any runtime-critical config from the base file must be duplicated in the Helm values.

Confirmed by the pod's startup log:
```
Loading config from MergedConfigSource{
  FileConfigSource{path="/app/app-config.session.yaml"},
  FileConfigSource{path="/app/app-config-from-configmap.yaml"},
  EnvConfigSource{count=1}
}
```

#### Error 6: `catalog returns 0 entities` (false alarm)

**Symptom:** Backend access log showed `GET /api/catalog/entities... 200 0` — the "0" looked like an empty response body.

**Reality:** Backstage 3.x catalog API uses `Transfer-Encoding: chunked` (no fixed `Content-Length` header). The HTTP access logger records `0` when no Content-Length header is present. The catalog had **36 entities** in PostgreSQL the whole time, confirmed by:

```bash
PGPASS=$(kubectl get secret -n backstage backstage-postgres-secret \
  -o jsonpath='{.data.password}' | base64 -d)
kubectl exec -n backstage backstage-postgresql-0 -- bash -c \
  "PGPASSWORD='$PGPASS' psql -U bn_backstage -d backstage_plugin_catalog \
  -c 'SELECT entity_ref FROM final_entities ORDER BY entity_ref;'"
```

The token issuance was also confirmed in the backend logs:
```json
{"message":"Issuing token for user:default/kanmegnea, with entities user:default/kanmegnea,group:default/andrelair-platform","plugin":"auth"}
```

---

### Verification

```bash
# Pod running
kubectl get pod -n backstage -l app.kubernetes.io/name=backstage

# Catalog entity count (36 expected)
PGPASS=$(kubectl get secret -n backstage backstage-postgres-secret \
  -o jsonpath='{.data.password}' | base64 -d)
kubectl exec -n backstage backstage-postgresql-0 -- bash -c \
  "PGPASSWORD='$PGPASS' psql -U bn_backstage -d backstage_plugin_catalog \
  -c 'SELECT COUNT(*) FROM final_entities;'"

# User entity present
kubectl exec -n backstage backstage-postgresql-0 -- bash -c \
  "PGPASSWORD='$PGPASS' psql -U bn_backstage -d backstage_plugin_catalog \
  -c \"SELECT entity_ref FROM final_entities WHERE entity_ref LIKE 'user:%' OR entity_ref LIKE 'group:%';\""
```

**Manual login test:**
1. Navigate to `https://backstage.devandre.sbs`
2. Click **SIGN IN**
3. Authenticate via Authentik (kanmegnea + TOTP)
4. Expect: catalog page at `/` showing all 14 Components + System + Group + User

---

### Catalog refresh — how it actually works

The catalog does NOT log individual location fetches. The processing loop runs via internal PostgreSQL state (`refresh_state` table). Scheduled tasks visible in logs:

| Task | Cadence | Purpose |
|---|---|---|
| `catalog_orphan_cleanup` | 30s | Removes entities with no provider claiming them |
| `search_index_software_catalog` | 10m | Updates search index from catalog |

The entity processing loop (reading GitHub URLs, processing YAML) runs asynchronously via the `refresh_state` Knex queue — it is NOT logged as a `Registered scheduled task`. Entities persist in PostgreSQL across pod restarts.

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Off-the-shelf vs custom Backstage trade-off** | The single most important Backstage adoption decision. Real teams agonize over this. |
| **Software Catalog as the entry point** | Catalog-first adoption is the canonical Backstage rollout pattern at scale (Spotify, Netflix, Roadie's customers, etc.) |
| **PostgreSQL bitnami subchart with `existingSecret`** | Standard pattern for any Helm chart that ships a DB subchart — pre-create the secret out-of-band, reference it via `existingSecret` |
| **`raw.githubusercontent.com` reads to avoid GitHub rate limits** | Real production knowledge: even reading public repo files via the GitHub API hits unauthenticated rate limits. raw.githubusercontent.com is faster and rate-limit-free. |
| **Annotations for future plugins** | Adding `argocd/app-name` and `prometheus.io/rule` annotations even before the corresponding plugins are wired is the high-signal move — when plugins arrive, the metadata is already there |
| **Production-mode auth gating** | `NODE_ENV=production` + `dangerouslyAllow` is a Backstage-specific quirk that's documented but easily missed. Real install knowledge. |
| **Risk-aware scope reduction** | Choosing minimal-IDP over full custom-build with all plugins is the same skill as Phase 11's Crossplane deferral, Phase 13's GitLab deferral, etc. |
| **Honest "this is portfolio-only" framing** | Naming what isn't operationally needed alongside what is. A portfolio that says "we don't actually use this much" is more credible than one that pretends the homelab needs Backstage. |
