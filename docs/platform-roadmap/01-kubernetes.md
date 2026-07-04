---
id: phase-1-kubernetes
title: Phase 1 — Kubernetes (k3s)
sidebar_position: 2
---

# Phase 1 — Kubernetes Cluster (k3s)

The cluster is the foundation of the entire platform. Everything else runs on top of it.

---

## Node Roles

| Node | IP | Role |
|---|---|---|
| set-hog | 10.0.0.2 | Control Plane |
| fast-skunk | 10.0.0.4 | Worker |
| fast-heron | 10.0.0.7 | Worker |
| star-kitten | 10.0.0.8 | Worker |

---

## 1. Install Control Plane

```bash
ssh ubuntu@10.0.0.2

curl -sfL https://get.k3s.io | sh -
```

k3s installs a full Kubernetes control plane (API server, scheduler, controller manager, etcd).

---

## 2. Get Join Token

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

Copy this token — you'll need it for the workers.

---

## 3. Join Worker Nodes

On each worker:

```bash
# fast-skunk
ssh ubuntu@10.0.0.4

curl -sfL https://get.k3s.io | \
  K3S_URL=https://10.0.0.2:6443 \
  K3S_TOKEN=<TOKEN_FROM_STEP_2> \
  sh -
```

```bash
# fast-heron
ssh ubuntu@10.0.0.7

curl -sfL https://get.k3s.io | \
  K3S_URL=https://10.0.0.2:6443 \
  K3S_TOKEN=<TOKEN_FROM_STEP_2> \
  sh -
```

---

## 4. Verify Cluster

```bash
sudo kubectl get nodes
```

Expected output:
```text
NAME          STATUS   ROLES                  AGE
set-hog       Ready    control-plane,master   X
fast-skunk    Ready    <none>                 X
fast-heron    Ready    <none>                 X
star-kitten   Ready    <none>                 X
```

All 4 nodes must show **Ready**.

---

## Done When

```text
✔ 4 nodes in Ready state
✔ kubectl get nodes returns all 4
```
