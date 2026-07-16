# Mini Cloud Platform — Documentation

[![Live site](https://img.shields.io/badge/docs-live-blue)](https://andrelair-platform.github.io/minicloud-platform-docs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docusaurus](https://img.shields.io/badge/Docusaurus-3.10-green)](https://docusaurus.io)

> **Complete bare-metal enterprise infrastructure** — built from scratch with MAAS, k3s, ArgoCD, GitOps, a full data layer, and an enterprise security layer.

**Live site:** [https://andrelair-platform.github.io/minicloud-platform-docs/](https://andrelair-platform.github.io/minicloud-platform-docs/)

**Part of the [andrelair-platform](https://github.com/andrelair-platform) GitHub organization** — see also: [minicloud-ansible](https://github.com/andrelair-platform/minicloud-ansible) · [minicloud-opentofu](https://github.com/andrelair-platform/minicloud-opentofu) · [minicloud-gitops](https://github.com/andrelair-platform/minicloud-gitops) · [platform-demo](https://github.com/andrelair-platform/platform-demo)

---

## Table of Contents

- [What This Project Is](#what-this-project-is)
- [Documentation Structure](#documentation-structure)
- [Full Tech Stack](#full-tech-stack)
- [Running Locally](#running-locally)
- [Deployment](#deployment)
- [License](#license)

---

## What This Project Is

This is the full technical documentation for a private cloud platform built on bare-metal ThinkPad nodes, provisioned via MAAS (Metal as a Service) and running production-grade Kubernetes workloads. It covers the entire stack from physical hardware to AI/ML pipelines — equivalent to what you would build on AWS/Azure/GCP, but self-hosted.

| Node | IP | Role | Hardware |
|---|---|---|---|
| set-hog | 10.0.0.2 | Control Plane | ThinkPad T15 Gen 1 |
| fast-skunk | 10.0.0.4 | Worker | ThinkPad T490 |
| fast-heron | 10.0.0.7 | Worker | ThinkPad T490 |

---

## Documentation Structure

| Section | Topics Covered |
|---|---|
| **Phase 0 — MAAS** | Hardware setup, PXE boot, network config, cloud-init, provisioning |
| **Phase 1-2** | k3s cluster, kubectl local access |
| **Phase 3** | Remote access — Tailscale VPN, Cloudflare Tunnel, Homer dashboard |
| **Phase 4** | MetalLB bare-metal load balancer |
| **Phase 5** | Persistent storage — Longhorn (distributed) + NFS (shared) |
| **Phase 6** | NGINX Ingress Controller |
| **Phase 7** | Harbor private container registry + Trivy scanning |
| **Phase 8** | Monitoring — Prometheus + Grafana |
| **Phase 9** | First workload deployment |
| **Phase 10** | Ansible — infrastructure automation playbooks |
| **Phase 11** | IaC — Terraform/OpenTofu + Crossplane |
| **Phase 12** | GitOps — ArgoCD (auto-sync staging, manual production) |
| **Phase 13** | CI/CD — GitHub Actions golden path |
| **App Deployment Guide** | Helm charts, ArgoCD deploy, raw YAML, full CI/CD pipeline |
| **Data Layer** | Kafka/Redpanda, ClickHouse, dbt, Apache Superset, OpenMetadata |
| **Security Layer** | Authentik SSO, OPA/Gatekeeper, Falco, Cosign+SBOM, kube-bench |
| **Phase 14** | Backup & DR — Velero + etcd snapshots |
| **Phase 15** | Secrets — HashiCorp Vault |
| **Phase 16** | Automation — n8n, Temporal, Apache Airflow |
| **Phase 17** | Event-driven — KEDA + NATS JetStream |
| **Phase 18** | Developer platform — Backstage |
| **Phase 19** | AI/ML — Ollama, LiteLLM, Open WebUI, RAG pipeline |
| **Phase 20** | Reliability — Chaos Mesh |
| **Phase 21** | Advanced observability — Loki, Jaeger, Alertmanager |
| **Phase 22** | eBPF networking — Cilium + Hubble |

---

## Full Tech Stack

```
── INFRASTRUCTURE ──────────────────────────
MAAS          bare-metal provisioning
k3s           Kubernetes cluster
MetalLB       load balancer IPs
Longhorn      distributed block storage
Harbor        private container registry + OCI charts

── AUTOMATION & DELIVERY ───────────────────
Ansible       infrastructure automation
Terraform     infrastructure as code
Crossplane    Kubernetes-native IaC
ArgoCD        GitOps continuous delivery
GitHub Actions build → test → scan → package → deploy

── PLATFORM SERVICES ───────────────────────
Vault         secrets management
Velero        backup & disaster recovery
n8n           visual workflow automation
Temporal      durable workflow orchestration
Airflow       data pipeline scheduling
KEDA          event-driven autoscaling
NATS          high-performance message broker
Backstage     internal developer portal
Plane CE      project management (Plane CE)
Vaultwarden   self-hosted password manager

── OBSERVABILITY ───────────────────────────
Prometheus    metrics collection
Grafana       dashboards & alerting
Loki          log aggregation
Jaeger        distributed tracing
Chaos Mesh    chaos engineering

── DATA LAYER ──────────────────────────────
Redpanda      event streaming (Kafka-compatible, no JVM)
Debezium      change data capture (CDC) from Postgres
ClickHouse    columnar analytics warehouse
dbt           SQL transformation layer
Superset      self-hosted BI dashboards
OpenMetadata  data catalog, lineage & governance

── SECURITY LAYER ──────────────────────────
Authentik     SSO / OIDC identity provider for all tools
OPA/Gatekeeper admission control — policy as code
Falco         runtime threat detection via eBPF syscalls
Cosign        image signing + SBOM supply chain security
kube-bench    CIS Kubernetes compliance scoring

── NETWORKING ──────────────────────────────
Cilium        eBPF CNI + Hubble network observability
Tailscale     mesh VPN remote access
Cloudflare    tunnel-based browser access

── AI / ML ─────────────────────────────────
Ollama        local LLM serving (phi4-mini, deepseek-r1)
LiteLLM       AI gateway — 8 cloud + local providers
Open WebUI    chat interface with RAG + hybrid BM25/HNSW search
Langfuse      LLM observability, traces, evals, prompt versioning
MLflow        experiment tracking + model registry
```

---

## Running Locally

```bash
# Install dependencies
npm install

# Start dev server (hot reload)
npm start

# Build for production (fails on broken internal links)
npm run build

# Clear Docusaurus cache
npm run clear
```

---

## Deployment

The site deploys automatically to GitHub Pages on every push to `main` via GitHub Actions (`.github/workflows/deploy.yml`).

```
git push origin main
  → GitHub Actions: npm ci → npm run build → deploy to Pages
  → Live at https://andrelair-platform.github.io/minicloud-platform-docs/
```

No manual deploy step needed.

---

## License

[MIT](LICENSE) © andrelair-platform
