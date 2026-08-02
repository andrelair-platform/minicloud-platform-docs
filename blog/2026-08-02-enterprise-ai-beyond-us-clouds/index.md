---
slug: enterprise-ai-beyond-us-clouds
title: "Enterprise AI Without Amazon, Microsoft, or Google: A European Perspective"
authors: [andrelair]
tags: [ai, enterprise, data-sovereignty, mistral, vllm, litellm, rgpd, gdpr, secnumcloud, mlops, kubernetes]
date: 2026-08-02
description: "The standard advice is Bedrock, Azure OpenAI, or Vertex AI. But what about organisations that cannot or will not send their data to American servers? Here is the full picture."
---

Every article about enterprise AI ends the same way. Use Amazon Bedrock. Use Azure OpenAI Service. Use Google Vertex AI. These platforms offer enterprise-grade compliance, data privacy, and zero-training guarantees.

The advice is correct — for organisations that can use American cloud infrastructure.

A large and growing number of organisations cannot. Some because of cost. Many because of regulation. A few because their data literally cannot cross a border under the law that governs their sector.

This post is for those organisations. It covers two separate problems — data sovereignty and cost — and the concrete options available for each.

{/* truncate */}

## Why the Standard Advice Falls Short in Europe

The "use Bedrock / Azure OpenAI / Vertex AI" recommendation solves a real problem: it gives you enterprise SLAs, DPAs, and no-training guarantees from a known counterparty. For a US company, or a multinational comfortable with Standard Contractual Clauses, it is a reasonable choice.

But it quietly assumes three things that many European organisations cannot accept:

**1. Your data will be processed in the United States.**

Even with EU data residency options, your data is processed by an American company subject to US law. Under the Cloud Act (2018), US authorities can compel American cloud providers to hand over data stored anywhere in the world — including data centres located in France or Germany. A DPA and SCCs provide contractual protection. They do not provide technical guarantees.

**2. Transfer impact assessments are manageable overhead.**

Under the CJEU's Schrems II ruling, any transfer of personal data to a third country requires a Transfer Impact Assessment demonstrating that the destination country's surveillance laws do not undermine GDPR protections. For procurement teams at mid-sized organisations, this is not a checkbox — it is a multi-week legal exercise that many simply decline to undertake.

**3. Price per token is acceptable at scale.**

At low volumes, cloud APIs are cheap. At enterprise scale — tens of thousands of employee queries per day, RAG pipelines processing thousands of documents, automated workflows calling models in loops — the cost compounds fast.

GPT-4o at $2.50 per million input tokens does not sound expensive until you have 500 employees using it daily for document summarisation. At 2,000 tokens per query, that is one million tokens per day, $2.50 per day — manageable. Add RAG retrieval (another 2,000 tokens per query for retrieved context) and you are at $5/day, $1,825/year, just for GPT-4o input. Multiply by actual enterprise usage patterns and multiply again for any workload that benefits from a more capable model.

---

## Problem 1: Data Sovereignty

### The Regulatory Landscape in France

French and European organisations face a layered set of requirements depending on their sector:

**RGPD (GDPR)**
The baseline for all organisations processing personal data of EU residents. Requires that data transferred outside the EU goes to a country with adequate protections, or is covered by SCCs plus a Transfer Impact Assessment. Personal data of employees, customers, or citizens cannot be sent to a third country without this legal basis.

**ACPR (banking and insurance)**
The Autorité de contrôle prudentiel et de résolution supervises French banks and insurers. Its guidelines treat cloud outsourcing as a significant operational risk. While ACPR does not prohibit US cloud providers outright, institutions must demonstrate that they can exit a cloud provider without disruption and that sensitive data is protected against third-country access. Mistral AI, as a French company, sidesteps most of these concerns without requiring a Transfer Impact Assessment.

**HDS (hébergement de données de santé)**
Health data in France must be hosted by an HDS-certified provider. US cloud providers can obtain HDS certification for their French data centres, but the Cloud Act exposure remains. For the most sensitive health workloads, self-hosting on certified French infrastructure eliminates the residual risk.

**SecNumCloud**
ANSSI's qualification framework for cloud providers handling sensitive government data and critical infrastructure. Currently only **OVHcloud** and **Outscale** (a Dassault Systèmes subsidiary) hold this qualification. AWS, Azure, and Google Cloud do not qualify and legally cannot under the current framework, because qualification requires that the provider not be subject to non-European law that could override its data protection obligations.

### European Alternatives That Actually Exist

| Provider | Country | Regulatory story | Models available |
|----------|---------|-----------------|-----------------|
| **Mistral AI** | 🇫🇷 France | French company, RGPD-compliant, no US law exposure, API with DPA available | Mistral 7B, Mistral NeMo, Mistral Large, Codestral |
| **OVHcloud AI Endpoints** | 🇫🇷 France | SecNumCloud-qualified, HDS-certified data centres, data never leaves France | Open models (Llama, Mistral, etc.) via hosted endpoints |
| **Aleph Alpha** | 🇩🇪 Germany | German company, DSGVO-first design, on-premise deployable | Luminous family (multilingual, strong on German/French) |
| **Scaleway** | 🇫🇷 France | French infrastructure, competitive GPU rental pricing | Bring your own model via GPU instances or managed endpoints |

### Mistral AI: The Default Answer for French Enterprises

Mistral AI, founded in Paris in 2023, is the clearest answer to the data sovereignty question for most French organisations.

**The API path:** `la-plateforme.mistral.ai` provides a standard OpenAI-compatible API backed by French infrastructure, under a French DPA, with no Transfer Impact Assessment required. Mistral Small (7B-class) is €0.10 per million tokens — comparable to GPT-3.5-Turbo pricing — with Mistral Large available at €2 per million for complex reasoning tasks.

**The self-host path:** Mistral releases the weights of its smaller models openly (Mistral 7B, Mistral NeMo 12B, Codestral 22B). You can download the weights, run them on your own GPU infrastructure, and your prompts never touch any external server. No API. No DPA needed. No Transfer Impact Assessment. No data leaves your network.

The pitch to a French enterprise compliance officer is simple: *"The model runs on our servers in France. Here is the network egress log showing zero outbound connections to any AI provider during these queries."* That is a fundamentally different level of assurance than "we have a DPA with Microsoft."

---

## Problem 2: Cost

### The Real Cost of Cloud APIs at Scale

The per-token pricing of cloud AI APIs has dropped dramatically over the past two years, which makes the cost argument harder to make at small scale. But enterprise deployments do not operate at small scale.

Consider a 200-person finance team using AI for:
- Daily portfolio briefings: 5,000 tokens per user × 200 users = 1M tokens/day
- Document analysis: 20,000 tokens per document × 50 documents/day = 1M tokens/day
- Internal chatbot queries: 2,000 tokens × 500 queries/day = 1M tokens/day

At 3M tokens/day, using GPT-4o-mini ($0.15/1M input + $0.60/1M output, roughly $0.40/1M blended):

**Monthly cost: 3M × 30 × $0.40 / 1M = $36/month**

That is remarkably cheap. Scale to a 2,000-person organisation with similar usage:

**Monthly cost: $360/month**

Still cheap. Now use GPT-4o instead of mini ($2.50 blended per million):

**Monthly cost at 2,000 users: $2,250/month = $27,000/year**

Add a RAG pipeline that doubles token consumption per query. Add a code review agent running on every pull request. Add automated document classification across a document management system with 10,000 new documents per month. The numbers scale with your ambition, and at some point self-hosting becomes the cheaper option.

### The Self-Hosting Math

A single NVIDIA A100 80GB GPU costs approximately €3/hour on OVHcloud bare-metal. Running Mistral 7B Q4_K_M (quantised to 4-bit):

- **Throughput:** approximately 400 tokens/second at full capacity
- **Daily cost:** €72 (24 hours at €3/hr)
- **Daily capacity:** 400 tok/s × 86,400s = 34.5 million tokens

At the same 3M tokens/day usage as the example above: **your GPU is idle 91% of the time.** You are paying €72/day to generate tokens that cost €1.20/day on GPT-4o-mini.

The crossover point with GPT-4o-mini is approximately 18M tokens/day — which requires a large organisation with heavy AI integration. Below that, cloud APIs are cheaper on pure token cost.

**But token cost is not the only variable.** Once you add:
- Data sovereignty requirements (non-negotiable for regulated sectors)
- The ability to fine-tune on proprietary data without sending that data to a provider
- Predictable cost regardless of usage spikes
- No rate limits or quota exhaustion during peak demand

…the self-hosting calculation shifts significantly in favour of owning the GPU.

---

## The Architecture That Makes Both Work

The good news is that you do not have to choose between cloud APIs and self-hosted models permanently. The right architecture lets you use both simultaneously, switch between them without application changes, and add new backends as they become relevant.

That architecture is a **model-agnostic proxy** — a single endpoint your applications call, which routes requests to whatever backend is most appropriate.

[LiteLLM](https://github.com/BerriAI/litellm) is the open-source implementation of this pattern. It accepts OpenAI-format requests and forwards them to any backend: OpenAI, Anthropic, Mistral, Groq, a self-hosted vLLM instance, or any other OpenAI-compatible endpoint.

```yaml
# The full model_list in a LiteLLM config.yaml
model_list:

  # European cloud API — Mistral, French company, EU data residency
  - model_name: mistral-small
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY

  # Self-hosted vLLM on your own GPU — zero data leaves the cluster
  - model_name: mistral-7b-local
    litellm_params:
      model: openai/mistralai/Mistral-7B-Instruct-v0.3
      api_base: http://vllm.ai.svc.cluster.local:8000/v1
      api_key: token-internal

  # Cloud fallback for burst capacity
  - model_name: groq-fast
    litellm_params:
      model: groq/llama-3.1-8b-instant
      api_key: os.environ/GROQ_API_KEY
```

Your application calls one endpoint — `https://litellm.yourdomain.com/v1/chat/completions` — and specifies a model name. The proxy handles routing, retries, fallbacks, and rate limiting. You can move traffic from Groq to Mistral to your own GPU without touching a single line of application code.

### What Stays the Same Regardless of Backend

When you route through a proxy layer, the entire observability and governance stack applies uniformly to every backend:

- **Langfuse tracing** — every request logged with user, model, latency, token count, and cost
- **Presidio PII masking** — prompts scrubbed before they reach any provider
- **Rate limiting** — per-team or per-role token budgets enforced at the proxy
- **RBAC** — virtual keys per department, with model allowlists per key
- **Prometheus metrics** — request rates, error rates, cost per model per team

Switch from Groq to your own GPU: the Langfuse trace still appears. The PII masking still runs. The rate limit still applies. The cost dashboard still updates (with zero for self-hosted requests, since there is no token billing).

---

## The French Enterprise Pitch

If you are a consultant or platform engineer working with French organisations, the conversation often goes like this:

**Client:** "We want to use AI but our legal team says we cannot send client data to ChatGPT."

**Standard advice:** "Use Azure OpenAI with EU data residency and a DPA."

**Better answer:** "We run Mistral 7B on OVHcloud SecNumCloud infrastructure in Gravelines, France. Your data never leaves French soil, never touches an American server, and we can prove it with egress logs. When you need a more powerful model for complex reasoning, we route to Mistral Large — still French infrastructure, still the same DPA."

The key difference: the better answer gives the client a *technical guarantee* rather than a *contractual guarantee*. A DPA tells you what the provider promises to do with your data. Network logs tell you what actually happened.

For the ACPR, for the CNIL, and for any compliance team that has been through a Schrems II Transfer Impact Assessment, the difference between "we have contractual protections" and "we have zero outbound connections to foreign servers" is very significant.

---

## Where to Start

| Your situation | Recommended path |
|----------------|-----------------|
| Regulated sector (banking, insurance, health), data cannot leave France | Mistral API via `la-plateforme.mistral.ai` for quick start; self-hosted vLLM on OVHcloud GPU for full sovereignty |
| Government or OIV, SecNumCloud required | OVHcloud AI Endpoints (qualified); or self-hosted on OVHcloud or Outscale bare-metal |
| Cost is the primary constraint, no hard sovereignty requirement | Groq (free tier, fast) + Mistral Small (cheap, EU) + self-hosted when volume justifies hardware |
| Want full control, no external dependencies | vLLM on your own GPU infrastructure with open Mistral or Llama weights |
| Starting out, unsure | Mistral API + LiteLLM proxy; add self-hosted backends when requirements become clear |

The pattern that works at every scale: build on a model-agnostic proxy from day one. Your application does not know whether the model is running in Paris, Frankfurt, or the server room down the hall — and it should not need to.
