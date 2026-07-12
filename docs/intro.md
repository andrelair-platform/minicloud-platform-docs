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

This documentation covers a complete bare-metal infrastructure built locally using **MAAS (Metal as a Service)**, provisioning a 5-node cluster ready for Kubernetes and production workloads.

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
| star-kitten | 10.0.0.8 | Worker | ThinkPad T490 |
| swift-mac | 10.0.0.10 | Worker | MacBook Pro 13" 2012 |

**MAAS Controller:** Ubuntu + dual NIC (WiFi → internet, Ethernet → 10.0.0.1)

---

## Complete Roadmap

Each phase builds directly on the previous one — nothing requires something that hasn't been set up yet.

| Phase | Topic | Key Technology | Status |
|---|---|---|---|
| **0** | MAAS + bare-metal provisioning (4× ThinkPad via PXE + 1× MacBook Pro via USB) | MAAS, PXE, cloud-init | ✅ Done |
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
| **25** | Public access via Cloudflare Tunnel — `*.devandre.sbs` live (10/10 apps, no Tailscale). Authentik OIDC issuers migrated to `auth.devandre.sbs`. Forward-auth extended to `devandre.sbs` cookie domain. `originServerName` per cloudflared rule to fix TLS SNI on IP origin. UFW host firewall on controller. All smoke tests green. | Cloudflare Tunnel, cloudflared, Authentik forward-auth, UFW | ✅ Done |
| **26** | Secrets management — Vault 2.0.2 with Raft on Longhorn. KV v2 (5 platform credentials + demo secret). Kubernetes auth backend. Agent Injector verified on platform-demo (2/2 pods, /vault/secrets/config injected). ArgoCD proxy fix (MAAS Squid) as bonus fix. | HashiCorp Vault, Raft, Vault Agent Injector | ✅ Done |
| **27** | Policy as code — OPA/Gatekeeper 3.22.2 admission controller. 3 enforced policies: block `:latest` tags, no privileged containers, require resource limits. Audit cycle confirmed 0 violations across all platform namespaces. All 3 rejection demos verified live. | OPA, Gatekeeper, Rego | ✅ Done |
| **28** | Runtime threat detection — Falco 0.44.1 DaemonSet (3/3 nodes) via modern_ebpf driver (BPF CO-RE, kernel 6.8, no headers). 2 live detections: `Contact K8S API Server From Container` (Vault pod, MITRE T1565) + `Read sensitive file untrusted` (cat /etc/shadow). Two install gotchas: Squid proxy for falcoctl + inotify exhaustion on control-plane. | Falco, eBPF, BPF CO-RE | ✅ Done |
| **29** | CIS Kubernetes Benchmark — kube-bench v0.9.4 scored against k3s-cis-1.8. Control-plane: 49 PASS / 6 FAIL / 55 WARN. All 6 FAILs are k3s false positives (kube-bench scans kubelet CLI args; k3s configures these through config file + auto-provisioned certs). Verified: anonymous-auth disabled (401), read-only-port closed. Gatekeeper + Vault already satisfy 4 of the WARN items. | kube-bench, CIS Benchmark | ✅ Done |
| **30** | Supply chain security — Cosign keyless signing (GitHub OIDC → Sigstore Fulcio CA, no key management) + syft CycloneDX SBOM generation integrated into platform-demo GHA CI. Signatures and SBOM attached as OCI referrers on ghcr.io. Gatekeeper `K8sAllowedRegistries` policy (warn): 116 violations audited across Helm workloads; platform-demo compliant (Harbor proxy prefix). Full chain: GHAS → Cosign/SBOM → Harbor Trivy → Gatekeeper → Falco. | Cosign, syft, Sigstore, OCI referrers | ✅ Done |
| **56** | Multi-environment namespaces — namespace-based isolation (`{team}-{env}` convention) for `insurance` and `collab` teams across dev/staging/prod. ArgoCD ApplicationSet matrix generator creates 6 apps automatically. Per-env ResourceQuota (dev: 500m/1Gi, staging: 1/2Gi, prod: none) + LimitRange defaults. 15 Cloudflare Tunnel routes for env-prefixed public subdomains. CI pipeline yq bug fixed (Deployment-only targeting) + Harbor push via crane. | ArgoCD ApplicationSet, Kustomize, ResourceQuota, LimitRange | ✅ Done |
| **57** | Nextcloud 33 + Authentik OIDC — on-cluster document collaboration; `user_oidc` 8.10.1 auto-provisions users from Authentik; available at `cloud.devandre.sbs`. | Nextcloud, user_oidc, Authentik | ✅ Done |
| **58** | Vault GitOps migration + CoreDNS completions — Vault adopted into ArgoCD app-of-apps (multi-source Helm); all 12 `*.devandre.sbs` hostnames resolve in-cluster via CoreDNS `coredns-custom` ConfigMap. | ArgoCD multi-source, CoreDNS | ✅ Done |
| **59** | External Secrets Operator + Vault KV — ESO 0.10.7, ClusterSecretStore `vault-backend` (Kubernetes auth), 9 ExternalSecrets (all platform credentials pulled from Vault KV v2 into cluster Secrets). | ESO, Vault KV v2 | ✅ Done |
| **60** | Cert observability — `cert-manager` ServiceMonitor scraped by Prometheus, Grafana dashboard 20842, 3 PrometheusRule alerts (expiring within 14 d warning, 3 d critical, not-ready). | cert-manager, Prometheus, Grafana | ✅ Done |
| **62** | IAM hardening — k3s OIDC flags on API server, kubelogin installed (int128/kubelogin), `minicloud-oidc` kubeconfig for daily use, ClusterRoleBindings per Authentik group (Direction IT → cluster-admin, Cybersécurité/Audit → view), anonymous-auth disabled. | kubelogin, OIDC, RBAC | ✅ Done |
| **63** | Cluster hardening — SSH hardened on all 4 nodes (`PasswordAuthentication no`, `PermitRootLogin no`), UFW default-deny on all nodes, k3s audit policy + AES-CBC-256 secrets encryption at rest, k3s upgraded to v1.36.1. | UFW, k3s audit, encryption-at-rest | ✅ Done |
| **64** | Namespace isolation — default-deny NetworkPolicy ingress on all 23 platform namespaces, ResourceQuota + LimitRange on 8 namespaces, flannel VTEP fix (`10.42.0.0/24` in webhook allowlists). | NetworkPolicy, ResourceQuota, flannel | ✅ Done |
| **65** | Vault auto-unseal via AWS KMS — KMS key `vault-auto-unseal` (eu-west-1), IAM user `vault-kms-unseal` scoped to `kms:Encrypt/Decrypt/DescribeKey`, seal migration verified (delete pod → 1/1 Ready in ~30 s, zero human input). | Vault, AWS KMS | ✅ Done |
| **66** | Ollama local-path migration — both Ollama instances (fast-heron + star-kitten) pinned via `nodeSelector`, PVCs migrated Longhorn → local-path NVMe (model weights are re-downloadable). 4 models: phi3-financial, phi3.5, llama3.2:3b, llama3.2:1b. | Ollama, local-path, nodeSelector | ✅ Done |
| **67** | Pod security hardening — PSA `warn:restricted` on all 23 namespaces, `enforce:restricted` on homer/podinfo/collab/insurance, 9 Gatekeeper admission policies in **deny** mode with **0 violations** (no-root, no-privileged, approved-registry, resource-limits, TLS-only ingress, no-LB-in-dev, no-hostPath, no-latest-tag, no-privilege-escalation). | PSA, Gatekeeper, Rego | ✅ Done |
| **AI Gateway** | Enterprise LLM gateway — LiteLLM 1.90.3 proxy with 7 cloud providers (Groq, OpenAI, Gemini, DeepSeek, Mistral, Anthropic Claude, HuggingFace featherless-ai) + 2 local Ollama nodes. Cloud fallback chain (Ollama → Groq → DeepSeek). **Circuit breaker** (3 failures → 60 s cooldown). **3-tier dept key governance** — 15 virtual keys with $5/$30/$100 monthly budget caps and 50k/100k/200k TPM limits. Valkey exact-match prompt cache (10 min TTL). Presidio PII/DLP pre-call guardrail. detect_secrets credential scanner. Langfuse tracing on every call. **Grafana cost dashboard** (8 SQL panels against LiteLLM PostgreSQL). | LiteLLM, Ollama, Valkey, Presidio, Langfuse | ✅ Done |
| **LLM Observability** | Langfuse 3.201.1 — traces every LiteLLM call with token counts, cost, model, department metadata, and latency. ClickHouse columnar store + Valkey + PostgreSQL + MinIO (S3 blobs). Authentik OIDC SSO; pre-provisioned org `minicloud-platform` + project `ai-gateway` via init env vars. | Langfuse, ClickHouse, Valkey | ✅ Done |
| **Security gaps** | Full security hardening — supply chain (Cosign + SBOM on both CIs, Dependabot on 4 repos, GPG-signed commits + branch protection on main), ingress & edge (HSTS globally, rate limiting, Authentik forward-auth on Prometheus/Alertmanager/Polaris), ArgoCD hardening (admin disabled, AppProject with explicit source/destination/resource whitelist). Regression check #19: **42 PASS / 0 FAIL / 0 WARN**. | Cosign, GPG, AppProject, NGINX | ✅ Done |
| **Observability gaps** | Full observability — Falco Sidekick → Alertmanager pipeline (failed logins, new cluster-admin, privileged pod alerts), Polaris workload quality scorer at `polaris.10.0.0.200.nip.io`, DB backup scripts (pg_dump → MinIO nightly), Vault raft snapshots (nightly), backup DR PrometheusRules (VeleroBackupFailed, MinioDiskFull), DR runbook (7 scenarios). | Falco Sidekick, Polaris, Alertmanager | ✅ Done |
| **—** | **Data Layer** | Kafka/Redpanda, ClickHouse, dbt, Superset, OpenMetadata | 🔜 |

---

## Current Stack (Live)

```text
── INFRASTRUCTURE ──────────────────────────────────────────────────
MAAS          → bare-metal provisioning (4 ThinkPads, PXE)
k3s v1.36.1   → Kubernetes cluster (1 control-plane + 3 workers)
MetalLB       → load balancer IPs (10.0.0.200)
Longhorn       → distributed block storage
local-path     → NVMe-backed storage (Ollama model weights)
Harbor        → private container registry (Trivy scanning)

── AUTOMATION & DELIVERY ───────────────────────────────────────────
Ansible       → infrastructure automation
OpenTofu      → IaC for MAAS resources
ArgoCD        → GitOps app-of-apps (AppProject with explicit whitelist)
GitHub Actions→ CI/CD (cosign-signed, GPG-signed bump commits)
ESO           → External Secrets Operator (9 ExternalSecrets ← Vault)

── PLATFORM SERVICES ───────────────────────────────────────────────
Velero + MinIO → backup & disaster recovery (daily + k3s snapshots)
Vault         → secrets management (AWS KMS auto-unseal, Raft)
KEDA          → event-driven autoscaling (NATS JetStream)
NATS          → message broker (JetStream HA)
Backstage     → developer portal (Authentik OIDC, Kubernetes + ArgoCD + Grafana plugins)
Nextcloud     → on-cluster collaboration (Authentik SSO)

── OBSERVABILITY ───────────────────────────────────────────────────
Prometheus    → metrics (kube-prometheus-stack)
Grafana       → dashboards (LiteLLM cost dashboard, cert expiry, backup DR)
Loki + Promtail → logs
Alertmanager  → 3-tier alert routing + Falco Sidekick webhook
Chaos Mesh    → reliability testing
Falco         → runtime threat detection (eBPF, modern_ebpf driver)
Falco Sidekick→ Falco → Alertmanager pipeline
Polaris       → workload quality scorer
Langfuse      → LLM observability (ClickHouse + Valkey, traces every AI call)
Tailscale     → remote access VPN
Cloudflare Tunnel → public access (*.devandre.sbs, no Tailscale)

── SECURITY LAYER ──────────────────────────────────────────────────
Authentik     → SSO / OIDC (16 dept groups, 16 demo personas, MFA enforced)
OPA/Gatekeeper→ 9 admission policies, deny mode, 0 violations
cert-manager  → internal PKI + cert observability PrometheusRules
Cosign + syft → keyless image signing + CycloneDX SBOM in CI
ESO + Vault KV→ all platform secrets in Vault (no plaintext in git)
NetworkPolicy  → default-deny ingress/egress on all 23 namespaces
PSA           → enforce:restricted on 8 namespaces
GPG commits   → signed commits + branch protection on critical repos
UFW           → host firewall on controller + all cluster nodes
HSTS + rate-limit → global HSTS, 20r/s public, 5r/s auth (NGINX ConfigMap)

── AI / ML ─────────────────────────────────────────────────────────
LiteLLM       → OpenAI-compatible gateway (7 cloud providers + 2 local Ollama)
Ollama        → local LLMs on NVMe (phi3-financial, llama3.2:3b/1b, phi3.5)
Valkey        → exact-match prompt cache (10 min TTL, ~80ms cache hit)
Presidio      → PII/DLP pre-call guardrail (anonymizes before cloud APIs)
detect_secrets→ credential scanner on all prompts
Open WebUI    → chat interface (Authentik OIDC, CA bundle init container)
Langfuse      → per-call traces with cost, model, department, latency

── DATA LAYER (future) ──────────────────────────────────────────────
Redpanda      → event streaming (Kafka-compatible)
ClickHouse    → columnar analytics warehouse
dbt           → SQL transformation layer
Superset      → self-hosted BI dashboards
OpenMetadata  → data catalog, lineage, governance
```

---

## CV / LinkedIn Summary

- Designed and deployed a 5-node bare-metal Kubernetes platform (4× Lenovo ThinkPad + 1× MacBook Pro 2012, 36 cores / 68 GiB RAM / 2.3 TB) using MAAS (Metal as a Service), PXE provisioning for ThinkPads, and USB install for Apple hardware incompatible with standard PXE
- Implemented full GitOps delivery pipeline: ArgoCD app-of-apps, GitHub Actions CI/CD, Cosign keyless image signing, CycloneDX SBOM, GPG-signed commits, and branch protection on critical repos
- Built enterprise AI gateway (LiteLLM 1.90.3) routing across 7 cloud providers and 2 local Ollama nodes — with cloud fallback chain, circuit breaker (3 failures → 60 s cooldown), 3-tier department budget governance ($5/$30/$100 / 30 d), Valkey prompt cache, and Grafana cost dashboard backed by PostgreSQL SQL
- Deployed PII/DLP and credential guardrails: Microsoft Presidio anonymizes prompts before any cloud API receives them; detect_secrets blocks credential leakage at inference time
- Implemented Langfuse LLM observability (ClickHouse + Valkey + PostgreSQL) tracing every AI Gateway call with token counts, cost, model, and department metadata
- Enforced 9 OPA/Gatekeeper admission control policies in deny mode with 0 violations: no-root containers, no-privileged pods, approved registry only, resource limits required, TLS-only ingress, no LoadBalancer in dev, no hostPath, no latest tag, no privilege escalation
- Applied defence-in-depth: default-deny NetworkPolicy on all 23 namespaces, PSA enforce:restricted on 8 namespaces, AES-CBC-256 secrets encryption at rest, k3s audit logs, SSH hardening + UFW default-deny on all 5 cluster nodes, HSTS globally, rate limiting, and Authentik forward-auth on internal dashboards
- Achieved zero-touch Vault auto-unseal via AWS KMS (scoped IAM policy, seal migration verified — pod deletion → 1/1 Ready in ~30 s with no human input)
- Deployed External Secrets Operator with Vault KV v2 backend (9 ExternalSecrets — all platform credentials pulled from Vault; no plaintext secrets in git)
- Implemented full backup & DR: Velero + MinIO (daily cluster backup), nightly DB dumps (pg_dump → MinIO), Vault raft snapshots, PrometheusRule alerts (VeleroBackupFailed, MinioDiskFull), and validated restore test
- Built Authentik-based department RBAC: 16 groups, 16 demo personas with group-based policy bindings across ArgoCD, Grafana, Harbor, Open WebUI, and Nextcloud; MFA enforced on all accounts
- Established full platform health suite: regression check script covering cluster, security, observability, AI Gateway, and backups — Regression check #37: **20 PASS / 0 FAIL / 3 WARN** (all warns are known drift)
- Implemented remote access via Tailscale VPN and Cloudflare Tunnel (`*.devandre.sbs` public edge, no Tailscale required)
- Applied chaos engineering with Chaos Mesh: PodChaos (0 ms downtime under 5 simultaneous kills), NetworkChaos (200 ms latency injection + clean recovery), StressChaos (contained cgroup OOM)
