---
slug: enterprise-ai-gateway-litellm
title: "Building an Enterprise AI Gateway on Kubernetes: LiteLLM, Local Models, and Zero-Trust Guardrails"
authors: [andrelair]
tags: [ai, llm, litellm, kubernetes, enterprise, mlops, self-hosted, data-sovereignty, presidio, langfuse, ollama, vllm, rgpd, gdpr]
date: 2026-08-08
description: "How to build a production AI gateway that routes between local models and cloud APIs, enforces department-level access controls, strips PII before it leaves your network, and traces every call — all behind a single OpenAI-compatible endpoint."
---

Most enterprise AI deployments make the same architectural mistake early on: they give every team a direct API key to OpenAI or Anthropic and call it done. The result is predictable — no cost visibility, no access control, no audit trail, and sensitive data being sent to cloud APIs without any guardrails.

A proper enterprise AI gateway changes the shape of the problem. Instead of many teams talking to many APIs, you have one endpoint that handles routing, rate limiting, PII scrubbing, caching, and observability. Teams consume it the same way regardless of whether the model is running on your own hardware or on a cloud provider's GPU fleet.

This post covers the full design of such a gateway, built on Kubernetes with LiteLLM as the proxy layer, Ollama and vLLM for local inference, and Presidio for PII protection — with real configuration that is running in production.

{/* truncate */}

## The Problem With Direct API Access

When teams connect directly to cloud LLM APIs, four problems compound quickly.

**Cost opacity.** You discover your monthly bill at the end of the month. By then the expensive model that someone used for a test pipeline has been running for three weeks.

**No data boundary.** Every prompt goes to an external API unless someone actively intervenes. For organisations handling personal data under GDPR, or financial data under ACPR oversight, this is not a configuration choice — it is a compliance problem.

**No access control.** The same API key that lets a developer prototype also lets them run automated batch jobs consuming a million tokens per hour. There is no per-department spending limit, no model tier, no rate limit.

**No audit trail.** When something goes wrong — an inappropriate prompt, an unexpected output, a cost spike — you have no record of what was asked, what was answered, or which team was responsible.

A gateway solves all four, and the cost of operating one is low enough that there is no good reason not to.

---

## Architecture Overview

The gateway sits between every AI consumer (chat interfaces, RAG pipelines, agents, scripts) and every AI provider (local models, cloud APIs). Nothing calls a model directly.

```
Open WebUI ──► LiteLLM Gateway (:4000)
Agents      ──►      │
Scripts     ──►      │
                     ├── Ollama primary   (fast-heron,  :11434)  ← local-first
                     ├── Ollama secondary (star-kitten, :11434)  ← local-first
                     ├── vLLM             (star-kitten, :8000)   ← high-throughput
                     │
                     ├── Groq             (llama-3.1-8b-instant) ← auto-fallback #1
                     ├── DeepSeek         (deepseek-chat)        ← auto-fallback #2
                     ├── Mistral          (large, small)
                     ├── Anthropic        (claude-sonnet, haiku)
                     ├── OpenAI           (gpt-4o, gpt-4o-mini)
                     ├── Gemini           (gemini-2.5-flash)
                     └── NVIDIA NIM       (nemotron-70b, deepseek-r1)

LiteLLM ──► Valkey cache   (:6379)    ← exact-match prompt dedup, 10 min TTL
LiteLLM ──► Langfuse               ← trace every call
LiteLLM ──► Postgres               ← virtual keys, spend tracking
```

LiteLLM exposes a single OpenAI-compatible endpoint. Every consumer uses the same `/v1/chat/completions` API regardless of whether the request ends up on a local Ollama instance or a cloud provider. Switching a team from GPT-4o to Mistral Large requires no code changes on their side — only a configuration change in the gateway.

---

## Local-First Routing With Automatic Cloud Fallback

The central routing principle is local-first: requests go to on-premise models by default and escalate to cloud only when local inference fails.

```yaml
router_settings:
  routing_strategy: least-busy
  num_retries: 2
  timeout: 120
  cooldown_time: 60
  allowed_fails: 3
  fallbacks:
    - qwen3.5:4b:
        - groq-fallback
        - deepseek-chat
    - phi4-mini:
        - groq-fallback
        - deepseek-chat
```

`least-busy` distributes requests across backends by in-flight count rather than round-robin. With two Ollama nodes, requests naturally balance toward whichever node is less loaded.

The circuit breaker is the critical piece: after 3 consecutive failures, a backend is marked degraded for 60 seconds. Without this, a hung Ollama process would absorb the full retry budget of every incoming request before timing out. With it, a degraded node is bypassed almost immediately and the request succeeds against the other backend — or against Groq if both local nodes are down.

Some models have **no cloud fallback by design**:

```yaml
# phi3-financial: domain-specific model, no cloud fallback
# Financial prompts must not leave the cluster
- model_name: phi3-financial
  litellm_params:
    model: ollama/phi3-financial
    api_base: http://ollama-primary.ai.svc.cluster.local:11434
```

The domain-specific fine-tuned model, vision models, and the embedding model are local-only. The gateway enforces this — there is no code path where a financial prompt reaches an external API.

---

## Department-Level Access Control

Virtual keys map each department to a set of constraints: allowed models, token rate limits, request rate limits, and a monthly budget cap.

Three tiers cover different risk profiles:

| Tier | Token limit | Request limit | Monthly budget | Model access |
|---|---|---|---|---|
| **premium** | 200k TPM | 500 RPM | $100 | All models including GPT-4o, Claude, Nemotron |
| **standard** | 100k TPM | 200 RPM | $30 | Local models + Groq, DeepSeek, Mistral Small, GPT-4o-mini |
| **basic** | 50k TPM | 100 RPM | $5 | Local models only |

Each department gets its own key, stored in Vault. When a department's key hits its budget limit, LiteLLM returns HTTP 429 (`BudgetExceededError`) and the reset happens automatically at the start of the next billing period.

The key metadata — department name, tier, budget — travels through to Langfuse and the Grafana cost dashboard. You can see, per department, how much they have spent, what percentage of their budget is consumed, and which models they are actually using.

This is the kind of visibility that is impossible with direct API keys. When your actuarial team spends $87 of their $100 monthly budget in the first week by routing everything through GPT-4o, you know immediately — and you can have the conversation about model selection before the overage hits.

---

## PII Protection Before Data Leaves Your Network

The most important guardrail is the one that runs before every cloud-bound request: a PII scrubber powered by Microsoft Presidio.

Presidio runs as two in-cluster services — an analyzer that detects PII entity types and an anonymizer that replaces them with typed placeholders. LiteLLM calls them as a `pre_call` guardrail before forwarding any prompt to an external API.

```
"Client jean.dupont@acme.fr, phone +33612345678, wants a quote for policy 78441"
        ↓  Presidio pre_call guardrail
"Client <EMAIL_ADDRESS>, phone <PHONE_NUMBER>, wants a quote for policy <IN_PAN>"
        ↓  sent to cloud model (GPT-4o, Claude, Mistral, etc.)
```

Local models are unaffected — they receive the original prompt because the data never leaves the cluster. Cloud models receive only the anonymized version.

The guardrail runs `default_on: true`, meaning it is active on every request without any opt-in required. Developers do not need to know it exists. It simply runs.

One important scope decision: the guardrail applies only to **input**. It does not anonymize model responses. This is intentional. Presidio's entity detection is aggressive — it will classify country names, historical figures, and dates as `<LOCATION>`, `<PERSON>`, and `<DATE_TIME>` respectively. A response to a general knowledge question would become unreadable. The compliance goal is protecting user data sent *to* cloud providers, not transforming what comes back.

A second guardrail runs in parallel using the `detect-secrets` library, which scans every prompt for credential patterns — API keys, tokens, connection strings. Prompts containing high-confidence real credentials are rejected with HTTP 400 before they reach any model.

---

## Prompt Caching for Speed and Cost

Identical prompts — same model, same message content — return a cached response from Valkey (Redis-compatible) without hitting inference.

The performance difference is significant: an 80ms cache hit versus a 2,500ms cold call to a local model, or a 600ms cold call to a cloud API. For RAG pipelines that call the same model repeatedly with similar retrieval context, the cache hit rate can be 40–60%.

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: litellm-cache.ai.svc.cluster.local
    port: 6379
    ttl: 600
    namespace: litellm
```

The TTL of 10 minutes is a deliberate trade-off. It is long enough to capture repeated queries in an interactive session but short enough that evolving context — a document being edited, a dataset being updated — does not return stale answers for more than a few minutes.

---

## Full Observability: Langfuse + Grafana

Every request produces a Langfuse trace containing the model used, token counts, latency, cost estimate, department key, and whether guardrails were triggered. The trace is available at the span level — you can inspect the raw prompt, the PII-masked version that was forwarded, and the response.

For cost reporting, a Grafana dashboard queries the LiteLLM PostgreSQL spend tables directly. Eight panels cover the metrics that actually matter in production:

- Total spend and token usage last 24 hours
- Department budget utilisation with colour thresholds (green / amber / red)
- Token and request breakdown by model last 30 days
- An audit trail of the last 50 requests with department attribution

The budget utilisation table is the one that gets shared with management. It shows, at a glance, whether any department is approaching their limit — and allows informed conversations about quota adjustments before limits are hit.

---

## What Makes the Gateway Approach Scale

The single most valuable property of this architecture is that **adding a new model requires no changes to consumers**.

When a new Ollama model is pulled, it appears in the LiteLLM model list and is immediately available to every team with the right tier. When a cloud provider releases a better model, the swap happens in a single config change — the department-level rate limits, PII guardrails, and cost tracking continue working exactly as before.

The inverse is also true: removing a model, changing a provider, or adjusting a department's budget all happen centrally, with immediate effect, without touching any consumer code.

This is what separates an AI gateway from a collection of API keys. The keys give you access. The gateway gives you control.

---

## Running It on Kubernetes

All components run in the `ai` namespace, managed by a single ArgoCD application. The gateway itself is stateless — it can be scaled horizontally behind a ClusterIP service. The only stateful components are PostgreSQL (for spend tracking and virtual keys) and Valkey (for the prompt cache), both on Longhorn persistent volumes.

The NetworkPolicy setup is worth noting: only LiteLLM pods have egress to port 443. Ollama and Open WebUI are internet-blocked by policy. This means that even if an application-level bug bypassed the gateway, there is no path for Ollama to contact an external API directly.

```yaml
# Only litellm pods can reach external cloud APIs
networkPolicy:
  name: allow-litellm-cloud-egress
  podSelector:
    matchLabels:
      app: litellm
  egress:
    - ports:
        - port: 443
```

For organisations that need to demonstrate data controls — whether to auditors, to legal, or to a DPO — this kind of network-layer enforcement is far stronger than an application-level promise.

---

The complete configuration — LiteLLM proxy config, guardrail definitions, NetworkPolicies, Langfuse integration, Grafana dashboard — is documented in the AI Gateway section of the platform documentation.
