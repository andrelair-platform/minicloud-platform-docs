---
id: objective
title: Objective
sidebar_position: 1
---

# Objective

```text
Build a local bare-metal infrastructure using MAAS
→ Provision multiple machines automatically
→ Create an isolated network (10.0.0.0/24)
→ Prepare for Kubernetes cluster deployment
```

---

## Why Bare-Metal?

Bare-metal provisioning gives you full control over hardware resources — no hypervisor overhead, no shared tenancy. This setup mimics a real private cloud (AWS-style) but runs entirely on local hardware.

---

## Technology Stack

| Tool | Role |
|---|---|
| **MAAS** | Bare-metal provisioning (PXE, DHCP, DNS) |
| **Ubuntu 24.04 LTS** | OS deployed on all nodes |
| **Cloud-init** | Post-install node configuration |
| **k3s** | Lightweight Kubernetes (next phase) |
| **ArgoCD** | GitOps continuous deployment |
| **Prometheus + Grafana** | Monitoring and dashboards |
