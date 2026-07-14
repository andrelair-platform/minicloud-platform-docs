---
id: nextcloud
title: Phase 57-58 — Nextcloud + OnlyOffice
sidebar_position: 4
---

# Phase 57-58 — Nextcloud 33 + Authentik SSO + OnlyOffice

Phase 57 (2026-06-22): Nextcloud 33.0.5 on k3s with Authentik OIDC SSO.
Phase 58 (2026-07-14): OnlyOffice DocumentServer 8.3.3 added — in-browser editing for .docx/.xlsx/.pptx files directly from the Nextcloud Files UI.

---

## What Was Deployed

| Component | Version | Notes |
|---|---|---|
| Nextcloud | 33.0.5 | Helm chart via ArgoCD |
| user_oidc plugin | 8.10.1 | Bundled in the chart |
| PostgreSQL | Bitnami (Longhorn PVC) | Dedicated DB for Nextcloud |
| Redis | Bitnami | Session cache + file-locking |
| Authentik provider | pk=9 | OIDC, explicit-consent flow |
| OnlyOffice DocumentServer | 8.3.3 | In-browser document editing |
| onlyoffice Nextcloud app | 10.1.2 | Nextcloud ↔ OnlyOffice bridge |

**URLs:**

| Access | URL |
|---|---|
| Nextcloud internal | `https://cloud.10.0.0.200.nip.io` |
| Nextcloud public | `https://cloud.devandre.sbs` |
| OnlyOffice internal | `https://onlyoffice.10.0.0.200.nip.io` |
| OnlyOffice public | `https://onlyoffice.devandre.sbs` |

Admin password: `ssh controller 'cat ~/.nextcloud-admin'`

---

## Architecture

```text
Browser → Cloudflare Tunnel → NGINX Ingress (10.0.0.200)
              │
              ├── /  → nextcloud pod (nextcloud namespace)
              │              │
              │              ├── PostgreSQL (PVC: longhorn, 10Gi)
              │              ├── Redis (session + file-lock)
              │              ├── Authentik (OIDC) ← SSO login
              │              └── onlyoffice app (occ configured)
              │
              └── /  → onlyoffice pod (ClusterIP)
                             └── DocumentServer 8.3.3

Document edit flow:
  Browser → opens doc in Nextcloud → Nextcloud redirects iframe to OnlyOffice
  OnlyOffice fetches doc from StorageUrl (https://cloud.devandre.sbs/)
  OnlyOffice saves changes back → Nextcloud
  JWT token authenticates all OnlyOffice ↔ Nextcloud calls
```

CoreDNS maps `cloud.devandre.sbs → 10.0.0.200` in-cluster so Nextcloud's OIDC callback hits NGINX directly without leaving the cluster.

---

## Authentik OIDC Provider Setup

Nextcloud uses the `user_oidc` plugin. The Authentik provider must be created via the API — the UI omits several required fields.

### Create the OAuth2 provider

Key fields that must be set explicitly (API defaults are wrong):

```python
payload = {
    "name": "Nextcloud",
    "authorization_flow": <explicit-consent-flow-uuid>,
    "invalidation_flow": <default-provider-invalidation-flow-uuid>,
    "client_type": "confidential",
    "client_id": "nextcloud",
    "redirect_uris": [
        {
            "matching_mode": "strict",
            "url": "https://cloud.devandre.sbs/apps/user_oidc/code"
        },
        {
            "matching_mode": "strict",
            "url": "https://cloud.10.0.0.200.nip.io/apps/user_oidc/code"
        }
    ],
    "grant_types": ["authorization_code", "refresh_token"],  # ← MUST set; API default is []
    "sub_mode": "hashed_user_id",
    "issuer_mode": "per_provider",                           # ← affects OIDC discovery URL
    "include_claims_in_id_token": True,
    "signing_key": <rs256-key-uuid>
}
```

**`grant_types` must be set explicitly.** The Authentik API defaults to an empty list `[]`, which means no grant type is allowed and every login attempt fails silently with a 400.

**`issuer_mode: per_provider`** gives each Authentik provider its own discovery URL (`/application/o/<slug>/`). If you later change `issuer_mode` on an existing provider, **clear the Nextcloud Redis cache** — Nextcloud caches the OIDC discovery document and will keep hitting the old issuer URL:

```bash
ssh controller "kubectl exec -n nextcloud deploy/nextcloud -- php occ cache:flush"
# or exec into Redis and FLUSHDB
```

### Allow SSRF for internal OIDC callback

Nextcloud blocks HTTP requests to private/internal IP ranges by default (SSRF protection). The Authentik provider URL resolves to `10.0.0.200` inside the cluster — add it to the allow list:

```bash
kubectl exec -n nextcloud deploy/nextcloud -- \
  php occ config:system:set allow_local_remote_servers --value=true --type=boolean
```

Without this, Nextcloud silently fails to fetch the OIDC discovery document.

### Use explicit-consent flow

Do **not** use `default-provider-authorization-implicit-consent`. Create an explicit-consent flow in Authentik (`default-provider-authorization-explicit-consent`) — Nextcloud requires user consent to be confirmed before issuing tokens.

---

## Helm Values (key excerpts)

```yaml
# minicloud-ansible/helm-values/nextcloud-values.yaml
nextcloud:
  host: cloud.10.0.0.200.nip.io
  existingSecret:
    enabled: true
    secretName: nextcloud-secrets
    usernameKey: nextcloud-username
    passwordKey: nextcloud-password

ingress:
  enabled: true
  ingressClassName: nginx
  hosts:
    - host: cloud.10.0.0.200.nip.io
      paths: [{path: /, pathType: Prefix}]
    - host: cloud.devandre.sbs
      paths: [{path: /, pathType: Prefix}]
  tls:
    - hosts: [cloud.10.0.0.200.nip.io, cloud.devandre.sbs]
      secretName: nextcloud-tls

postgresql:
  enabled: true
  primary:
    persistence:
      storageClass: longhorn
      size: 10Gi

redis:
  enabled: true

persistence:
  enabled: true
  storageClass: longhorn
  size: 20Gi
```

---

## Configuring user_oidc in Nextcloud

After the Authentik provider is created, register it in Nextcloud via CLI:

```bash
kubectl exec -n nextcloud deploy/nextcloud -- \
  php occ user_oidc:provider Authentik \
    --clientid="nextcloud" \
    --clientsecret="<client-secret>" \
    --discoveryuri="https://auth.10.0.0.200.nip.io/application/o/nextcloud/.well-known/openid-configuration" \
    --mapping-uid="preferred_username" \
    --unique-uid=0
```

Use the **nip.io** discovery URI (not devandre.sbs) — in-cluster DNS maps it to 10.0.0.200 and avoids the CoreDNS → Cloudflare → back round-trip.

---

---

## OnlyOffice DocumentServer (Phase 58)

OnlyOffice 8.3.3 is deployed as a separate pod in the `nextcloud` namespace alongside the Nextcloud Helm release. All manifests live in `minicloud-gitops/manifests/nextcloud/` and are tracked via a third `source` in the ArgoCD Application.

### GitOps Multi-Source Layout

```yaml
# apps/nextcloud.yaml — three sources:
sources:
  - repoURL: https://nextcloud.github.io/helm/  # Helm chart
    chart: nextcloud
    targetRevision: 9.1.3
    helm:
      valueFiles:
        - $values/helm-values/nextcloud-values.yaml
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    ref: values                # $values reference
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    path: manifests/nextcloud  # raw YAML directory
```

The `manifests/nextcloud/` directory contains:

| File | Purpose |
|---|---|
| `10-onlyoffice.yaml` | Deployment + ClusterIP Service |
| `11-onlyoffice-ingress.yaml` | cert-manager Certificate + NGINX Ingress |
| `12-onlyoffice-rbac.yaml` | ServiceAccount + Role + RoleBinding for config Job |
| `13-onlyoffice-config-job.yaml` | ArgoCD PostSync hook Job (idempotent occ config) |

### Secret Management

The JWT shared secret lives in Vault at `secret/platform/nextcloud-secrets` under key `onlyoffice-jwt-secret`. ESO fetches the entire secret path via `dataFrom.extract` — all keys appear as fields in the `nextcloud-secrets` k8s Secret automatically.

```bash
# Add the key to Vault (vault CLI not installed on controller — use curl):
TOKEN=$(cat ~/.vault-root-token)
ssh controller "curl -sk -X POST \
  -H 'X-Vault-Token: $TOKEN' \
  -d '{\"data\":{\"onlyoffice-jwt-secret\":\"<64-char-hex>\"}}' \
  https://vault.10.0.0.200.nip.io/v1/secret/data/platform/nextcloud-secrets"

# Force ESO to re-sync after adding the key:
kubectl annotate externalsecret nextcloud-secrets -n nextcloud \
  force-sync=$(date +%s) --overwrite
```

### OnlyOffice Deployment Specifics

```yaml
image: onlyoffice/documentserver:8.3.3
env:
  - JWT_ENABLED: "true"
  - JWT_HEADER: "AuthorizationJwt"    # non-standard header avoids conflicts
  - JWT_SECRET: <from nextcloud-secrets>
  - ALLOW_PRIVATE_IP_ADDRESS: "true"  # OnlyOffice must reach Nextcloud on 10.0.0.x
  - ALLOW_META_IP_ADDRESS: "true"
resources:
  requests: {cpu: 250m, memory: 1Gi}
  limits:   {cpu: "2",  memory: 3Gi}
```

Liveness and readiness probes hit `/healthcheck` on port 80 (`initialDelaySeconds: 60` — DocumentServer takes 45-60s to start).

The `nextcloud` namespace is excluded from the Gatekeeper registry allowlist, so `docker.io/onlyoffice/documentserver` is allowed without a policy exception.

### Nextcloud occ Configuration

The PostSync Job runs these commands after every ArgoCD sync (idempotent):

```bash
NC_POD=$(kubectl get pod -n nextcloud -l app.kubernetes.io/name=nextcloud \
  -o jsonpath='{.items[0].metadata.name}')

# Install/enable the bridge app
kubectl exec -n nextcloud "$NC_POD" -- php /var/www/html/occ app:install onlyoffice \
  || kubectl exec -n nextcloud "$NC_POD" -- php /var/www/html/occ app:enable onlyoffice

# Browser URL (Cloudflare Tunnel — what the user's browser reaches)
kubectl exec -n nextcloud "$NC_POD" -- \
  php /var/www/html/occ config:app:set onlyoffice DocumentServerUrl \
  --value="https://onlyoffice.devandre.sbs/"

# Internal URL (cluster DNS — what Nextcloud server uses for health checks)
kubectl exec -n nextcloud "$NC_POD" -- \
  php /var/www/html/occ config:app:set onlyoffice DocumentServerInternalUrl \
  --value="http://onlyoffice.nextcloud.svc.cluster.local/"

# Storage URL (OnlyOffice fetches/saves docs back to Nextcloud via this URL)
kubectl exec -n nextcloud "$NC_POD" -- \
  php /var/www/html/occ config:app:set onlyoffice StorageUrl \
  --value="https://cloud.devandre.sbs/"

# JWT (must match JWT_SECRET env var on the OnlyOffice pod)
kubectl exec -n nextcloud "$NC_POD" -- \
  php /var/www/html/occ config:app:set onlyoffice jwt_secret --value="$JWT_SECRET"
kubectl exec -n nextcloud "$NC_POD" -- \
  php /var/www/html/occ config:app:set onlyoffice jwt_header --value="AuthorizationJwt"

# Default to modern open formats
kubectl exec -n nextcloud "$NC_POD" -- \
  php /var/www/html/occ config:app:set onlyoffice defFormats \
  --value='{"docx":"1","xlsx":"1","pptx":"1","odt":"","ods":"","odp":""}'
```

### Cloudflare Tunnel Route

```bash
# Run on controller — registers onlyoffice.devandre.sbs in Cloudflare DNS:
~/.local/bin/cloudflared tunnel route dns minicloud onlyoffice.devandre.sbs

# Add to ~/.cloudflared/config.yml ingress rules:
- hostname: onlyoffice.devandre.sbs
  service: https://10.0.0.200
  originRequest:
    originServerName: onlyoffice.10.0.0.200.nip.io

# Restart cloudflared:
sudo systemctl restart cloudflared
```

The `originServerName` must match the TLS certificate on the NGINX Ingress (`onlyoffice.10.0.0.200.nip.io`) — without it, cloudflared cannot verify the backend TLS certificate and fails with a TLS SNI error.

---

## Gotchas

| Issue | Symptom | Fix |
|---|---|---|
| `grant_types: []` API default | Login fails with 400 | Set `grant_types: ["authorization_code", "refresh_token"]` explicitly |
| SSRF protection | Discovery fetch silently fails | `occ config:system:set allow_local_remote_servers --value=true` |
| `issuer_mode` change cached | OIDC discovery URL mismatch after provider edit | `occ cache:flush` and Redis FLUSHDB |
| Explicit consent required | Token not issued | Use `default-provider-authorization-explicit-consent` flow |
| Cloudflare Tunnel TLS SNI | `originServerName` must match nip.io cert | Set `originServerName: cloud.10.0.0.200.nip.io` in cloudflared config |
| ESO key not in secret | `onlyoffice` pod `CreateContainerConfigError` | `kubectl annotate externalsecret ... force-sync=$(date +%s) --overwrite` |
| `bitnami/kubectl:1.31` not found | Config Job `ImagePullBackOff` | Use `bitnami/kubectl:latest` — minor-only tags may not exist |
| OnlyOffice slow start | Readiness probe fails for 45-60s | `initialDelaySeconds: 60` on probes is required |
| JWT header conflict | OnlyOffice rejects requests with 401 | Use `JWT_HEADER: AuthorizationJwt` (not `Authorization`) to avoid collision with Nginx auth headers |

---

## Verify SSO

1. Navigate to `https://cloud.devandre.sbs`
2. Click **Login with Authentik**
3. Authentik consent screen appears → Accept
4. Redirected back to Nextcloud, logged in as Authentik user
5. User auto-provisioned in Nextcloud — no manual user creation needed

```bash
# Confirm user was provisioned
kubectl exec -n nextcloud deploy/nextcloud -- php occ user:list
```

---

## Operational Notes

```bash
# Nextcloud admin CLI (all occ commands run inside the pod)
kubectl exec -n nextcloud deploy/nextcloud -- php occ <command>

# List OIDC providers
kubectl exec -n nextcloud deploy/nextcloud -- php occ user_oidc:provider

# Flush all caches
kubectl exec -n nextcloud deploy/nextcloud -- php occ cache:flush

# Check Nextcloud background jobs
kubectl exec -n nextcloud deploy/nextcloud -- php occ background:cron

# Admin password
ssh controller "cat ~/.nextcloud-admin"
```

```bash
# Verify OnlyOffice health check
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://onlyoffice.10.0.0.200.nip.io/healthcheck

# Check OnlyOffice pod logs
kubectl --context minicloud logs -n nextcloud -l app.kubernetes.io/name=onlyoffice --tail=50

# Force re-run the config job (delete it — ArgoCD will recreate on next sync)
ssh controller "kubectl delete job onlyoffice-configure -n nextcloud --ignore-not-found"
```
