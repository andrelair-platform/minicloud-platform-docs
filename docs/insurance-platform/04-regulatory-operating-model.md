---
id: regulatory-operating-model
title: Regulatory Operating Model (overview)
sidebar_label: Regulatory Operating Model
---

# Regulatory Operating Model (overview)

> How ktayl — a **regulated commercial-lines / IARD insurer** — turns ~17 regulatory frameworks from a
> documentation burden into a **design-time discipline**. This page is the **map**; the detail lives in
> two artifacts.

:::note Insurer ≠ bank · two-layer
Spine = **Solvency II** + transversal EU/FR frameworks (DORA, GDPR, EU AI Act, IDD, AML/sanctions,
IFRS 17, SFDR…). **CRR/CRD/PSD2 don't apply.** This is the **ktayl-solution IS** obligation model; **Retrieva**
is a separate product that only *proves* the DORA third-party slice.
:::

## The core idea — compliance by design, not a silo

Regulation attaches **where work happens**, and **one capability triggers many frameworks at once**. The
FDE discovery chain carries every capability through its regulatory tail:

```
business process → pain → systems + data → AI/automation → value
   → REGULATORY IMPACT → CONTROLS REQUIRED → AUDIT EVIDENCE → MONITORING
```

Controls are declared **at design time** (verified at the security/architecture governance gate), and
evidence accrues to a **control library** owned by Regulatory & Compliance (#15). Standard:
`bmad-compliance.md` *The regulatory layer*.

## The two artifacts

| Artifact | What it is | Where |
|---|---|---|
| **Obligations Register** | the authoritative map — every framework × owner/systems/data/controls/ACPR-EIOPA ref/**applicability caveat**/status | [`ktayl-compliance/docs/obligations-register.md`](https://github.com/andrelair-platform/ktayl-compliance/blob/main/docs/obligations-register.md) (epic RC-05) |
| **AI-Act Gate** | classify every AI use case by risk tier → proportionate controls, at design time | [AI Act Gate](../ai-ml/ai-act-gate) |

## Framework → domain ownership (who owns / consumes what)

- **Solvency II** (spine) → spans **UW → Pricing → Claims → Reserves → Reinsurance → Finance → Reporting** — *not just Finance*.
- **DORA** → Enterprise IT (#3) + **Retrieva** (third-party ICT register).
- **GDPR** → cross-cutting; DPO/Compliance (#15); Presidio is the deployed PII control.
- **EU AI Act** → AI Platform (#4) + Compliance (#15) via the **AI-Act gate**.
- **IDD/DDA** → Distribution & CRM (#13).
- **AML / Sanctions** → Regulatory & Compliance (#15).
- **IFRS 17 / statutory** → Insurance Finance & Billing (#14).
- **Reinsurance / International / Tax** → #22 / #23 / #14.

## The ktayl AI-Act nuance (why this is *sharp*, not box-ticking)

The Act's high-risk insurance item is **life & health pricing for natural persons**. ktayl is **B2B /
IARD** — it insures **companies**, not natural persons, and not life/health — so **most of its UW/pricing
AI is *limited-risk*, not high-risk.** The real high-risk vectors are narrow (claimants, sole traders,
HR AI, autonomous decisions) where **GDPR Art. 22** often bites harder than the Act. Getting that scoping
*right* is the insurance-FDE differentiator. Full rubric: [AI Act Gate](../ai-ml/ai-act-gate).

## How it respects build-order

The register + gate are **governance (cheap, done now)**; actual **controls are implemented per
capability as each domain is built** (business-tools-first). The map fills itself in as domains stand up.
Cert evidence: **BC01 (piloter)** + **BC02/BC03 (concevoir · déployer & sécuriser)**.
