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
| 🟢 LIVE | 22 | 15% | Policy, IAM, AI platform, parts of Finance |
| 🟡 PARTIAL | 34 | 23% | ERPNext finance, compliance/DORA, integration primitives, DMS storage |
| 🟡 SCAFFOLD | 40 | 27% | Underwriting, Claims, Risk-Eng, Reinsurance, International, ITSM |
| 🔴 GAP | 54 | 36% | Submission, CRM/MDM, Pricing, Billing, Data Platform, Channels |

**~15% of the insurer's capabilities are live.** The GAPs cluster exactly where P1/P2 bite (pricing,
portfolio, data, prevention). Criticality mix: **31 Critical · 80 High · 39 Medium**.

Per-domain status is in the [EA Blueprint gap analysis](./enterprise-architecture-blueprint); per-capability detail (owner, data, API, pain, AI potential, priority score) is in the registry spreadsheet.

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
- **Stage E — the rest of the core + channels:** Claims (via the GlobalCore legacy strangler), Insurance Billing, International/DIC-DIL, Reinsurance, Actuarial; then Broker + Client portals.

> This refines — does not replace — the blueprint's *business-tools-first, AI-last* build order. The
> difference is the **problem lens**: within "business tools first," build the ones that move P1/P2/P3
> first (Data + prevention + accumulation), not simply the operational order.

## 6. Sources

- **Registry (authoritative, fine-grained):** `insurance_enterprise_capability_registry.xlsx` — 150 capabilities × 28 fields (owner, data, API, criticality, DORA, RTO/RPO, pain, automation/AI potential, priority score, status).
- **Narrative map:** [EA Blueprint](./enterprise-architecture-blueprint) · [Architecture at a Glance](./architecture-at-a-glance).
- **Foundations:** [System of Record](./system-of-record) · [Canonical Data Model](./canonical-data-model).
- **Detail:** [Business Applications Catalog](./business-applications-catalog) · [Regulatory Operating Model](./regulatory-operating-model).
