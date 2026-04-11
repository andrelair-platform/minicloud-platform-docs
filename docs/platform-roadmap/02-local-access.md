---
id: phase-2-access
title: Phase 2 — kubectl Local Access
sidebar_position: 3
---

# Phase 2 — Developer Access (kubectl)

Configure your local machine to manage the cluster with `kubectl`.

---

## 1. Install kubectl

```bash
sudo apt install kubectl
```

Or via snap:

```bash
sudo snap install kubectl --classic
```

---

## 2. Copy kubeconfig from Control Plane

```bash
scp ubuntu@10.0.0.2:/etc/rancher/k3s/k3s.yaml ~/.kube/config
```

---

## 3. Edit the Server Address

Open `~/.kube/config` and replace the loopback address:

```yaml
# Change this:
server: https://127.0.0.1:6443

# To this:
server: https://10.0.0.2:6443
```

---

## 4. Verify Access

```bash
kubectl get nodes
```

You should see all 3 nodes from your local machine — no SSH required.

---

## Done When

```text
✔ kubectl get nodes works from local machine
✔ All 3 nodes visible and Ready
```
