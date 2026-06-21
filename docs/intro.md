---
id: intro
title: Mini Cloud Platform
sidebar_position: 1
slug: /
---

# Mini Cloud Platform — Bare-Metal Infrastructure

> **Private datacenter-equivalent infrastructure** — built from scratch with MAAS, k3s, ArgoCD, and GitOps.

---

## What This Project Is

This documentation covers a complete bare-metal infrastructure built locally using **MAAS (Metal as a Service)**, provisioning a 3-node cluster ready for Kubernetes and production workloads.

```text
Equivalent to: AWS EC2 + VPC + Auto Provisioning — but local.
```

---

## Infrastructure at a Glance

| Node | IP | Role | Hardware |
|---|---|---|---|
| set-hog | 10.0.0.2 | Control Plane | ThinkPad T15 Gen 1 |
| fast-skunk | 10.0.0.4 | Worker | ThinkPad T490 |
| fast-heron | 10.0.0.7 | Worker | ThinkPad T490 |

**MAAS Controller:** Ubuntu + dual NIC (WiFi → internet, Ethernet → 10.0.0.1)

---

## Complete Roadmap

Each phase builds directly on the previous one — nothing requires something that hasn't been set up yet.

| Phase | Topic | Key Technology | Status |
|---|---|---|---|
| **0** | MAAS + 3-node provisioning | MAAS, PXE, cloud-init | ✅ Done |
| **1** | Kubernetes cluster | k3s | ✅ Done |
| **2** | kubectl local access | kubeconfig | ✅ Done |
| **3** | Remote access from anywhere | Tailscale, Cloudflare Tunnel, Homer | ✅ Done |
| **4** | Load balancer IPs on bare-metal | MetalLB | ✅ Done |
| **5** | Persistent storage | Longhorn, NFS | ✅ Done |
| **6** | Expose apps to the network | F5 NGINX Ingress | ✅ Done |
| **7** | Private container registry | Harbor + Trivy | ✅ Done |
| **8** | Cluster monitoring | Prometheus, Grafana | ✅ Done |
| **9** | First real workload | podinfo, HPA, ServiceMonitor | ✅ Done |
| **10** | Infrastructure automation | Ansible | ✅ Done |
| **11** | Infrastructure as Code | OpenTofu (MAAS) — Crossplane deferred | ✅ Done |
| **12** | GitOps deployment | ArgoCD (App-of-Apps) | ✅ Done |
| **13** | CI/CD pipelines | GitHub Actions + ghcr.io + ArgoCD image promotion | ✅ Done |
| **14** | Backup & disaster recovery | Velero + MinIO on controller + hourly k3s SQLite pull | ✅ Done |
| **15** | TLS / cert-manager (internal PKI) — Vault + RBAC deferred | cert-manager, self-signed root CA | ✅ Done |
| **16** | Harbor as Sovereign Registry — 4 proxy-cache projects, mirror+fallback, supply-chain control point. Original n8n/Temporal/Airflow plan deferred. | Harbor proxy cache | ✅ Done |
| **17** | Event-driven autoscaling — KEDA + NATS JetStream HA, scale-to-zero verified end-to-end | KEDA, NATS | ✅ Done |
| **18** | Backstage minimal IDP — catalog-only, off-the-shelf image, Vault/plugins/templates deferred | Backstage | ✅ Done |
| **19** | Self-hosted AI — Ollama (CPU, llama3.2:3b, ~13 TPS) + Open WebUI chat. MLflow + Kubeflow deferred. | Ollama, Open WebUI | ✅ Done |
| **20** | Reliability & chaos engineering — 3 validation experiments on podinfo: PodChaos (0 ms downtime under 5 pod kills), NetworkChaos (200 ms latency injection + clean recovery), StressChaos (contained cgroup OOM, 0 node-mate restarts). NodeChaos / dashboard Ingress / automated GameDays deferred. | Chaos Mesh | ✅ Done |
| **21** | Logs (Loki single-binary, Promtail DaemonSet, Grafana datasource) + Alertmanager 3-tier routing tree + in-cluster webhook receiver + custom `PodinfoAvailabilityLost` rule. End-to-end alert validated via Chaos Mesh kill-both-replicas → webhook receives FIRING JSON. **Jaeger / distributed tracing deferred** — no multi-service topology to trace. | Loki, Promtail, Alertmanager | ✅ Done |
| **22** | eBPF networking — **migration runbook authored, execution deferred to fresh-cluster rebuild**. cilium CLI installed on controller; dry-run helm values captured. Senior scope-reduction call: 111 live pods + 22 phases of validated infrastructure on top of Flannel make hot CNI swap not worth it at our cluster scale. | Cilium, Hubble | ✅ Done |
| **23** | Enterprise SSO — Authentik as IdP; 11/13 apps on SSO. 5 via native OIDC (ArgoCD, Grafana, Harbor, MinIO, Open WebUI), 5 via forward-auth Outpost (Homer, podinfo, platform-demo, whoami, NATS). Backstage + MAAS deferred. | Authentik, OIDC, forward-auth | ✅ Done |
| **24** | Backstage custom image — org-owned build (bcec03f); Authentik OIDC SSO; Kubernetes, ArgoCD, TechDocs, Grafana plugins; published to Harbor. | Backstage, crane, Harbor, Authentik | ✅ Done |
| **25** | Public access via Cloudflare Tunnel — `*.devandre.sbs` live on Cloudflare edge (no Tailscale needed). Authentik redirect URIs extended to public URLs. CoreDNS stub zone added. UFW host firewall on controller. **Pending:** OIDC issuer URL switch to `auth.devandre.sbs` once DNS propagates from Namecheap → Cloudflare NS. | Cloudflare Tunnel, cloudflared, UFW, CoreDNS | 🔄 In progress |
| **—** | **Data Layer** | Kafka/Redpanda, ClickHouse, dbt, Superset, OpenMetadata | 🔜 |
| **—** | **Security Layer** | OPA/Gatekeeper, Falco, Cosign+SBOM, kube-bench | 🔜 |

---

## Final Stack (When Complete)

```text
── INFRASTRUCTURE ──────────────────────────────────────────────────
MAAS          → bare-metal provisioning
k3s           → Kubernetes cluster
MetalLB       → load balancer IPs
Longhorn      → distributed storage
Harbor        → private container registry

── AUTOMATION & DELIVERY ───────────────────────────────────────────
Ansible       → infrastructure automation
Terraform     → infrastructure as code
Crossplane    → Kubernetes-native IaC
ArgoCD        → GitOps
GitHub Actions→ CI/CD

── PLATFORM SERVICES ───────────────────────────────────────────────
Velero        → backup & disaster recovery
Vault         → secrets management
n8n           → visual workflow automation
Temporal      → code-based workflow orchestration
Airflow       → data pipeline scheduling
KEDA          → event-driven autoscaling
NATS          → message broker
Backstage     → developer portal

── OBSERVABILITY ───────────────────────────────────────────────────
Prometheus    → metrics
Grafana       → dashboards
Loki          → logs
Jaeger        → traces
Chaos Mesh    → reliability testing
Cilium        → eBPF networking + Hubble
Tailscale     → remote access VPN

── DATA LAYER ──────────────────────────────────────────────────────
Redpanda      → event streaming (Kafka-compatible)
Debezium      → change data capture (CDC)
ClickHouse    → columnar analytics warehouse
dbt           → SQL transformation layer
Superset      → self-hosted BI dashboards
OpenMetadata  → data catalog, lineage, governance

── SECURITY LAYER ──────────────────────────────────────────────────
Authentik     → SSO / OIDC identity provider (self-hosted)
OPA/Gatekeeper→ admission control (policy as code)
Falco         → runtime threat detection (eBPF)
Cosign        → image signing + SBOM supply chain
kube-bench    → CIS compliance scoring
UFW           → host firewall on controller

── AI / ML ─────────────────────────────────────────────────────────
Ollama        → local LLMs (Mistral, LLaMA 3)
MLflow        → ML experiment tracking
Kubeflow      → ML pipelines + distributed training
```

---

## CV / LinkedIn Summary

- Designed and deployed a 3-node bare-metal infrastructure using MAAS
- Implemented PXE-based automated OS provisioning via network boot (PXE)
- Built isolated cluster network (10.0.0.0/24) with DHCP/DNS management
- Resolved complex networking issues (IPv6 conflicts, DHCP overlap, alias interfaces)
- Deployed full Kubernetes platform: k3s, ArgoCD, Prometheus, Harbor, Vault
- Built private AI platform with local LLM serving (Ollama) and ML pipelines (Kubeflow)
- Implemented remote access via Tailscale VPN and Cloudflare Tunnel (`*.devandre.sbs` on Cloudflare edge)
- Hardened controller with UFW host firewall (blocked MAAS + Squid public IPv6 exposure)
- Applied chaos engineering with Chaos Mesh to validate cluster resilience
- Deployed enterprise SSO via Authentik: OIDC for 5 apps, forward-auth for 5 apps, MFA enforced, one-toggle user deprovisioning across all services
- Implemented GHAS: CodeQL SAST, Dependabot SCA, Secret Scanning + Push Protection across all org repos
