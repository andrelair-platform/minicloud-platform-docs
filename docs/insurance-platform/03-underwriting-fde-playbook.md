---
id: underwriting-fde-playbook
title: Underwriting — FDE Playbook (overview)
sidebar_label: Underwriting FDE Playbook
---

# Underwriting & Pricing — FDE Playbook (overview)

> A Forward-Deployed-Engineer field guide to ktayl's **underwriting & pricing** domain — how the
> business works, where the pain is, and where software + AI deliver measurable value. This page is the
> **map**; the **full detail lives with the code** in the product repo.

**📖 Full playbook →** [`ktayl-underwriting/docs/fde-underwriting-playbook.md`](https://github.com/andrelair-platform/ktayl-underwriting/blob/main/docs/fde-underwriting-playbook.md)

**Domain:** Underwriting workbench (#2) + Pricing (#3) in the [EA Blueprint](./enterprise-architecture-blueprint) · **Board:** [#12](https://github.com/orgs/andrelair-platform/projects/12) · **Initiative:** Insurance LOB

:::note Two-layer model
This is the **ktayl-solution insurance IS** (business context) — **not** the certification. The RNCP
deliverable is **Retrieva**, a separate product. Underwriting appears nowhere in Retrieva.
:::

## What the playbook covers

ktayl is a **commercial-lines / large-risk IARD** insurer, so
underwriting means **technical underwriting of complex business risks** — judgement-heavy,
document-heavy, referral-heavy. The full playbook walks the domain end-to-end:

- **Actors** — broker, UW assistant, underwriter, technical/senior UW, manager, actuary, cat modeller,
  committee, compliance (primary user = the **underwriter**).
- **Process** — submission → triage → appetite/eligibility → risk assessment → pricing → aggregate/cat
  check → quote → referral/committee → negotiation → **bind → handoff to Policy Admin** (+ renewal and
  endorsement variants).
- **Data objects** — submission, risk/insured, exposure, guideline, rate table, quote, referral,
  decision, aggregate, authority matrix.
- **As-is vs target systems** — the pain (unstructured submissions, no single file, Excel rating) mapped
  to the epic backlog **UW-01 … UW-05**.
- **Pain points → manual tasks** — ranked by leverage.
- **AI / automation opportunities** — traced through the FDE chain, split into **build-now** (thin AI
  *inside* the workbench: submission extraction, guideline check, renewal pre-fill, referral routing)
  vs the **parked AI Ops Copilot capstone**; grounded doc-Q&A flagged as **Open WebUI, not code**.
- **KPIs** — quote turnaround, hit ratio, referral/straight-through rate, rate adequacy, aggregate
  utilisation — the "measurable outcome" every automation must move.
- **A recommended thin slice** — one LOB, one broker path, that actually binds.

## How it connects

- **Build order** — *business tools first, AI/automation last.* The workbench/guidelines/pricing come
  before the AI Ops Copilot (parked capstone). See the [EA Blueprint build order](./enterprise-architecture-blueprint).
- **Bind target** — [`ktayl-policy-service`](./ktayl-policy-service) (Policy Admin), already live.
- **MDM** — client/broker/insured are shared master data; MDM (#20) is parked and *emerges* as this
  domain needs shared entities — UW-01 is **not** blocked on it.
