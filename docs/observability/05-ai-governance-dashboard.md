---
id: ai-governance-dashboard
title: Phase 76 — AI Governance & Operations Dashboard
sidebar_position: 5
---

# Phase 76 — AI Governance & Operations Dashboard

A real-time Grafana dashboard covering the operational health of the AI platform: latency percentiles, error rates, guardrail activity, cache efficiency, model deployment state, and Langfuse trace signals. It completes the observability layer that was missing after Phase 14 (Langfuse) and Phase 22 (LiteLLM AI Gateway).

Dashboard UID: `ai-governance-v1` — `https://grafana.devandre.sbs/d/ai-governance-v1`

---

## Context: what was broken and why

After deploying LiteLLM in Phase 22, Langfuse in Phase 14, and the `LangfusePromptHandler` custom logger in Phase 17, every request was generating a Langfuse trace — but those traces had **zero observations, zero cost, zero latency**. 660 traces existed with empty `observations: []`.

The root cause was a silent misconfiguration in two places.

### Bug 1 — Callbacks in the wrong config section

`minicloud-litellm-custom/config/litellm-config.yaml` had `success_callback`, `failure_callback`, and `callbacks` under `general_settings:`.

```yaml
# BROKEN — LiteLLM silently ignores these keys in general_settings
general_settings:
  callbacks: ["langfuse_prompt_handler.LangfusePromptHandler"]
  success_callback: ["langfuse", "prometheus"]
  failure_callback: ["prometheus"]
```

LiteLLM's `proxy_server.py` processes these keys **only** in the `litellm_settings.items()` loop. `general_settings` is parsed for a fixed set of known keys via explicit `general_settings.get(key)` calls — unknown keys are silently discarded.

**Fix:** move all three keys to `litellm_settings:`.

```yaml
litellm_settings:
  callbacks: ["langfuse_prompt_handler.LangfusePromptHandler"]
  success_callback: ["langfuse", "prometheus"]
  failure_callback: ["prometheus"]
```

Verification in pod logs after restart:
```
Initialized Success Callbacks - ['langfuse', 'prometheus']
```

### Bug 2 — Custom logger exposed as a class, not an instance

LiteLLM's `get_instance_fn(value="module.ClassName")` calls:
```python
instance = getattr(module, instance_name)
return instance   # returns the CLASS, not an instance
```

Calling an async hook method on a bare class fails immediately:
```
TypeError: async_post_call_success_hook() missing 1 required positional argument: 'self'
```

**Fix:** rename the class to `_LangfusePromptHandler` and expose a module-level instance under the name LiteLLM references:

```python
class _LangfusePromptHandler(CustomLogger):
    async def async_pre_call_hook(self, ...):
        ...

# get_instance_fn does getattr(module, "LangfusePromptHandler")
# — must return an instance, not the class
LangfusePromptHandler = _LangfusePromptHandler()
```

Source files changed: `minicloud-litellm-custom/config/litellm-config.yaml`, `minicloud-litellm-custom/langfuse_prompt_handler.py`, and their cluster mirrors `manifests/ai/00-litellm-configmap.yaml`, `manifests/ai/15-langfuse-prompt-handler-configmap.yaml` (minicloud-gitops PRs #24 and #26).

After both fixes:
- Every request to LiteLLM generates a Langfuse trace with a `GENERATION` observation
- Observation carries: `model: ollama/llama3.2:1b`, `latency: 2.99s`, `promptTokens: 30`, `completionTokens: 5`
- `totalCost: 0` is expected for local Ollama — no pricing model configured

---

## Architecture

```
                          ┌─────────────────────────────────┐
                          │       Grafana (monitoring ns)    │
                          │                                  │
                          │  ┌──────────────────────────┐   │
                          │  │  ai-governance-v1        │   │
                          │  │  Governance Dashboard    │   │
                          │  └────┬──────────────┬──────┘   │
                          │       │              │           │
                          └───────┼──────────────┼───────────┘
                                  │              │
             ┌────────────────────┘              │
             ▼                                   ▼
  ┌─────────────────────┐           ┌─────────────────────────┐
  │ Prometheus (uid:    │           │ Infinity datasource      │
  │ "prometheus")       │           │ (uid: langfuse-infinity) │
  │                     │           │ Basic Auth via ESO secret│
  └──────────┬──────────┘           └────────────┬────────────┘
             │                                   │
             ▼                                   ▼
  ┌──────────────────────┐          ┌─────────────────────────┐
  │ LiteLLM ServiceMonitor│         │ Langfuse REST API        │
  │ /metrics (~70 metrics)│         │ /api/public/metrics/daily│
  │ litellm_proxy_total_* │         │ /api/public/traces       │
  │ litellm_guardrail_*   │         │ langfuse-web.langfuse    │
  │ litellm_cache_*       │         │ .svc.cluster.local:3000  │
  └──────────────────────┘          └─────────────────────────┘
```

The Prometheus panels use `$__rate_interval` so they adapt automatically as the selected time range changes. The Infinity panels make backend (proxy-mode) HTTP calls from the Grafana pod directly to `langfuse-web.langfuse.svc.cluster.local` — no ingress hop, no TLS.

---

## Components deployed

### 1. ESO ExternalSecret `grafana-langfuse`

`manifests/eso-platform-secrets/16-grafana-langfuse.yaml` — syncs Langfuse project API keys from Vault into the `monitoring` namespace so Grafana can use them as Basic Auth credentials for the Infinity datasource.

```yaml
# Vault path: platform/langfuse
# Keys: project-public-key → public-key, project-secret-key → secret-key
# Secret name: grafana-langfuse (monitoring namespace)
```

Verify:
```bash
kubectl get externalsecret -n monitoring grafana-langfuse
# NAME               STORE           REFRESH INTERVAL   STATUS         READY
# grafana-langfuse   vault-backend   1h                 SecretSynced   True
```

### 2. Grafana helm values (`kube-prometheus-stack-values.yaml`)

Three additions under `grafana:`:

```yaml
grafana:
  plugins:
    - yesoreyeram-infinity-datasource        # installed at pod startup (~5 s)

  envValueFrom:
    GF_LANGFUSE_PUBLIC_KEY:
      secretKeyRef:
        name: grafana-langfuse
        key: public-key
    GF_LANGFUSE_SECRET_KEY:
      secretKeyRef:
        name: grafana-langfuse
        key: secret-key

  additionalDataSources:
    - name: Langfuse
      uid: langfuse-infinity
      type: yesoreyeram-infinity-datasource
      access: proxy
      basicAuth: true
      basicAuthUser: "${GF_LANGFUSE_PUBLIC_KEY}"
      secureJsonData:
        basicAuthPassword: "${GF_LANGFUSE_SECRET_KEY}"
      jsonData:
        allowedHosts:
          - "http://langfuse-web.langfuse.svc.cluster.local:3000"
```

The Grafana helm chart maps `plugins:` to `GF_PLUGINS_PREINSTALL_SYNC`, which triggers background installation at pod startup via `plugin.backgroundinstaller`. Installation took ~5 seconds; the datasource is available immediately after.

### 3. Dashboard ConfigMap `ai-governance-dashboard`

`manifests/ai/19-ai-governance-dashboard.yaml` — provisioned via the `grafana_dashboard: "1"` label, picked up by the Grafana sidecar.

---

## Dashboard panels

| Section | Panel | Type | Query |
|---|---|---|---|
| KPIs | Requests — last 1h | stat | `sum(increase(litellm_proxy_total_requests_metric_total[1h]))` |
| KPIs | Error Rate — last 5m | stat | `100 * failed / total` — green < 1% / red ≥ 5% |
| KPIs | P95 Latency — last 5m | stat | `histogram_quantile(0.95, ...)` — green < 5s / red ≥ 15s |
| KPIs | Cache Hit Rate — last 5m | stat | `hits / (hits + misses)` — red < 30% / green ≥ 60% |
| Traffic | Request Rate by Model | timeseries | `sum by (requested_model)` |
| Traffic | Token Throughput | timeseries | input tokens/s + output tokens/s |
| Latency | P50/P95/P99 | timeseries | three histogram_quantile queries |
| Latency | P95 by Model | bargauge | per-model P95, gradient threshold |
| Guardrails | Invocations — 24h | stat | `increase(litellm_guardrail_requests_total[24h])` |
| Guardrails | Errors — 24h | stat | `increase(litellm_guardrail_errors_total[24h])` — red if ≥ 1 |
| Guardrails | P95 Latency | stat | `histogram_quantile(0.95, litellm_guardrail_latency_seconds_bucket)` |
| Guardrails | Activity | timeseries | rate over time |
| Model Health | Deployment State | table | `litellm_deployment_state` — 0 = healthy, 1 = failed |
| Langfuse | Daily Trace Summary | table (Infinity) | `/api/public/metrics/daily?days=7` |
| Langfuse | Recent Traces | table (Infinity) | `/api/public/traces?limit=20&orderBy=timestamp` |

---

## Difference from the existing `litellm-cost-dept` dashboard

The two dashboards answer fundamentally different questions and are designed for different audiences. They are complementary — neither replaces the other.

**`litellm-cost-dept` answers: "Who spent what, and are we within budget?"**

Source is the LiteLLM PostgreSQL database (`LiteLLM_SpendLogs`, `LiteLLM_VerificationToken`). It shows dollars consumed per department, tokens billed, budget utilisation bars (green/yellow/red thresholds at 70%/90% of monthly allocation), and a table of the 50 most recent requests with unit cost. The default window is 30 days because billing is a monthly concern. The intended reader is a CIO, CFO, or department head reviewing a monthly chargeback report.

**`ai-governance-v1` answers: "Is the system working correctly right now?"**

Source is Prometheus (real-time LiteLLM metrics) and the Langfuse REST API via the Infinity datasource. It shows P50/P95/P99 latency, error rate %, guardrail invocations and errors from the Presidio PII filter, Redis cache hit rate, deployment health per model, and a live trace table from Langfuse. The default window is 3 hours with a 30-second refresh because platform health is a real-time concern. The intended reader is a platform engineer, AI lead, or CISO responding to an alert or doing a daily health check.

| | `litellm-cost-dept` (Phase 22) | `ai-governance-v1` (Phase 76) |
|---|---|---|
| **The question** | Who spent what and are we in budget? | Is the system healthy right now? |
| **Source** | PostgreSQL `LiteLLM_SpendLogs` + `LiteLLM_VerificationToken` | Prometheus + Langfuse REST API (Infinity) |
| **Default window** | 30 days | 3 hours |
| **Refresh** | 5 min | 30 s |
| **Audience** | CIO, CFO, budget owners | Platform engineer, AI lead, CISO |
| **Key panels** | Spend USD, budget utilisation %, spend by department, cost per request | P95 latency, error rate, guardrail invocations, cache hit rate, deployment state |
| **Latency** | Not visible | P50/P95/P99 timeseries + bargauge by model |
| **Guardrails** | Not visible | Invocations/errors/latency for every Presidio PII scan |
| **Langfuse** | Not connected | Daily trace count + recent trace table |
| **Use case** | Monthly budget review, department chargeback | Incident response, daily ops, compliance audit |

Use `litellm-cost-dept` for monthly budget reviews and chargeback reporting. Use `ai-governance-v1` for day-to-day operations, incident response, and SRE/CISO reviews. Both should be open during any AI platform incident: one tells you the blast radius in cost, the other tells you where the failure is.

---

## Infinity plugin — gotchas

**`enabled: false` in the plugin API** does not mean the plugin is disabled. The `/api/plugins/<id>/settings` endpoint returns `enabled: false` for datasource plugins that lack a frontend admin page — this is cosmetic. The plugin registers correctly and the datasource works.

**`allowedHosts` is required in Infinity v2+.** Without it, backend-mode URL calls to unlisted hosts return an error. Set it to the exact scheme+host+port of the target service. The format is an array in provisioning YAML:

```yaml
jsonData:
  allowedHosts:
    - "http://langfuse-web.langfuse.svc.cluster.local:3000"
```

**No TLS needed for cluster-internal calls.** Langfuse web runs HTTP on port 3000 inside the cluster; TLS terminates at the NGINX ingress. The Infinity datasource calls the internal service directly — no CA cert required.

**`basicAuthUser` supports env var substitution.** Even though `basicAuthUser` is not a `secureJsonData` field, Grafana substitutes `${ENV_VAR}` in all provisioning YAML fields before writing them to the database. Both `basicAuthUser: "${GF_LANGFUSE_PUBLIC_KEY}"` and `secureJsonData.basicAuthPassword: "${GF_LANGFUSE_SECRET_KEY}"` resolve correctly.

---

## LiteLLM config gotchas (documented here for permanence)

### `success_callback` must be under `litellm_settings`, not `general_settings`

```yaml
# WRONG — silently ignored
general_settings:
  success_callback: ["langfuse", "prometheus"]

# CORRECT
litellm_settings:
  success_callback: ["langfuse", "prometheus"]
```

This is not documented prominently in the LiteLLM docs. The source-of-truth is `proxy_server.py`: the `for key, value in litellm_settings.items():` loop at line ~4054 is where these keys are processed.

### Custom loggers must expose a module-level instance

```python
# WRONG — get_instance_fn returns the class → TypeError: missing self
class LangfusePromptHandler(CustomLogger):
    ...

# CORRECT — get_instance_fn returns an already-instantiated object
class _LangfusePromptHandler(CustomLogger):
    ...

LangfusePromptHandler = _LangfusePromptHandler()
```

`get_instance_fn` does `getattr(module, "LangfusePromptHandler")` and returns the result directly without calling it. If the result is a class, every hook call fails with `missing 1 required positional argument: self`.

---

## Verification commands

```bash
# Plugin installed in Grafana
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana \
  | grep 'infinity\|Plugin registered'

# ESO secret synced
kubectl get externalsecret -n monitoring grafana-langfuse
kubectl get secret -n monitoring grafana-langfuse -o jsonpath='{.data.public-key}' \
  | base64 -d | cut -c1-12

# Dashboard provisioned (sidecar picked it up)
kubectl get cm -n monitoring ai-governance-dashboard

# Grafana API: list datasources (check langfuse-infinity is present)
PASS=$(kubectl get secret -n monitoring grafana-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3001:80 &
curl -s -u "admin:$PASS" http://localhost:3001/api/datasources \
  | python3 -m json.tool | grep -E 'uid|name|type'

# Dashboard accessible via Grafana API
curl -s -u "admin:$PASS" \
  http://localhost:3001/api/dashboards/uid/ai-governance-v1 \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); \
    print(d["dashboard"]["title"], "-", len(d["dashboard"]["panels"]), "panels")'
# AI Platform — Governance & Operations - 20 panels

kill %1
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Langfuse traces exist but `observations: []` | `success_callback` under `general_settings` | Move to `litellm_settings` and restart LiteLLM pod |
| HTTP 500 on LiteLLM requests after enabling callbacks | `get_instance_fn` returns the class, not an instance | Rename class to `_Foo`, expose `Foo = _Foo()` at module level |
| Infinity panels show "Forbidden" | `allowedHosts` not set or wrong URL | Add scheme+host+port to `jsonData.allowedHosts` in datasource provisioning |
| Infinity panels show "Plugin not found" | `yesoreyeram-infinity-datasource` not installed yet | Wait 30s after pod restart — background installer takes ~5s, health probe may make pod appear Ready before install completes |
| `GF_LANGFUSE_PUBLIC_KEY` empty in Grafana | ESO not yet synced or Vault path wrong | `kubectl get externalsecret -n monitoring grafana-langfuse` — check STATUS and READY |
| Prometheus panels show no data | LiteLLM ServiceMonitor not scraping | `kubectl get servicemonitor -n ai litellm-servicemonitor` and check Prometheus targets at `prometheus.10.0.0.200.nip.io/targets` |
| Cache hit rate panel shows `—` (no data) | No requests have passed through the Redis cache in the last 5m | Expected when traffic is low; panel shows `noValue: "—"` by design |
| Deployment state shows `1` (failed) for a model | Cooldown or consecutive failures triggered by LiteLLM router | Check LiteLLM logs: `kubectl logs -n ai deploy/litellm --tail=50` |

---

## Dashboard 2 — AI ROI & Business Value

Dashboard UID: `ai-roi-v1` — `https://grafana.devandre.sbs/d/ai-roi-v1`

Answers the question **"Is the platform paying for itself?"** for a platform engineering lead or CFO. Sources: Prometheus for request volume (used to derive ROI) and the LiteLLM PostgreSQL database for actual API spend and adoption metrics.

### Business logic

Three constants are baked into the PromQL expressions:

| Constant | Value | Rationale |
|---|---|---|
| Time saved per query | 0.05 h (3 min) | Conservative estimate: AI answers a question in seconds that would take 3 min manual research |
| Knowledge-worker cost | 35 €/h | French average for a mid-level analyst |
| Platform cost | 50 €/month | Fixed: electricity + hardware amortisation for the 5-node ThinkPad cluster |

**Net ROI formula:**
```
Net ROI (€) = queries_30d × 0.05 h × 35 €/h − 50 €
```

The Net ROI stat panel is red when negative, yellow when 0–50 €, green above 50 €.

### Panels

| Section | Panel | Source | Query / SQL |
|---|---|---|---|
| Business KPIs | Queries — 30 d | Prometheus | `sum(increase(litellm_proxy_total_requests_metric_total[30d]))` |
| Business KPIs | Hours Saved — 30 d | Prometheus | queries × 0.05 |
| Business KPIs | Cost Avoidance — 30 d (€) | Prometheus | queries × 0.05 × 35 |
| Business KPIs | Actual API Spend — month ($) | PostgreSQL `litellm` | `SELECT COALESCE(SUM(spend),0) FROM "LiteLLM_SpendLogs" WHERE "startTime" >= date_trunc('month', NOW())` |
| Business KPIs | Platform Cost — month (€) | Prometheus | `vector(50)` |
| Business KPIs | Net ROI — 30 d (€) | Prometheus | queries × 0.05 × 35 − 50 |
| Adoption | Active Callers — 7 d | PostgreSQL `litellm` | `COUNT(DISTINCT COALESCE("user", 'anonymous'))` last 7 d |
| Adoption | Daily Request Volume | PostgreSQL `litellm` | `date_trunc('day', "startTime")`, COUNT(*), grouped by day |
| Spend Breakdown | Spend by Model | PostgreSQL `litellm` | requests, spend $, prompt/completion tokens per model, current month |
| Spend Breakdown | Spend by Caller | PostgreSQL `litellm` | requests, spend $ per API key caller, current month |

ConfigMap: `manifests/ai/20-ai-roi-dashboard.yaml`

---

## Dashboard 3 — RAG Quality & Indexing

Dashboard UID: `ai-rag-quality-v1` — `https://grafana.devandre.sbs/d/ai-rag-quality-v1`

Answers the question **"What is indexed in the knowledge base and is it healthy?"** Sources exclusively the `ragdb` PostgreSQL database (table `document_chunk`, powered by pgvector). No Qdrant — the RAG pipeline uses pgvector directly.

### New Grafana datasource: RAG PostgreSQL

Added in `helm-values/kube-prometheus-stack-values.yaml`:

```yaml
additionalDataSources:
  - name: RAG PostgreSQL
    uid: ragdb-postgres
    type: postgres
    access: proxy
    url: postgresql-ai.ai.svc.cluster.local:5432
    user: aiplatform
    isDefault: false
    editable: false
    secureJsonData:
      password: "${GF_LITELLM_PG_PASSWORD}"   # same user/password as LiteLLM PostgreSQL
    jsonData:
      database: ragdb
      sslmode: disable
      postgresVersion: 1400
```

The same `postgresql-ai` instance hosts both the `litellm` and `ragdb` databases for the same `aiplatform` user — no new secret or ESO resource is needed.

### `ragdb.document_chunk` schema

```sql
-- Queried by this dashboard
id              TEXT         -- chunk identifier
collection_name TEXT         -- UUID grouping chunks by ingest session
text            TEXT         -- raw chunk content
vmetadata       JSONB        -- {"source": "...", "section": "...", "document_type": "..."}
vector          USER-DEFINED -- pgvector embedding (1536-dim)
```

Current content (as of 2026-07-17): **942 chunks**, **3 source documents**, **1 collection** (Basel III Framework — regulatory).

### Panels

| Section | Panel | SQL |
|---|---|---|
| Index Health | Total Chunks | `SELECT COUNT(*) FROM document_chunk` |
| Index Health | Indexed Documents | `SELECT COUNT(DISTINCT vmetadata->>'source') FROM document_chunk` |
| Index Health | Collections | `SELECT COUNT(DISTINCT collection_name) FROM document_chunk` |
| Index Health | Avg Chunks / Document | `ROUND(COUNT(*) / COUNT(DISTINCT vmetadata->>'source'), 0)` |
| Document Detail | Documents by Source | source, doc_type, chunk count, avg chars/chunk — GROUP BY source |
| Document Detail | Doc Type Distribution | doc_type, chunk count, distinct docs — GROUP BY doc_type |
| Retrieval Metrics | Note panel | Explains per-query metrics not yet instrumented |

### Retrieval metrics — current limitation

Per-query signals (hit rate, similarity score, retrieval latency) are not available. The `rag-ingest` service does not expose a `/metrics` endpoint and does not log query results to Langfuse. To add these in a future phase:

1. Add `rag_retrieval_total{collection, status}` counter and `rag_retrieval_latency_seconds` histogram to `rag-ingest`
2. Add a ServiceMonitor for Prometheus scraping
3. Log cosine similarity scores per retrieved chunk to Langfuse as evaluation scores

ConfigMap: `manifests/ai/21-ai-rag-quality-dashboard.yaml`

---

## Alerting — PrometheusRule `ai-governance-alerts`

`manifests/ai/22-ai-governance-alerts.yaml` — deployed in namespace `monitoring` with labels `release: kube-prometheus-stack` so the Prometheus Operator picks it up.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: ai-governance-alerts
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:
    - name: ai-governance
      interval: 5m
```

### Alert 1 — `AIMonthlyAPISpendOverrun`

```yaml
expr: |
  (
    sum(increase(litellm_input_tokens_metric_total{api_provider="groq"}[30d])) * 0.00000005
    +
    sum(increase(litellm_output_tokens_metric_total{api_provider="groq"}[30d])) * 0.00000008
  ) > 5
for: 1h
severity: warning
```

Estimates Groq API spend from token volume using the `llama-3.1-8b-instant` public pricing: $0.05/M input tokens, $0.08/M output tokens. Fires when the 30-day rolling estimate exceeds $5 and has been above threshold for at least 1 hour.

Runbook link: `https://grafana.devandre.sbs/d/litellm-cost-dept`

### Alert 2 — `AIAdoptionLow`

```yaml
expr: sum(increase(litellm_proxy_total_requests_metric_total[24h])) < 5
for: 6h
severity: info
```

Fires when the platform has received fewer than 5 requests in the last 24 hours, sustained for 6 consecutive hours. This catches both zero-adoption periods and silent platform failures. The threshold (5 requests) is intentionally low for a portfolio-scale deployment.

Verify alerts loaded:
```bash
ssh controller "kubectl get prometheusrule -n monitoring ai-governance-alerts"
# Check Prometheus web UI → Alerts tab for the ai-governance group
```

---

## Langfuse metadata tagging

`manifests/ai/15-langfuse-prompt-handler-configmap.yaml` — the `LangfusePromptHandler` was extended so that **every** LLM request, regardless of model, receives structured Langfuse metadata tags.

### What changed in `async_pre_call_hook`

Step 1 (all models) now runs before step 2 (phi3-financial prompt injection):

```python
_MODEL_METADATA = {
    "phi3-financial": {
        "department": "finance",
        "use_case": "financial-advisory",
        "tags": ["department:finance", "use_case:financial-advisory"],
    },
}
_DEFAULT_METADATA = {
    "department": "general",
    "use_case": "general-assistant",
    "tags": ["department:general", "use_case:general-assistant"],
}

async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
    # Step 1: inject metadata for all models
    model = data.get("model", "")
    meta = _MODEL_METADATA.get(model, _DEFAULT_METADATA)
    md = data.setdefault("metadata", {})
    md.setdefault("department", meta["department"])
    md.setdefault("use_case", meta["use_case"])
    existing_tags = md.setdefault("tags", [])
    for tag in meta["tags"]:
        if tag not in existing_tags:
            existing_tags.append(tag)

    # Step 2: phi3-financial system-prompt injection (unchanged)
    if model != TARGET_MODEL:
        return data
    ...
```

LiteLLM forwards `data["metadata"]` to the Langfuse callback, which maps it to trace properties and tags. After this change, every Langfuse trace shows the business context of the request.

### Effect in Langfuse UI

```
Trace metadata:
  department:  finance          (or "general")
  use_case:    financial-advisory (or "general-assistant")
  tags:        ["department:finance", "use_case:financial-advisory"]
```

The `setdefault` pattern means callers can override these values per-request by passing their own `metadata` field — the hook only sets the defaults if the keys are absent.

Source of truth: `minicloud-litellm-custom/langfuse_prompt_handler.py` (`feat/qwen2.5-replace-phi4mini` branch, commit `567a5d2`). The cluster ConfigMap is a verbatim mirror — no image rebuild required to update it.

---

## GitOps references

| Commit/PR | What |
|---|---|
| minicloud-gitops PR #24 | Move LiteLLM `success_callback` to `litellm_settings` (ConfigMap fix) |
| minicloud-gitops PR #26 | Fix `LangfusePromptHandler` module-level instance (handler ConfigMap) |
| minicloud-gitops PR #28 | Phase 76: Infinity plugin + ESO + AI Governance dashboard |
| minicloud-gitops PR #30 | Complete AI-2: ROI dashboard, RAG dashboard, 2 alerts, Langfuse tagging |
| minicloud-litellm-custom commit 7673213 | Langfuse handler bugfixes in source repo |
| minicloud-litellm-custom commit 567a5d2 | Add department/use_case metadata tagging to handler |
