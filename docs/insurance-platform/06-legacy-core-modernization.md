---
id: legacy-core-modernization
title: Legacy-Core Modernization (Strangler Fig)
sidebar_label: Legacy-Core Modernization
---

# Legacy-Core Modernization — the Oracle legacy & the strangler

:::note Status — PROPOSAL for validation (no build yet)
This is the **documentation alignment** for the legacy-core spine of the ktayl IS. Nothing is built:
no Oracle image is pulled, no `ktayl-legacy-core` repo exists, no code. The gates are:
**align docs (this + the EA blueprint) → validate → Path-C planning set → validate → build.**
This is **ktayl-solution IS** work (the business/org context), **not** the Retrieva certification product.
:::

## 1. Why a legacy core at all

A real IARD insurer's information system is **not** 16 clean greenfield microservices. It is a
**legacy core that still works** — an old, authoritative, PL/SQL-heavy claims/policy system — with a
**modern platform grown around it** that wraps it, intercepts its changes, and gradually *strangles*
it, but rarely rips-and-replaces it. Full replacement almost never happens; **the wrapping is the
steady state**. This is the **Strangler Fig + Anti-Corruption Layer (ACL)** pattern (Fowler), and it is
already a stated ktayl principle (*"Strangler Fig / ACL / event interception for legacy"*) — it just
never had a legacy artifact to apply to.

Standing up a deliberate legacy core is what turns the ktayl IS from *"I built some modern insurance
services"* into *"I modernized a real enterprise with a legacy Oracle heart"* — which is exactly how
HDI (and most insurers, banks, telecoms) actually operate, and a materially stronger architecture story.

## 2. What the legacy is (the decision)

**The legacy = a GERAS-style Claims + legacy-Policy core**, on Oracle, holding the authoritative
historical book, with business logic in **PL/SQL**. **`ktayl-claims` (#11)** becomes its modern
**Anti-Corruption Layer / strangler**. This resolves cleanly because:

- `ktayl-claims` is an empty scaffold today → no modern service to conflict with.
- **GERAS** is the real anchor for "legacy claims" (an HDI legacy claims system).
- **`ktayl-policy-service`** stays the *modern* PAS (live, Go/Postgres) and simply **reads the legacy**
  for the historical policy book via the ACL — the two coexist, exactly like reality.
- It yields one coherent narrative: *a modern GitOps + AI platform strangling a legacy Oracle insurance core.*

### The legacy schema (indicative — real, not a toy)

The legacy must actually behave like a legacy: it runs, holds the authoritative data, and carries real
business logic in PL/SQL that you must **understand before wrapping** (you do not edit its internals).

```
Tables:   CUSTOMER · POLICY (legacy book) · CLAIM · CLAIM_TRANSACTION
          CLAIM_RESERVE · PAYMENT · BROKER · PRODUCT
PL/SQL:   PKG_CLAIMS · PKG_POLICIES · PKG_PAYMENTS
          PROC_CREATE_CLAIM · FUNC_CALCULATE_RESERVE · TRG_CLAIM_AUDIT
```

Some business rules live in PL/SQL, some in the wrapping service — the point is the boundary is explicit
and the legacy is **frozen** (wrapped, intercepted, strangled — not refactored).

## 3. How Oracle runs — the image & placement

**No standalone Oracle infrastructure.** One container, official Free edition — the old XE lineage,
zero licensing cost, a single self-contained instance (which is what a wrapped legacy core looks like
from the outside anyway).

- **Image:** `container-registry.oracle.com/database/free:latest-lite` (the `-lite` tag). Community
  mirror `gvenzl/oracle-free` (Docker Hub) is the fallback if the registry terms-acceptance/login is
  inconvenient.
- **Placement — deliberately OUTSIDE Kubernetes**, as a Docker container on the controller (next to
  MinIO). This is *more* correct, not a compromise:
  - **Realism:** mirrors "legacy core on traditional infra, modern platform on k8s" — the exact
    enterprise shape this whole spine is about.
  - **Resource pragmatism:** keeps ~2 GB Oracle + its storage off the k3s cluster (no Longhorn PVC, no
    dependency on the storage layer that has been the platform's reliability pain).
  - Modern services in k8s reach it at `controller-ip:1521` **through the ACL** — a clean, realistic
    "cross the boundary to the legacy" hop, governed by NetworkPolicy egress.
- **Sizing gate (to settle in the Path-C architecture):** the controller disk is tight (98 G, MinIO
  ~33 G, prior disk-full cascades). Oracle Free needs a few GB — size it and gate it, or place the
  container on a worker node's local disk (still plain Docker, still outside k3s) if the controller is
  too tight.

Connection facts (Free image): port `1521`, service `FREEPDB1` (pluggable) / `FREE` (container),
`ORACLE_PWD` sets `SYS`/`SYSTEM`/`PDBADMIN`. Credentials go to **Vault** (`secret/platform/oracle-legacy`)
→ ESO → the ACL service — never in Git or images.

## 4. The integration seams (how the modern layer wraps it)

Three seams, all already native to the platform:

1. **Anti-Corruption-Layer APIs** — `ktayl-claims` (#11) exposes clean REST/OpenAPI (`GET /claims/{id}`,
   `POST /claims`, `PATCH /claims/{id}/status`, …) over the legacy. No app, portal, or AI touches Oracle
   directly; everything goes through the ACL, where authz/audit/rate-limits/PII controls live.
2. **CDC (Debezium → NATS)** — a Debezium connector captures legacy changes and publishes domain events
   (`CLAIM_STATUS_CHANGED`, `POLICY_ENDORSED`, `PAYMENT_RECEIVED`) to **NATS** (the existing backbone —
   **not** Kafka; Debezium Server sinks to NATS). Consumers (risk, analytics, notifications) **react**
   instead of polling Oracle. This is a new **platform capability** (`ktayl-integration` / IS Foundations),
   valuable independently of Oracle.
3. **AI access, governed** — the AI reaches **structured legacy data only via approved SQL-tools behind
   the ACL** (never the LLM emitting SQL at Oracle), and **documents via RAG** (Qdrant). The human's
   identity is propagated into every tool call (Authentik) — the AI can never become an authz bypass
   (threat-model T7). PII is Presidio-masked before any LLM call.

## 5. Per-domain re-alignment (what changes for the existing scaffolds)

| Domain / repo | Role in the spine |
|---|---|
| **`ktayl-legacy-core`** (new) | the Oracle legacy system-of-record (GERAS-style claims + legacy policy book) |
| **`ktayl-claims` #11** | the **ACL / strangler** over the legacy; new claims capability built modern |
| **`ktayl-policy-service`** (live) | modern PAS; reads the legacy for the historical book via the ACL |
| **`ktayl-underwriting` #12** | modern; binds into the modern PAS (unchanged) |
| **`ktayl-integration` #25** | hosts the **CDC (Debezium→NATS)** capability + the ACL egress patterns |
| distribution/finance/risk/reinsurance/compliance | net-new modern; consume via ACL APIs + NATS events |
| **Data Platform #5** | OLAP/BI reads through CDC/ACL — never the legacy directly (OLTP↔OLAP split) |
| **AI Ops Copilot #19** | LAST — orchestrates ACL tools + RAG once domains hold real data |

## 6. Build sequence (gated)

```
now      Underwriting #12 thin slice (in flight — don't interrupt)
  →      align docs (EA blueprint §2b + this doc)   ← YOU VALIDATE HERE
  →      ktayl-legacy-core Path-C planning set (brief/PRD/architecture/threat-model/ADRs)  ← validate
  →      build: Oracle Free container + legacy schema/PL/SQL  →  ktayl-claims ACL  →  CDC→NATS
  →      strangler domains + Data Platform #5
  →      AI Ops Copilot #19 (the "Claims Copilot") — the capstone, last
```

**Three validation gates before any Oracle runs.** No image is pulled and no repo is created until the
`ktayl-legacy-core` Path-C planning set is written and validated — same discipline as Underwriting #12.

## 7. Governance & compliance

Path-C (new product + a security/architecture boundary — a legacy datastore, CDC, cross-boundary AI
access) → the **architecture + security review gates** apply. Compliance-by-design lands in the Path-C
threat model: legacy connection secrets (Vault/ESO), default-deny egress to `controller-ip:1521`, PII
masking before AI, identity propagation, and an audit trail on every ACL + AI action. Evidence accrues to
the **Regulatory & Compliance #15** control library. This blueprint spine is **BC01 (piloter)** evidence;
the wrapping design is **BC02/BC03**.

## References

- [Enterprise Architecture Blueprint](./enterprise-architecture-blueprint) §2b — the spine in the IS model
- [Business Applications Catalog](./business-applications-catalog) — per-app inventory
- Pattern origin: Strangler Fig + Anti-Corruption Layer (Fowler); ktayl principle *Strangler Fig / ACL / event interception*
