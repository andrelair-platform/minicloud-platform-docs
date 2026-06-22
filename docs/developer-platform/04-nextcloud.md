---
id: nextcloud
title: Phase 57 — Nextcloud + Authentik SSO
sidebar_position: 4
---

# Phase 57 — Nextcloud 33 + Authentik OIDC SSO

Deployed 2026-06-22. Nextcloud 33.0.5 on k3s with Authentik OIDC single sign-on — users log in with their Authentik account and are auto-provisioned in Nextcloud on first login.

---

## What Was Deployed

| Component | Version | Notes |
|---|---|---|
| Nextcloud | 33.0.5 | Helm chart via ArgoCD |
| user_oidc plugin | 8.10.1 | Bundled in the chart |
| PostgreSQL | Bitnami (Longhorn PVC) | Dedicated DB for Nextcloud |
| Redis | Bitnami | Session cache + file-locking |
| Authentik provider | pk=9 | OIDC, explicit-consent flow |

**URLs:**

| Access | URL |
|---|---|
| Internal (Tailscale) | `https://cloud.10.0.0.200.nip.io` |
| Public (Cloudflare Tunnel) | `https://cloud.devandre.sbs` |

Admin password: `ssh controller 'cat ~/.nextcloud-admin'`

---

## Architecture

```text
Browser → Cloudflare Tunnel → NGINX Ingress (10.0.0.200)
              → nextcloud pod (nextcloud namespace)
                    │
                    ├── PostgreSQL (PVC: longhorn)
                    ├── Redis (session + file-lock)
                    └── Authentik (OIDC) ← SSO login
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

## Gotchas

| Issue | Symptom | Fix |
|---|---|---|
| `grant_types: []` API default | Login fails with 400 | Set `grant_types: ["authorization_code", "refresh_token"]` explicitly |
| SSRF protection | Discovery fetch silently fails | `occ config:system:set allow_local_remote_servers --value=true` |
| `issuer_mode` change cached | OIDC discovery URL mismatch after provider edit | `occ cache:flush` and Redis FLUSHDB |
| Explicit consent required | Token not issued | Use `default-provider-authorization-explicit-consent` flow |
| Cloudflare Tunnel TLS SNI | `originServerName` must match nip.io cert | Set `originServerName: cloud.10.0.0.200.nip.io` in cloudflared config |

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

Future: OnlyOffice + MinIO integration tracked in platform-backlog #12.
