---
id: is-build-roadmap
title: ktayl IS — Build Roadmap (start here)
sidebar_label: 🧭 IS Build Roadmap (start here)
sidebar_position: 0
---

# ktayl IS — Build Roadmap (the single place)

> **If you're ever unsure what to build next, read this.** Everything on the ktayl-solution IS sits in
> **one of three parallel tracks** (plus the live foundations). This page is the map of the tracks, their
> order, and — crucially — **how they interlock**, so nothing feels scattered.

```
 FOUNDATIONS (live) ──────────────────────────────────────────────────────────
   platform #3 · AI platform #4 · digital workplace #10 · Policy Admin #6 · ERPNext #8

 TRACK A — BUSINESS BUILD (the insurance value chain — sequenced)
   Distribution #13 → UNDERWRITING #12 → Policy Admin #6 → Claims #11 → Billing #14 → Reinsurance #22
                                     (live)
        every domain is built the same way, and passes ↓

 TRACK B — GOVERNANCE & COMPLIANCE (continuous — the gate every Track-A build clears)
   regulatory layer · AI-Act gate · obligations register   (framework built ✅, applied per domain)

 TRACK C — MODERNIZATION PRACTICE LAB (parallel skills cadence, feeds real integration skill into Track A)
   GlobalCore ✅ · GenApp modernization M1–M4
```

**All three are valuable and all three stay on the roadmap.** Track A delivers the business; Track B keeps
it compliant *by design*; Track C builds the legacy/integration muscle real insurers need. They are not
competing — they interlock (see *How they interlock*).

---

## Track A — Business build (the value chain)

Build **outward from what's already live** (Policy Admin #6). Sequenced by value + dependency:

| Phase | Build | Why here |
|---|---|---|
| **1** | **Underwriting & Pricing #12** ← *recommended start* | highest value; FDE playbook ready; feeds the live Policy Admin |
| **1** | Distribution / broker portal #13 | where submissions come *in* (feeds #12) |
| **1** | Claims #11 | the other half of the policy lifecycle |
| **1** | Billing #14 | premium in |
| **2** | Reinsurance #22 · Risk Engineering #21 · International #23 · Compliance #15 | specialty + control |
| **3** | Data/Actuarial #5; Documents #24 / Integration #25 / MDM #20 **as a domain needs them** | insight + layers-on-demand |
| **4** | AI/automation capstone: Knowledge Assistant #18 · AI Ops Copilot #19 | **LAST** — automates *over* real systems |

**Opportunistic quick win** (Enterprise-IT, not the value chain): GLPI/ITSM #16 — do when convenient.

## Track B — Governance & compliance (continuous, not a phase)

The framework is **built** — it now **applies to every Track-A domain** as a gate, not a separate project:
- **Regulatory layer** (compliance-by-design) — each capability declares its triggered frameworks + controls.
- **AI-Act gate** — every AI use case gets a risk tier → proportionate controls.
- **Obligations register** (RC-05) — the single map of what applies.

→ docs: *Regulatory Operating Model*, *AI-Act Gate*; register in `ktayl-compliance`.

## Track C — Modernization practice lab (parallel cadence)

A **skills track** that builds the wrap / strangler / legacy-comprehension muscle — then feeds it back
into Track A whenever a domain integrates with something legacy:
- **GlobalCore** — a deliberately-legacy Java/SOAP core, **built ✅** (`globalcore-legacy`).
- **GenApp modernization (M1–M4)** — recover the real IBM COBOL app's rules → reimplement on the cluster
  (`cics-genapp/docs/business-rules-catalog.md`).

→ full plan: `ktayl-integration/docs/legacy-wrapper-initiative-spec.md`.

---

## How they interlock (one repeatable recipe per domain)

Building **any** Track-A domain is the *same loop* — and that loop is where B and C plug in:

```
1. FDE playbook        (understand the domain: process, users, pain, data, KPIs)
2. BMAD spec + stories (the implementation contract)
3. Build a thin end-to-end slice   ──uses Track-C patterns when it touches legacy/integration
4. Pass the governance gate        ──Track-B: regulatory impact + AI-Act tier + controls by design
5. Deploy (GAP wrapper chart) + iterate
```

So Underwriting #12 = its FDE playbook (done) → spec → thin slice (submission→quote→bind→PAS) → clears the
governance gate (any AI in it gets an AI-Act tier) → deploy → next slice. Every domain repeats it.

## The one open decision
**Where to start Track A.** Recommended: **Underwriting #12** (value + playbook ready + feeds the live
PAS). Once chosen, the recipe above repeats per domain and the roadmap stops feeling ad-hoc.

## Where the detail lives
- **Domain map (what exists):** [EA Blueprint](../insurance-platform/enterprise-architecture-blueprint)
- **Per-domain deep-dive:** FDE playbooks (e.g. [Underwriting](../insurance-platform/underwriting-fde-playbook))
- **Governance:** [Regulatory Operating Model](../insurance-platform/regulatory-operating-model) · [AI-Act Gate](../ai-ml/ai-act-gate)
- **Practice lab:** `ktayl-integration/docs/legacy-wrapper-initiative-spec.md`
- **Detailed backlog / quarter view:** [Product Roadmap (detail)](./overview)
