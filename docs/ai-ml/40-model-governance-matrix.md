---
id: model-governance-matrix
title: AI Model Governance Matrix
sidebar_label: Model Governance Matrix
---

# AI Model Governance Matrix

> Source of truth for **which model may process which class of data**, and the
> third-party-ICT register for the LiteLLM gateway. Feeds **EU AI Act** (technical
> documentation + risk classification) and **DORA** (register of ICT third parties
> + concentration/exit analysis) and **GDPR/ACPR** (data residency).
>
> Stories: platform-backlog **#301** (this matrix) + **#302** (data classes).
> Enforcement (tag-based routing + PII pre-check) is **#305**.

## 1. Data classification scheme (#302)

| Class | Meaning | Examples (ktayl insurance IS) |
|---|---|---|
| **P0 — Public** | Non-sensitive, publicly shareable | marketing copy, public docs, generic Q&A |
| **P1 — Internal** | Internal business, **no personal data** | internal procedures, non-personal analytics |
| **P2 — Confidential** | Sensitive business, limited personal data | contract terms, aggregated claims data |
| **P3 — Restricted** | **Personal data / regulated** (DORA/ACPR scope) | policyholder PII, claims dossiers, health/financial data |

**Golden rule:** a request may only be routed to a model whose **max allowed class ≥ the request's class**. PII detected (Presidio) forces the request to the on-cluster tier regardless of the declared class.

## 2. Per-provider governance matrix (#301)

| Tier / Provider | Models in the gateway | Jurisdiction | Data terms (training / residency) | **Max data class** | Cost |
|---|---|---|---|---|---|
| **On-cluster** (vLLM + agents) 🏠 | `phi3-financial`, `phi3-financial-ft`, `research-agent`, `deep-research-agent` | 🇫🇷 self-hosted (minicloud) | data **never leaves the cluster**; no external call; no training | **P3 — Restricted** ✅ | free |
| **Mistral** 🇪🇺 | `mistral-large`, `mistral-small`, `mistral-embed` | 🇫🇷 France / EU | API data **not used for training**; EU/GDPR-aligned | **P2 — Confidential** | paid (cheap) |
| **AWS Bedrock** (E1, EU) 🇪🇺 | Claude/Llama/Mistral via `bedrock/` (region `eu-west-1`) | 🇪🇺 EU | **contractual** no-training + EU residency | **P2 — Confidential** | tokens |
| **Azure OpenAI** (E2, EU) 🇪🇺 | GPT-4o/Claude via `azure/` (EU region) | 🇪🇺 EU | **contractual** no-training + EU residency | **P2 — Confidential** | tokens |
| **OpenAI** 🇺🇸 | `gpt-4o`, `gpt-4o-mini`, `text-embedding-3-small` | 🇺🇸 US | API not trained (since 2023); **US CLOUD Act** (no EU residency) | **P1 — Internal** | paid |
| **Anthropic** 🇺🇸 | `claude-sonnet`, `claude-haiku` | 🇺🇸 US | API not trained; US jurisdiction | **P1 — Internal** | paid |
| **Google Gemini** 🇺🇸 | `gemini-2.0-flash`, `gemini-1.5-pro` | 🇺🇸 US | **paid** tier not trained; **free tier MAY be** | **P1 — Internal** (paid only) | paid |
| **NVIDIA NIM** 🇺🇸 | `nvidia-nemotron-70b`, `nvidia-llama-8b`, `nvidia-deepseek-r1` | 🇺🇸 US (build.nvidia.com) | free inference tier — terms **uncertain** | **P0 — Public** | free tier |
| **Groq** 🇺🇸 | `groq-fallback` (+ `phi3-financial` route) | 🇺🇸 US | fast inference; enterprise terms less clear | **P0 — Public** | free/cheap |
| **HuggingFace** (router) 🇺🇸 | `hf-qwen`, `hf-gemma` (featherless-ai router) | 🇺🇸 US (3rd-party router) | third-party routing, terms **uncertain** | **P0 — Public** | paid |
| **Ollama Cloud** 🌐 | `ollama-cloud` (`gpt-oss:120b`, 3-key round-robin) | US-ish (new service) | terms **uncertain** (new provider) | **P0 — Public** | tokens |
| **DeepSeek** 🇨🇳 🔴 | `deepseek-chat`, `deepseek-r1:7b` | 🇨🇳 **China** (PIPL, **no GDPR adequacy**) | 🔴 data-sovereignty risk | **P0 — Public ONLY — NEVER PII/regulated** | cheap |

**Nuance — DeepSeek via NVIDIA:** `nvidia-deepseek-r1` runs the DeepSeek *model* on **NVIDIA US** infra → data goes to the US, **not** to China. It's P0 (US free tier), distinct from the direct `deepseek-*` (→ China) which carry the 🔴 CN sovereignty flag.

## 3. Routing policy (input to #305)

| Request data class | Allowed models |
|---|---|
| **P3 — Restricted** (PII/regulated) | **on-cluster ONLY** (vLLM + agents + `mistral-embed`… on-cluster embeddings) |
| **P2 — Confidential** | on-cluster **+ EU** (Mistral, Bedrock-EU, Azure-EU) |
| **P1 — Internal** | + US enterprise (OpenAI, Anthropic, Gemini-paid) |
| **P0 — Public** | any, incl. cheap/free (Groq, NVIDIA-free, HF, Ollama Cloud, DeepSeek) |


**Enforcement (#305, LIVE):** each model carries `model_info.access_group` in the LiteLLM config (`onprem`/`eu`/`us`; untagged = P0-only). A virtual key scoped to `models: ["onprem"]` can only reach P3-safe on-cluster models, `["eu"]` only EU models, etc. (key scoping = #306). Presidio PII masking is `default_on` globally → PII is masked before any cloud call regardless of class.

**Hard blocks:** DeepSeek-CN and any "uncertain-terms" free tier are **never** eligible for P1+. A Presidio PII hit downgrades routing to on-cluster.

## 4. Compliance mapping

- **EU AI Act:** this matrix is part of the *technical documentation*. The Retrieva DORA-RAG is **limited-risk / transparency-tier** (assists, cites sources, human-in-the-loop); the gateway is infrastructure. High-risk use cases (if introduced) must use the on-cluster / EU tier + human oversight + audit (#309).
- **DORA (Reg. EU 2022/2554):** each external LLM provider is an **ICT third party** — this table is the register (provider · jurisdiction · criticality). Watch **concentration risk** (don't route all critical flows to one US provider) and keep an **exit path** (the LiteLLM gateway makes provider swap a config change; on-cluster is the fallback).
- **GDPR / ACPR:** personal/regulated data (P3) stays **on-cluster** (data residency + minimisation). EU providers (P2) only with a DPA.

## 5. Maintenance
Update this file whenever a model is added/removed in `manifests/ai/00-litellm-configmap.yaml`. The machine-readable projection (`model_info` tags per model → tag-based routing) is applied in **#305**.
