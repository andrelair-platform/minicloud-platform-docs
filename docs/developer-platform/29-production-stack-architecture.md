---
id: production-stack-architecture
title: Production Stack Architecture
sidebar_label: Production Stack Architecture ✅
---

# Production Stack Architecture

A complete view of the minicloud production platform — 5-node on-premises k3s cluster running Phase 0–80 workloads across infrastructure, security, observability, AI/ML, and collaboration layers.

:::tip Interactive diagram
Open the full diagram in your browser for PNG/PDF export and zoom-level control:

**[View full architecture diagram →](pathname:///diagrams/minicloud-production-stack.html)**
:::

---

## Platform at a Glance

| Dimension | Value |
|-----------|-------|
| Nodes | 4 ThinkPads + MacBook Pro 2012 (Ubuntu 22.04) |
| k3s version | v1.36.2+k3s1 (all 5 nodes) |
| ArgoCD apps | 71 live applications |
| Prometheus targets | 64 up / 64 total (17 custom app targets) |
| Recording rules | 33 (SLO + regression + infrastructure) |
| Grafana dashboards | 35+ |
| GitOps repos | 8 (all → Harbor via Tailscale) |
| Phases complete | 0–80 |

---

## Architecture Layers

### Access Layer

All traffic enters through a single MetalLB IP (`10.0.0.200`). Two paths:

- **Public (devandre.sbs):** Cloudflare CDN → Cloudflared Tunnel (controller systemd) → NGINX Ingress community 4.15.1
- **Internal/VPN:** Tailscale → NGINX Ingress directly via `*.10.0.0.200.nip.io`

Every application is protected by **Authentik SSO** (OIDC + TOTP) via NGINX forward-auth ingress annotations. cert-manager handles TLS for both Let's Encrypt (public) and the minicloud root CA (internal).

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

ArgoCD manages 71 apps via the app-of-apps pattern from `minicloud-gitops`. All Helm values live in `helm-values/`, never in `minicloud-ansible/`.

**Argo Rollouts** handles progressive delivery:
- `platform-demo`: Canary 50% → AnalysisRun (Prometheus gates) → 100%
- `minicloud-plane`: BlueGreen prePromotion (health) + postPromotion (Prometheus)

### Security

| Component | Role |
|-----------|------|
| Vault (HashiCorp CE) | PKI, secrets, AWS KMS auto-unseal, fast-heron pinned |
| ESO | ExternalSecrets from Vault KV to k8s Secrets |
| Gatekeeper OPA | 9 constraints: BlockNetRaw, BlockCapabilities, RequireSeccomp |
| Falco | Runtime syscall monitoring, DaemonSet |
| cert-manager | Let's Encrypt (public) + minicloud CA (internal) |
| Vaultwarden | Timshel fork 1.34.1-6, SSO via Authentik |
| NetworkPolicies | default-deny-ingress on all namespaces |
| kube-bench | k3s-CIS-1.7: 16/16 PASS on all 4 workers |

### AI / ML Platform

```
Open WebUI → LiteLLM Proxy → Ollama (phi4-mini, nomic-embed-text)
                           └→ Groq API (llama-3.1-8b-instant fallback)

RAG pipeline:
  Document → markitdown-proxy (PDF/Office → Markdown)
           → rag-ingest (chunk → embed → store)
           → pgvector (ragdb, 768-dim nomic-embed-text)

Observability:
  Langfuse: TTFT, tokens/s, cost/request, prompt eval scores
  LiteLLM Prometheus: litellm_proxy_total_requests_metric_total, input tokens
```

The phi3-financial PromptOps pipeline routes through `groq/llama-3.1-8b-instant` (primary, weight 10) with Ollama phi4-mini as fallback. 25/25 CI eval cases pass.

### Observability

The observability stack uses four complementary tools:

| Tool | Purpose | Key metric |
|------|---------|-----------|
| Prometheus | metrics collection + alerting | 64 targets, 33 recording rules |
| Grafana | dashboards + explore | 35+ dashboards, TraceQL, LogQL |
| Loki | log aggregation | OTLP native, 30-day retention, LogQL ruler |
| Tempo 2.9.0 | distributed tracing | TraceQL, tracesToLogsV2, 14-day retention |
| OTel Collector | log + trace shipping | DaemonSet, OTTL transforms, replaces Promtail |
| Alertmanager | alert routing | → Stalwart:587 → SES → kanmegnea@devandre.sbs |

**Log pipeline (Gaps 1–7 closed):**
- Promtail replaced by OTel Collector DaemonSet (otelcol-contrib 0.156.0)
- OTTL `transformprocessor`: Kopia job cardinality collapsed, `level` label extracted and normalised
- Controller logs via Promtail Docker container (`--net=host` for MetalLB routing)

**SLO & Regression Detection:**
- 7 SLO objectives, 11 recording rules, burn-rate 2-tier alerts
- 5 regression alerts comparing current vs `offset 1h` baseline (latency, error rate, throughput, CPU, memory)
- `RolloutAutoRollback` alert on `argo_rollout_info{phase="Degraded"} == 1` for 1m

### Collaboration & Email

| Service | URL | Notes |
|---------|-----|-------|
| Stalwart Mail | mail.devandre.sbs | v0.16.13, JMAP API, RocksDB |
| AWS SES | eu-west-1 | outbound relay + inbound pipeline (production approved) |
| Matrix + Element | element.devandre.sbs | Synapse v1.156.0, OIDC via Authentik |
| ERPNext | erp.devandre.sbs | v16.28.0, HR source of truth, employee onboard webhook |
| Jitsi Meet | meet.devandre.sbs | v2.21.0, JVB pinned star-kitten |
| Nextcloud | files.devandre.sbs | OnlyOffice DocumentServer, SSO |
| Plane CE | plane.devandre.sbs | project management |
| Vaultwarden | vault-pw.devandre.sbs | SSO password manager |

**Email flows (bidirectional, 2026-07-26):**
- **Outbound:** Stalwart SMTP:587 → ses-relay → SES eu-west-1 → recipient
- **Inbound:** External → MX `inbound-smtp.eu-west-1.amazonaws.com` → SES Receipt → S3 → SNS → SQS → ses-ingest pod → Stalwart → mailbox

### Storage

| Store | Location | Used by |
|-------|----------|---------|
| Longhorn | Distributed (swift-mac preferred) | All stateful workloads with RWO/RWX PVCs |
| MinIO | MAAS Controller (Docker) | Velero backup bucket, S3-compat |
| pgvector (ragdb) | PostgreSQL in `ai` ns | RAG embeddings (768-dim) |
| ClickHouse | langfuse ns | LLM trace storage |
| MariaDB | erp ns | ERPNext HR data |

**multipathd gotcha (all 5 nodes):** IET VIRTUAL-DISK devices blacklisted in `/etc/multipath.conf` to prevent Longhorn iSCSI volumes from being claimed as `mpatha`.

---

## Hardware

| Node | IP | Role | Notes |
|------|----|------|-------|
| MAAS Controller (ThinkPad X390) | 100.88.123.8 | NAT, MAAS, Tailscale, MinIO | 98G NVMe, node_exporter :9100 |
| set-hog | 10.0.0.2 | k3s control-plane | Kine/SQLite, socat proxy for scheduler+ctrl-mgr metrics |
| fast-skunk | 10.0.0.4 | k3s worker | General workloads |
| fast-heron | 10.0.0.7 | k3s worker | Vault pinned (nodeSelector) |
| star-kitten | 10.0.0.8 | k3s worker | Jitsi JVB pinned (hostNetwork) |
| swift-mac | 10.0.0.10 | k3s worker | MacBook Pro 13" 2012, Ubuntu 22.04, Longhorn preferred, no Apple SMC auto-restart |

**Boot order:** Controller (30s) → cluster nodes (2 min) → Tailscale on Mac.

**Power failure recovery:** After controller reboot, run `sudo sh -c 'iptables-restore < /etc/iptables/rules.v4'` + add FORWARD rules manually. See CLAUDE.md for the full procedure.

---

## Key Design Decisions

**Why on-premises?** Portfolio-grade work demonstrating infrastructure ownership, cost awareness, and operational discipline beyond managed cloud. All compute, networking, and storage decisions are explicit.

**Why app-of-apps?** Single ArgoCD application (`minicloud-gitops`) owns everything. New services are added by dropping an `apps/<name>.yaml` file — no manual ArgoCD config.

**Why Harbor vs ghcr.io?** All custom images stay on-premises via Tailscale. Air-gap-capable registry with Cosign signature verification, SBOM storage, and CVE scanning in a single tool.

**Why OTel Collector instead of Promtail?** Stack-agnostic — only the exporter block changes when swapping backends. OTTL transforms handle cardinality normalization and label extraction without coupling to Loki's scrape config format.

**Why Stalwart + SES instead of a managed email provider?** Full control over deliverability, DKIM rotation, and JMAP automation for the employee onboarding template. SES production access (50k msg/day) eliminates sandbox restrictions at near-zero cost.
