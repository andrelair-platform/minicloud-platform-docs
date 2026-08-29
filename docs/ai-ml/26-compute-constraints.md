---
id: compute-constraints
title: Compute Constraints & Operating Envelope
sidebar_label: Compute Constraints
---

# Compute Constraints & Operating Envelope

> The cluster has **no GPU** (4 ThinkPads, CPU-only i7-8565U / i7-10510U; the
> MacBook Pro 2012 is storage, not compute). This page states honestly what that
> limits, what it does **not** limit, and the resulting operating envelope. The
> short version: no-GPU limits **self-hosting and training models**, not
> **integrating AI into products** — and the [AI Gateway](ai-gateway) hybrid
> design was built precisely to route heavy work to the cloud.

## What "no GPU" actually limits (on-cluster only)

| Capability | Reality on CPU-only ThinkPads |
|---|---|
| **Local LLM inference (vLLM)** | **1–3B quantised (Q4)** = usable (~5–15 tok/s, simple tasks). **7–8B** = slow (~2–4 tok/s, batch/async only). **13B+** = impractical. |
| **Local embeddings** | Work (bge-m3/nomic) but **slow in bulk** → this is why embeddings moved to `mistral-embed` (cloud, EU). |
| **Fine-tuning / training** | **Not feasible on-cluster** without a GPU → use cloud (Bedrock/Azure) or don't. |
| **Local vision / multimodal** | Very slow (llava on CPU). |
| **Real-time / high-throughput self-hosted** | Not viable. |

## What is NOT limited — the full-capability field

Anything routed through the **LiteLLM gateway to a cloud provider uses someone
else's GPU** → unlimited capability, pay-per-token (capped at €15/provider):

| Capability | Status | How |
|---|---|---|
| **Frontier LLMs** (GPT-4o, Claude, Gemini, Mistral Large, Llama) | ✅ full | AWS Bedrock-EU, Azure OpenAI-EU, direct APIs, NVIDIA/Groq, Ollama Cloud |
| **Embeddings** | ✅ full | `mistral-embed` / OpenAI (cloud) |
| **RAG** | ✅ full | **Qdrant is CPU-friendly** (vector search is not GPU-bound) + cloud embeddings |
| **Agents / orchestration** (LangGraph, CrewAI) | ✅ full | orchestration is **CPU-light**; LLM calls go to the cloud |
| **Governance / routing / observability / platform** | ✅ full | 100% CPU |

## Operating envelope (what you can build)

Practically **any applied-AI product** that *integrates* models rather than
*hosts/trains* them:

- Enterprise **RAG** (e.g. Retrieva), contextual **copilots**, multi-step
  **agents**, extraction/classification, business assistants.
- The hybrid governance model makes the GPU constraint largely irrelevant:
  - **P3 sovereign/restricted** → small CPU models on-cluster (slow but private)
    **or** EU cloud (Bedrock/Azure EU, EU residency guaranteed).
  - **P0–P2** → frontier cloud models (full capability).
  - The gateway abstracts the choice (see [governance matrix](ai-gateway)).

## Out of scope (accept it explicitly)

1. Serving a **frontier model locally** (latency/cost).
2. **Fine-tuning / training** on-cluster.
3. **High-volume self-hosted** inference (economically).
4. Heavy **local multimodal**.

## Recommendation — maximise the on-cluster (sovereign) tier

For the P3 sovereign tier, keep **≤3–4B quantised** models on CPU via vLLM
(phi3, qwen-3B, llama-3B) for simple tasks, fallback, and ultra-confidential
low-throughput work. Everything else → the governed cloud tier.

**In one line:** without a GPU you are limited for **hosting/training** models,
but **fully capable** for **integrating** AI into products — which is exactly the
platform's purpose and architecture. No-GPU is a **local-compute** constraint,
not a **product-capability** one.
