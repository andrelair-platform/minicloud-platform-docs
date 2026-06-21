---
id: phase25-public-access
title: Phase 25 — Public Access & SSO Migration
sidebar_position: 9
---

# Phase 25 — Public Access & SSO Migration to devandre.sbs

Phase 25 extends Phase 23's SSO to the public internet via Cloudflare Tunnel, making all platform apps reachable at real `*.devandre.sbs` URLs without Tailscale. It also hardens the controller with UFW and migrates OIDC issuers from nip.io to the public domain — the latter step is gated on DNS propagation.

---

## What Was Completed (2026-06-20 / 2026-06-21)

| Task | Status | Notes |
|---|---|---|
| Cloudflare Tunnel `minicloud` deployed | ✅ | Tunnel ID `bf5117ec-5986-47f0-a3ce-b96ab8854d21`; systemd on controller |
| `*.devandre.sbs` routes all apps to NGINX Ingress at `10.0.0.200` | ✅ | Config in `~/.cloudflared/config.yml` |
| All Ingresses updated with `devandre.sbs` host rules | ✅ | Each app has both `nip.io` and `devandre.sbs` hosts |
| Authentik redirect URIs extended to public URLs | ✅ | All 6 OIDC providers updated with `https://app.devandre.sbs/...` callback URIs |
| CoreDNS stub zone added (`devandre.sbs → 10.0.0.200`) | ✅ | Internal cluster traffic to `devandre.sbs` resolves locally, no Cloudflare round-trip |
| `cloudflared httpHostHeader` rewrite removed | ✅ | Apps resolve correctly without forced Host override |
| UFW host firewall installed on controller | ✅ | Blocks MAAS UI + Squid on public IPv6; Tailscale + cluster nodes unaffected |
| **`devandre.sbs` Cloudflare NS propagation** | 🔄 | Namecheap → Cloudflare NS change in progress; DNS still on `registrar-servers.com` |
| OIDC issuer URLs updated to `auth.devandre.sbs` | ⏳ | **Blocked on DNS propagation** |
| Authentik outpost `authentik_host` updated | ⏳ | **Blocked on DNS propagation** |

---

## Public URL Map

| App | Internal URL | Public URL |
|---|---|---|
| Homer | https://homer.10.0.0.200.nip.io | https://homer.devandre.sbs |
| ArgoCD | https://argocd.10.0.0.200.nip.io | https://argocd.devandre.sbs |
| Grafana | https://grafana.10.0.0.200.nip.io | https://grafana.devandre.sbs |
| Harbor | https://harbor.10.0.0.200.nip.io | https://harbor.devandre.sbs |
| Backstage | https://backstage.10.0.0.200.nip.io | https://backstage.devandre.sbs |
| Authentik | https://auth.10.0.0.200.nip.io | https://auth.devandre.sbs |
| Open WebUI | https://chat.10.0.0.200.nip.io | https://chat.devandre.sbs |
| platform-demo | https://platform-demo.10.0.0.200.nip.io | https://demo.devandre.sbs |
| NATS monitor | https://nats.10.0.0.200.nip.io | https://nats.devandre.sbs |
| ktayl-solution | https://ktayl.10.0.0.200.nip.io | https://ktayl.devandre.sbs |

Root `devandre.sbs` and `www` stay on Vercel (portfolio site, separate project).

---

## Architecture

```text
Browser (any network, no Tailscale needed)
        │
        ▼
Cloudflare edge (anycast, HTTPS terminated here)
        │  QUIC / H2 outbound tunnel
        ▼
cloudflared (systemd on controller, ktayl-ThinkPad-X390)
        │
        ▼
NGINX Ingress Controller (10.0.0.200:443)
  → TLS terminated (minicloud-ca cert, valid internally)
  → Routes by Host header to cluster services
```

The controller's `~/.cloudflared/config.yml` maps each `*.devandre.sbs` hostname to `https://10.0.0.200` with SNI matching the nip.io hostname. Cloudflare issues its own public TLS cert to the browser — users see a valid Cloudflare cert, never the internal CA.

---

## Controller UFW Firewall

UFW was installed and configured 2026-06-21. See [Host Firewall Hardening](host-hardening) for the full runbook.

**Effective rules:**

```
Default: deny (incoming), allow (outgoing)
22/tcp            ALLOW IN   Anywhere      ← emergency SSH recovery
tailscale0        ALLOW IN   Anywhere      ← all admin access via Tailscale
Anywhere          ALLOW IN   10.0.0.0/24   ← cluster nodes → MAAS/Squid
```

**What this blocks:** MAAS UI (port 5240) and Squid proxy (port 8000) were exposed on the controller's public IPv6. Now blocked. Cloudflare Tunnel and Tailscale are unaffected because cloudflared uses outbound-only connections and Tailscale operates on the `tailscale0` interface.

---

## Pending Steps — Run After DNS Propagates

**Trigger:** `dig +short NS devandre.sbs @1.1.1.1` returns `apollo.ns.cloudflare.com`.

Check propagation:
```bash
dig +short NS devandre.sbs @1.1.1.1
# Expected when ready: apollo.ns.cloudflare.com.
#                      nora.ns.cloudflare.com.
```

### Step 1 — Update Authentik outpost `authentik_host`

The embedded outpost (forward-auth for Homer, podinfo, platform-demo, whoami, NATS) needs to know the Authentik public URL for redirect flows:

```bash
# Authentik UI → Admin → Outposts → embedded-outpost → Edit
# Change: authentik_host = https://auth.10.0.0.200.nip.io
# To:     authentik_host = https://auth.devandre.sbs
```

Or via API:
```bash
AUTHENTIK_TOKEN=$(cat ~/.authentik-api-token)
OUTPOST_ID=$(curl -s https://auth.10.0.0.200.nip.io/api/v3/outposts/instances/ \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  | jq -r '.results[] | select(.name == "authentik Embedded Outpost") | .pk')

curl -s -X PATCH "https://auth.10.0.0.200.nip.io/api/v3/outposts/instances/${OUTPOST_ID}/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config": {"authentik_host": "https://auth.devandre.sbs"}}'
```

### Step 2 — Update OIDC issuer URLs in Helm values

Four apps have the OIDC issuer URL hardcoded in their Helm values on the controller. Update all four, then upgrade:

**ArgoCD** (`/home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/argocd-values.yaml`):
```yaml
# Change:
server.config.oidc.config: |
  issuer: https://auth.10.0.0.200.nip.io/application/o/argocd/
# To:
server.config.oidc.config: |
  issuer: https://auth.devandre.sbs/application/o/argocd/
```

**Grafana** (grafana-values.yaml):
```yaml
# Change:
auth.generic_oauth:
  auth_url: https://auth.10.0.0.200.nip.io/application/o/authorize/
  token_url: https://auth.10.0.0.200.nip.io/application/o/token/
  api_url: https://auth.10.0.0.200.nip.io/application/o/userinfo/
# To: replace all three with auth.devandre.sbs equivalent URLs
```

**Open WebUI** (open-webui-values.yaml):
```yaml
# Change all OAUTH_*_URL env vars from auth.10.0.0.200.nip.io to auth.devandre.sbs
```

**Backstage** (backstage-values.yaml):
```yaml
# Change under appConfig.auth.providers.oidc:
metadataUrl: https://auth.10.0.0.200.nip.io/application/o/backstage/.well-known/openid-configuration
# To: https://auth.devandre.sbs/application/o/backstage/.well-known/openid-configuration
```

**Apply all four:**
```bash
ssh controller "
  helm upgrade argocd argo/argo-cd -n argocd \
    --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/argocd-values.yaml --wait &
  helm upgrade grafana grafana/grafana -n monitoring \
    --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/grafana-values.yaml --wait &
  helm upgrade open-webui open-webui/open-webui -n ai \
    --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/open-webui-values.yaml --wait &
  helm upgrade backstage backstage/backstage -n backstage \
    --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/backstage-values.yaml --timeout 8m --wait &
  wait
"
```

### Step 3 — Smoke test

```bash
# From a browser (no Tailscale):
# 1. Open https://argocd.devandre.sbs → click "Log in via Authentik"
#    → redirects to auth.devandre.sbs → login → back to ArgoCD ✓
# 2. Open https://grafana.devandre.sbs → "Sign in with Authentik" ✓
# 3. Open https://chat.devandre.sbs → "Continue with Authentik" ✓
# 4. Open https://homer.devandre.sbs → should load immediately (forward-auth) ✓

# From Mac terminal (no Tailscale needed — public URL):
/usr/bin/curl -sI https://homer.devandre.sbs | head -5
# Expect: HTTP/2 200 or 302 (Authentik redirect if not logged in)

/usr/bin/curl -sI https://argocd.devandre.sbs | head -5
# Expect: HTTP/2 302 → location: https://auth.devandre.sbs/...
```

---

## Why the Order Matters

OIDC issuer URLs must **not** be changed before DNS propagates on client browsers. If `auth.devandre.sbs` doesn't resolve on a user's browser, the OIDC redirect loop fails silently — the browser gets a `NXDOMAIN` after Authentik redirects to the public URL. The nip.io URLs remain valid indefinitely (they resolve `10.0.0.200` directly from the IP in the hostname), so there is no urgency to switch before DNS is confirmed live.

Precedence rule: **internal users (Tailscale)** continue working on nip.io URLs until DNS is confirmed. Then switch. Both hostname sets remain on every Ingress permanently for redundancy.

---

## Cloudflare DNS Records (Reference)

Set in the Cloudflare dashboard for `devandre.sbs`. All set to **Proxied** (orange cloud):

| Name | Type | Value | Notes |
|---|---|---|---|
| `homer` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `argocd` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `grafana` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `harbor` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `backstage` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `auth` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `chat` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `demo` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `nats` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |
| `ktayl` | CNAME | `tunnel.devandre.sbs` | via Tunnel route |

Tunnel routes are managed via cloudflared:
```bash
ssh controller "~/.local/bin/cloudflared tunnel route dns minicloud <subdomain>.devandre.sbs"
```

---

## Operational Checks

```bash
# DNS propagation status
dig +short NS devandre.sbs @1.1.1.1
# Ready when: apollo.ns.cloudflare.com.

# Tunnel health
ssh controller "sudo systemctl status cloudflared"
ssh controller "~/.local/bin/cloudflared tunnel info minicloud"

# UFW status
ssh -t controller "sudo ufw status verbose"

# Verify public access (no Tailscale)
/usr/bin/curl -sI https://homer.devandre.sbs
/usr/bin/curl -sI https://argocd.devandre.sbs
```
