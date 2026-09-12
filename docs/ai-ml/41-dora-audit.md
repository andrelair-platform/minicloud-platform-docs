---
id: dora-audit
title: DORA Audit Trail & Retention — AI Gateway
sidebar_label: DORA Audit Trail
---

# DORA Audit Trail & Retention — AI Gateway

> How the minicloud AI gateway meets **DORA** (Reg. EU 2022/2554) audit,
> third-party-ICT register, resilience and retention expectations, and how to
> produce an audit report. Companion to `model-governance-matrix.md`.
> Story: platform-backlog **#309** (closes AI-GW epic **#296**).

## 1. Audit trail — what is captured, per AI call

| Signal | Source | Fields |
|---|---|---|
| **Per-request trace** | **Langfuse** (`success_callback: langfuse`) | timestamp · **team/key** (caller identity) · **model** · input/output tokens · **cost** · latency · trace/session id |
| **Prompt/response** | Langfuse (store) | prompt + completion (PII **already masked** by the Presidio guardrail before any cloud call) |
| **Metrics** | **Prometheus** (`success_callback: prometheus`) | requests/errors/latency/tokens per model; **residency recording rules** (`ai:litellm_*_by_tier`) → traffic by jurisdiction |
| **Guardrails** | Prometheus | Presidio PII invocations/errors; LlamaGuard |

The **data class of each call is derivable**: `model → access_group/class` via the governance matrix. Caller → team (RBAC #306). So every call has *who · what model · which class · which jurisdiction · cost*.

## 2. Register of ICT third parties (DORA Art. 28)

The **model governance matrix** (`model-governance-matrix.md` §2) **is** the register of ICT third-party providers: provider · jurisdiction · data terms · max data class. Maintained on every model add/remove.

- **Concentration risk:** traffic is spread across providers; no single external provider is a single point of failure (on-cluster vLLM is always available).
- **Criticality:** external LLMs are **support** functions (assist/RAG), not critical banking functions; the on-cluster tier serves restricted (P3) data.

## 3. Resilience & exit strategy (DORA Art. 11–12, 28)

- **Substitutability:** the **LiteLLM gateway** abstracts all providers → switching provider = a config change (`model_list`), **no application change**. Exit from any single provider is a one-line edit.
- **Fallback:** `router_settings` (retries, cooldown, fallbacks) + the **on-cluster vLLM tier** as the sovereign fallback if all cloud providers are unavailable.
- **Data residency:** restricted/PII data is confined to **on-cluster (P3)** or **EU (P2)** tiers by RBAC (#305/#306) — it cannot leave the EU.

## 4. Retention

| Store | Retention | Notes |
|---|---|---|
| Langfuse traces (audit log) | **≥ 12 months** | DORA/audit evidence; PII pre-masked (GDPR minimisation). Verify Langfuse project retention config. |
| Prometheus metrics | per cluster retention (≈ 30 d hot) | long-term SLO/FinOps; residency ratios |
| Governance matrix + this doc | git history (permanent) | versioned register + policy |

**GDPR:** prompts are stored **PII-masked** (Presidio `default_on`), satisfying data minimisation. No raw personal data in the audit store.

## 5. Alerting (incident evidence — DORA Art. 17–18)

Compliance-relevant alerts (story #308) route `critical` → **email + Slack**:
`AIPresidioGuardrailErrors` (PII control failing = reportable), `AIOutOfEURatioHigh` (residency), `AILatencySLOBreach`, `AIProviderErrorSpike` (provider outage / fallback storm).

## 6. Producing an audit report

1. **Usage by caller & model** — Langfuse dashboards (filter by team/date) → who used which model, tokens, cost.
2. **Residency evidence** — Grafana *AI Residency & Governance FinOps* (out-of-EU %, traffic by tier).
3. **Third-party register** — `model-governance-matrix.md` §2 (providers, jurisdiction, terms).
4. **Enforcement proof** — RBAC team scoping (`/team/info` shows `models: [onprem,eu,us]`) + Presidio guardrail `default_on`.
5. **Incident log** — Alertmanager history for the `AI*` alerts.

## 7. Gaps / follow-ups
- Confirm/set Langfuse project **retention ≥ 12 months** in the Langfuse UI (config, not git).
- Restricted-document embeddings currently may use a US model (`text-embedding-3-small`) via unscoped paths — prefer on-cluster/EU embeddings (`mistral-embed`) for P3 data (route via a scoped key).
