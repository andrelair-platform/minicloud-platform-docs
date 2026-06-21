---
id: phase25-public-access
title: Phase 25 — Public Access & SSO Migration
sidebar_position: 9
---

# Phase 25 — Public Access & SSO Migration to devandre.sbs

Phase 25 extends Phase 23's SSO to the public internet via Cloudflare Tunnel, making all platform apps reachable at real `*.devandre.sbs` URLs without Tailscale. It also hardens the controller with UFW and migrates OIDC issuers from nip.io to the public domain.

**Phase status: ✅ Complete (2026-06-21)**

---

## What Was Completed

| Task | Status | Notes |
|---|---|---|
| Cloudflare Tunnel `minicloud` deployed | ✅ | Tunnel ID `bf5117ec-5986-47f0-a3ce-b96ab8854d21`; systemd on controller |
| `*.devandre.sbs` routes all apps to NGINX Ingress at `10.0.0.200` | ✅ | Config in `~/.cloudflared/config.yml`; `originServerName` per rule |
| All Ingresses updated with `devandre.sbs` host rules | ✅ | Each app has both `nip.io` and `devandre.sbs` hosts in `spec.rules` and `spec.tls` |
| Authentik redirect URIs extended to public URLs | ✅ | All 6 OIDC providers updated with `https://app.devandre.sbs/...` callback URIs |
| CoreDNS stub zone added (`devandre.sbs → 10.0.0.200`) | ✅ | Internal cluster traffic to `devandre.sbs` resolves locally, no Cloudflare round-trip |
| UFW host firewall installed on controller | ✅ | Blocks MAAS UI + Squid on public IPv6; Tailscale + cluster nodes unaffected |
| Authentik outpost `authentik_host` updated | ✅ | Changed from `auth.10.0.0.200.nip.io` to `auth.devandre.sbs` |
| Authentik forward-auth provider for `devandre.sbs` | ✅ | New provider pk=8 (`cookie_domain: devandre.sbs`) added to embedded outpost |
| OIDC issuer URLs updated to `auth.devandre.sbs` | ✅ | ArgoCD, Grafana, Open WebUI, Backstage helm values updated + upgraded |
| Smoke test 10/10 endpoints — all green | ✅ | All `*.devandre.sbs` return 200 or correct 302 to Authentik |

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
cloudflared (controller, ktayl-ThinkPad-X390)
        │  TLS SNI = <app>.10.0.0.200.nip.io (originServerName)
        │  Host header = <app>.devandre.sbs  (passthrough)
        ▼
NGINX Ingress Controller (10.0.0.200:443)
  → TLS selected by SNI (uses nip.io cert, noTLSVerify=true bypasses check)
  → Routes by Host header to cluster services
        │
        ▼
  forward-auth check → Authentik outpost (cookie_domain: devandre.sbs)
```

Cloudflare issues its own public TLS cert to the browser — users see a valid Cloudflare cert, never the internal CA.

---

## cloudflared Config (`~/.cloudflared/config.yml`)

Each rule sets `originServerName` to the corresponding nip.io hostname. This is required because the service URL is an IP (`https://10.0.0.200`); without it NGINX rejects the TLS handshake with "unrecognized name" since no SNI is sent for an IP address.

Harbor additionally needs `httpHostHeader` rewrite because Harbor's `externalURL` is still set to the nip.io hostname — it returns 404 for any other Host header.

```yaml
tunnel: bf5117ec-5986-47f0-a3ce-b96ab8854d21
credentials-file: /home/ktayl/.cloudflared/bf5117ec-5986-47f0-a3ce-b96ab8854d21.json

ingress:
  - hostname: homer.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: homer.10.0.0.200.nip.io

  - hostname: demo.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: platform-demo.10.0.0.200.nip.io

  - hostname: grafana.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: grafana.10.0.0.200.nip.io

  - hostname: argocd.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: argocd.10.0.0.200.nip.io

  - hostname: harbor.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: harbor.10.0.0.200.nip.io
      httpHostHeader: harbor.10.0.0.200.nip.io

  - hostname: backstage.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: backstage.10.0.0.200.nip.io

  - hostname: auth.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: auth.10.0.0.200.nip.io

  - hostname: chat.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: chat.10.0.0.200.nip.io

  - hostname: nats.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: nats.10.0.0.200.nip.io

  - hostname: ktayl.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      originServerName: ktayl.10.0.0.200.nip.io

  - service: http_status:404
```

**Cloudflared restart note:** The cloudflared service runs under systemd (`/etc/systemd/system/cloudflared.service`). After editing `config.yml`, restart via:

```bash
sudo systemctl restart cloudflared
```

The `ktayl` user requires a password for sudo. If unavailable, start manually with:

```bash
pkill -f 'cloudflared tunnel'
nohup ~/.local/bin/cloudflared tunnel --config ~/.cloudflared/config.yml run >> ~/.cloudflared/tunnel.log 2>&1 &
```

The systemd unit will restart it automatically on next controller reboot.

---

## Authentik Forward-Auth for devandre.sbs

Authentik's `forward_domain` mode uses `cookie_domain` to decide which incoming hostnames the outpost handles. The existing provider (pk=1) had `cookie_domain: 10.0.0.200.nip.io` — the outpost returned 404 for all `*.devandre.sbs` requests.

**Fix:** A second proxy provider was created via the Authentik API and added to the embedded outpost:

| Provider | pk | mode | cookie_domain | external_host |
|---|---|---|---|---|
| `minicloud-forward-auth` | 1 | forward_domain | `10.0.0.200.nip.io` | `https://auth.10.0.0.200.nip.io` |
| `minicloud-forward-auth-public` | 8 | forward_domain | `devandre.sbs` | `https://auth.devandre.sbs` |

Both are assigned to the `authentik Embedded Outpost` (`pk: 93d11dbf-e7fe-4604-afb1-7269980a5b47`). The outpost now handles forward-auth for both `*.10.0.0.200.nip.io` (internal Tailscale access) and `*.devandre.sbs` (public Cloudflare Tunnel access) simultaneously.

The app `minicloud-forward-auth-public` (slug: `minicloud-forward-auth-public`, pk: `1c6a0257-d290-429a-a72d-ea66cb907a7f`) is linked to provider pk=8.

To recreate if needed:

```bash
TOKEN=8faRrP7cbqx4N2qmAD48iFuZbNdtFDy2EiP9AaL2emoqJNEovzImPy9y7Xpj

# Create provider
curl -s -X POST 'https://auth.10.0.0.200.nip.io/api/v3/providers/proxy/' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --cacert /home/ktayl/minicloud-ca.crt \
  -d '{
    "name": "minicloud-forward-auth-public",
    "authorization_flow": "3cb61a3d-47ba-47ac-bf32-b270179bb735",
    "invalidation_flow": "2c1cd937-5a93-4e36-b9df-96839a9e3e05",
    "property_mappings": ["35c5c354-c9ce-4942-a919-43208923127f","06730f5f-cf59-4227-afe7-7fdf9dc113ba","d4967c11-acbe-4ae6-80c0-4b45c0fcf95b","677d145c-2abe-407e-9e5f-e425b65a8740","6e52eb60-9e8c-4684-be85-6cf79e894a01"],
    "mode": "forward_domain",
    "external_host": "https://auth.devandre.sbs",
    "cookie_domain": "devandre.sbs",
    "access_token_validity": "hours=24",
    "refresh_token_validity": "days=30",
    "intercept_header_auth": true,
    "redirect_uris": [
      {"matching_mode":"strict","url":"https://auth.devandre.sbs/outpost.goauthentik.io/callback?X-authentik-auth-callback=true","redirect_uri_type":"authorization"},
      {"matching_mode":"strict","url":"https://auth.devandre.sbs?X-authentik-auth-callback=true","redirect_uri_type":"authorization"}
    ]
  }'

# Add to outpost (replace 1 with new pk)
curl -s -X PATCH 'https://auth.10.0.0.200.nip.io/api/v3/outposts/instances/93d11dbf-e7fe-4604-afb1-7269980a5b47/' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --cacert /home/ktayl/minicloud-ca.crt \
  -d '{"providers": [1, 8]}'
```

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

## Smoke Test Results (2026-06-21)

Verified from Mac with Tailscale disabled (pure public internet):

```bash
for app in homer argocd grafana harbor backstage auth chat demo nats ktayl; do
  d="${app}.devandre.sbs"
  code=$(curl -sI "https://${d}" --max-time 10 | head -1 | awk '{print $2}')
  printf "%-35s %s\n" "${d}" "${code}"
done
```

Results:
```
homer.devandre.sbs                  302  ← Authentik forward-auth redirect
argocd.devandre.sbs                 200  ← ArgoCD login page
grafana.devandre.sbs                302  ← Authentik OIDC redirect
harbor.devandre.sbs                 200  ← Harbor login page
backstage.devandre.sbs              200  ← Backstage app
auth.devandre.sbs                   302  ← Authentik itself (→ login)
chat.devandre.sbs                   200  ← Open WebUI
demo.devandre.sbs                   302  ← Authentik forward-auth redirect
nats.devandre.sbs                   302  ← Authentik forward-auth redirect
ktayl.devandre.sbs                  200  ← ktayl-solution (no auth, public site)
```

10/10 ✅

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

---

## Operational Checks

```bash
# Tunnel health
ssh controller "~/.local/bin/cloudflared tunnel info minicloud"
ssh controller "tail -5 ~/.cloudflared/tunnel.log"

# UFW status
ssh -t controller "sudo ufw status verbose"

# Authentik outpost providers
curl -s https://auth.10.0.0.200.nip.io/api/v3/outposts/instances/93d11dbf-e7fe-4604-afb1-7269980a5b47/ \
  -H 'Authorization: Bearer 8faRrP7cbqx4N2qmAD48iFuZbNdtFDy2EiP9AaL2emoqJNEovzImPy9y7Xpj' \
  --cacert ~/minicloud-ca.crt | jq '.providers'
# Expected: [1, 8]

# Verify public access (no Tailscale)
for app in homer argocd grafana harbor backstage auth chat demo nats ktayl; do
  d="${app}.devandre.sbs"
  code=$(curl -sI "https://${d}" --max-time 10 | head -1 | awk '{print $2}')
  printf "%-35s %s\n" "${d}" "${code}"
done
```
