---
id: ai-gateway
title: AI Gateway — LiteLLM + PostgreSQL
sidebar_label: AI Gateway
---

# AI Gateway — LiteLLM + PostgreSQL

**Phase complete:** 2026-07-04  
**Issues closed:** #34 (LiteLLM proxy), #41 (inference optimization)  
**GitOps:** `manifests/ai/` in minicloud-gitops — ArgoCD Application `litellm` Synced/Healthy

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
                     └── HuggingFace      (Qwen/Gemma via featherless-ai) ← standard

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

| Model name | Backend | Tier access |
|---|---|---|
| `phi3-financial` | Ollama (both) | premium, standard |
| `llama3.2:3b` | Ollama (both) → Groq → DeepSeek | premium, standard |
| `llama3.2:1b` | Ollama (both) → Groq → DeepSeek | all |
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

`gemini-2.0-flash` and `gemini-1.5-pro` are model_name aliases kept for department key compatibility — both route to `gemini/gemini-2.5-flash` behind the scenes.

**HuggingFace routing note:** `api-inference.huggingface.co` was retired in 2025. HF models use `https://router.huggingface.co/featherless-ai/v1` (OpenAI-compatible, free-tier provider). LiteLLM config uses `openai/` provider type with explicit `api_base` and `HUGGINGFACE_API_KEY`.

## Routing strategy

`router_settings.routing_strategy: least-busy` — LiteLLM picks the backend with the fewest in-flight requests.

**Cloud fallback** — Groq then DeepSeek activate only when both Ollama backends exhaust `num_retries: 2`:

```yaml
router_settings:
  fallbacks:
    - llama3.2:3b:
        - groq-fallback
        - deepseek-chat
    - llama3.2:1b:
        - groq-fallback
        - deepseek-chat
```

`phi3-financial` has no cloud fallback — financial prompts must stay on-premise.

## PostgreSQL databases

| Database | Owner | Used by |
|---|---|---|
| `openwebui` | `aiplatform` | Open WebUI session/user data |
| `litellm` | `aiplatform` | LiteLLM virtual keys, spend tracking |

Credentials: ESO ExternalSecret `ai-postgresql-secret` ← Vault KV `secret/platform/ai-postgresql`.

## Department virtual key tiers

16 keys pre-provisioned (stored at `~/.litellm-department-keys` on controller, mode 600).

| Tier | Departments | TPM | RPM | Allowed models |
|---|---|---|---|---|
| **premium** | IT, Data Analytics, Actuariat, Transformation | 200k | 500 | all 15 models |
| **standard** | Cybersecurity, Audit, Finance, Reinsurance, Juridique, Souscription, Commercial | 100k | 200 | local + groq + deepseek + mistral-small + gpt-4o-mini + gemini-2.0-flash + hf-qwen + hf-gemma |
| **basic** | Sinistres, Operations, RH, Services Généraux | 50k | 100 | phi3-financial only |

Update a key's limits:

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
    "models": ["phi3-financial", "llama3.2:3b", "gpt-4o"],
    "metadata": {"department": "direction-it", "tier": "premium"}
  }'
```

To bulk-update all 15 keys: scp `/tmp/update_keys.py` (on controller) and run it with `kubectl port-forward` active.

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

## Secret scanning guardrail

`general_settings.detect_secrets_on_all_keys: true` — LiteLLM scans every prompt using the `detect-secrets` library before forwarding to inference. Prompts containing high-confidence credential patterns (real API keys, tokens, connection strings) are rejected with HTTP 400.

The `detect-secrets` library is pre-installed in the base Wolfi venv (`/app/.venv`). Known-safe documentation example keys (e.g., AWS `AKIAIOSFODNN7EXAMPLE`) pass through — only high-entropy real credentials are blocked.

## Langfuse tracing

Every call produces a Langfuse trace with token counts, cost estimate, model used, department (from virtual key metadata), and latency.

```yaml
general_settings:
  success_callback: ["langfuse"]
  langfuse_host: "http://langfuse-web.langfuse.svc.cluster.local:3000"
```

LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY injected from ESO-synced `litellm-credentials` secret.

## Cloud provider secrets

API keys in Vault at `secret/platform/cloud-providers`:

```bash
VAULT_TOKEN=$(cat ~/.vault-root-token)
kubectl exec -n vault vault-0 -- \
  env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN="$VAULT_TOKEN" \
  vault kv get secret/platform/cloud-providers
```

ESO ExternalSecret `litellm-credentials` (file `manifests/eso-platform-secrets/10-ai-postgresql.yaml`) syncs 7 cloud provider keys from `secret/platform/cloud-providers` into `ai/litellm-credentials`: `groq-api-key`, `openai-api-key`, `gemini-api-key`, `deepseek-api-key`, `mistral-api-key`, `anthropic-api-key`, `hf-token`.

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
VE secret/platform/cloud-providers  # Groq, OpenAI, Gemini API keys
```
