---
id: production-stack-architecture
title: Production Stack Architecture
sidebar_label: Production Stack Architecture ✅
---

# Production Stack Architecture

A complete view of the minicloud production platform — 5-node on-premises k3s cluster running Phase 0–90 workloads across infrastructure, security, observability, AI/ML, automation, and collaboration layers.

:::tip Interactive diagram
Open the full diagram in your browser for PNG/PDF export and zoom-level control:

**[View full architecture diagram →](pathname:///diagrams/minicloud-production-stack.html)**
:::

---

## Platform at a Glance

| Dimension | Value |
|-----------|-------|
| Nodes | 4 ThinkPads + MacBook Pro 2012 (Ubuntu 22.04) |
| k3s version | v1.36.3+k3s1 (all 5 nodes, upgraded 2026-08-13) |
| ArgoCD apps | 78 live applications |
| PrometheusRule objects | 53 (monitoring ns + podinfo) |
| Grafana dashboards | 43+ |
| GitOps repos | 11 (all → Harbor via Tailscale) |
| Phases complete | 0–90 |

---

## Architecture Layers

### Access Layer

All traffic enters through a single MetalLB IP (`10.0.0.200`). Two paths:

- **Public (devandre.sbs):** Cloudflare CDN → Cloudflare Tunnel (k8s Deployment, 2 replicas, `cloudflare-tunnel` ns, anti-affinity spread across workers)
- **Internal/VPN:** Tailscale → NGINX Ingress directly via `*.10.0.0.200.nip.io`

Every application is protected by **Authentik SSO** (OIDC + TOTP) via NGINX forward-auth ingress annotations. cert-manager handles TLS for both Let's Encrypt (public) and the minicloud root CA (internal).

:::note Cloudflare Tunnel — HA since 2026-08-13
Cloudflare Tunnel moved from a controller systemd service to a 2-replica Kubernetes Deployment (PRs #678+#679). Tunnel remains active during controller reboots. SSH backup path: `controller.devandre.sbs → ssh://10.0.0.1:22` (PR #680).
:::

### GitOps & Automation

```
Developer push → GitHub Actions (CI)
                    ├── Build → Trivy scan → Cosign sign → syft SBOM
                    ├── Push → Harbor (via Tailscale tag:ci)
                    └── bump-gitops (GPG-signed PR) → ArgoCD auto-sync
                              │
                              ├── canary-load (parallel) — k6 5 min sustained
                              └── rollout-gate (parallel) — polls Rollout phase
                                        │
                                        └── promote-staging (needs both pass)
```

ArgoCD manages 78 apps via the app-of-apps pattern from `minicloud-gitops`. All Helm values live in `helm-values/`, never in `minicloud-ansible/`.

**Argo Rollouts** handles progressive delivery:
- `platform-demo`: Canary 50% → AnalysisRun (Prometheus gates) → 100%
- `minicloud-plane`: BlueGreen prePromotion (health) + postPromotion (Prometheus)

### Security

| Component | Role |
|-----------|------|
| Vault (HashiCorp CE) | PKI, secrets, AWS KMS auto-unseal, fast-heron pinned |
| ESO | ExternalSecrets from Vault KV to k8s Secrets |
| Gatekeeper OPA | 18 constraints: require-non-root, no-privilege-escalation, no-hostpath, block-capabilities, require-seccomp, and more |
| Falco | Runtime syscall monitoring, DaemonSet |
| cert-manager | Let's Encrypt (public) + minicloud CA (internal) |
| Vaultwarden | Timshel fork 1.34.1-6, SSO via Authentik |
| NetworkPolicies | default-deny-ingress on all namespaces |
| kube-bench | k3s-CIS-1.7: 16/16 PASS on all 4 workers |
| Chaos Mesh | Fault injection for Game Day reliability testing |
| cosign + SBOM | Supply-chain: every staging/prod image is signed + has SBOM attached |

### AI / ML Platform

```
Open WebUI (custom minicloud-open-webui)
    └→ LiteLLM Proxy (2 replicas, KEDA auto-scale)
            ├→ vLLM v0.6.6 (Mistral / phi-mini, on-cluster, star-kitten)
            ├→ Ollama (nomic-embed-text, embeddings)
            └→ Cloud fallback (Azure OpenAI / Anthropic — €10/mo cap each)

RAG pipeline:
  Document → markitdown-proxy (PDF/Office/images → Markdown via Docling)
           → rag-ingest (chunk → embed → store)
           → Qdrant v1.x (policy-docs, incident-reports, regulatory collections)
           → nomic-embed-text (768-dim via Ollama)

AI agents:
  minicloud-agent 1.0.1     — LangChain single-agent, MCP tool layer
  minicloud-crew-agent 1.0.1 — CrewAI multi-agent, insurance workflow automation

Observability:
  Langfuse: TTFT, tokens/s, cost/request, prompt eval scores, 90-day trace retention
  LiteLLM Prometheus: litellm_proxy_total_requests_metric_total, input tokens
  vLLM dashboard: vllm-inference-v1 (7 panels, ServiceMonitor in ai ns)
```

**Specialised AI services (all in `ai` namespace, managed under `litellm` ArgoCD app):**

| Service | Version | Purpose |
|---------|---------|---------|
| vLLM | v0.6.6 | GPU-optimised LLM inference (CPU on-cluster) |
| MLflow | v2.16.0-psycopg2 | Experiment tracking, model registry |
| Flowise | 2.2.7 | Visual LLM flow builder |
| minicloud-agent | 1.0.1 | LangChain agent + MCP |
| minicloud-crew-agent | 1.0.1 | CrewAI multi-agent |
| Presidio | latest | PII detection + anonymisation |
| Langfuse | 3.x | LLM observability (ClickHouse backend) |
| Open WebUI | custom | Chat interface, French BM25 RAG |
| Qdrant | 1.x | Vector store (RAG collections) |

**phi3-financial PromptOps pipeline:** routes through `groq/llama-3.1-8b-instant` (primary, weight 10) with vLLM phi3-mini as fallback. 25/25 CI eval cases pass.

### Automation & Workflows

| Service | Namespace | URL | Notes |
|---------|-----------|-----|-------|
| n8n 2.32.7 | `automation` | n8n.devandre.sbs | Phase 83, 5Gi Longhorn RWO |
| Temporal v1.31.2 | `temporal` | temporal.devandre.sbs | Phase 84, 4 historyShards (PERMANENT), PostgreSQL backend |

### Observability

The observability stack uses five complementary tools:

| Tool | Purpose | Key metric |
|------|---------|-----------|
| Prometheus | metrics collection + alerting | 53 PrometheusRule objects |
| Grafana | dashboards + explore | 43+ dashboards, TraceQL, LogQL |
| Loki | log aggregation | OTLP native, 30-day retention, LogQL ruler |
| Tempo 2.9.0 | distributed tracing | TraceQL, tracesToLogsV2, 14-day retention |
| OTel Collector | log + trace shipping | DaemonSet, OTTL transforms, replaces Promtail |
| Alertmanager | alert routing | → Stalwart:587 → SES → kanmegnea@devandre.sbs + healthchecks.io watchdog |

**Log pipeline (Gaps 1–7 closed):**
- Promtail replaced by OTel Collector DaemonSet (otelcol-contrib 0.156.0)
- OTTL `transformprocessor`: Kopia job cardinality collapsed, `level` label extracted and normalised
- Controller logs via Promtail Docker container (`--net=host` for MetalLB routing)

**SLO & Regression Detection:**
- 7 SLO objectives, 11 recording rules, burn-rate 2-tier alerts
- 5 regression alerts comparing current vs `offset 1h` baseline (latency, error rate, throughput, CPU, memory)
- `RolloutAutoRollback` alert on `argo_rollout_info{phase="Degraded"} == 1` for 1m

**Operational resilience:**
- healthchecks.io: 3 checks — Alertmanager watchdog (`cc3f232b`), controller heartbeat (`b2ac9ab5`), recovery failures (`6a37bfa6`)
- minicloud-ops: Python recovery check, 15 health probes, systemd-managed on controller

### Collaboration & Business Apps

| Service | URL | Notes |
|---------|-----|-------|
| Stalwart Mail | mail.devandre.sbs | v0.16.13, JMAP API, RocksDB |
| AWS SES | eu-west-1 | outbound relay + inbound pipeline (production approved) |
| Matrix + Element | element.devandre.sbs | Synapse v1.156.0, dedicated postgresql-synapse in `chat` ns |
| ERPNext | erp.devandre.sbs | v16.28.0, French insurance config (PCG 2025, TSCA, LOBs, Factur-X) |
| Jitsi Meet | meet.devandre.sbs | v2.21.0, JVB pinned star-kitten, TURN = Lightsail 54.171.137.209 |
| Nextcloud | files.devandre.sbs | OnlyOffice DocumentServer, SSO |
| Plane CE | plane.devandre.sbs | project management |
| Vaultwarden | vault-pw.devandre.sbs | Timshel fork (SSO button), human credential store |
| Docuseal | sign.devandre.sbs | e-Signature (eIDAS Simple), 4 insurance templates |
| n8n | n8n.devandre.sbs | workflow automation |
| Temporal | temporal.devandre.sbs | durable workflow engine v1.31.2 |

**Email flows (bidirectional, 2026-07-26):**
- **Outbound:** Stalwart SMTP:587 → ses-relay → SES eu-west-1 → recipient
- **Inbound:** External → MX `inbound-smtp.eu-west-1.amazonaws.com` → SES Receipt → S3 → SNS → SQS → ses-ingest pod → Stalwart → mailbox

### Storage

| Store | Location | Used by |
|-------|----------|---------|
| Longhorn | Distributed (swift-mac preferred) | All stateful workloads with RWO/RWX PVCs |
| MinIO | MAAS Controller (Docker) | Velero backup bucket, kine SQLite backups, S3-compat |
| Qdrant | `ai` ns (Longhorn PVC) | RAG vector collections (768-dim nomic-embed-text) |
| PostgreSQL-ai | `ai` ns | MLflow, LiteLLM cache, RAG metadata |
| postgresql-synapse | `chat` ns, set-hog pinned | Matrix-synapse dedicated DB (migrated 2026-08-07) |
| ClickHouse | `langfuse` ns | LLM trace storage |
| MariaDB | `erp` ns | ERPNext data |

**Backup layers:**
- **Velero (daily):** Longhorn snapshots → MinIO `velero/` bucket (local)
- **Velero off-site (weekly):** Cloudflare R2 `minicloud-velero-offsite` bucket (72h TTL)
- **kine SQLite (daily):** `sqlite3 .backup` → MinIO `k3s-backup/` + controller timer → `db-backups/kine/`

**multipathd gotcha (all 5 nodes):** IET VIRTUAL-DISK devices blacklisted in `/etc/multipath.conf` to prevent Longhorn iSCSI volumes from being claimed as `mpatha`.

---

## Hardware

| Node | IP | Role | Notes |
|------|----|------|-------|
| MAAS Controller (ThinkPad X390) | 100.88.123.8 | NAT, MAAS, Tailscale, MinIO, cloudflared systemd (SSH backup path) | 98G NVMe |
| set-hog | 10.0.0.2 | k3s control-plane | Kine/SQLite, socat proxy for scheduler+ctrl-mgr metrics |
| fast-skunk | 10.0.0.4 | k3s worker | General workloads, NVMe-first boot (BIOS) |
| fast-heron | 10.0.0.7 | k3s worker | Vault pinned (nodeSelector) |
| star-kitten | 10.0.0.8 | k3s worker (ai,worker) | Jitsi JVB pinned (hostNetwork), vLLM inference |
| swift-mac | 10.0.0.10 | k3s worker (storage,worker) | MacBook Pro 13" 2012, Ubuntu 22.04, Longhorn preferred |

**Boot order:** Controller (30s) → cluster nodes (2 min) → Tailscale on Mac.

**NVMe boot fix (2026-08-13):** All 4 ThinkPads boot NVMe-first. fast-skunk via BIOS; fast-heron/star-kitten/set-hog via `efibootmgr --create`.

**Power failure recovery:** NAT is automated (`restore-cluster-nat.service` on controller — no manual step needed). MinIO requires a manual restart after disk-full events (caches error state in memory):
```bash
ssh controller "docker restart minio"
```

---

## Key Design Decisions

**Why on-premises?** Portfolio-grade work demonstrating infrastructure ownership, cost awareness, and operational discipline beyond managed cloud. All compute, networking, and storage decisions are explicit.

**Why app-of-apps?** Single ArgoCD application (`minicloud-gitops`) owns everything. New services are added by dropping an `apps/<name>.yaml` file — no manual ArgoCD config.

**Why Harbor vs ghcr.io?** All custom images stay on-premises via Tailscale. Air-gap-capable registry with Cosign signature verification, SBOM storage, and CVE scanning in a single tool.

**Why OTel Collector instead of Promtail?** Stack-agnostic — only the exporter block changes when swapping backends. OTTL transforms handle cardinality normalization and label extraction without coupling to Loki's scrape config format.

**Why Stalwart + SES instead of a managed email provider?** Full control over deliverability, DKIM rotation, and JMAP automation. SES production access (50k msg/day) eliminates sandbox restrictions at near-zero cost.

**Why Qdrant over pgvector?** Dedicated vector DB with named collections, HNSW indexing, and snapshot API. pgvector is still running in `postgresql-ai` for legacy RAG metadata; new collections use Qdrant.

**Why Cloudflare Tunnel in k8s (not systemd)?** 2-replica Deployment with pod anti-affinity eliminates the ~90s devandre.sbs outage that occurred on every controller reboot. Cloudflare load-balances across connectors automatically.
