---
title: System-of-Record Registry — ktayl IS
sidebar_label: 🗂 System of Record
---

# System-of-Record (SoR) Registry — ktayl IS

> **One business object → one authoritative source.** Other systems hold projections/copies, never
> become the official source. This is the rule that stops "Customer Name" differing across CRM / Policy /
> Claims / Finance / Excel. Companion: [Canonical Data Model](./canonical-data-model) · [Capability Map](./capability-map).

Status: 🟢 live SoR · 🟡 partial/scaffold · 🔴 no authoritative source yet.

## Transactional objects

| Business object | Target SoR | Our SoR today | Status |
|---|---|---|---|
| **Policy** | Policy Admin | **ktayl-policy-service** | 🟢 |
| **Identity** | IAM | **ktayl-iam** + Authentik | 🟢 |
| **Payment / Ledger** | Finance ERP | **ERPNext** (GL/AP/AR) | 🟡 |
| **Risk / Quote** | Underwriting | ktayl-underwriting (scaffold) | 🟡 |
| **Claim / Reserve** | Claims | ktayl-claims (scaffold; legacy GlobalCore spine) | 🟡 |
| **Survey / Recommendation** | Risk Engineering | ktayl-risk-engineering (scaffold) | 🟡 |
| **Reinsurance Contract** | Reinsurance | ktayl-reinsurance (scaffold) | 🟡 |
| **Document** | DMS | ktayl-dms (scaffold); Nextcloud/Docuseal (storage/e-sign) | 🟡 |
| **ICT vendor / third-party** | Procurement / GRC | **Retrieva** (DORA arrangement graph) — ICT only | 🟡 |
| **Submission** | Submission Platform | — | 🔴 |
| **Customer / Broker** | CRM / MDM | — | 🔴 |
| **Invoice / Premium** | Billing | — | 🔴 |

## MDM master / reference objects (all 🔴 — no MDM yet)

Legal Entity · Country · Currency · Industry · Product · Coverage · Location/Site — none have an
authoritative master today.

## Two structural consequences

1. **No authoritative Customer** (no CRM/MDM) is the most damaging gap — every domain will invent its own
   customer record. **MDM + a customer SoR should lead the foundation wave.**
2. **Retrieva is authoritative for ICT third-party only** (DORA). Keep that boundary — it is *not* the SoR
   for business Vendors/Procurement generally.
