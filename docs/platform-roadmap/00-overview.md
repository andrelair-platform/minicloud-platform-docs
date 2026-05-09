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
| 6 | Ingress controller (F5 NGINX) | ✅ Complete |
| 7 | Harbor + Trivy (private registry) | ✅ Complete |
| 8 | Monitoring stack (Prometheus + Grafana) | ✅ Complete |
| 9 | First workload (podinfo) | ✅ Complete |
| 10 | Ansible (post-MAAS bootstrap + Day-2 ops) | ✅ Complete |
| 11 | OpenTofu (IaC, MAAS provider) — Crossplane deferred | ✅ Complete |
| 12 | ArgoCD (GitOps, App-of-Apps) — Homer + whoami managed | ✅ Complete |
| 13 | CI/CD pipeline (GitHub Actions + ghcr.io + ArgoCD image promotion) — GitLab/Gitea deferred | ✅ Complete |
| 14 | Backup/DR (Velero → MinIO on controller + hourly k3s SQLite snapshot) — etcd-snapshot pivoted to SQLite | ✅ Complete |
| 15 | TLS / cert-manager (self-signed root CA + chained ClusterIssuer) — Vault + RBAC deferred | ✅ Complete |
| 16 | Harbor as Sovereign Registry (4 proxy-cache projects + mirror config). Original n8n/Temporal/Airflow plan deferred. | ✅ Complete |
| 17 | KEDA + NATS event-driven autoscaling (3-replica HA + JetStream + scale-to-zero verified) | ✅ Complete |
| 18 | Backstage minimal IDP (catalog-only, 5 Components + 1 System) — Vault/plugins/templates deferred | ✅ Complete |
| 19 | Self-hosted AI — Ollama (llama3.2:3b CPU inference, ~13 TPS) + Open WebUI chat at chat.10.0.0.200.nip.io. MLflow + Kubeflow deferred. | ✅ Complete |
| 20 | Chaos Mesh (reliability testing) | 🔜 Next |
| 12 | Container strategy | 🔜 |
| 13 | Ansible automation | 🔜 |
| 14 | Security hardening | 🔜 |
| 15 | Advanced observability | 🔜 |
