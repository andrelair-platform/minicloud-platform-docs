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
| 4 | **Evaluation & Red-teaming** | **Ragas** (faithfulness CI gate) + online drift CronJob + **red-team gate** (adversarial suite, #312) | ✅ Covered |
| 5 | **Security & Guardrails** | **Presidio** (PII) + **LlamaGuard** + detect-secrets + prompt-injection detection | ✅ Strong |
| 6 | **Vector Databases** | **Qdrant** (hybrid BM25 + HNSW + cross-encoder) | ✅ Covered (reference tool) |
| 7 | **Data Management & Alignment** | **MLflow** (≈ W&B) + **Langfuse annotation** (queues/scores/datasets, #313) | ✅ Annotation covered · fine-tuning out of scope |
| 8 | **Inference Engines** | **vLLM** (CPU on-cluster); Ollama → Ollama Cloud | ✅ Covered · **CPU-constrained** (see [Compute Constraints](compute-constraints)) |

**8/8 layers covered** (LiteLLM · Langfuse · Ragas · LlamaGuard · Qdrant · vLLM · MLflow), with red-teaming (#312) and annotation (#313) closed; fine-tuning delegated to managed cloud.

## Gaps

### ✅ Gap 1 — Systematic red-teaming (layer 4) — *CLOSED (#312)*
Runtime guardrails exist (LlamaGuard, injection detection, Presidio) but there is
**no adversarial test suite in CI** — attacks are reacted to at runtime, not
tested offensively before merge. **Fix:** add **Promptfoo / DeepEval** as a CI
gate (injections, jailbreaks, PII-leak, prompt-extraction) — like the Ragas eval gate. **Delivered** as a PostSync red-team gate (8 attacks: injection/jailbreak/extraction/PII/toxicity), verified run **8/8 PASS**.

### ✅ Gap 2 — Annotation & data curation (layer 7) — *CLOSED (#313)*
No human-annotation tool (Argilla / Label Studio). Golden sets (Ragas eval, RAG)
and dataset quality depend on hand-built sets with no human-in-the-loop. **Fix:**
**delivered via Langfuse** (Annotation Queues + Scores + Datasets — already deployed) instead of Argilla, which needs ElasticSearch (too heavy for the CPU-only cluster). See `docs/ai-governance/annotation-workflow.md`.

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
