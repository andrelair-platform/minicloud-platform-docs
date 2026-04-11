---
id: remote-access-overview
title: Phase 3 — Remote Access
sidebar_position: 1
---

# Remote Access — Overview

Access your entire infrastructure from any machine connected to WiFi — no need to be on the same network as the MAAS controller.

---

## The Problem

All your services live on a private network (`10.0.0.x`):

```text
MAAS UI     → http://10.0.0.1:5240/MAAS
Grafana     → http://10.0.0.x:3000
ArgoCD      → http://10.0.0.x:8080
kubectl     → https://10.0.0.2:6443
SSH         → ubuntu@10.0.0.x
```

None of these are reachable from outside the local network. Without being physically connected to the MAAS switch, you are locked out.

---

## Solution Architecture

Two layers work together:

```text
Remote Machine (any WiFi)
        │
        │  Layer 1 — Secure Tunnel
        │  (Tailscale VPN  OR  Cloudflare Tunnel)
        │
        ▼
MAAS Controller (10.0.0.1)
        │
        │  Layer 2 — Web Dashboard
        │  Homer (running in k3s)
        │
        ▼
┌──────────────────────────────────┐
│   Mini Cloud Platform Dashboard  │
│  MAAS · Grafana · ArgoCD · ...   │
└──────────────────────────────────┘
```

---

## Options Comparison

| | Tailscale | Cloudflare Tunnel |
|---|---|---|
| Remote access method | VPN mesh | Browser URL |
| Client required | Yes (Tailscale app) | No — any browser |
| kubectl / SSH works | Yes (full network) | No (HTTP only) |
| Needs domain name | No | Yes |
| Needs public IP | No | No |
| Traffic route | Peer-to-peer | Via Cloudflare |
| Setup difficulty | Very easy | Easy |
| Cost | Free (up to 100 devices) | Free |
| Best for | Full dev workflow | Sharing UI with others |

---

## What You Will Have After Both

```text
From any device, anywhere:

Option A (Tailscale):
  http://100.x.x.x:7902       → Homer dashboard
  http://100.x.x.x:5240/MAAS  → MAAS UI
  kubectl get nodes            → works
  ssh ubuntu@100.x.x.x        → works

Option B (Cloudflare):
  https://dashboard.yourdomain.com  → Homer dashboard
  https://maas.yourdomain.com       → MAAS UI
  https://grafana.yourdomain.com    → Grafana
  https://argocd.yourdomain.com     → ArgoCD
```

---

## Recommended Setup

Run **both** in parallel:

```text
Tailscale  → your personal full-access dev workflow
Cloudflare → share specific UIs with teammates or access from locked-down devices
```
