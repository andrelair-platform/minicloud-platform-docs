---
id: roadmap-overview
title: Platform Roadmap
sidebar_position: 1
---

# Platform Roadmap — Complete Blueprint

From current bare-metal infra → full private cloud platform (production-grade).

---

## Final Target Architecture

```text
                ┌──────────────────────────────┐
                │        Developer             │
                │  kubectl / Git / CI/CD       │
                └─────────────┬────────────────┘
                              │
                     ┌────────▼────────┐
                     │   Git Platform  │
                     │ (GitLab/Gitea)  │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   GitOps Layer  │
                     │    ArgoCD       │
                     └────────┬────────┘
                              │
                ┌─────────────▼─────────────┐
                │     Kubernetes (k3s)      │
                │  set-hog   (CP)           │
                │  fast-skunk (worker)      │
                │  fast-heron (worker)      │
                └─────────────┬─────────────┘
                              │
        ┌─────────────────────▼───────────────────────┐
        │   Monitoring / Observability Stack          │
        │   Prometheus + Grafana + Loki               │
        └─────────────────────────────────────────────┘

        Infra Base:
        MAAS + 10.0.0.0/24 isolated network
```

---

## Final Stack

| Layer | Technology |
|---|---|
| Infra provisioning | MAAS |
| Cluster | k3s (Kubernetes) |
| Container runtime | containerd |
| GitOps | ArgoCD |
| CI/CD | GitLab / Gitea |
| Metrics | Prometheus |
| Dashboards | Grafana |
| Logs | Loki |
| Automation | Ansible |

---

## Phase Status

| Phase | Description | Status |
|---|---|---|
| 0 | MAAS + 3-node provisioning | ✅ Complete |
| 1 | Kubernetes (k3s) | ✅ Complete |
| 2 | kubectl local access | ✅ Complete |
| 3 | Remote access (Tailscale + Homer) | ✅ Complete |
| 4 | MetalLB load balancer | ✅ Complete |
| 5 | Persistent storage (Longhorn + NFS) | ✅ Complete |
| 6 | Ingress controller | 🔜 Next |
| 7 | Monitoring stack | 🔜 |
| 8 | First workload | 🔜 |
| 6 | ArgoCD (GitOps) | 🔜 |
| 7 | CI/CD platform | 🔜 |
| 8 | Container strategy | 🔜 |
| 9 | Ansible automation | 🔜 |
| 10 | Security hardening | 🔜 |
| 11 | Advanced observability | 🔜 |
