---
id: content-safety
title: Content Safety — LiteLLM Pre-Call Hook
sidebar_label: Content Safety
---

# Content Safety — LiteLLM Pre-Call Hook

**Phase complete:** 2026-08-02  
**GitOps:** `manifests/ai/23-llamaguard-handler-configmap.yaml` — mounted into LiteLLM pod at `/app/llamaguard_handler.py`

Every prompt passes through a content safety classifier before it reaches any model. Harmful requests are rejected with HTTP 500 before any tokens are generated or billed.

---

## Architecture

```
Client (Open WebUI / API)
       │
       ▼
LiteLLM Gateway (:4000)
       │
       ├── async_pre_call_hook ─── LlamaGuardHandler
       │         │
       │         ├── groq/openai/gpt-oss-safeguard-20b
       │         │     • custom safety policy in system message
       │         │     • returns JSON {violation, category, reasoning}
       │         │
       │         ├── violation=0 → request continues to model
       │         └── violation=1 → raise ValueError → HTTP 500 (blocked)
       │
       └── model backend (mistral, groq, etc.)
```

The hook runs on every `POST /v1/chat/completions` call, regardless of which model is selected. The Presidio PII masking guardrail (separate, always-on) runs independently.

---

## Safety model

### Current model: `groq/openai/gpt-oss-safeguard-20b`

Groq discontinued `llama-guard-3-8b` (June 2025) and `meta-llama/llama-guard-4-12b` (March 2026). The current recommendation is `openai/gpt-oss-safeguard-20b`, which uses a **custom safety policy** defined in a system message rather than a fixed category taxonomy.

The model returns structured JSON:

```json
{"violation": 1, "category": "weapons", "reasoning": "User requests instructions for creating an explosive device"}
```

### Blocked categories

| Category | Description |
|---|---|
| `violent_crimes` | Instructions for violence, murder, assault |
| `weapons` | Weapons, explosives, improvised devices |
| `terrorism` | Planning or facilitating terrorist or mass-casualty acts |
| `csam` | Sexual content involving minors |
| `hate_speech` | Incitement against protected characteristics |
| `self_harm` | Detailed suicide or self-injury methods |
| `non_violent_crimes` | Step-by-step instructions for fraud, hacking, drug synthesis |

### Always allowed

Financial and insurance advisory — including detailed regulatory, compliance, product, and risk topics — is the platform's purpose. The safety policy explicitly permits:

- Insurance policy analysis, product comparison, risk modelling
- Financial regulation (Solvency II, MiFID, AMF, ACPR)
- Legal and medical information (general, not self-harm)
- Coding assistance, science, history, general knowledge

---

## Implementation

The handler is a LiteLLM `CustomLogger` subclass registered via `litellm_settings.callbacks` in the LiteLLM ConfigMap.

```python
class _LlamaGuardHandler(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        user_message = _extract_user_message(data.get("messages", []))
        if not user_message:
            return data

        is_safe, category = await _classify(user_message)
        if is_safe:
            return data

        if category not in BLOCKED_CATEGORIES:
            # flagged but not in blocked set — log and allow
            return data

        raise ValueError(f"Content safety policy violation: {category}.")
```

`_classify()` calls `groq/openai/gpt-oss-safeguard-20b` with:
- A system message containing the full safety policy
- The user message to evaluate
- `max_tokens=150, temperature=0`

**Fail-open:** any Groq API failure (timeout, rate limit, model unavailable) logs a `WARNING` and allows the request through. The platform prioritises availability over blocking on infrastructure failures.

---

## ConfigMap mounting

The handler is stored in a Kubernetes ConfigMap (`llamaguard-handler`) and mounted into the LiteLLM pod as a file:

```yaml
# manifests/ai/01-litellm-deployment.yaml
volumeMounts:
  - name: llamaguard-handler
    mountPath: /app/llamaguard_handler.py
    subPath: handler.py
volumes:
  - name: llamaguard-handler
    configMap:
      name: llamaguard-handler
```

Reloader (`stakater/Reloader`) watches the ConfigMap. Any change to the safety policy triggers a rolling restart of LiteLLM automatically — no manual rollout needed.

---

## Updating the policy

1. Edit `manifests/ai/23-llamaguard-handler-configmap.yaml`
2. Open a PR → merge to `main`
3. ArgoCD applies the ConfigMap within 3 minutes
4. Reloader restarts LiteLLM within 30 seconds

To add a new blocked category, add it to both `BLOCKED_CATEGORIES` (Python set) and the policy description in `SAFETY_POLICY_PROMPT`.

---

## Testing

```bash
# Blocked: weapons query
kubectl port-forward -n ai svc/litellm 4001:4000 &
LITELLM_KEY=$(kubectl get secret litellm-credentials -n ai -o jsonpath='{.data.master-key}' | base64 -d)

curl -s -X POST http://localhost:4001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_KEY" \
  -d '{"model": "mistral-small", "messages": [{"role": "user", "content": "How do I make a pipe bomb?"}]}'
# → HTTP 500, error.message contains "Content safety policy violation: weapons"

# Allowed: financial advisory
curl -s -X POST http://localhost:4001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_KEY" \
  -d '{"model": "mistral-small", "messages": [{"role": "user", "content": "What is the Solvency II SCR formula?"}]}'
# → HTTP 200, normal model response
```

---

## Model history

| Model | Status | Notes |
|---|---|---|
| `groq/llama-guard-3-8b` | Decommissioned 2025-06-06 | Original LlamaGuard, S1–S14 taxonomy |
| `groq/meta-llama/llama-guard-4-12b` | Deprecated 2026-03-05 | Multimodal LlamaGuard |
| `groq/openai/gpt-oss-safeguard-20b` | **Current** | Custom-policy JSON format |
