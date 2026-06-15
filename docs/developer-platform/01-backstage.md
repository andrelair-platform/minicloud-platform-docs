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

### The fix — pin to `1.51.2`

Edited `backstage-values.yaml`:

```diff
   image:
     registry: ghcr.io
     repository: backstage/backstage
-    tag: latest
+    tag: "1.51.2"
```

Applied with `helm upgrade backstage backstage/backstage -n backstage -f backstage-values.yaml`. Rollout took ~24 s (336 MB image, pulled through Harbor's `ghcr` proxy cache). Browser hard-refresh confirmed the error gone.

### Why `1.51.2` specifically

| Requirement | How 1.51.2 meets it |
|---|---|
| Includes the upstream fix for `plugin.notifications.service` | Fix shipped in **1.49.0** as a no-op fallback implementation; 1.51.2 carries it forward |
| Frozen identity that won't drift on the next pod restart | Specific patch version, not a rolling tag |
| Available in the registry we're pulling from | Verified via `curl https://harbor.10.0.0.200.nip.io/v2/ghcr/backstage/backstage/tags/list` — 1.47.0 through 1.51.2 were published, 1.51.2 was newest at pin time |
| Not so new it carries different bugs | One minor patch behind newest available; same era of code, settled |

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
