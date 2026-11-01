---
id: adr-document-intelligence-spine
title: "ADR: Document Intelligence as a Horizontal Platform Spine"
sidebar_label: 📄 ADR — Document Intelligence Spine
---

# ADR: Document Intelligence as a Horizontal Platform Spine

**Status:** Accepted · **Date:** 2026-11-01 · **Scope:** cross-domain — Submission, Underwriting, Policy,
Billing, Claims, Risk Engineering, Reinsurance, DMS

> **This page is the overview. The authoritative ADR lives with the platform** (so it appears in the org
> ADR index): **[minicloud-gitops/docs/document-intelligence-spine.md](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/document-intelligence-spine.md)**.

## Decision in brief

Corporate insurance is document-intensive — a single international policy can spawn hundreds, sometimes
thousands, of documents over its life, and the **same** primitives (OCR / IDP, structured extraction, RAG,
AI assistance, workflow) are needed by every domain. The capability register already places those
primitives in **platform** domains (DMS, Integration, AI Platform, Data), not inside any one business
domain. Therefore:

> **Build document intelligence once, as a shared horizontal "document spine," consumed by every business
> domain through APIs and events — never re-implemented per domain.**

```
INGEST -> CLASSIFY -> EXTRACT (structured) -> LINK (policy / claim / client)
       -> INDEX (RAG) -> ASSIST (AI, human-in-the-loop) -> GOVERN (PII / retention / audit)
```

- **Reuse the live primitives** (markitdown + Docling, rag-ingest, Qdrant, LiteLLM, Langfuse, Presidio;
  Retrieva multimodal ingestion is the reference) — build only the thin insurance-specific layer.
- **Human-in-the-loop + governance are mandatory**; the linkage / dossier layer is sequenced behind MDM.

Full context, the rejected options (per-domain / SaaS), and the consequences + build order are in the
authoritative ADR linked above. Companion decision: [AI as Governed Domain Copilots](./adr-ai-domain-copilots.md).
