---
id: ai-gateway
title: AI Gateway — LiteLLM + PostgreSQL
sidebar_label: AI Gateway
---

# AI Gateway — LiteLLM + PostgreSQL

**Phase complete:** 2026-07-05 · **Hardened:** 2026-08-29 (epic #296)  
**Issues closed:** #34 (LiteLLM proxy), #41 (inference optimization), **#296 + #297–310 (Enterprise Hardening)**  
**GitOps:** `manifests/ai/` in minicloud-gitops — ArgoCD Application `litellm` Synced/Healthy · cloud IaC: `minicloud-cloud` (OpenTofu)

:::note Doc status
Sections below the *Enterprise Hardening* block describe the original 2026-07 design. Some details are now **superseded**: Ollama was dropped from the cluster (generation moved to **Ollama Cloud** + cloud providers; embeddings moved to **mistral-embed**, not `bge-m3`), and department key tiers are complemented by **sensitivity-tier RBAC**. The Enterprise Hardening section is the current source of truth for governance, routing, residency and audit.
:::

## AI Gateway Enterprise Hardening (Epic #296 — 2026-08-29)

Turned the gateway from "multi-model proxy" into a **governed, multi-cloud AI Platform** with EU data residency, sensitivity-based routing, per-consumer RBAC, PII masking, SLO/FinOps/residency observability, compliance alerting and a DORA audit trail. All 13 stories done (milestone #17 closed).

### Architecture (current)

```
callers (teams, RBAC-scoped keys)
        │
        ▼
  LiteLLM Gateway (:4000)  ── Presidio PII masking (pre_call, default_on)
        │
 ┌──────┼───────────────────────────────────────────────┐
 ▼      ▼                    ▼                    ▼
on-cluster (P3)         EU cloud (P2)        US enterprise (P1)   untrusted (P0-only)
vLLM phi3 / agents      mistral-* (Mistral)  gpt-4o / claude /    groq / nvidia / hf /
(sovereign)             AWS Bedrock (eu-west-1)  gemini             ollama-cloud / deepseek-CN
                        Azure OpenAI (Sweden C.)
```

Provider tiers are tagged with `model_info.access_group` (`onprem`/`eu`/`us`; untagged = P0-only). Teams are scoped to tiers → **confidential data can never reach an untrusted/CN provider**.

### What was delivered

| # | Story | Outcome |
|---|---|---|
| **P0** #297-300 | Cloud IaC foundation | Repo **`minicloud-cloud`** (OpenTofu, single tool, split by scope) · state **S3+DynamoDB** (EU) · **root AWS key deactivated → scoped IAM users** (`minicloud-tofu` provisioning, `litellm-bedrock` runtime) + Azure **Service Principal** · **€15/provider budget alerts** (AWS Budgets + Azure Cost) |
| **P1** #301-302 | Governance | **Model governance matrix** (per-model jurisdiction/residency/training-terms/max-class) + **4 data classes** P0-P3 → `minicloud-gitops/docs/ai-governance/model-governance-matrix.md` |
| **P2** #303-304 | Cloud tier (EU) | **AWS Bedrock** `bedrock-mistral-large` (eu-west-1) + **Azure OpenAI** `azure-gpt-4.1-mini` (Sweden Central, Standard-regional) — both EU-resident, wired via LiteLLM, tested e2e |
| **P3** #305-306 | Enforcement | `model_info.access_group` per model + **teams scoped to tiers** (`[onprem,eu,us]` → never untrusted P0/CN) + per-consumer budgets/tpm/rpm |
| **P4** #307-309 | Obs & audit | **Residency recording rules** (`ai:litellm_*_by_tier`, `out_of_eu_ratio`) + Grafana *Residency & Governance FinOps* · compliance alerts (`AIPresidioGuardrailErrors`=critical→email+Slack, out-of-EU, SLO, error-spike) · **DORA audit doc** (`docs/ai-governance/dora-audit.md`) |
| #310 | Embeddings fix | `nomic-embed-text` (dropped Ollama model) → **`mistral-embed`** (EU, 1024-dim) — restricted-doc (P3) embeddings now stay in the EU |

### Cost model
**AI tokens only** — Standard/on-demand tiers, no PTU/PrivateLink/cloud-monitoring/managed-KB. Cloud credentials live only in **Vault** (`secret/platform/cloud-providers`), reusable via `source scripts/load-env.sh` in `minicloud-cloud`.

### Compliance mapping
- **EU AI Act:** governance matrix = technical documentation + risk tiers.
- **DORA:** matrix = ICT third-party register; Langfuse per-call audit trail (retention **365d**); LiteLLM gateway = provider-swap-as-config exit strategy; on-cluster vLLM fallback.
- **GDPR/ACPR:** PII masked pre-call (Presidio); restricted (P3) data confined to on-cluster/EU tiers.

**Detailed governance docs** (in `minicloud-gitops/docs/ai-governance/`): `model-governance-matrix.md` · `dora-audit.md`.

### Routing: two independent axes (design decision)

A common expectation is that "the gateway decides which model to use" — *simple
question → cheap model, complex analysis → premium, ultra-confidential → private*.
Those examples actually mix **two orthogonal axes**, and this gateway deliberately
automates only one:

| Axis | Question | Who decides | Status here |
|---|---|---|---|
| **Sensitivity** (confidentiality) | *may this data go to this provider?* | **the gateway** | ✅ **automatic & enforced** |
| **Complexity / cost** (cheap vs premium) | *is a big model worth it here?* | **the calling application** | 🟡 app-driven (by design) |

**Design decision — sensitivity first.** In a regulated (insurance) IS, compliance
and security must **always** win over FinOps optimisation. The gateway therefore
applies **hard governance on the sensitivity axis** — `model_info.access_group`
per model + tier-scoped RBAC keys + Presidio PII masking — so confidential data
**can never** reach an untrusted/CN provider, regardless of what the caller asks
for. This is enforced, not advisory.

**Why complexity routing is left to the application.** Deciding "simple vs
complex" automatically means either a magic classifier (adds latency, opacity, an
extra decision point to govern) or brittle heuristics. The application knows its
own intent far better than a guesser — so it selects the model **explicitly**.
The gateway's job is to make that choice *safe* (a P3 key still can't escape the
EU/on-cluster tier even if it asks for a US premium model) and *portable* (aliases,
not hard-coded SKUs).

**How each example maps today:**

| Flow | Handled by |
|---|---|
| Ultra-confidential → private/EU | ✅ gateway (sensitivity RBAC — automatic) |
| No big model needed → local Llama (vLLM) | app picks the `phi3-financial` (on-cluster) alias |
| Simple question → cheap model | app picks `gpt-4o-mini` / `mistral-small` |
| Complex analysis → premium | app picks `claude-sonnet` / `bedrock-mistral-large` |
| RAG → specialised | app assembles the pipeline (`mistral-embed` + a generator) |

### Resilience & rate-limit handling

Independent of the two routing axes, three layers keep the gateway available even
on rate-limited **free-tier** providers. Fallback chains **never cross a
governance tier** (free↔free, EU↔EU) so a failover cannot leak data out of its
residency class.

| Layer | Mechanism | Behaviour |
|---|---|---|
| **0 — Semantic cache** | Valkey `redis-semantic`, similarity ≥ 0.8, TTL 600s | Near-duplicate prompts are served from cache — fewer provider calls, fewer 429s at the source |
| **1 — Key rotation / load-balance** | `routing_strategy: least-busy` + `num_retries: 3`, `allowed_fails: 3`, `cooldown_time: 60` | A model declared N times (e.g. `ollama-cloud` ×3 keys) is load-balanced; a backend that returns 429 `allowed_fails` times is cooled for 60s and retries route to another key — the next key takes over automatically |
| **2 — Cross-model fallback** | `router_settings.fallbacks` | When **all** keys of a model are cooled, fall through to a same-tier alternative |

Current fallback chains (`manifests/ai/00-litellm-configmap.yaml`):

```
free (dev):   ollama-cloud (3 keys) ⇄ nvidia-nano-30b        # 4 paths before failure
EU (prod):    bedrock-mistral-large → mistral-large → mistral-small
```

**Not everything gets a fallback on purpose:** embeddings have none —
`nvidia-embed` (2048-dim) and `mistral-embed` (1024-dim) differ in dimension, and
a cross-dim failover would poison the Qdrant collection; embeddings rely on
retries/cooldown only. On-cluster models (`phi3-financial`, vision) have no cloud
fallback so sensitive content stays on-prem. A chronic free-tier saturation is
surfaced by the **`AIProviderErrorSpike`** alert + the Grafana error-rate panel.

**Recommended pattern — intent aliases (not hard-coded model names).** Applications
should target **functional aliases** by intent rather than provider SKUs, so the
cost/performance ratio is a config decision, not code:

- `chat-fast` / `tier-economy` → cheap models (mistral-small, gpt-4o-mini)
- `chat-reasoning` / `tier-premium` → premium (claude-sonnet, bedrock-mistral-large)
- `embeddings` → `mistral-embed` (EU)

This keeps complexity/cost app-driven **and** governed: the alias resolves only to
backends the caller's tier is allowed to reach (sensitivity × intent). Wiring these
intent aliases (LiteLLM `model_group_alias`) is a tracked backlog item —
**complexity/cost-aware routing, Option 1** (explicit intent), preferred over an
automatic semantic router whose latency/infra cost usually outweighs the savings.

---

## Architecture

```
Open WebUI ──► LiteLLM Gateway (:4000)
                     │
                     ├── Ollama primary   (fast-heron,  :11434)  ← local-first
                     ├── Ollama secondary (star-kitten, :11434)  ← local-first
                     │
                     ├── Groq             (llama-3.1-8b-instant) ← auto-fallback #1
                     ├── DeepSeek         (deepseek-chat)        ← auto-fallback #2
                     ├── Mistral          (large, small)         ← premium/standard
                     ├── Anthropic        (claude-sonnet, haiku) ← premium
                     ├── OpenAI           (gpt-4o, gpt-4o-mini)  ← premium/standard
                     ├── Gemini           (gemini-2.5-flash)     ← premium/standard
                     ├── HuggingFace      (Qwen/Gemma via featherless-ai) ← standard
                     └── NVIDIA NIM       (nemotron-70b, llama-8b, deepseek-r1) ← premium/standard

LiteLLM ──► Valkey cache   (:6379)    ← exact-match prompt dedup, 10 min TTL
LiteLLM ──► Langfuse       (:3000)    ← trace every call with token/cost/model metadata
```

All components in the `ai` namespace. LiteLLM is the single OpenAI-compatible endpoint — Open WebUI talks only to LiteLLM, never to Ollama directly.

## Components

| Component | Image | Storage | Node |
|---|---|---|---|
| LiteLLM gateway | `harbor.10.0.0.200.nip.io/library/litellm:1.90.3-guardrails-v1` | stateless | any |
| PostgreSQL (ai) | `harbor.10.0.0.200.nip.io/library/postgresql:18.4.0` | Longhorn 5Gi | any |
| Ollama primary | `ollama/ollama` | local-path 10Gi | fast-heron |
| Ollama secondary | `ollama/ollama` | local-path 10Gi | star-kitten |
| Valkey cache | `valkey/valkey:8.1-alpine` | local-path 1Gi | any |

## Models

### Local models (data stays on-premise)

| Model name | Size | Capability | Tier access |
|---|---|---|---|
| `phi3-financial` | 2.2 GB | Finance-domain text, restricted | premium, standard |
| `qwen3.5:4b` | 3.4 GB | General text, native tool calling | premium, standard |
| `phi4-mini` | 2.5 GB | Instruction following, technical | all |
| `deepseek-r1:7b` | 4.7 GB | Reasoning — math, code, logic | premium |
| `llama3.2:1b` | 1.3 GB | Ultra-fast, simple queries | all |
| `moondream` | 1.7 GB | **Vision** — fast OCR, image description | premium, standard |
| `llava-phi3` | 2.9 GB | **Vision** — detailed image analysis, document OCR | premium |
| `bge-m3` | 1.2 GB | **Embeddings** — 1024-dim vectors, 100+ languages, French RAG | premium, standard |

`phi3-financial` and vision models (`moondream`, `llava-phi3`) have no cloud fallback — sensitive content stays on-premise.

`bge-m3` is available via `/v1/embeddings`. Open WebUI calls Ollama directly (bypassing LiteLLM) for RAG embeddings to avoid polluting cost tracking — see [RAG Pipeline](rag-pipeline).

### Cloud models (premium and standard tiers)

| Model name | Backend | Tier access |
|---|---|---|
| `groq-fallback` | `groq/llama-3.1-8b-instant` | automatic fallback only |
| `deepseek-chat` | `deepseek/deepseek-chat` | automatic fallback + standard |
| `mistral-large` | `mistral/mistral-large-latest` | premium |
| `mistral-small` | `mistral/mistral-small-latest` | premium, standard |
| `claude-sonnet` | `anthropic/claude-3-5-sonnet-20241022` | premium |
| `claude-haiku` | `anthropic/claude-3-haiku-20240307` | premium |
| `gpt-4o` | `openai/gpt-4o` | premium |
| `gpt-4o-mini` | `openai/gpt-4o-mini` | premium, standard |
| `gemini-2.0-flash` | `gemini/gemini-2.5-flash` | premium, standard |
| `gemini-1.5-pro` | `gemini/gemini-2.5-flash` | premium |
| `hf-qwen` | `Qwen/Qwen2.5-1.5B-Instruct` via featherless-ai | premium, standard |
| `hf-gemma` | `google/gemma-2-2b-it` via featherless-ai | premium, standard |
| `nvidia-nemotron-70b` | `nvidia/llama-3.1-nemotron-70b-instruct` via NVIDIA NIM | premium |
| `nvidia-llama-8b` | `meta/llama-3.1-8b-instruct` via NVIDIA NIM | premium, standard |
| `nvidia-deepseek-r1` | `deepseek-ai/deepseek-r1` via NVIDIA NIM | premium, standard |

`gemini-2.0-flash` and `gemini-1.5-pro` are model_name aliases kept for department key compatibility — both route to `gemini/gemini-2.5-flash` behind the scenes.

**qwen3.5:4b thinking mode:** qwen3 generates reasoning tokens (think phase) before the answer. Set `max_tokens ≥ 500` — small values exhaust the token budget on reasoning, leaving `content` empty. For simple fast queries without thinking overhead, use `phi4-mini` or `llama3.2:1b`.

**HuggingFace routing note:** `api-inference.huggingface.co` was retired in 2025. HF models use `https://router.huggingface.co/featherless-ai/v1` (OpenAI-compatible, free-tier provider). LiteLLM config uses `openai/` provider type with explicit `api_base` and `HUGGINGFACE_API_KEY`.

**NVIDIA NIM routing note:** NVIDIA's inference API at `https://integrate.api.nvidia.com/v1` is OpenAI-compatible. LiteLLM uses the `openai/` provider type with explicit `api_base` and `NVIDIA_API_KEY`. Model IDs use the full `org/model-name` format (e.g. `openai/nvidia/llama-3.1-nemotron-70b-instruct`). Key registered at `build.nvidia.com`, stored in Vault at `secret/platform/cloud-providers` as `nvidia-api-key`, added 2026-07-07.

## Routing strategy

`router_settings.routing_strategy: least-busy` — LiteLLM picks the backend with the fewest in-flight requests.

**Cloud fallback** — Groq then DeepSeek activate only when both Ollama backends exhaust `num_retries: 2`:

```yaml
router_settings:
  routing_strategy: least-busy
  num_retries: 2
  timeout: 120
  # Circuit breaker: after 3 consecutive failures a backend is marked
  # degraded for 60 s — prevents a hung Ollama draining the retry budget.
  cooldown_time: 60
  allowed_fails: 3
  fallbacks:
    - qwen3.5:4b:
        - groq-fallback
        - deepseek-chat
    - phi4-mini:
        - groq-fallback
        - deepseek-chat
    - llama3.2:1b:
        - groq-fallback
        - deepseek-chat
```

`phi3-financial` has no cloud fallback — financial prompts must stay on-premise.

**Circuit breaker behaviour:** if one Ollama node becomes slow or unresponsive, LiteLLM stops routing to it after 3 failures and retries on the other Ollama node (or the Groq/DeepSeek fallback for llama models) for 60 seconds. Without this, a hung backend absorbs retries from every incoming request until `timeout` fires.

## PostgreSQL databases

| Database | Owner | Used by |
|---|---|---|
| `openwebui` | `aiplatform` | Open WebUI session/user data |
| `litellm` | `aiplatform` | LiteLLM virtual keys, spend tracking |

Credentials: ESO ExternalSecret `ai-postgresql-secret` ← Vault KV `secret/platform/ai-postgresql`.

## Department virtual key tiers

15 keys pre-provisioned (stored at `~/.litellm-department-keys` on controller, mode 600).

| Tier | Departments | TPM | RPM | Budget / 30 d | Allowed models |
|---|---|---|---|---|---|
| **premium** | IT, Data Analytics, Actuariat, Transformation | 200k | 500 | **$100** | all models (local + cloud + vision) |
| **standard** | Cybersecurity, Audit, Finance, Reinsurance, Juridique, Souscription, Commercial | 100k | 200 | **$30** | phi3-financial, qwen3.5:4b, phi4-mini, llama3.2:1b, moondream + groq + deepseek + mistral-small + gpt-4o-mini + gemini-2.0-flash + hf-qwen + hf-gemma |
| **basic** | Sinistres, Operations, RH, Services Généraux | 50k | 100 | **$5** | phi3-financial, phi4-mini, llama3.2:1b |

`budget_duration: 30d` resets automatically. When `max_budget` is reached LiteLLM returns HTTP 429 (`BudgetExceededError`) for that key until the next reset.

Update a key's rate limits or budget:

```bash
MASTER_KEY=$(kubectl get secret -n ai litellm-credentials -o jsonpath='{.data.master-key}' | base64 -d)
kubectl port-forward -n ai svc/litellm 4000:4000 &

curl -X POST http://localhost:4000/key/update \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "sk-<dept-key>",
    "tpm_limit": 200000,
    "rpm_limit": 500,
    "max_budget": 100.0,
    "budget_duration": "30d",
    "models": ["phi3-financial", "llama3.2:3b", "gpt-4o"],
    "metadata": {"department": "direction-it", "tier": "premium"}
  }'
```

**API field name gotcha:** the budget cap field is `max_budget` (not `budget_limit`) — the LiteLLM API docs sometimes show both names but only `max_budget` is persisted.

Verify current spend and budget for all keys:

```bash
curl -s -H "Authorization: Bearer $MASTER_KEY" http://localhost:4000/key/list \
  | python3 -m json.tool | grep -E 'key_alias|spend|max_budget'
```

## Prompt caching (Valkey)

Exact-match Redis cache. Identical prompts (same model + messages) return the cached response without hitting inference — typically 80ms vs 2500ms for a cold call.

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: litellm-cache.ai.svc.cluster.local
    port: 6379
    ttl: 600      # 10 minutes
    namespace: litellm
```

Check cache stats: `kubectl exec -n ai litellm-cache-0 -- valkey-cli info stats | grep hit`

## PII / DLP guardrail (Presidio)

Microsoft Presidio runs as two in-cluster services (`presidio-analyzer` + `presidio-anonymizer`, both in the `ai` namespace, `mcr.microsoft.com/presidio-*:2.2.362`). LiteLLM's `pre_call` guardrail `presidio-pii-masking` intercepts every prompt before it reaches any model.

**What it does:** Presidio analyzer detects PII entities in user prompts and the anonymizer replaces them with typed placeholders **before the prompt is forwarded to any cloud model**:

```
"Client jean.dupont@acme.com phone +33612345678 wants a quote"
     ↓ Presidio pre_call guardrail (input only)
"Client <EMAIL_ADDRESS> phone <PHONE_NUMBER> wants a quote"
     ↓ sent to cloud model (GPT-4o, Claude, Gemini, etc.)
```

**Why this matters:** Local models (phi3-financial, phi4-mini) keep data on-cluster. Cloud models (GPT-4o, Claude, Groq, DeepSeek, Mistral, HF) send the prompt to an external API — Presidio ensures the external API never receives raw PII. Covers models with cloud fallbacks too (if Ollama is down, PII is still anonymized before Groq receives it).

**Scope: input only.** `output_parse_pii` is intentionally NOT set. Anonymizing LLM responses would replace country names, public figures and sports results with `<LOCATION>`/`<PERSON>` placeholders, making general-knowledge responses unreadable. The security goal is protecting user data sent *to* cloud providers — not transforming the model's *output*.

**Fail mode:** `default_on: true` — guardrail is active on all requests by default.

```yaml
guardrails:
  - guardrail_name: "presidio-pii-masking"
    litellm_params:
      guardrail: presidio
      mode: pre_call          # input protection only — output_parse_pii NOT set
      presidio_analyzer_api_base: "http://presidio-analyzer.ai.svc.cluster.local:3000"
      presidio_anonymizer_api_base: "http://presidio-anonymizer.ai.svc.cluster.local:3000"
      default_on: true
```

Verify Presidio is active:
```bash
MASTER=$(kubectl get secret -n ai litellm-credentials -o jsonpath='{.data.master-key}' | base64 -d)
kubectl port-forward -n ai svc/litellm 4000:4000 &
curl -s -H "Authorization: Bearer $MASTER" http://localhost:4000/guardrails/list | python3 -m json.tool
```

**Presidio gotcha:** Both `presidio-analyzer` and `presidio-anonymizer` MCR images listen on port **3000** (gunicorn default) — not 3000/5001 as the Presidio docs suggest for local dev.

**output_parse_pii gotcha:** Setting `output_parse_pii: true` anonymizes the LLM's response text. Presidio treats country names ("France", "Cameroun"), historical figures and dates as LOCATION/PERSON/DATE_TIME entities. A sports question gets back `"<LOCATION> a battu <LOCATION> <DATE_TIME>"` — unreadable. Only set `output_parse_pii` if your use case specifically requires redacting model outputs (e.g., a system that echoes back user-submitted documents).

## Secret scanning guardrail (detect-secrets)

`general_settings.detect_secrets_on_all_keys: true` — LiteLLM scans every prompt using the `detect-secrets` library before forwarding to inference. Prompts containing high-confidence credential patterns (real API keys, tokens, connection strings) are rejected with HTTP 400.

The `detect-secrets` library is pre-installed in the base Wolfi venv (`/app/.venv`). Known-safe documentation example keys (e.g., AWS `AKIAIOSFODNN7EXAMPLE`) pass through — only high-entropy real credentials are blocked.

Both guardrails (`presidio-pii-masking` and `detect_secrets_on_all_keys`) run in sequence on every request.

## Langfuse tracing

Every call produces a Langfuse trace with token counts, cost estimate, model used, department (from virtual key metadata), and latency.

```yaml
general_settings:
  success_callback: ["langfuse", "prometheus"]
  failure_callback: ["prometheus"]
  langfuse_host: "http://langfuse-web.langfuse.svc.cluster.local:3000"
```

LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY injected from ESO-synced `litellm-credentials` secret.

**Prometheus note:** `success_callback: ["prometheus"]` is configured and the ServiceMonitor (`manifests/ai/06-litellm-servicemonitor.yaml`) is in git. However, LiteLLM 1.90.3's `PrometheusLogger._mount_metrics_endpoint()` registers the `/metrics` route via `app.mount()` after Starlette startup — the route does not take effect. Prometheus scraping from LiteLLM directly requires a future image rebuild. The Grafana cost dashboard below uses the PostgreSQL spend tables instead and is fully functional.

## Cost dashboard (Grafana)

Live at `https://grafana.10.0.0.200.nip.io/d/litellm-cost-dept/` (also available at `https://grafana.devandre.sbs/d/litellm-cost-dept/`).

**Datasource:** `litellm-postgres` (PostgreSQL, UID `litellm-postgres`) — points directly at the `litellm` database in the `ai` namespace PostgreSQL pod. Provisioned via Grafana API; credentials NOT in git.

```bash
# Re-provision the datasource if the Grafana pod is replaced:
MASTER=$(kubectl get secret -n ai litellm-credentials -o jsonpath='{.data.master-key}' | base64 -d)
GRAFANA_PASS=$(ssh controller cat ~/.grafana-admin)
curl -X POST -u "admin:$GRAFANA_PASS" https://grafana.10.0.0.200.nip.io/api/datasources \
  --cacert ~/minicloud-ca.crt -H "Content-Type: application/json" -d '{
    "name": "litellm-postgres",
    "type": "postgres",
    "url": "ai-postgresql.ai.svc.cluster.local:5432",
    "user": "aiplatform",
    "database": "litellm",
    "uid": "litellm-postgres",
    "secureJsonData": {"password": "<aiplatform-password>"},
    "jsonData": {"sslmode": "disable"}
  }'
```

The dashboard ConfigMap (`manifests/ai/07-litellm-grafana-dashboard.yaml`) is in the `monitoring` namespace with `grafana_dashboard: "1"` — the Grafana sidecar auto-loads it.

**8 panels:**

| # | Type | Query |
|---|---|---|
| 1 | Stat | Total spend last 24 h (USD) |
| 2 | Stat | Total tokens last 24 h |
| 3 | Stat | Requests last 24 h |
| 4 | Stat | Active departments (30 d) |
| 5 | Table | **Department budget utilisation** — spend, budget, used% (colour thresholds: green < 70%, yellow < 90%, red ≥ 90%) |
| 6 | Bar gauge | Token usage by model last 30 d |
| 7 | Table | Requests by model last 30 d |
| 8 | Table | Recent requests (last 50) — audit trail with department column |

Key SQL joins `LiteLLM_SpendLogs` (per-request records) with `LiteLLM_VerificationToken` (key metadata including `max_budget`) on `api_key = token`:

```sql
SELECT key_alias as "Department",
       ROUND(spend::numeric, 6) as "Spend (USD)",
       max_budget as "Budget (USD)",
       budget_duration as "Period",
       CASE WHEN max_budget > 0
            THEN ROUND((spend / max_budget * 100)::numeric, 1)
            ELSE 0 END as "Used %"
FROM "LiteLLM_VerificationToken"
WHERE key_alias LIKE 'direction-%'
ORDER BY spend DESC
```

## Cloud provider secrets

API keys in Vault at `secret/platform/cloud-providers`:

```bash
VAULT_TOKEN=$(cat ~/.vault-root-token)
kubectl exec -n vault vault-0 -- \
  env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN="$VAULT_TOKEN" \
  vault kv get secret/platform/cloud-providers
```

ESO ExternalSecret `litellm-credentials` (file `manifests/eso-platform-secrets/10-ai-postgresql.yaml`) syncs 8 cloud provider keys from `secret/platform/cloud-providers` into `ai/litellm-credentials`: `groq-api-key`, `openai-api-key`, `gemini-api-key`, `deepseek-api-key`, `mistral-api-key`, `anthropic-api-key`, `hf-token`, `nvidia-api-key`.

NetworkPolicy `allow-litellm-cloud-egress` permits port 443 egress only from `app=litellm` pods — Ollama and Open WebUI remain internet-blocked.

## Custom LiteLLM image (`1.90.3-guardrails-v1`)

Three fixes over the upstream `ghcr.io/berriai/litellm-database` Wolfi OS base:

| Fix | Reason |
|---|---|
| `chmod -R 755 /root/.cache/prisma-python` | Prisma `BINARY_PATHS` hardcodes root-owned paths; UID 1000 gets PermissionError before override env vars load |
| `apk add --no-cache libatomic` | Node.js binary (used by Prisma CLI) needs `libatomic.so.1`, absent on newer nodes |
| Install `google-generativeai>=0.8.0` via venv pip | Missing from base image; required for `gemini/` provider |

Source: `~/Developer/cloudplateform/litellm-custom/Dockerfile`

Rebuild:
```bash
cd ~/Developer/cloudplateform/litellm-custom
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build --platform linux/amd64 \
  -t "litellm:1.90.3-guardrails-v1-amd64" .
docker save "litellm:1.90.3-guardrails-v1-amd64" -o /tmp/litellm.tar
crane push /tmp/litellm.tar "harbor.10.0.0.200.nip.io/library/litellm:1.90.3-guardrails-v1"
rm /tmp/litellm.tar
```

**Important Wolfi gotchas:**
- Package manager is `apk` (not `apt`) — Wolfi is Alpine-compatible
- No global `pip`/`pip3` — use `/app/.venv/bin/python -m ensurepip && /app/.venv/bin/python -m pip install`
- `callbacks: ["detect_secrets"]` in `litellm_settings` is NOT a valid proxy callback in 1.90.3 — causes `ImportError`. Use `general_settings.detect_secrets_on_all_keys: true` instead

## Inference tuning (both Ollama instances)

```yaml
OLLAMA_NUM_PARALLEL: "4"
OLLAMA_NUM_THREADS: "6"
OLLAMA_MAX_LOADED_MODELS: "2"
OLLAMA_FLASH_ATTENTION: "1"
OLLAMA_KV_CACHE_TYPE: "q8_0"
OLLAMA_NUM_CTX: "4096"
```

CPU governor set to `performance` on all 4 cluster nodes (persistent via `cpu-performance.service`).

## Health check

```bash
kubectl port-forward -n ai svc/litellm 4000:4000 &
MASTER=$(kubectl get secret -n ai litellm-credentials -o jsonpath='{.data.master-key}' | base64 -d)

# Health
curl http://localhost:4000/health/readiness
# Expected: {"status": "healthy", "db": "connected"}

# Model list
curl -H "Authorization: Bearer $MASTER" http://localhost:4000/v1/models | python3 -m json.tool

# Test local
curl -H "Authorization: Bearer $MASTER" -H 'Content-Type: application/json' \
  http://localhost:4000/v1/chat/completions \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":5}'

# Test Gemini
curl -H "Authorization: Bearer $MASTER" -H 'Content-Type: application/json' \
  http://localhost:4000/v1/chat/completions \
  -d '{"model":"gemini-2.0-flash","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":5}'
```

## Adding models to Ollama

```bash
SECONDARY_POD=$(kubectl get pods -n ai -l app.kubernetes.io/instance=ollama-secondary \
  -o jsonpath='{.items[0].metadata.name}')

# Temp egress for model pull (delete after)
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: temp-allow-ollama-pull
  namespace: ai
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/instance: ollama-secondary
  egress:
  - ports:
    - port: 443
  policyTypes:
  - Egress
EOF

# Pull via REST (avoids TTY requirement)
kubectl port-forward -n ai pod/$SECONDARY_POD 11434:11434 &
curl -X POST http://localhost:11434/api/pull -d '{"model":"phi3.5","stream":false}'

kubectl delete networkpolicy temp-allow-ollama-pull -n ai
```

## All secrets in Vault

```bash
VAULT_TOKEN=$(cat ~/.vault-root-token)
VE() { kubectl exec -n vault vault-0 -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN="$VAULT_TOKEN" vault kv get "$1"; }

VE secret/platform/ai-postgresql    # DB credentials
VE secret/platform/litellm          # master key, Langfuse keys
VE secret/platform/cloud-providers  # Groq, OpenAI, Gemini, DeepSeek, Mistral, Anthropic, HuggingFace, NVIDIA API keys
```
