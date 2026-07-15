---
id: minicloud-plane
title: Phase 69 — minicloud-plane (Level 4 Integration + Backstage)
sidebar_label: Phase 69 — minicloud-plane
---

# Phase 69 — minicloud-plane — Level 4 API Integration + Backstage

`minicloud-plane` is a custom Go service that bridges Plane CE into the rest of the platform. It provides two capabilities:

1. **REST proxy API** — authenticated Plane data over a clean JSON API, consumed by Backstage
2. **Webhook → NATS bridge** — Plane events (issue created/updated/deleted) published to NATS for downstream consumers

This is a **Level 4 integration** — original code that wraps an existing service via its public API, rather than forking or patching it.

---

## The Four Levels of Open-Source Customization

Understanding this taxonomy clarifies the architectural choice:

| Level | What you do | Example in minicloud | When to choose |
|---|---|---|---|
| **L1 — Deploy as-is** | `helm install`, no source changes | NATS, Longhorn, Grafana, ArgoCD | ~80% of tools |
| **L2 — Custom image wrapper** | Your Dockerfile `FROM upstream`, add files | minicloud-backstage (CA cert + plugins), open-webui (CA cert + BM25) | Need files inside the container |
| **L3 — Fork + patch** | Clone upstream, apply patches, maintain a fork | *(avoided in minicloud)* | Upstream won't merge your fix |
| **L4 — API integration service** | New service that calls the upstream's API | minicloud-plane (this phase) | Tool exposes a stable API; you want to connect it to other systems |

**Why not L2 for Plane?** A custom Plane image would let you add CA certs or patch Python files — but the real need is connecting Plane to Backstage and NATS, which are external systems. That connection has to live somewhere outside Plane. L4 is the right layer.

**Why not L3?** Forking Plane means rebasing on every release. Plane CE releases roughly monthly. The integration surface (REST API + webhooks) is stable and versioned — no reason to take on that maintenance burden.

---

## Architecture

```
                   Plane CE (plane namespace)
                         │
                         │  HMAC-signed webhooks (X-Plane-Signature)
                         ▼
         ┌──────────────────────────────────────┐
         │   minicloud-plane-dev namespace      │
         │                                      │
         │   minicloud-plane (Go service)       │
         │   ┌──────────┐   ┌──────────────┐   │
         │   │ /webhook │   │ /api/        │   │
         │   │ handler  │   │ REST proxy   │   │
         │   └────┬─────┘   └──────┬───────┘   │
         │        │                │           │
         └────────┼────────────────┼───────────┘
                  │                │
                  ▼                ▼
         NATS (messaging ns)   Backstage (via proxy)
         plane.<ws>.<event>    /api/proxy/minicloud-plane/
```

**Service endpoints:**
| Path | Purpose |
|---|---|
| `GET /health` | Liveness/readiness probe |
| `POST /webhook` | Receives Plane webhook events |
| `GET /api/projects` | Returns all workspace projects |
| `GET /api/projects/{id}/issues` | Returns issues for a project |

---

## Repository — `andrelair-platform/minicloud-plane`

```
minicloud-plane/
├── cmd/server/main.go            # entrypoint: wires all handlers
├── internal/
│   ├── api/handler.go            # REST proxy (projects, issues)
│   ├── nats/publisher.go         # NATS publisher
│   ├── plane/
│   │   ├── client.go             # Plane API client (X-Api-Key auth)
│   │   └── types.go              # Project, Issue, WebhookEvent structs
│   └── webhook/handler.go        # HMAC verification + NATS publish
├── Containerfile                 # Go 1.25, distroless/static:nonroot
└── .github/workflows/ci.yml      # test → build → Trivy → Cosign → gitops
```

---

## Key Gotchas Encountered

### 1. Plane has two Django modules with different auth

```
plane.app  → /api/        → Authorization: Bearer <session-token>
plane.api  → /api/v1/     → X-Api-Key: <api-key>
```

The API key integration always uses `/api/v1/` with `X-Api-Key`. Using `/api/` or `X-Api-Token` returns 401/403. Source: `/code/plane/app/middleware/api_authentication.py`.

### 2. NATS service is in the `messaging` namespace

The NATS Helm release is named `nats` but deployed in namespace `messaging`. The internal DNS name is:

```
nats://nats.messaging.svc.cluster.local:4222
```

Not `nats.nats.svc.cluster.local`. The pod CrashLoopBackOff'ed until this was corrected in both `deployment.yaml` and the Go default in `cmd/server/main.go`.

### 3. Webhook signature — plain hex, not `sha256=` prefixed

Plane's webhook task generates the signature as:

```python
# /code/plane/bgtasks/webhook_task.py
signature = hmac_signature.hexdigest()
```

No prefix — it sends the raw hex digest in `X-Plane-Signature`. Our initial handler expected `sha256=<hex>` (the GitHub-style format). Fix:

```go
// internal/webhook/handler.go
func (h *Handler) verifySignature(sig string, body []byte) bool {
    mac := hmac.New(sha256.New, []byte(h.secret))
    mac.Write(body)
    expected := hex.EncodeToString(mac.Sum(nil))  // no "sha256=" prefix
    return hmac.Equal([]byte(sig), []byte(expected))
}
```

### 4. Plane SSRF protection blocks internal webhook targets

`validate_url()` in `/code/plane/utils/ip_address.py` rejects RFC1918 addresses and `.svc.cluster.local` hostnames. Escape hatch: set `WEBHOOK_ALLOWED_HOSTS` in the Plane worker environment (see Phase 68).

### 5. Workspace must exist before API calls work

Plane returns 403 on all `/api/v1/workspaces/` calls until the onboarding flow is completed. If Plane was installed without visiting the UI, bootstrap via Django shell (see Phase 68).

### 6. ESO secret refresh — 1h default TTL

After updating a Vault secret (e.g., `PLANE_URL` changed from public to internal URL), the ESO ExternalSecret doesn't refresh immediately. Force-refresh:

```bash
kubectl annotate externalsecret minicloud-plane-secrets \
  -n minicloud-plane-dev \
  force-sync=$(date +%s) --overwrite
```

---

## Vault Secrets

```
secret/platform/minicloud-plane
├── PLANE_URL          http://plane-api.plane.svc.cluster.local  (internal)
├── PLANE_TOKEN        <api-key from Django shell>
├── PLANE_WORKSPACE    andrelair
└── PLANE_WEBHOOK_SECRET  <random hex — matches Plane webhook config>
```

Set with:
```bash
vault kv put secret/platform/minicloud-plane \
  PLANE_URL="http://plane-api.plane.svc.cluster.local" \
  PLANE_TOKEN="<token>" \
  PLANE_WORKSPACE="andrelair" \
  PLANE_WEBHOOK_SECRET="<secret>"
```

---

## Vault Policy + Kubernetes Auth

The ESO `ClusterSecretStore vault-backend` uses the `external-secrets-reader` policy (`secret/data/platform/*` wildcard), so no additional policy was needed. A dedicated Kubernetes auth role was created for the service's own service account:

```bash
vault write auth/kubernetes/role/minicloud-plane \
  bound_service_account_names=minicloud-plane \
  bound_service_account_namespaces=minicloud-plane-dev,minicloud-plane-staging,minicloud-plane-prod \
  policies=external-secrets-reader \
  ttl=1h
```

---

## CI Pipeline

```
push to dev   → test → build → Trivy (CRITICAL=0) → push Harbor (dev-<sha>)
                             → bump gitops overlays/dev/kustomization.yaml

push to main  → test → build → Trivy → push Harbor (<sha>)
                             → Cosign sign (keyless, GitHub OIDC → Sigstore)
                             → syft SBOM → cosign attach sbom
                             → bump gitops overlays/prod/kustomization.yaml (GPG signed)
```

**CVE-2025-68121:** Found during first Trivy scan. Go stdlib `crypto/tls` CRITICAL vulnerability. Fixed by bumping Go from 1.23 → 1.25 in `Containerfile`, `ci.yml`, and `go.mod`.

**Kustomize install fix:** The `install_kustomize.sh` from the kustomize master branch is flaky (tar fails when the download path doesn't match). Fixed by switching to `imranismail/setup-kustomize@v2` action with `kustomize-version: "5.6.0"`.

---

## NATS Subject Format

Events are published to:
```
plane.<workspace_slug>.<event>.<action>
```

Example:
```
plane.andrelair.issue.created  (865 bytes)
plane.andrelair.issue.updated
plane.andrelair.cycle.created
```

Subscribe to all Plane events for a workspace:
```bash
# From nats-box in messaging namespace
kubectl exec -n messaging -it deploy/nats-box -- \
  nats sub "plane.andrelair.>"
```

---

## Verified Pipeline

```
Plane issue created via UI/API
→ plane-worker dispatches webhook_send_task (Celery)
→ POST to minicloud-plane /webhook (with X-Plane-Signature header)
→ HMAC-SHA256 verified (plain hex)
→ Event parsed: event=issue action=created
→ Published to NATS: plane.andrelair.issue.created (865 bytes)
```

Pod log:
```
2026/07/15 05:58:08 webhook: event=issue action=created actor=
2026/07/15 05:58:08 published plane.andrelair.issue.created (865 bytes)
```

---

## GitOps Layout (minicloud-gitops)

```
services/minicloud-plane/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml       # envFrom: minicloud-plane-secrets + NATS_URL env
│   ├── service.yaml
│   └── serviceaccount.yaml
└── overlays/
    ├── dev/                  # auto-sync, CI bumps newTag
    ├── staging/              # manual sync (manual PR to promote)
    └── prod/                 # manual sync, CI bumps newTag on main push
```

ArgoCD application: `minicloud-plane-dev` (auto-sync) in project `minicloud-platform`.

---

## Backstage Integration — `@internal/plugin-minicloud-plane`

A local Backstage frontend plugin (`plugins/minicloud-plane/` in `minicloud-backstage`) adds a **"Plane Issues" tab** to any catalog entity with the `plane.io/project-id` annotation.

### How it works

```
Backstage frontend
  → EntityPlaneIssuesContent component
    → reads entity.metadata.annotations['plane.io/project-id']  (e.g. "PT")
    → PlaneApiClient.getProjects()    → /api/proxy/minicloud-plane/api/projects
    → finds project by id or identifier
    → PlaneApiClient.getIssues(id)   → /api/proxy/minicloud-plane/api/projects/{id}/issues
    → renders table: # | Title | Priority | State
```

### Proxy config

Production config lives in `minicloud-gitops/helm-values/backstage-values.yaml` (the ConfigMap source — `app-config.yaml` in the image is never loaded in production):

```yaml
# minicloud-gitops/helm-values/backstage-values.yaml → appConfig
proxy:
  endpoints:
    '/minicloud-plane':
      target: 'http://minicloud-plane.minicloud-plane-dev.svc.cluster.local:8080'
      changeOrigin: true
```

For local dev, `app-config.yaml` has:
```yaml
proxy:
  endpoints:
    '/minicloud-plane':
      target: 'http://localhost:8080'   # port-forward the svc locally
```

```bash
# Port-forward to test without cluster access
kubectl --context minicloud port-forward -n minicloud-plane-dev svc/minicloud-plane 8080:8080
```

### Plugin registration

```ts
// packages/app/src/App.tsx
import minicloudPlanePlugin from '@internal/plugin-minicloud-plane';

export default createApp({
  features: [..., minicloudPlanePlugin, ...],
});
```

### Wiring entities

Add to any `catalog-info.yaml`:

```yaml
metadata:
  annotations:
    plane.io/project-id: "PT"   # project identifier OR UUID
```

Value can be:
- The project **identifier** (e.g. `PT`, `MINI`) — human-readable, shown in the Plane UI
- The project **UUID** (e.g. `870d8973-8525-4d5d-9bab-43a4d6a517f1`)

The plugin tries both, so either works.

### Currently wired entities

| Entity | Annotation value | Project |
|---|---|---|
| `platform-demo` | `PT` | Platform Tasks |
| `minicloud-plane` | `PT` | Platform Tasks |

---

## Backstage Catalog Entity

`minicloud-plane/catalog-info.yaml` is a multi-document YAML file containing both a `Component` and an `API` entity. This populates:
- The **Provided APIs** tab on the `minicloud-plane` component page
- The **Consumed APIs** tab on the `minicloud-backstage` component page
- The **APIs** section in the Backstage left nav

### Component → API relationship

```yaml
# minicloud-plane/catalog-info.yaml (Component doc)
spec:
  providesApis:
    - minicloud-plane-api
---
# Same file (API doc)
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: minicloud-plane-api
spec:
  type: openapi
  definition: |
    openapi: "3.0.3"
    # ... full spec inline (health, /api/projects, /api/projects/{id}/issues)
```

```yaml
# minicloud-backstage/catalog-info.yaml
spec:
  consumesApis:
    - minicloud-plane-api
```

### Kubernetes tab

The Backstage Kubernetes plugin associates cluster resources with a component via the `backstage.io/kubernetes-id` pod label. This label is set in the deployment pod template:

```yaml
# minicloud-gitops/services/minicloud-plane/base/deployment.yaml
spec:
  template:
    metadata:
      labels:
        app: minicloud-plane
        backstage.io/kubernetes-id: minicloud-plane
```

Without this label, the Kubernetes tab shows "No resources on any known clusters" even though the pod is running.

---

## Quick Reference

```bash
# Check pod health
kubectl get pod -n minicloud-plane-dev

# Test API (port-forward)
kubectl port-forward -n minicloud-plane-dev svc/minicloud-plane 8080:8080 &
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/projects | jq '.[].name'
curl -s http://localhost:8080/api/projects/PT/issues | jq 'length'
kill %1

# Watch NATS events
kubectl exec -n messaging -it deploy/nats-box -- \
  nats sub "plane.andrelair.>"

# Force ESO secret refresh after Vault update
kubectl annotate externalsecret minicloud-plane-secrets \
  -n minicloud-plane-dev force-sync=$(date +%s) --overwrite

# CI status
gh run list --repo andrelair-platform/minicloud-plane --limit 5
```
