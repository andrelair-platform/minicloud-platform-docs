---
title: Capability Map & Registry — ktayl IS
sidebar_label: 🗺 Capability Map & Registry
---

# Capability Map & Registry — ktayl IS

> The **fine-grained functional target**: 19 L1 domains → ~150 L2/L3 capabilities, each mapped to our
> actual system, status, criticality and resilience target. This is the machine-readable companion to the
> [EA Blueprint](./enterprise-architecture-blueprint) (the narrative map). The full registry is the
> spreadsheet `insurance_enterprise_capability_registry.xlsx`; this page is its published summary + the
> **why** (the four problems) and the **order** (the roadmap).

:::note Two-layer model
This is the **ktayl-solution IS** (the insurer). **Retrieva** is a separate product — but its
provider→dependency→nth-party **graph is a reusable pattern** for portfolio accumulation (Problem 3 below).
:::

## 1. The north star — four existential problems (the *why* behind priority)

A capability earns priority by how much it attacks the industry's structural problems, not by parity with
a generic map.

| # | Problem (AXA/Chubb/HDI/Allianz) | What attacks it | Our position |
|---|---|---|---|
| **P1** | **Insurability crisis** — climate & secondary perils blow past actuarial models | Risk Engineering (**prevention**), CAT, Exposure & **Accumulation**, portfolio geo-steering | 🔴 our weakest area vs the #1 problem |
| **P2** | **Margin squeeze** — soft market + claims/social inflation | **Pricing Engine**, portfolio analytics (loss/combined ratio), UW discipline, **Data Platform** | 🔴 largely gap |
| **P3** | **Systemic cyber/AI accumulation** — one vuln → cascade of claims | portfolio **dependency graph**, exposure aggregation, cyber LOB, scenario analysis | 🟡 we own the exact pattern (Retrieva graph) |
| **P4** | **Legacy tech + talent gap** | a modern automated core + **AI copilots** | 🟢 our strength — no legacy debt, mature AI platform |

**The shape of the gap:** strong bottom-of-stack + AI (answers P4), a unique graph asset (answers P3),
and most of the insurance business core missing (which is exactly what attacks P1/P2).

## 2. The 19 domains (B2B industrial model) ↔ the 12-domain blueprint

The [EA Blueprint](./enterprise-architecture-blueprint) groups the IS as **12 business domains + 4
transversal layers**; the registry uses the finer **19 L1 domains** of the B2B-industrial capability
model. They reconcile — the 19 just split what the 12 bundled:

- **Submission (02)** and **Pricing & Portfolio (04)** are broken out of Underwriting.
- **Data (12)**, **Document (14)**, **Integration (16)**, **IT Ops (17)**, **Cyber/IAM (18)**, **AI (19)**
  are the blueprint's transversal layers made explicit L1 domains.
- **Compliance (13)** and **International (06)** are first-class L1s.

## 3. Status — the honest headline (150 capabilities)

| Status | Count | % | Where |
|---|---|---|---|
| 🟢 LIVE | 22 | 15% | Policy, **Claims (prod)**, IAM, AI platform, **Data Platform (Metabase BI)**, parts of Finance |
| 🟡 PARTIAL | 34 | 23% | **Underwriting (live on dev)**, ERPNext finance, compliance/DORA, integration primitives, DMS storage |
| 🟡 SCAFFOLD | 40 | 27% | Risk-Eng, Reinsurance, International, ITSM |
| 🔴 GAP | 54 | 36% | Submission, CRM/MDM, Pricing, Billing (insurance), Channels |

**~15% of the insurer's capabilities are live.** The GAPs cluster exactly where P1/P2 bite (pricing,
portfolio, prevention). Criticality mix: **31 Critical · 80 High · 39 Medium**.

> **Updated 2026-09-30 (verified against the running cluster):** since the last registry count, **Claims**
> promoted to **prod** (GlobalCore strangler shipped), the **Data Platform (Metabase BI, Slice 1)** came
> live, and **Underwriting** is **live on dev** — so the live/partial mix slightly understates reality; the
> exact counts await a registry re-count. Stage-by-stage live-vs-planned is in [§3.1](#31-contract-lifecycle-coverage--the-b2b-industrial-policy-end-to-end) below.

Per-domain status is in the [EA Blueprint gap analysis](./enterprise-architecture-blueprint); per-capability detail (owner, data, API, pain, AI potential, priority score) is in the registry spreadsheet.

### 3.1 Contract lifecycle coverage — the B2B industrial policy end-to-end

Corporate insurance is a **risk-engineering process**, not a product sale — *the insurer prices the
**exposure**, and the submission dossier IS that exposure*. This walks the full industrial-policy lifecycle
(`courtier → submission → underwriting → quote → bind → policy → billing → vie du contrat → renouvellement`)
and marks what actually runs. 🟢 prod · 🔵 dev only · 🟡 partial · ⚪ planned (verified 2026-09-30).

| Lifecycle stage | System / domain | Board | Status |
|---|---|---|---|
| Courtier / relationship | Distribution & CRM | #13 | ⚪ planned (no CRM) |
| **Submission / appel d'offres** (dossier d'exposition) | **Submission Hub** | #27 | ⚪ **not built** — board #27 opened 2026-09-30; build not started (the #1 front-door gap) |
| Underwriting — analyse · rating · capacité · T&C | **ktayl-underwriting** | #12 | 🔵 **live on dev** (intake→appetite→rating→quote→bind) |
| Pricing (dedicated) + portfolio analytics | Pricing & Portfolio | #04/#12 | ⚪ planned |
| Capacité (traité / facultative) | Reinsurance & Captive | #22 | ⚪ scaffold |
| **Quote** | ktayl-underwriting | #12 | 🔵 live on dev |
| Négociation courtier ↔ assureur | Broker portal | #13/#15 | ⚪ planned |
| **Binding** (→ écrit la police) | ktayl-underwriting → PAS | #12 | 🔵 live on dev |
| **Police / Policy** | **ktayl-policy-service** | #6 | 🟢 **live prod** |
| **Facturation de la prime** (échéances · IPT · commissions) | Insurance Billing | #14 | ⚪ planned — ERPNext is *general* finance, **not** insurance billing |
| Vie — avenants / endorsements | ktayl-policy-service | #6 | 🟡 live prod (depth partial) |
| Vie — certificates | Policy / International | #6/#23 | ⚪ planned |
| Vie — Risk Engineering (continu) | Risk Engineering | #21 | 🟡 scaffold |
| Vie — **sinistres / Claims** | **ktayl-claims** (GlobalCore ACL) | #11 | 🟢 **live prod** |
| **Renouvellement annuel** | UW / Policy renewal | #12/#6 | ⚪ planned |

**Verdict:** no single tool spans the lifecycle end-to-end. It is **live in the middle** — `Underwriting
(dev) → Policy (prod) → Claims (prod)` — while the **front door (Submission)**, the **financial tail
(insurance Billing, Renewal)** and the **prevention layer (Risk Engineering, Exposure/CAT/Accumulation)**
are gaps. The highest-leverage next build is the **Submission Hub**: it is the entry point of the whole
corporate flow and feeds the already-live Underwriting workbench — and it is exactly the "prices-the-
exposure" capability (P1/P2). See the [roadmap](#5-the-order--problem-prioritised-roadmap) (Stage C).

## 4. Resilience by design — DORA RTO/RPO tiers (business-capability layer)

DORA is a **transversal layer over every business capability**, distinct from Retrieva's third-party-ICT
slice. Each capability carries a criticality + RTO/RPO target (in the registry):

| Tier | Domains | RTO | RPO | DORA |
|---|---|---|---|---|
| **Critical** | Policy · Claims · Billing/Premium · Cyber/IAM | 2–4 h | 5–15 min | CIF |
| **High** | Underwriting · Submission · Pricing · Reinsurance · Finance/Actuarial · Data · Compliance · Risk Eng · International · Integration | 4–8 h | 15–60 min | Important |
| **Medium** | Distribution · Documents · Channels · IT Ops · AI | 8–24 h | 1–4 h | Supporting |

These are **targets**, not yet verified DR capabilities for the unbuilt domains — a capability's DORA row
is only "done" once backup + DR are tested (the DoD in the blueprint). Retrieva covers the ICT-third-party
obligation; this table covers the *business* capabilities.

## 5. The order — problem-prioritised roadmap

We are **past the tech foundation and the AI platform** already, so the backlog re-sequences around P1–P4:

- **Stage A — foundation registry (this work):** capability registry populated · [System of Record](./system-of-record) · [Canonical Data Model](./canonical-data-model) · DORA/RTO-RPO per capability. *(done)*
- **Stage B — unlock P1/P2/P3 analytics:** **Data Platform** (keystone) + **MDM** (Customer/Entity/Broker).
- **Stage C — operational core + AI showcase (P2 + P4):** **Submission Hub** → **Underwriting Workbench** + **Pricing Engine** (UW Copilot lands here).
- **Stage D — the P1/P3 differentiators:** **Risk Engineering** (prevention → P1) + **Exposure/Accumulation/CAT** (reuse the Retrieva graph → P3).
- **Stage E — the rest of the core + channels:** Insurance Billing, International/DIC-DIL, Reinsurance, Actuarial; then Broker + Client portals. *(Claims — via the GlobalCore legacy strangler — has since **shipped and is LIVE in prod**.)*

> This refines — does not replace — the blueprint's *business-tools-first, AI-last* build order. The
> difference is the **problem lens**: within "business tools first," build the ones that move P1/P2/P3
> first (Data + prevention + accumulation), not simply the operational order.

## 6. Sources

- **Registry (authoritative, fine-grained):** `insurance_enterprise_capability_registry.xlsx` — 150 capabilities × 28 fields (owner, data, API, criticality, DORA, RTO/RPO, pain, automation/AI potential, priority score, status).
- **Narrative map:** [EA Blueprint](./enterprise-architecture-blueprint) · [Architecture at a Glance](./architecture-at-a-glance).
- **Foundations:** [System of Record](./system-of-record) · [Canonical Data Model](./canonical-data-model).
- **Detail:** [Business Applications Catalog](./business-applications-catalog) · [Regulatory Operating Model](./regulatory-operating-model).
