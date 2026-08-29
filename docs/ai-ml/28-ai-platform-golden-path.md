---
id: ai-platform-golden-path
title: AI Platform Golden Path — onboarding a project
sidebar_label: AI Platform Golden Path
---

# AI Platform Golden Path — onboarding a project

> **You do not rebuild the LLMOps stack per project.** It's a **shared platform**
> — projects *plug in*, they don't re-provision. This page is the golden path a
> new AI project (RAG app, copilot, agent…) follows to connect to the platform
> and inherit governance, EU residency, PII masking and audit **for free**.

## Mental model — platform vs project

The LLMOps stack is shared infrastructure, like Kubernetes itself: you don't
reinstall the cluster per app, you deploy onto it.

| Layer | Shared (already running) | The project does |
|---|---|---|
| Gateway | **LiteLLM** — one endpoint for all | point `LITELLM_BASE_URL` + get a key |
| Observability | **Langfuse** | `success_callback: langfuse` (automatic) |
| Guardrails | **Presidio + LlamaGuard** on the gateway | nothing — transparent |
| Red-team gate | tests the gateway | nothing (optionally add domain attacks) |
| Vector DB | **Qdrant** | create its own collection |
| Evaluation | **Ragas** pattern | provide a golden set + threshold |
| RBAC / budgets | governance matrix + tiers | receive a tier-scoped key |

**Plug in, don't rebuild.** A new project inherits routing, EU residency, PII
masking, RBAC/budgets and the DORA audit trail automatically.

## Onboarding checklist

### 1. Classify your data → pick your tier
Decide the highest data class the project handles (see the
[governance matrix](ai-gateway)): P0 Public · P1 Internal · P2 Confidential ·
P3 Restricted (PII/regulated). This determines which models you may use.

### 2. Get a tier-scoped LiteLLM key
Request a virtual key (or a team) scoped to the right tier — e.g. a P2/P3
project gets `models: ["onprem","eu"]` and **can never** reach untrusted P0/CN
providers. Keys carry per-consumer budget + tpm/rpm.

```bash
# master key from the cluster; issue a scoped team key:
MK=$(kubectl -n ai get secret litellm-credentials -o jsonpath='{.data.master-key}' | base64 -d)
# (team seeding runs as a Job — see the AI Gateway page; keys inherit the team's tier)
```

### 3. Point your app at the gateway
One endpoint, OpenAI-compatible. Never call a provider directly.

```bash
LITELLM_BASE_URL=http://litellm.ai.svc.cluster.local:4000   # in-cluster
# public: https://litellm.devandre.sbs
LITELLM_API_KEY=<your tier-scoped key>
```

Use model **aliases**, not provider SKUs, so you stay provider-agnostic and
governed: `mistral-large`, `bedrock-mistral-large`, `azure-gpt-4.1-mini`,
`phi3-financial` (on-cluster), `mistral-embed` (embeddings)…

### 4. (RAG only) create a Qdrant collection
Embed via the gateway (`mistral-embed`, EU, 1024-dim) and store in your own
Qdrant collection — vector search is CPU-friendly (see
[Compute Constraints](compute-constraints)).

```
QDRANT_URL=http://qdrant.ai.svc.cluster.local:6333
EMBED_MODEL=mistral-embed   # EU/P2, keeps restricted embeddings in the EU
```

### 5. Observability is automatic
Because you go through LiteLLM, every call is traced in **Langfuse**
(token/cost/model/latency/team) and counted in Prometheus/Grafana (SLO,
residency, FinOps). Nothing to wire.

### 6. Add an evaluation gate
Provide a **golden set** and a threshold; reuse the **Ragas** eval pattern
(`manifests/ai/16-rag-eval-job`) as a CI/PostSync gate. Grow the golden set with
the [Langfuse annotation workflow](https://andrelair-platform.github.io/minicloud-platform-docs/docs/ai-governance/annotation-workflow).

### 7. (optional) domain red-team
The platform red-team gate (#312) already tests injection/jailbreak/PII/toxicity
against the gateway. Add **domain-specific** attacks to the suite if your product
has its own abuse surface.

## What the project actually owns

Only its **business logic**: the prompt/chain/agent (LangGraph, CrewAI, Express…),
its Qdrant collection + corpus, its golden set, optionally its domain attacks,
and its tier-scoped key. Everything else is inherited.

## Reference implementation

**Retrieva** (enterprise DORA-RAG) is the reference: it reuses the shared
**Qdrant + LiteLLM + Langfuse** (embeddings on `mistral-embed`, no external
Groq), deploys only its own app + MongoDB, and inherits governance/observability.
That's the golden path in action — integrate AI into a product by *reusing* a
ready platform, not reinventing the tooling. This is also the exact model of the
Ydays **IA Integration Lab**.

## One-line summary

Build the LLMOps stack **once** (done); each project **plugs in** — a golden
path, not repeated work.
