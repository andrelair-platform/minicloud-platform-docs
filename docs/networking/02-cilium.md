---
id: cilium
title: Phase 23 — Cilium
sidebar_position: 2
---

# Cilium — eBPF-Based Networking & Observability

Cilium replaces the default k3s CNI (Flannel) and kube-proxy with an eBPF-based data plane. It runs directly in the Linux kernel — faster, more observable, and capable of things traditional networking stacks cannot do.

---

## Why Cilium Over Default Flannel

| | Flannel + kube-proxy | Cilium |
|---|---|---|
| Data plane | iptables (user space) | eBPF (kernel) |
| Performance | Baseline | Up to 2x faster |
| Network policies | Basic | Rich L3/L4/L7 policies |
| mTLS between pods | No | Yes (built-in) |
| Traffic visibility | None | Hubble UI (full flow map) |
| Load balancing | kube-proxy | eBPF (replaces kube-proxy) |

---

## Hubble UI Preview

Cilium includes **Hubble** — a real-time network traffic visualizer showing which pod is talking to which, with latency and error rates:

```text
┌─────────────────────────────────────────────┐
│               Hubble UI                     │
│                                             │
│  [frontend] ──────→ [backend]               │
│      │                  │                   │
│      └──────→ [redis]   └──→ [postgres]     │
│                                             │
│  Flows: 1,243/s   Drops: 0   Errors: 0     │
└─────────────────────────────────────────────┘
```

---

## Install Cilium (replaces Flannel)

:::warning
This replaces the existing CNI. Do this on a fresh k3s install or be prepared to reinstall k3s.
:::

### Install k3s without default CNI

```bash
# On set-hog (control plane) — fresh install
curl -sfL https://get.k3s.io | sh -s - \
  --flannel-backend=none \
  --disable-network-policy \
  --disable=traefik
```

### Install Cilium CLI

```bash
curl -L --remote-name-all \
  https://github.com/cilium/cilium-cli/releases/latest/download/cilium-linux-amd64.tar.gz

sudo tar xzvfC cilium-linux-amd64.tar.gz /usr/local/bin
```

### Deploy Cilium

```bash
cilium install \
  --set k8sServiceHost=10.0.0.2 \
  --set k8sServicePort=6443 \
  --set kubeProxyReplacement=true \
  --set ipam.mode=kubernetes

cilium status --wait
```

---

## Enable Hubble (Observability)

```bash
cilium hubble enable --ui

# Port-forward the UI
cilium hubble ui
```

Opens `http://localhost:12000` — a live flow map of all traffic in the cluster.

---

## Enable Hubble CLI

```bash
export HUBBLE_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/hubble/master/stable.txt)
curl -L --remote-name-all \
  https://github.com/cilium/hubble/releases/download/$HUBBLE_VERSION/hubble-linux-amd64.tar.gz
sudo tar xzvfC hubble-linux-amd64.tar.gz /usr/local/bin

cilium hubble port-forward &
hubble observe --follow
```

Real-time stream of all network flows across the cluster.

---

## Network Policy Example (L7)

Cilium can enforce policies at HTTP level — not just IP/port:

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: allow-get-only
spec:
  endpointSelector:
    matchLabels:
      app: backend
  ingress:
    - fromEndpoints:
        - matchLabels:
            app: frontend
      toPorts:
        - ports:
            - port: "80"
              protocol: TCP
          rules:
            http:
              - method: GET
                path: "/api/.*"
```

This allows `frontend` to call `GET /api/*` on `backend` — and nothing else. iptables cannot do this.

---

## Done When

```text
✔ cilium status shows all green
✔ kubectl get pods -n kube-system shows cilium pods Running
✔ Hubble UI shows live traffic flows
✔ kube-proxy replaced (verify: no kube-proxy pods running)
```
