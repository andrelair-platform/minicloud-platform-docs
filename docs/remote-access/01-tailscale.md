---
id: tailscale
title: Tailscale VPN
sidebar_position: 2
---

# Tailscale — Full Remote Access via VPN

Tailscale creates a private mesh VPN between your machines using WireGuard under the hood. Every device gets a stable `100.x.x.x` IP that works from any network.

---

## How It Works

```text
Your Laptop (any WiFi)
100.x.x.10
      │
      │  WireGuard encrypted tunnel
      │  (peer-to-peer when possible, relayed otherwise)
      │
      ▼
MAAS Controller
100.x.x.1  ←──── stable Tailscale IP
10.0.0.1   ←──── local cluster IP
      │
      ▼
All cluster services become reachable via 100.x.x.1
```

No port forwarding. No public IP. Works through NAT and firewalls.

---

## Step 1 — Create a Tailscale Account

Go to [tailscale.com](https://tailscale.com) and sign up (free, up to 100 devices).

---

## Step 2 — Install Tailscale on the MAAS Controller

```bash
ssh ubuntu@10.0.0.1  # or however you access your controller

curl -fsSL https://tailscale.com/install.sh | sh

sudo tailscale up
```

A URL will appear — open it in your browser and authenticate with your Tailscale account.

After auth, note the Tailscale IP assigned to the controller:

```bash
tailscale ip -4
# Example: 100.72.14.33
```

---

## Step 3 — Install Tailscale on Your Remote Machine

**Linux:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

**macOS:**

Download from [tailscale.com/download](https://tailscale.com/download) or:
```bash
brew install tailscale
```

**Windows / iOS / Android:**

Available in respective app stores.

---

## Step 4 — Verify the Connection

From your remote machine:

```bash
ping 100.72.14.33   # use your controller's actual Tailscale IP
```

Then test cluster access:

```bash
# MAAS UI
curl -s -o /dev/null -w "%{http_code}" http://100.72.14.33:5240/MAAS
# → 200

# SSH into a node (through controller as jump host)
ssh -J ubuntu@100.72.14.33 ubuntu@10.0.0.2

# kubectl (copy kubeconfig first)
kubectl get nodes
```

---

## Step 5 — Configure kubectl for Remote Use

Copy kubeconfig from the control plane through the Tailscale tunnel:

```bash
scp -J ubuntu@100.72.14.33 ubuntu@10.0.0.2:/etc/rancher/k3s/k3s.yaml ~/.kube/config
```

Edit `~/.kube/config` — replace the server address:

```yaml
# Before:
server: https://127.0.0.1:6443

# After:
server: https://10.0.0.2:6443
```

Then add a route so your machine knows to reach `10.0.0.x` through Tailscale:

```bash
# On the MAAS controller — advertise the cluster subnet
sudo tailscale up --advertise-routes=10.0.0.0/24

# In the Tailscale admin console → approve the route for this device
```

After route approval, from your remote machine:

```bash
kubectl get nodes
# All 3 nodes visible — no VPN client config needed beyond tailscale up
```

---

## Services Accessible via Tailscale

Replace `100.72.14.33` with your actual controller Tailscale IP:

| Service | URL |
|---|---|
| MAAS UI | `http://100.72.14.33:5240/MAAS` |
| Homer Dashboard | `http://100.72.14.33:7902` |
| Grafana | `http://100.72.14.33:3000` |
| ArgoCD | `http://100.72.14.33:8080` |
| SSH (controller) | `ssh ubuntu@100.72.14.33` |
| SSH (nodes via jump) | `ssh -J ubuntu@100.72.14.33 ubuntu@10.0.0.2` |
| kubectl | works after subnet route approval |

---

## Tailscale Admin Console

Manage all your devices and routes at [login.tailscale.com/admin](https://login.tailscale.com/admin):

```text
✔ See all connected devices
✔ Approve subnet routes (10.0.0.0/24)
✔ Set ACLs (restrict which device can reach what)
✔ View last seen / connection status
```

---

## How Subnet Routing Works (Why 10.0.0.x Is Reachable Remotely)

`10.0.0.x` is a private IP — normally unreachable from any device outside the home network. With Tailscale subnet routing enabled, this changes completely.

When you ran `sudo tailscale up --advertise-routes=10.0.0.0/24` and approved the route in the admin console, Tailscale told every connected device: *"any traffic to 10.0.0.x, send it through the tunnel to the controller."*

```text
MacBook Air (any WiFi)
    │  wants 10.0.0.2:30902
    │
    ▼
Tailscale tunnel → 100.88.123.8 (MAAS controller)
    │  knows 10.0.0.2 is on its local cluster network
    │
    ▼
set-hog (10.0.0.2) → Homer pod on port 30902
```

This is why `http://10.0.0.2:30902` (Homer dashboard) opens in your browser from a MacBook on a completely different WiFi — the controller acts as a gateway into the cluster network through the encrypted tunnel.

Without Tailscale, that URL would time out. With it, the entire `10.0.0.0/24` subnet is transparently accessible from any Tailscale-connected device, anywhere in the world.

---

## Verified Access Points (Controller Tailscale IP: 100.88.123.8)

| What | URL / Command |
|---|---|
| MAAS UI | `http://100.88.123.8:5240/MAAS` |
| Homer dashboard | `http://10.0.0.2:30902` |
| SSH into controller | `ssh ktayl@100.88.123.8` |
| SSH into node (via jump) | `ssh -J ktayl@100.88.123.8 ubuntu@10.0.0.2` |
| Ping cluster nodes | `ping 10.0.0.2` / `10.0.0.4` / `10.0.0.7` |

---

## Done When

```text
✔ tailscale ip -4 returns a 100.x.x.x address on the controller
✔ ping 100.88.123.8 works from remote machine (0% packet loss)
✔ ping 10.0.0.2 works from remote machine (subnet routing confirmed)
✔ http://100.88.123.8:5240/MAAS opens in browser from remote machine
✔ http://10.0.0.2:30902 opens Homer dashboard from remote machine
✔ ssh ktayl@100.88.123.8 connects from remote machine
```
