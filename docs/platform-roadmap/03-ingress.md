---
id: phase-3-ingress
title: Phase 6 — Ingress Controller
sidebar_position: 4
---

# Phase 3 — Ingress Controller

Expose services running in the cluster to the local network.

---

## Install NGINX Ingress Controller

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/baremetal/deploy.yaml
```

Use the **baremetal** provider — this is for bare-metal nodes without a cloud load balancer.

---

## Verify Installation

```bash
kubectl get pods -n ingress-nginx
```

Wait until the ingress controller pod shows `Running`.

---

## How It Works

```text
External request → NodePort (30000-32767)
                → Ingress Controller
                → Service
                → Pod
```

On bare-metal, you access apps via `http://10.0.0.2:<nodeport>` or with a local DNS entry pointing to a node IP.

---

## Done When

```text
✔ ingress-nginx pod Running
✔ Can reach services via node IP
```
