---
id: llmops-stack-assessment
title: LLMOps Stack Assessment
sidebar_label: LLMOps Stack Assessment
---

# LLMOps Stack Assessment

> How the minicloud LLMOps stack maps to the reference 8-layer LLMOps framework,
> which layers are covered (with which reference tools), and the remaining gaps.
> Backlog: epic **#311** (close red-teaming + annotation gaps).

## Scorecard — 8-layer reference framework

| # | Layer | What we run | Verdict |
|---|---|---|---|
| 1 | **Orchestration & Frameworks** | LangGraph (minicloud-agent), CrewAI (crew-agent), LangChain, Flowise | ✅ Covered |
| 2 | **Gateways & Routing** | **LiteLLM** — multi-cloud, least-busy routing, fallback, Valkey cache, budgets, tier RBAC | ✅ Strong (reference tool) |
| 3 | **Observability & Tracing** | **Langfuse** v3 + ClickHouse + Prometheus + Grafana + residency recording rules | ✅ Strong |
| 4 | **Evaluation & Red-teaming** | **Ragas** (faithfulness CI gate + ROUGE-L/Hit-Rate/MRR) + online drift CronJob → Langfuse | 🟡 Eval covered · **red-teaming gap** |
| 5 | **Security & Guardrails** | **Presidio** (PII) + **LlamaGuard** + detect-secrets + prompt-injection detection | ✅ Strong |
| 6 | **Vector Databases** | **Qdrant** (hybrid BM25 + HNSW + cross-encoder) | ✅ Covered (reference tool) |
| 7 | **Data Management & Alignment** | **MLflow** (≈ W&B) | 🔴 Gap: no annotation / no fine-tuning |
| 8 | **Inference Engines** | **vLLM** (CPU on-cluster); Ollama → Ollama Cloud | ✅ Covered · **CPU-constrained** (see [Compute Constraints](compute-constraints)) |

**6/8 layers covered with the exact reference tools** (LiteLLM · Langfuse · Ragas · LlamaGuard · Qdrant · vLLM · MLflow).

## Gaps

### 🟡 Gap 1 — Systematic red-teaming (layer 4) — *addressable, CPU-free*
Runtime guardrails exist (LlamaGuard, injection detection, Presidio) but there is
**no adversarial test suite in CI** — attacks are reacted to at runtime, not
tested offensively before merge. **Fix:** add **Promptfoo / DeepEval** as a CI
gate (injections, jailbreaks, PII-leak, prompt-extraction) — like the Ragas eval
gate. Strong AI-Act/DORA value. → backlog **#312**.

### 🔴 Gap 2 — Annotation & data curation (layer 7) — *addressable, CPU-free*
No human-annotation tool (Argilla / Label Studio). Golden sets (Ragas eval, RAG)
and dataset quality depend on hand-built sets with no human-in-the-loop. **Fix:**
deploy **Argilla** → annotate Langfuse traces, build/validate golden sets, curate
RAG datasets. Complements Ragas. → backlog **#313**.

### ⚪ Gap 3 — Fine-tuning / alignment (layer 7) — *accepted, out of scope*
Unsloth/Axolotl require a **GPU** → blocked by the infra (see
[Compute Constraints](compute-constraints)).

**Decision:** fine-tuning is **left to managed cloud providers** (AWS Bedrock /
Azure OpenAI), and used **only**:
1. **if no other option suffices** (prompt-engineering + RAG + few-shot exhausted), **and**
2. **depending on the problem** — a genuine domain-specialisation need that RAG/prompting cannot meet.

By default the strategy stays **prompt-engineering + RAG** (the platform's real
operating field, GPU-free). Managed fine-tuning is a **case-by-case last resort**,
not a standing objective — no on-cluster GPU, no self-hosted Unsloth/Axolotl, no
permanent training pipeline.

## Summary
The stack is **complete at 6/8 with reference tools**; the two real gaps
(**red-teaming + annotation**) are **CPU-free and addressable** (epic #311); the
third (**fine-tuning**) is correctly out of scope given the no-GPU infra, deferred
to managed cloud only when a specific problem demands it.
