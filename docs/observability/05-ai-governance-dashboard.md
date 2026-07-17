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

Both dashboards are complementary. They answer different questions.

| | `litellm-cost-dept` (Phase 22) | `ai-governance-v1` (Phase 76) |
|---|---|---|
| **Source** | PostgreSQL `LiteLLM_SpendLogs` + `LiteLLM_VerificationToken` | Prometheus + Langfuse REST API (Infinity) |
| **View** | Financial — who spends what, budget utilisation per department | Operational — is the system healthy, how fast, how safe |
| **Time range** | 30 days default | 3 hours default (real-time) |
| **Refresh** | 5 min | 30 s |
| **Audience** | CIO, CFO, budget owners | Platform engineer, AI lead, CISO |
| **Key panels** | Spend USD, budget utilisation bar, tokens by model, spend by department | P95 latency, error rate, guardrail invocations, cache hit rate, deployment state |
| **Guardrails** | Not visible | Invocations/errors/latency for every Presidio PII scan |
| **Langfuse** | Not connected | Daily trace count + recent trace table |

Use `litellm-cost-dept` for monthly budget reviews and chargeback. Use `ai-governance-v1` for day-to-day operations, incident response, and compliance audit trails.

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

## GitOps references

| Commit/PR | What |
|---|---|
| minicloud-gitops PR #24 | Move LiteLLM `success_callback` to `litellm_settings` (ConfigMap fix) |
| minicloud-gitops PR #26 | Fix `LangfusePromptHandler` module-level instance (handler ConfigMap) |
| minicloud-gitops PR #28 | Phase 76: Infinity plugin + ESO + AI Governance dashboard |
| minicloud-litellm-custom commit 7673213 | Same fix in source repo |
