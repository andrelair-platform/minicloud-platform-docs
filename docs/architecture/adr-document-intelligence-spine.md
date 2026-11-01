---
id: adr-document-intelligence-spine
title: "ADR: Document Intelligence as a Horizontal Platform Spine"
sidebar_label: 📄 ADR — Document Intelligence Spine
---

# ADR: Document Intelligence as a Horizontal Platform Spine

**Status:** Accepted · **Date:** 2026-11-01 · **Deciders:** Platform / IS Architecture
**Scope:** cross-domain — Submission, Underwriting, Policy, Billing, Claims, Risk Engineering, Reinsurance, DMS

## Context

Corporate insurance is document-intensive. A single international policy can generate hundreds — in
complex structures, thousands — of documents and exchanges over its life: submission, quote, binder,
policy, schedule, endorsement, certificate, invoice, claim notification, loss report, risk-engineering
and survey reports, reinsurance bordereau, broker statement, renewal presentation. The **same**
intelligence primitives — classification, OCR / IDP, structured extraction, RAG, AI assistance, workflow —
are needed by **every** business domain.

The capability register already identifies these primitives, and — tellingly — they sit in **platform**
domains (14 DMS, 16 Integration / Workflow, 19 AI Platform, 12 Data), not inside any one business domain:
`CAP-646` OCR/IDP, `CAP-309` Document Intelligence, `CAP-130`/`CAP-132`/`CAP-248` RAG / vector / publication,
`CAP-133` Agent Platform, `CAP-265`–`CAP-270` Workflow, `CAP-078`–`CAP-082` Data Acquisition,
`CAP-648`/`CAP-649` document-to-record linkage + dossier, `CAP-526`–`CAP-531` generation,
`CAP-641`–`CAP-645` e-signature / sealing.

The platform already runs the core primitives in production: a RAG ingestion pipeline (markitdown + Docling,
`rag-ingest`, Qdrant), a governed model gateway (LiteLLM), LLM observability (Langfuse), and PII redaction
(Presidio). Retrieva's multimodal ingestion is a working reference implementation.

## Decision

Build document intelligence **once, as a shared horizontal "document spine,"** consumed by every business
domain through APIs and events. Business domains MUST NOT re-implement OCR / RAG / extraction privately.

The spine is a single governed pipeline:

```
INGEST -> CLASSIFY -> EXTRACT (structured) -> LINK (policy / claim / client)
       -> INDEX (RAG) -> ASSIST (AI, human-in-the-loop) -> GOVERN (PII / retention / audit)
```

Principles:

1. **Reuse the live primitives — extend, don't rebuild.** New work is the thin insurance-specific layer
   (per-document-type extraction schemas and generation templates), not another RAG stack.
2. **Model each document type as an extraction schema plus a generation template, registered in the DMS** —
   never a bespoke per-domain parser. That is what keeps the capability horizontal.
3. **Human-in-the-loop + governance are mandatory.** Documents feed underwriting and claims *decisions*, so
   never LLM-alone: deterministic extraction + AI reasoning + human decision, wrapped with PII masking
   (`CAP-317`), retention / legal-hold (`CAP-096`/`CAP-097`/`CAP-242`), AI audit trail (`CAP-315`), eIDAS
   sealing (`CAP-643`), LiteLLM-governed models and default-deny egress.
4. **Sequence against the MDM dependency.** Ingest / classify / RAG / search are not blocked (already live).
   Document-to-record linkage and the client/policy dossier (`CAP-648`/`CAP-649`) need the MDM client and
   policy keys plus the canonical data model first.

## Options considered

- **A — Per-domain document handling (rejected).** Each domain builds its own OCR / extraction / RAG.
  Fastest locally, but duplicates the hardest, most governance-sensitive code N times, drifts, and
  multiplies the PII / DORA surface.
- **B — Horizontal document spine (chosen).** One governed pipeline, many consumers. Higher up-front
  coordination, but a single place for PII / audit / retention, reuse of the live primitives, and
  consistent extraction quality.
- **C — Buy a document-intelligence SaaS (partial).** Viable for commodity OCR, but the insurance-specific
  extraction / linkage and the DORA data-residency / egress posture argue for self-hosting on the existing
  platform. Revisit per the need-first adoption gate.

## Consequences

- **Positive:** one governed PII / audit / retention boundary; reuse of the live RAG / model-gateway /
  LLMOps stack; consistent extraction; a clear AI-native differentiator (the same muscle as Retrieva);
  business domains stay thin.
- **Accepted trade-offs:** the spine is a shared dependency and needs clear API / SLA ownership
  (DMS #24 / Integration #25 / AI Platform #19); the linkage and dossier layer is blocked on MDM; and each
  document type needs up-front schema / template modelling.
- **Build order:** (a) ingest + classify + RAG / search over the live corpus; (b) structured IDP on
  high-value types (submission exposure `CAP-135`, loss runs, bordereaux); (c) linkage + dossier once MDM
  lands; (d) template assembly / generation (`CAP-647`, `CAP-526`–`CAP-531`); with AI assistants (`CAP-659`)
  as human-in-the-loop copilots throughout.

## Related

- Capability register: `data/capability-register.csv` (the primitives referenced above) and gap analysis §9 C.
- Boundary rule: `platform-vs-information-system.md` (document intelligence is a platform capability the IS consumes).
- Reference implementation: Retrieva multimodal ingestion.
