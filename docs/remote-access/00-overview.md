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

---

## Mac (or any external device) — full setup in three tiers

This is the practical "what do I install on my MacBook to actually use this platform" guide. Three tiers, each builds on the previous. **Stop after whichever tier you need** — most casual use only needs Tier 1.

> **Prerequisite for ALL tiers:** the MAAS controller (ThinkPad X390) must be powered on. It's the Tailscale tunnel endpoint, NAT gateway, MAAS provisioner, and SSH jump host. Nothing reachable until it boots. See the [main-controller boot sequence in CLAUDE.md](https://github.com/andrelair-platform/minicloud-platform-docs).

### Tier 1 — Browser access (~15 min, minimum viable)

Gets you Grafana, ArgoCD, Harbor, Backstage, podinfo, chat (Open WebUI), Homer, etc. — every workload reachable at `https://*.10.0.0.200.nip.io` from your Mac.

#### Step 1.1 — Install Tailscale on the Mac

```bash
# Open Terminal.app
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"   # if no brew yet
brew install --cask tailscale
```

Launch Tailscale from `/Applications/`. Menu-bar icon appears.

#### Step 1.2 — Sign in to your tailnet

Menu-bar icon → **Sign in** → **Google** → use the same email that owns the tailnet (the controller's account). Verify the controller is visible in the menu, listed at its tailnet IP (e.g. `100.88.123.8`).

```bash
ping -c 2 100.88.123.8       # controller — should reply
ping -c 2 10.0.0.2           # set-hog over the advertised subnet route — should reply
```

If both reply, network plumbing is done. **If only `100.88.123.8` works** but not `10.0.0.2`, the subnet route isn't accepted — Tailscale menu → toggle **Use this device's subnets** (or `sudo tailscale set --accept-routes` in Terminal).

#### Step 1.3 — Trust your self-signed CA (one-time, green padlocks)

Your platform's HTTPS certs are signed by your own root CA (Phase 15). Without trust, every dashboard shows "Not Secure". Fix it once:

```bash
# From the MacBook Air Terminal:
scp ktayl@100.88.123.8:/home/ktayl/minicloud-ca.crt ~/Downloads/minicloud-ca.crt
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/Downloads/minicloud-ca.crt
```

You'll get the macOS sudo prompt + Touch ID. Verify:

```bash
curl -I https://grafana.10.0.0.200.nip.io/
```

Expected: `HTTP/1.1 302 Found` (cert validated, redirect to login).

#### Step 1.4 — Bookmark the dashboards

| Service | URL | Login |
|---|---|---|
| **Homer** (landing — links to everything below) | `https://homer.10.0.0.200.nip.io` | none |
| ArgoCD | `https://argocd.10.0.0.200.nip.io` | `admin` / `cat ~/.argocd-admin` on controller |
| Grafana | `https://grafana.10.0.0.200.nip.io` | `admin` / `cat ~/.grafana-admin` |
| Harbor (registry) | `https://harbor.10.0.0.200.nip.io` | `admin` / `cat ~/.harbor-admin` |
| Backstage (catalog) | `https://backstage.10.0.0.200.nip.io` | guest |
| podinfo (demo) | `https://podinfo.10.0.0.200.nip.io` | none |
| platform-demo (CI/CD demo) | `https://platform-demo.10.0.0.200.nip.io` | none |
| whoami | `https://whoami.10.0.0.200.nip.io` | none |
| Open WebUI chat (Ollama) | `https://chat.10.0.0.200.nip.io` | first-signup-becomes-admin |
| NATS monitoring | `https://nats.10.0.0.200.nip.io` | none |
| **MAAS UI** | `http://100.88.123.8:5240/MAAS` | MAAS admin login |
| **MinIO console** | `http://100.88.123.8:9001` | `admin` / `cat ~/.minio-admin` (see [Velero/MinIO doc](../backup-dr/01-velero.md#4a-accessing-the-minio-console-from-outside-the-controller) for why the tailnet IP, not `10.0.0.1`) |

If Tier 1 is enough, **stop here**.

---

### Tier 2 — SSH access to controller + nodes (~10 min)

For shell-into-controller / shell-into-cluster-node workflows. Adds password-less SSH and a clean `~/.ssh/config` shortcut layer.

#### Step 2.1 — Generate an SSH key (if none yet)

```bash
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "your.email@example.com" -f ~/.ssh/id_ed25519 -N ""
```

#### Step 2.2 — Push to controller

```bash
ssh-copy-id ktayl@100.88.123.8
ssh ktayl@100.88.123.8 "hostname && uptime"     # should connect with no password
```

#### Step 2.3 — Shortcut config for the nodes

```bash
cat >> ~/.ssh/config <<'EOF'
Host controller
  HostName 100.88.123.8
  User ktayl

Host set-hog fast-skunk fast-heron
  User ubuntu
  ProxyJump controller

Host set-hog
  HostName 10.0.0.2
Host fast-skunk
  HostName 10.0.0.4
Host fast-heron
  HostName 10.0.0.7
EOF
chmod 600 ~/.ssh/config
```

Now `ssh controller`, `ssh set-hog`, `ssh fast-skunk`, `ssh fast-heron` all work. `ProxyJump` is the belt-and-suspenders fallback — the `10.0.0.x` IPs are usually directly reachable via the Tailscale subnet route, but ProxyJump keeps things working if that route ever drops.

---

### Tier 3 — Full kubectl + Helm from the Mac (~15 min)

So you can run `kubectl get pods -A`, `helm list`, etc. without SSH-ing in. Most senior platform-engineer workflows live here.

#### Step 3.1 — Install the CLI tools

```bash
brew install kubectl helm jq
```

#### Step 3.2 — Copy kubeconfig, rewrite the server URL

```bash
mkdir -p ~/.kube
ssh ktayl@100.88.123.8 "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed 's/127\.0\.0\.1/10.0.0.2/g' \
  > ~/.kube/config
chmod 600 ~/.kube/config
```

The `sed` rewrites `127.0.0.1` (meaningful only on the node itself) → `10.0.0.2` (set-hog's reachable IP over Tailscale).

#### Step 3.3 — Verify

```bash
kubectl get nodes
kubectl get pods -A | head -20
kubectl get applications -n argocd
```

Expected: 3 nodes Ready, hundreds of pods, 5 ArgoCD Applications Synced + Healthy.

#### Step 3.4 — Port-forward cluster-internal services

Some services are deliberately ClusterIP-only (Prometheus, Alertmanager, Longhorn UI, etc.). Reach them via port-forward:

```bash
kubectl port-forward svc/longhorn-frontend -n longhorn-system 9000:80
# Open http://localhost:9000 in the Mac browser
```

---

## Quick post-reboot health check from the Mac

Once everything is set up, this one-liner verifies the whole chain end-to-end. Run it any time you suspect drift after a power cycle.

```bash
ping -c 1 100.88.123.8 >/dev/null && echo "✅ tailscale" ; \
curl -sI https://homer.10.0.0.200.nip.io >/dev/null && echo "✅ TLS + ingress" ; \
kubectl get nodes 2>/dev/null | tail -3 && echo "✅ kubectl"
```

All three lines printing = fully wired in.

---

## Notes & gotchas

- **Tailscale must be on.** macOS occasionally disconnects after sleep — if `ping 100.88.123.8` fails, check the menu-bar icon first before debugging anything deeper.
- **The controller must be powered on.** It's the Tailscale exit + DHCP + DNS for the cluster. Nothing reachable until it boots.
- **No public internet exposure.** Everything is internal-only via Tailscale. To share a demo URL with a recruiter, you'd need a Tailscale Funnel or a public reverse proxy (a future Cloudflare Tunnel phase covers this).
- **Some URLs use `http://` not `https://`.** MinIO console and MAAS are HTTP-only on the controller — type the protocol explicitly in the URL bar; modern browsers will try to "upgrade" HTTP→HTTPS and the request will fail otherwise. Both are protected by the Tailscale auth boundary, so HTTP is acceptable here.
- **`*.10.0.0.200.nip.io` is wildcard DNS.** `nip.io` resolves any `*.<IP>.nip.io` hostname to the embedded IP. No DNS records to manage; works as long as the Mac can reach `10.0.0.200` (which it can, via the advertised subnet route).
