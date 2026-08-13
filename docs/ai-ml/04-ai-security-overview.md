---
id: ai-security-overview
title: AI Security Overview
sidebar_position: 4
---

# AI Platform Security Overview

Building AI is straightforward. Securing it is not. The ktayl-solution AI platform handles confidential policy documents, claim records, financial data, and actuarial models — all of which are targets for a distinct set of attacks that do not exist in conventional software systems.

This section covers six threat categories and the controls implemented against each.

---

## Threat Landscape

```text
┌─────────────────────────────────────────────────────────────────────┐
│  THREAT 1 — HALLUCINATION                                           │
│  Model invents facts: wrong franchise amounts, non-existent clauses  │
│  → Retrieval gate · System prompts · Citation check · LLM-as-judge  │
├─────────────────────────────────────────────────────────────────────┤
│  THREAT 2 — BIAS                                                    │
│  Model treats people differently based on name, age, origin          │
│  → Counterfactual CI gate · Neutrality score · ACPR audit report    │
├─────────────────────────────────────────────────────────────────────┤
│  THREAT 3 — PROMPT INJECTION                                        │
│  Attacker overrides system prompt or hides instructions in documents  │
│  → PromptGuard sidecar · Regex hook · RAG chunk scan · Canary token │
├─────────────────────────────────────────────────────────────────────┤
│  THREAT 4 — DATA POISONING                                          │
│  Corrupted documents enter Qdrant; wrong answers look correct         │
│  → Provenance · Collection ACL · Consistency check · Integrity scan  │
├─────────────────────────────────────────────────────────────────────┤
│  THREAT 5 — MODEL INVERSION / EXTRACTION                            │
│  Systematic querying reconstructs the full knowledge base            │
│  → Enumeration detection · Response abstraction · LUKS encryption   │
├─────────────────────────────────────────────────────────────────────┤
│  THREAT 6 — MEMBERSHIP INFERENCE                                    │
│  Single-query probing confirms whether a specific record is indexed  │
│  → Identifier stripping · Neutral error message · GDPR Art. 15     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Six Controls Pages

| Page | Threat | Primary risk |
|---|---|---|
| [Hallucination Controls](hallucination-controls) | Model accuracy | Wrong claim amounts, invented policy clauses |
| [Bias Detection](bias-detection) | Fairness + legal | Differential treatment by name/age/origin — EU AI Act Art. 9 |
| [Prompt Injection](prompt-injection) | Active attack | System prompt override, document-embedded instructions |
| [Data Poisoning](data-poisoning) | Knowledge base integrity | Corrupt Qdrant documents that fool all quality metrics |
| [Model Inversion](model-inversion) | Data extraction | Systematic enumeration of entire policy knowledge base |
| [Membership Inference](membership-inference) | Record existence probing | Confirming whether a specific claim/policy/person is indexed |

---

## Risk by Department

How each threat maps to department criticality:

| Department | Hallucination | Bias | Prompt Injection | Data Poisoning | Extraction | Membership Inference |
|---|---|---|---|---|---|---|
| Sinistres | CRITICAL | CRITICAL | CRITICAL | CRITICAL | HIGH | CRITICAL |
| Finance | CRITICAL | CRITICAL | HIGH | CRITICAL | HIGH | HIGH |
| Juridique | CRITICAL | CRITICAL | HIGH | CRITICAL | HIGH | HIGH |
| Souscription | HIGH | HIGH | HIGH | HIGH | HIGH | HIGH |
| Actuariat | HIGH | HIGH | MEDIUM | HIGH | MEDIUM | MEDIUM |
| Réassurance | HIGH | HIGH | MEDIUM | HIGH | MEDIUM | MEDIUM |
| Audit | HIGH | HIGH | MEDIUM | HIGH | LOW | MEDIUM |
| Commercial | MEDIUM | MEDIUM | MEDIUM | MEDIUM | LOW | LOW |
| IT | LOW | LOW | MEDIUM | LOW | LOW | LOW |
| RH | LOW | LOW | MEDIUM | LOW | LOW | LOW |

---

## Controls Across the Request Lifecycle

Every user request passes through a layered set of controls. Each layer operates independently — a failure in one does not disable the others.

```text
User query (Open WebUI)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  PRE-CALL HOOKS (LiteLLM)                                 │
│                                                           │
│  EnumerationDetectionHook  ← model inversion              │
│  PromptInjectionHook       ← direct injection + GDPR Art.15│
│  PromptGuard sidecar       ← ML-based injection detection │
│  RetrievalGroundingHook    ← hallucination + identifier   │
│  │                            stripping (membership inf.) │
│  IngestionAuthHook         ← data poisoning (write ACL)   │
│  DataSovereigntyHook       ← data sovereignty routing     │
└───────────────────┬───────────────────────────────────────┘
                    │ all hooks pass
                    ▼
        Qdrant retrieval (RAG)
                    │
                    ▼
┌───────────────────────────────────────────────────────────┐
│  RAG CHUNK SCAN                                           │
│  Indirect injection patterns removed from context         │
│  Chunk provenance metadata attached to trace              │
└───────────────────┬───────────────────────────────────────┘
                    │
                    ▼
        Ollama (inference)
        Department system prompt: cite · abstract · say "I don't know"
                    │
                    ▼
┌───────────────────────────────────────────────────────────┐
│  POST-CALL HOOKS (LiteLLM)                                │
│                                                           │
│  Canary token check        ← prompt injection detection   │
│  Persona break detection   ← injection success signal     │
│  Citation check            ← hallucination (uncited fact) │
│  Verbatim reproduction     ← model inversion (abstraction)│
│  RAG sources logged        ← data poisoning (provenance)  │
│  Feedback anomaly check    ← data poisoning (👍 abuse)    │
└───────────────────┬───────────────────────────────────────┘
                    │
                    ▼
        Response to user
```

---

## Async / Batch Controls

Controls that run outside the request path — measuring quality over time and generating compliance evidence:

| Schedule | Control | Threat |
|---|---|---|
| Every 15 min | Ragas fast pass (faithfulness + relevancy) | Hallucination |
| Nightly 02:00 | Full Ragas + LLM-as-judge (5 dims + neutrality) | Hallucination + Bias |
| Nightly 02:00 | Counterfactual consistency evaluation | Bias |
| Weekly Sunday | Qdrant integrity scan (all collections) | Data poisoning |
| Weekly Sunday | Model tier comparison (1B vs 3B golden datasets) | Hallucination |
| Monthly 1st | ACPR bias audit report → MinIO `ai-audit/` | Bias (regulatory) |
| Every PR | Ragas CI gate + counterfactual CI gate | Hallucination + Bias |

---

## Langfuse Event Quick Reference

All security events land in Langfuse. Filter by `event.name` to see any threat category:

| Event name | Threat | Level |
|---|---|---|
| `retrieval_gate_blocked` | Hallucination | INFO |
| `uncited-specific-claim` | Hallucination | WARNING |
| `low_self_confidence` | Hallucination | WARNING |
| `protected-attr-comparison-detected` | Bias | WARNING |
| `feedback-quality-mismatch` | Bias / Data poisoning | WARNING |
| `coordinated-positive-feedback` | Data poisoning | ERROR |
| `prompt-injection-blocked` | Prompt injection | ERROR |
| `promptguard-injection-detected` | Prompt injection | ERROR |
| `indirect-injection-chunk-stripped` | Prompt injection | WARNING |
| `system-prompt-leak-detected` | Prompt injection | ERROR |
| `persona-break-detected` | Prompt injection | ERROR |
| `repeated-injection-attempts` | Prompt injection | ERROR |
| `indirect-injection-in-document` | Data poisoning | ERROR |
| `document-consistency-conflict` | Data poisoning | WARNING |
| `collection-write-denied` | Data poisoning | WARNING |
| `bulk-ingestion-rate-exceeded` | Data poisoning | ERROR |
| `rag-sources-used` | Data poisoning (audit) | INFO |
| `document-ingested` | Data poisoning (audit) | INFO |
| `weekly-integrity-scan-complete` | Data poisoning | INFO/ERROR |
| `enumeration-detected` | Model inversion | ERROR |
| `enumeration-warning` | Model inversion | WARNING |
| `verbatim-reproduction-detected` | Model inversion | WARNING |
| `membership-probe-identifiers-stripped` | Membership inference | WARNING |
| `gdpr-access-request-detected` | Membership inference | INFO |

---

## Implementation Status

| Control | Issue | Status |
|---|---|---|
| LiteLLM gateway + virtual keys + rate limits | #34 | Planned |
| Presidio PII masking | #37 | Planned |
| Qdrant RAG pipeline | #38 | Planned |
| Ragas evaluation CronJob | #39 | Planned |
| Retrieval grounding gate + citation check hook | #44 | Planned |
| Counterfactual CI gate + neutrality judge + ACPR audit report | #45 | Planned |
| PromptGuard sidecar + injection hook + canary token | #46 | Planned |
| Chunk provenance + collection ACL + integrity scan + feedback anomaly | #47 | Planned |
| Enumeration detection + response abstraction + Qdrant LUKS | #48 | Planned |
| Identifier stripping + neutral error message + GDPR Art. 15 routing | #49 | Planned |

All issues are tracked in [andrelair-platform/platform-backlog](https://github.com/andrelair-platform/platform-backlog/issues).

---

## Regulatory Coverage

| Regulation | Controls that satisfy it |
|---|---|
| EU AI Act Art. 9 (risk management) | Counterfactual gate, neutrality judge, ACPR monthly report |
| EU AI Act Art. 13 (transparency) | Langfuse trace provenance, citation compliance score |
| EU AI Act Art. 14 (human oversight) | Human feedback loop, annotation queue, neutrality alert |
| GDPR Art. 22 (no fully automated decisions) | Human oversight rate tracked in ACPR report |
| Code pénal Art. 225-1 (anti-discrimination) | Counterfactual consistency ≥ 0.85 per protected attribute |
| GDPR Art. 15 (right of access) | GDPR routing hook → HTTP 451 → DPO email; AI never answers membership questions |
| ACPR inspection | Monthly bias audit PDF → MinIO `ai-audit/`, 7-year retention |
