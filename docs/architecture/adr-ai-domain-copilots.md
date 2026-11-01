---
id: adr-ai-domain-copilots
title: "ADR: AI as Governed Domain Copilots (not a chatbot)"
sidebar_label: 🤖 ADR — AI Domain Copilots
---

# ADR: AI as Governed Domain Copilots (not a chatbot)

**Status:** Accepted · **Date:** 2026-11-01 · **Scope:** cross-domain — Underwriting, Claims, Risk
Engineering, International Programmes, Broker Servicing · **Companion to:** the Document Intelligence Spine ADR

> **This page is the overview. The authoritative ADR lives with the platform** (so it appears in the org
> ADR index): **[minicloud-gitops/docs/ai-domain-copilots.md](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/ai-domain-copilots.md)**.

## Decision in brief

AI adds value across the whole value chain — not as a chatbot, but as assistance embedded in each domain's
workflow (underwriting extraction / synthesis, claims summarisation + fraud signals, risk-engineering
recommendation analysis, international master-vs-local diff, broker servicing). The shared AI-platform
primitives already run in production (LiteLLM, Qdrant, Langfuse, Presidio, agents); a domain assistant is
modelled only for Underwriting. Therefore:

> **Deliver AI as one shared, governed AI platform with many thin, human-in-the-loop domain copilots —
> never a standalone chatbot, never an autonomous decision-maker.**

- **One platform, many thin copilots** — Underwriting (`CAP-659`), Claims (`CAP-686`), Risk Engineering
  (`CAP-687`), Broker Servicing (`CAP-688`); each is a domain prompt + tool-set + workbench surface, not a
  new AI stack.
- **Human-in-the-loop is non-negotiable** — AI extracts / summarises / compares / signals; the human
  decides (never sets a reserve, declines a risk, or confirms fraud).
- **Governed, observable, cost-capped** — model gateway, LLMOps tracing, PII masking, guardrails, audit,
  egress control.

Full context, the rejected options (chatbot / per-domain stacks) and the prioritised build order are in the
authoritative ADR linked above. Companion decision: [Document Intelligence Spine](./adr-document-intelligence-spine.md).
