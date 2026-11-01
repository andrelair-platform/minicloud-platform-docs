---
id: adr-ai-domain-copilots
title: "ADR: AI as Governed Domain Copilots (not a chatbot)"
sidebar_label: 🤖 ADR — AI Domain Copilots
---

# ADR: AI as Governed Domain Copilots (not a chatbot)

**Status:** Accepted · **Date:** 2026-11-01 · **Deciders:** Platform / IS Architecture
**Scope:** cross-domain — Underwriting, Claims, Risk Engineering, International Programmes, Broker Servicing
**Companion to:** the Document Intelligence Spine ADR (AI is that spine's `ASSIST` stage).

## Context

AI can add value across the whole corporate-insurance value chain — not as a chatbot, but as assistance
embedded in each domain's workflow: underwriting (submission / exposure extraction, claims-history
synthesis, risk signals, renewal prep), claims (document classification, coverage retrieval, claim
summarisation, reserve-support, fraud / anomaly signals), risk engineering (compare reports, extract and
track recommendations, surface critical open recommendations, correlate them with losses), international
programmes (master-vs-local difference detection), and broker servicing (certificates, document requests,
endorsement tracking, programme-status answers, renewal consolidation).

The register shows the shape of the problem: the shared AI-platform primitives already exist
(`CAP-127`–`CAP-133` model gateway / RAG / agents / embeddings / vector search, `CAP-309`–`CAP-317`
document-intelligence / guardrails / observability / cost / access / audit / governance / PII) and run in
production (LiteLLM, Qdrant, Langfuse, Presidio, the existing agents). But a domain AI assistant is
modelled only for **Underwriting** (`CAP-659`). Claims, Risk Engineering and Broker Servicing have none;
the international master-local diff is already covered by deterministic capabilities (`CAP-539`–`CAP-543`).

## Decision

Deliver AI as **one shared, governed AI platform with many thin, human-in-the-loop domain copilots** —
never a standalone chatbot, never an autonomous decision-maker.

1. **Copilots, not a chatbot.** AI is the `ASSIST` stage of the document spine plus signals / analytics
   over the data platform, surfaced inside each domain's workbench (the underwriter's, the adjuster's, the
   risk engineer's, the broker-servicing desk).
2. **One platform, many thin copilots.** Every copilot runs on the same primitives (model gateway, RAG,
   agents, LLMOps). A copilot is a domain prompt + tool-set + workbench surface — not a new AI stack.
   Copilots: Underwriting (`CAP-659`), Claims (`CAP-686`), Risk Engineering (`CAP-687`), Broker Servicing
   (`CAP-688`).
3. **Human-in-the-loop is non-negotiable.** AI extracts, summarises, compares and signals; the human
   decides. AI never sets a reserve, declines a risk, confirms fraud, or issues a binding answer — it
   drafts and surfaces, a person approves. Deterministic rules + AI reasoning + human decision.
4. **Governed, observable, cost-capped.** Every copilot routes through the governed model gateway
   (budget + routing), is traced in the LLMOps layer, PII-masked, guardrailed, access-controlled, audited,
   and egress-gated.
5. **Reuse over rebuild.** Same ingestion / RAG / agent stack as the document spine and the existing
   agents (Retrieva is the reference).

## Options considered

- **A — AI chatbot bolt-on (rejected).** A single general assistant detached from domain data and
  workflow: low trust, no governance surface, no workflow integration.
- **B — Per-domain bespoke AI stacks (rejected).** Each domain builds its own models / RAG: duplication,
  drift, N governance surfaces — the same anti-pattern the document-spine ADR rejects.
- **C — One platform, thin HITL copilots (chosen).** Shared governed platform, domain copilots on top;
  single governance / observability / cost boundary; consistent human-in-the-loop posture.

## Consequences

- **Positive:** one governance / observability / cost boundary for all AI; fast to add a domain copilot
  (thin layer); a consistent HITL + audit posture for DORA; a clear AI-native differentiator.
- **Accepted trade-offs:** the AI platform is a shared dependency needing clear ownership (AI Platform
  #4 / #19); copilot quality depends on the document spine + data platform maturity; each copilot needs
  domain prompt / tool work and an evaluation harness.
- **Prioritisation (leverage × data-readiness):** UW submission extraction + renewal year-on-year
  comparison first (doc-spine-ready) → Claims summarisation + fraud signals → Risk-Engineering
  recommendation copilot → Broker servicing. The international master-local diff is nearly free (automate
  `CAP-539`–`CAP-543` with the same platform).

## Related

- Companion: the Document Intelligence Spine ADR (AI is its `ASSIST` stage).
- Capabilities: `CAP-127`–`CAP-133` / `CAP-309`–`CAP-317` (AI platform); `CAP-659` / `CAP-686` / `CAP-687` /
  `CAP-688` (domain copilots); `CAP-539`–`CAP-543` (deterministic master-local diff).
- Governance: the per-product LLMOps standard and the AI-native DORA (human-in-the-loop) posture.
