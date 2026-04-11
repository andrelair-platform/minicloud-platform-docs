---
id: cloudflare-tunnel
title: Cloudflare Tunnel
sidebar_position: 3
---

# Cloudflare Tunnel — Browser Access Without a VPN

Cloudflare Tunnel (`cloudflared`) runs on your MAAS controller and creates a secure outbound-only connection to Cloudflare's edge. Your services become reachable at real HTTPS URLs from any browser — no client install, no public IP, no port forwarding.

---

## How It Works

```text
Any Browser (any WiFi)
        │
        │  HTTPS → maas.yourdomain.com
        │
        ▼
   Cloudflare Edge
   (global CDN + TLS termination)
        │
        │  Encrypted tunnel (outbound only)
        │
        ▼
   cloudflared daemon
   (running on MAAS controller)
        │
        ▼
   Internal services (10.0.0.x)
```

The controller initiates the tunnel outbound — no inbound firewall rules needed.

---

## Prerequisites

- A domain name you own (e.g. `myinfra.dev`)
- A [Cloudflare account](https://cloudflare.com) (free)
- Domain added to Cloudflare (change nameservers — free)

---

## Step 1 — Add Your Domain to Cloudflare

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com)
2. Add site → enter your domain → select Free plan
3. Follow instructions to update nameservers at your registrar
4. Wait for propagation (~5 minutes)

---

## Step 2 — Install cloudflared on the MAAS Controller

```bash
ssh ubuntu@10.0.0.1

# Download and install
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
  -o cloudflared.deb

sudo dpkg -i cloudflared.deb
```

---

## Step 3 — Authenticate cloudflared

```bash
cloudflared tunnel login
```

A URL will print — open it in your browser, select your domain, authorize.

A certificate is saved to `~/.cloudflared/cert.pem`.

---

## Step 4 — Create the Tunnel

```bash
cloudflared tunnel create minicloud
```

Note the tunnel ID returned (e.g. `a1b2c3d4-...`). A credentials file is saved under `~/.cloudflared/`.

---

## Step 5 — Configure Routes

Create the config file:

```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

```yaml
tunnel: minicloud
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: dashboard.yourdomain.com
    service: http://localhost:7902        # Homer dashboard

  - hostname: maas.yourdomain.com
    service: http://localhost:5240

  - hostname: grafana.yourdomain.com
    service: http://localhost:3000

  - hostname: argocd.yourdomain.com
    service: http://localhost:8080

  - service: http_status:404             # catch-all (required)
```

Replace `yourdomain.com` with your actual domain.

---

## Step 6 — Create DNS Records

```bash
cloudflared tunnel route dns minicloud dashboard.yourdomain.com
cloudflared tunnel route dns minicloud maas.yourdomain.com
cloudflared tunnel route dns minicloud grafana.yourdomain.com
cloudflared tunnel route dns minicloud argocd.yourdomain.com
```

This creates CNAME records in Cloudflare DNS automatically.

---

## Step 7 — Run the Tunnel

Test manually first:

```bash
cloudflared tunnel run minicloud
```

Open `https://dashboard.yourdomain.com` in your browser from any network.

---

## Step 8 — Run as a System Service

So the tunnel starts automatically on boot:

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

Check status:

```bash
sudo systemctl status cloudflared
```

---

## Services Accessible via Cloudflare Tunnel

| Service | URL |
|---|---|
| Homer Dashboard | `https://dashboard.yourdomain.com` |
| MAAS UI | `https://maas.yourdomain.com` |
| Grafana | `https://grafana.yourdomain.com` |
| ArgoCD | `https://argocd.yourdomain.com` |

All URLs use **HTTPS with a valid TLS certificate** — provided automatically by Cloudflare.

---

## Optional — Add Access Control (Cloudflare Access)

Protect your UIs behind a login gate (Google, GitHub, email OTP) — free on Cloudflare:

```text
Cloudflare Dashboard
→ Zero Trust
→ Access → Applications
→ Add Application → Self-hosted
→ Set domain: maas.yourdomain.com
→ Add policy: require email = your@email.com
```

Now anyone hitting `maas.yourdomain.com` must authenticate before seeing the UI.

---

## Limitations vs Tailscale

```text
✔ Works from any browser, no client needed
✔ Valid HTTPS URLs, shareable
✗ kubectl does NOT work (not TCP-level)
✗ SSH does NOT work through the tunnel
✗ Requires a domain name
```

Use Cloudflare Tunnel for **UI access**, Tailscale for **full dev workflow**.

---

## Done When

```text
✔ cloudflared service running on controller
✔ https://dashboard.yourdomain.com opens from remote browser
✔ TLS certificate valid (green padlock)
✔ All service subdomains reachable
```
