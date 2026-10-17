---
id: matrix-synapse-element-web
title: Phase 76 — Matrix Synapse + Element Web
sidebar_position: 25
---

# Phase 76 — Matrix Synapse + Element Web (Team Chat)

**Deployed:** 2026-07-18 | **Chart:** ananace/matrix-synapse 3.12.31 | **Synapse:** v1.156.0 | **Element Web:** v1.11.105

Self-hosted Matrix homeserver with Element Web client, Authentik OIDC SSO, and Longhorn-backed media storage. Runs in the `chat` namespace, shares the PostgreSQL instance in the `ai` namespace.

---

## Architecture

```
Browser → Cloudflare → element.devandre.sbs
           ↓ (Authentik proxy on ingress)
      Element Web (nginx, port 8080, UID 101)
           ↓ (Matrix CS API)
Browser → Cloudflare → matrix.devandre.sbs
           ↓
      Synapse (ghcr.io/element-hq/synapse:v1.156.0)
      ├─ PostgreSQL: postgresql-ai.ai.svc.cluster.local (synapse DB)
      ├─ Redis: bundled (matrix-synapse-redis)
      ├─ PVC: 10Gi Longhorn (media)
      └─ OIDC: auth.devandre.sbs → Authentik
```

**Namespace:** `chat`  
**Public URLs:** `https://element.devandre.sbs` (Element Web) · `https://matrix.devandre.sbs` (homeserver)  
**Internal URLs:** `https://element.10.0.0.200.nip.io` · `https://matrix.10.0.0.200.nip.io`  
**Server name:** `matrix.devandre.sbs`

---

## Pre-requisites

Before deploying:

1. **PostgreSQL user + database** in the `ai` namespace:
   ```sql
   CREATE USER synapse WITH PASSWORD '<pw>';
   CREATE DATABASE synapse OWNER synapse;
   GRANT ALL PRIVILEGES ON DATABASE synapse TO synapse;
   ```

2. **Vault secrets** at `secret/platform/matrix`:
   ```bash
   vault kv put secret/platform/matrix \
     oidc-client-id=<from Authentik> \
     oidc-client-secret=<from Authentik> \
     registration-shared-secret=$(openssl rand -hex 32) \
     macaroon-secret-key=$(openssl rand -hex 32) \
     pg-password=<postgresql synapse user password>
   ```

3. **Authentik OAuth2 provider** for Matrix Synapse:
   - Application slug: `matrix-synapse`
   - Redirect URIs: `https://matrix.devandre.sbs/_synapse/client/oidc/callback`
   - Grant types: `authorization_code`, `refresh_token`
   - Property mappings: `openid`, `profile`, `email`

4. **Cloudflare Tunnel DNS routes:**
   ```bash
   cloudflared tunnel route dns minicloud matrix.devandre.sbs
   cloudflared tunnel route dns minicloud element.devandre.sbs
   ```
   And in `~/.cloudflared/config.yml` on the controller:
   ```yaml
   - hostname: matrix.devandre.sbs
     service: https://10.0.0.200
     originRequest:
       noTLSVerify: true
       originServerName: matrix.10.0.0.200.nip.io
   - hostname: element.devandre.sbs
     service: https://10.0.0.200
     originRequest:
       noTLSVerify: true
       originServerName: element.10.0.0.200.nip.io
   ```

---

## GitOps Structure

```
minicloud-gitops/
├── apps/matrix-synapse.yaml          # ArgoCD multi-source app
├── helm-values/synapse-values.yaml   # ananace chart values
└── manifests/matrix/
    ├── 00-eso-synapse-secret.yaml    # ExternalSecret → synapse-secrets
    ├── 01-element-web.yaml           # ConfigMap + Deployment + Service + Ingress
    └── 02-minicloud-ca-configmap.yaml # minicloud CA cert (for OIDC TLS trust)
```

The ArgoCD app uses **three sources**: the ananace Helm chart, the values file, and the raw manifests path.

---

## Gatekeeper Constraint Exclusions

The `chat` namespace was added to all 9 Gatekeeper constraint exclusion lists. Notable reasons:

| Constraint | Why excluded |
|---|---|
| `block-latest-tag` | Signing key job uses `bitnami/kubectl:latest` (no semver tags in bitnami) |
| `require-resource-limits` | Signing key job (batch Job) has no resource limits in chart defaults |
| `require-non-root` | Signing key job init uses bitnami/kubectl — chart doesn't set `runAsNonRoot` |
| `no-privilege-escalation` | Same signing key job — chart omits `allowPrivilegeEscalation` |

---

## Key Configuration

### Synapse values (`helm-values/synapse-values.yaml`)

```yaml
serverName: matrix.devandre.sbs
publicServerName: matrix.devandre.sbs

signingkey:
  job:
    enabled: false  # disable after first install — key stored in matrix-synapse-signingkey secret

extraConfig:
  oidc_providers:
    - idp_id: authentik
      discover: false  # required — see GOTCHA below
      issuer: "https://auth.devandre.sbs/"
      authorization_endpoint: "https://auth.devandre.sbs/application/o/authorize/"
      token_endpoint: "https://auth.devandre.sbs/application/o/token/"
      userinfo_endpoint: "https://auth.devandre.sbs/application/o/userinfo/"
      jwks_uri: "https://auth.devandre.sbs/application/o/matrix-synapse/jwks/"

synapse:
  extraCommands:
    - "cp /etc/ssl/certs/ca-certificates.crt /tmp/ca-bundle.crt"
    - "cat /etc/minicloud-ca/ca.crt >> /tmp/ca-bundle.crt"
    - "export SSL_CERT_FILE=/tmp/ca-bundle.crt"
  extraVolumes:
    - name: minicloud-ca
      configMap:
        name: minicloud-ca-cert
  extraVolumeMounts:
    - name: minicloud-ca
      mountPath: /etc/minicloud-ca
```

---

## GOTCHA Collection

These were discovered during the 54+ PR debugging process.

### GOTCHA 1 — ananace chart: `extraInitContainers` is NOT supported

The ananace chart's `values.yaml` exposes `extraEnv`, `extraVolumes`, `extraVolumeMounts`, `extraCommands` — but **not** `extraInitContainers`. Setting `synapse.extraInitContainers` in your values file is silently ignored.

```
# These work ✓          # This is silently ignored ✗
synapse.extraEnv         synapse.extraInitContainers
synapse.extraVolumes
synapse.extraVolumeMounts
synapse.extraCommands
```

Use `extraCommands` instead. They run in the same `sh -c` block as `exec python`, so `export` statements are inherited by the Python process.

### GOTCHA 2 — ananace chart: `securityContext` and `podSecurityContext` are INVERTED

The chart maps field names opposite to standard Kubernetes:

| Chart field | Applies to |
|---|---|
| `synapse.securityContext` | **pod**-level securityContext |
| `synapse.podSecurityContext` | per-**container** securityContext |

`signingkey.job.podSecurityContext` applies at container-level, so `fsGroup` (pod-level only) cannot be set there. Remove all custom security contexts from the signing key job to avoid schema validation failures with `ServerSideApply`.

### GOTCHA 3 — Remove `ServerSideApply=true` from the ArgoCD Application

With `ServerSideApply=true`, ArgoCD enforces typed schema validation against the live cluster. The ananace chart generates fields in positions that fail strict type checking (pod vs. container security context mismatch). Remove `ServerSideApply=true` from `apps/matrix-synapse.yaml`'s `syncOptions`. Client-side 3-way merge is permissive enough.

### GOTCHA 4 — Gatekeeper blocks `bitnami/kubectl:1.30` and `vectorim/element-web`

The `K8sAllowedRepos` constraint requires image strings to have an explicit registry prefix (`docker.io/`, `ghcr.io/`, etc.). Images without a prefix are rejected:

```
# Rejected ✗           # Accepted ✓
bitnami/kubectl:1.30   docker.io/bitnami/kubectl:latest
vectorim/element-web   docker.io/vectorim/element-web:v1.11.105
```

Additionally, `bitnami/kubectl:1.30` does not exist — bitnami only publishes full version tags like `1.30.7-debian-12-r0`. Use `latest` (the `chat` namespace is excluded from the `block-latest-tag` constraint).

### GOTCHA 5 — Element Web nginx crashes with `invalid host in tcp://...`

Kubernetes injects service environment variables including `ELEMENT_WEB_PORT=tcp://10.43.x.x:80` into every pod in the same namespace. The Element Web nginx template uses `${ELEMENT_WEB_PORT}` as a variable — nginx substitutes it with the full TCP URL and produces an invalid config.

Additionally, nginx can't bind port 80 as UID 101 with `CAP_NET_BIND_SERVICE` dropped.

**Fix**: Set `enableServiceLinks: false` on the pod spec and use port 8080:
```yaml
spec:
  enableServiceLinks: false  # prevent ELEMENT_WEB_PORT env var collision
containers:
  - env:
      - name: NGINX_PORT
        value: "8080"
      - name: ELEMENT_WEB_PORT
        value: "8080"
    ports:
      - containerPort: 8080
```
Service maps port 80 → targetPort 8080 (external access unchanged).

### GOTCHA 6 — OidcDiscoveryError: `auth.devandre.sbs` resolves to MetalLB inside the cluster

From inside the cluster, `auth.devandre.sbs` DNS resolves to `10.0.0.200` (MetalLB VIP, nginx ingress), which presents a **minicloud CA-signed certificate** — not a public CA cert. Synapse's Python/twisted TLS stack doesn't trust the minicloud CA by default.

This caused:
- `discover: true` → `RequestTimedOutError` at startup (discovery HTTP call to `auth.devandre.sbs` fails)
- `discover: false` + internal `http://` endpoints → `ValueError: token_endpoint MUST use https scheme`
- `discover: false` + public `https://` endpoints → TLS failure on JWKS fetch

**Fix**: Use `discover: false`, mount the minicloud CA cert via a ConfigMap, and use `extraCommands` to inject it into the SSL trust chain before Synapse starts:

```yaml
synapse:
  extraCommands:
    - "cp /etc/ssl/certs/ca-certificates.crt /tmp/ca-bundle.crt"
    - "cat /etc/minicloud-ca/ca.crt >> /tmp/ca-bundle.crt"
    - "export SSL_CERT_FILE=/tmp/ca-bundle.crt"
```

`extraCommands` run in the same `sh -c` invocation as `exec python`, so the `SSL_CERT_FILE` environment variable is inherited by the Python process. Python/pyOpenSSL/OpenSSL reads `SSL_CERT_FILE` via `SSL_CTX_set_default_verify_paths()`.

### GOTCHA 7 — OIDC `issuer` must not include the application path

Synapse's `issuer` field is validated against the `iss` claim in ID tokens issued by Authentik.

Authentik's discovery document returns:
```json
{ "issuer": "https://auth.devandre.sbs/" }
```

Not:
```json
{ "issuer": "https://auth.devandre.sbs/application/o/matrix-synapse/" }
```

Always match the actual discovery document. Use `discover: false` with explicit endpoints and set:
```yaml
issuer: "https://auth.devandre.sbs/"
```

### GOTCHA 8 — Signing key job: disable after first install

The signing key job (`signingkey.job.enabled: true`) generates the Synapse signing key once and stores it in the `matrix-synapse-signingkey` secret. ArgoCD sees the completed Job as OutOfSync on every sync (Job status changes after completion).

After the first install, verify the secret exists:
```bash
kubectl get secret matrix-synapse-signingkey -n chat
```
Then set `signingkey.job.enabled: false` in `synapse-values.yaml` and push.

### GOTCHA 9 — Longhorn RWO PVC corruption from repeated forced unmounts

Rapid termination cycles (multiple `kubectl delete pod --force`) during debugging can corrupt the ext4 filesystem on the Longhorn volume. Symptoms: Synapse logs `OSError: Errno 5 Input/output error: /synapse/data/media`.

**Fix**:
```bash
kubectl scale deployment/matrix-synapse -n chat --replicas=0
kubectl delete pvc matrix-synapse -n chat
# ArgoCD recreates the PVC on next sync
```

After PVC deletion, delete any stale VolumeAttachment if the new PVC gets stuck:
```bash
kubectl get volumeattachment | grep <pvc-id>
kubectl delete volumeattachment <name>
```

---

## Verification

```bash
# Matrix API health
/usr/bin/curl -sk https://matrix.10.0.0.200.nip.io/_matrix/client/versions \
  --cacert ~/minicloud-ca.crt | python3 -m json.tool | head -5

# SSO redirect flow (should return 302 → Authentik)
/usr/bin/curl -sk \
  'https://matrix.10.0.0.200.nip.io/_matrix/client/v3/login/sso/redirect/authentik?redirectUrl=https://element.devandre.sbs' \
  --cacert ~/minicloud-ca.crt -o /dev/null -w 'status=%{http_code}'

# Element Web (should return 200)
/usr/bin/curl -sk https://element.10.0.0.200.nip.io/ --cacert ~/minicloud-ca.crt -o /dev/null -w '%{http_code}'

# Pod status
kubectl get pods -n chat
```

---

## User Registration

Registration is disabled (`enable_registration: false`). Users log in exclusively via Authentik SSO. The first time an Authentik user logs in to Element Web, Synapse creates their Matrix account automatically (`allow_existing_users: true`).

Username format: `@<authentik_preferred_username>:matrix.devandre.sbs`

---

## Resources

| Resource | Value |
|---|---|
| Synapse CPU | 100m req / 500m limit |
| Synapse Memory | 512Mi req / 1Gi limit |
| Redis CPU | 10m req / 100m limit |
| Redis Memory | 32Mi req / 64Mi limit |
| Element Web CPU | 10m req / 100m limit |
| Element Web Memory | 32Mi req / 128Mi limit |
| PVC (media) | 10Gi Longhorn RWO |
