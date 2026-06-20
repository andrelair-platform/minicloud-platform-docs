---
id: cloudflare-tunnel
title: Cloudflare Tunnel
sidebar_position: 3
---

:::info Deployed 2026-06-20
Tunnel `minicloud` is live on the controller. All platform apps are reachable at `*.devandre.sbs` without Tailscale.
:::

# Cloudflare Tunnel — Public HTTPS Access

Cloudflare Tunnel (`cloudflared`) runs on the MAAS controller as a systemd service and creates a secure outbound-only connection to Cloudflare's edge. All cluster apps are reachable at real HTTPS URLs from any browser — no client install, no public IP, no port forwarding.

---

## Architecture

```text
Browser (any network)
        │
        │  HTTPS → homer.devandre.sbs  (Cloudflare cert, valid everywhere)
        │
        ▼
   Cloudflare Edge  (TLS termination)
        │
        │  QUIC tunnel (outbound-only, initiated by controller)
        │
        ▼
   cloudflared  (systemd on ktayl-ThinkPad-X390)
        │
        │  HTTPS to 10.0.0.200 + Host header override
        │  noTLSVerify: true  (internal self-signed cert OK)
        │
        ▼
   NGINX Ingress (10.0.0.200)
        │  Routes on the nip.io hostname from httpHostHeader
        ▼
   App pod  (homer, backstage, grafana, etc.)
```

Key design: `httpHostHeader` rewrites the Host header from the public subdomain back to the internal `*.10.0.0.200.nip.io` hostname so NGINX matches existing Ingress rules without modification. No changes needed to any Ingress resource.

---

## Public URLs

| App | Public URL | Routes to internal host |
|---|---|---|
| Homer | https://homer.devandre.sbs | homer.10.0.0.200.nip.io |
| Backstage | https://backstage.devandre.sbs | backstage.10.0.0.200.nip.io |
| Grafana | https://grafana.devandre.sbs | grafana.10.0.0.200.nip.io |
| ArgoCD | https://argocd.devandre.sbs | argocd.10.0.0.200.nip.io |
| Harbor | https://harbor.devandre.sbs | harbor.10.0.0.200.nip.io |
| Authentik | https://auth.devandre.sbs | auth.10.0.0.200.nip.io |
| Open WebUI | https://chat.devandre.sbs | chat.10.0.0.200.nip.io |
| platform-demo | https://demo.devandre.sbs | platform-demo.10.0.0.200.nip.io |
| NATS monitor | https://nats.devandre.sbs | nats.10.0.0.200.nip.io |

Root `devandre.sbs` and `www` stay on Vercel (portfolio, unchanged).

**SSO caveat:** Apps using Authentik OIDC (Backstage, ArgoCD, Grafana) have redirect URIs configured for the `nip.io` hostnames. Accessing them via the `devandre.sbs` URLs will break the SSO redirect until the public redirect URIs are added in Authentik (Phase 25 follow-up).

---

## Deployed State

| Item | Value |
|---|---|
| Tunnel name | `minicloud` |
| Tunnel ID | `bf5117ec-5986-47f0-a3ce-b96ab8854d21` |
| Credentials | `/home/ktayl/.cloudflared/bf5117ec-5986-47f0-a3ce-b96ab8854d21.json` |
| Config | `/home/ktayl/.cloudflared/config.yml` |
| Systemd unit | `/etc/systemd/system/cloudflared.service` |
| Protocol | QUIC (fallback TCP/HTTP2) |
| PoPs at deploy | cdg08, bru01, bru03, cdg10 |
| Domain | `devandre.sbs` (Namecheap registrar → Cloudflare DNS) |
| NS | `apollo.ns.cloudflare.com` + `nora.ns.cloudflare.com` |

---

## Config file (`~/.cloudflared/config.yml`)

```yaml
tunnel: bf5117ec-5986-47f0-a3ce-b96ab8854d21
credentials-file: /home/ktayl/.cloudflared/bf5117ec-5986-47f0-a3ce-b96ab8854d21.json

ingress:
  - hostname: homer.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "homer.10.0.0.200.nip.io"

  - hostname: demo.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "platform-demo.10.0.0.200.nip.io"

  - hostname: grafana.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "grafana.10.0.0.200.nip.io"

  - hostname: argocd.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "argocd.10.0.0.200.nip.io"

  - hostname: harbor.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "harbor.10.0.0.200.nip.io"

  - hostname: backstage.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "backstage.10.0.0.200.nip.io"

  - hostname: auth.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "auth.10.0.0.200.nip.io"

  - hostname: chat.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "chat.10.0.0.200.nip.io"

  - hostname: nats.devandre.sbs
    service: https://10.0.0.200
    originRequest:
      noTLSVerify: true
      httpHostHeader: "nats.10.0.0.200.nip.io"

  - service: http_status:404
```

---

## Systemd unit (`/etc/systemd/system/cloudflared.service`)

```ini
[Unit]
Description=Cloudflare Tunnel (minicloud)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ktayl
ExecStart=/home/ktayl/.local/bin/cloudflared tunnel --config /home/ktayl/.cloudflared/config.yml run
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

---

## How to reproduce from scratch

```bash
# 1. Install binary (already at ~/.local/bin/cloudflared)
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared

# 2. Login (prints URL — open in browser, select devandre.sbs)
~/.local/bin/cloudflared tunnel login

# 3. Create tunnel
~/.local/bin/cloudflared tunnel create minicloud

# 4. Write config.yml (see above)

# 5. Create DNS CNAMEs
for sub in homer demo grafana argocd harbor backstage auth chat nats; do
  ~/.local/bin/cloudflared tunnel route dns minicloud ${sub}.devandre.sbs
done

# 6. Install systemd service (requires sudo)
sudo cp /tmp/cloudflared.service /etc/systemd/system/cloudflared.service
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 7. Verify
sudo systemctl status cloudflared
```

---

## Operational commands

```bash
# Status
sudo systemctl status cloudflared
tail -f ~/.cloudflared/tunnel.log

# Restart after config change
sudo systemctl restart cloudflared

# Add a new subdomain
~/.local/bin/cloudflared tunnel route dns minicloud newapp.devandre.sbs
# Then add the hostname block to config.yml and restart
```

---

## Limitations vs Tailscale

```text
✔ Works from any browser, no client needed
✔ Valid Cloudflare HTTPS cert (no CA trust required)
✔ All 9 apps publicly reachable
✗ kubectl does NOT work (not TCP-level)
✗ SSH does NOT work through the tunnel
✗ SSO apps need Authentik redirect URI update for devandre.sbs
```

Use Cloudflare Tunnel for **browser/UI access**, Tailscale for **full dev workflow** (kubectl, SSH, git).

---

## Done When

```text
✔ cloudflared systemd service running on controller (enabled, active)
✔ https://homer.devandre.sbs opens from any network without Tailscale
✔ TLS certificate valid (Cloudflare universal cert — green padlock)
✔ All 9 subdomains respond
✔ Service survives controller reboot
```
