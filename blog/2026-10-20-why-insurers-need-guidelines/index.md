---
slug: why-insurers-need-guidelines
title: "Why an Insurer Needs Guidelines — and How I Built the Whole Framework as Code"
authors: [andrelair]
tags: [governance, compliance, insurance, solvency-ii, dora, policy-as-code, platform-engineering]
date: 2026-10-20
description: "An insurance company doesn't run by hiring people and letting each department decide how to work. It runs on a framework of policies, standards, guidelines, procedures and controls. I built that framework for my simulated insurer — 15 governance books, 80 pages, wired to the business apps — and learned that the hard part isn't writing the rules. It's keeping the human rule, the executable rule and the engineering decision as one thing."
---

A real insurer like **HDI Global SE** does not operate by hiring employees and letting each department improvise. It runs on a structured framework — **policies, standards, guidelines, procedures and controls** — that defines how decisions are made, who is authorized to make them, what controls apply, and what evidence is kept. For an insurer this isn't bureaucracy: the company carries financial responsibility for risks worth millions or billions of euros.

Picture five situations:

- An underwriter accepts a €200 million industrial risk without proper assessment.
- A claims handler approves a €2 million claim without checking coverage or getting the required approval.
- A salesperson promises cover the company legally cannot provide.
- An IT administrator grants access to confidential claims data without authorization.
- A manager signs a contract with a supplier under financial sanctions.

Each one is a potential financial loss, legal problem, regulatory breach or reputational hit. Guidelines exist precisely to stop these — by defining *how* decisions must be made, *who* may make them, *what* controls are required, and *what* evidence must survive.

I rebuilt this framework end-to-end for **ktayl-solution**, a simulated insurer I run as an engineering laboratory. Here's what I learned.

{/* truncate */}

## The governance hierarchy (five levels, not one pile of PDFs)

The single most useful idea is that a regulation, a policy, a guideline and a procedure are **not the same thing** — they answer different questions:

| Level | Example | Answers |
|---|---|---|
| **1 — External requirement** | Solvency II · DORA · GDPR · IDD | What must we comply with? |
| **2 — Corporate policy** | Information Security Policy · Risk Management Policy | What principles are non-negotiable? |
| **3 — Business guideline** | Access Management · Underwriting Appetite | How do we operate day-to-day? |
| **4 — Procedure (SOP)** | Onboarding SOP · deployment runbook | What exact steps? |
| **5 — Assurance** | Approvals · audit trails · KPIs · exceptions | How do we *prove* it happened? |

They overlap in conversation, but they serve different management purposes — and a mature insurer manages not just its business processes, but the **rules governing those processes.**

This isn't theoretical. HDI Global SE's public [2025 Solvency and Financial Condition Report](https://www.hdi.global/globalassets/_local/international/downloads/solvency-and-financial-condition-reports-fatca/sfcr-hg_ye_2025_en.pdf) describes a Group-wide Code of Conduct, supported by more detailed compliance guidelines, across subjects like anti-bribery, antitrust, sales compliance, **financial sanctions and embargoes**, anti-money-laundering and supervisory law — reviewed regularly, with managers required to adapt affected working instructions. It runs a **Three Lines of Defence** model: operations own the risk, Risk/Compliance oversee and challenge, Internal Audit independently assures.

## The 12 domains I actually built

I organized ktayl-solution's governance into **12 domains**, each a "Cadre de gouvernance" book with the same `01 Politique → 02 Standard → 03 Directive → 04 Procédure → 05 Runbook` hierarchy:

> Corporate Governance & Strategy · Legal/Compliance/Ethics · Enterprise Risk Management · Underwriting & Policy Administration · Claims & Fraud · Reinsurance & International Programmes · Finance/Investments/Actuarial · HR & Employee Conduct · IT/Cyber/Digital Resilience · Data Governance/Privacy/AI · Procurement/Third-Parties/Outsourcing · Sustainability/Communications/Business Continuity.

Concretely that landed as **15 governance books / 80 pages** in a wiki (BookStack), behind SSO, grounded in Solvency II Pillar 2, IDD POG, DORA, GDPR, IFRS 17 and the LCB-FT/sanctions regime. Each page carries its owner, review cadence and regulatory references — because a guideline without an owner and a review date is already rotting.

*(To be clear, as the framework reference itself is: this catalogue combines publicly confirmed HDI governance topics with a recommended comprehensive framework. It is not a claim that HDI uses every exact title or workflow.)*

## The hard part wasn't writing rules. It was three homes for one rule.

The lesson that actually mattered: a single guideline lives in **three places at once**, and they must stay one thing.

1. **The human guideline** — the policy/standard/guideline a person reads (the wiki).
2. **The executable rule** — the same rule enforced by the business application (appetite, authority limits, pricing floor).
3. **The engineering decision** — the architecture/ADR that says how it's built.

If those three drift, governance becomes theatre. So I made the link explicit. The Underwriting guideline's **delegation-of-authority matrix** and **technical-pricing floor** aren't just prose — they're *executed* by the underwriting workbench: a quote under the technical floor is blocked and referred; a bind above an authority tier requires four-eyes. The access policy is *executed* by the IAM system (least-privilege, dual approval, joiner-mover-leaver). Each of those wiki pages carries a **"policy-as-code" complement** that names exactly which rules the app enforces — and says plainly that the wiki remains the source of truth.

That's the difference between *"we have a policy"* and *"the policy cannot be violated."* The data model I aim for threads the whole chain:

```
Regulation → Obligation → Policy → Guideline → Process → Control → Application → Evidence → Audit
```
For example: `DORA → ICT change control → IT change policy → deployment guideline → release mgmt → deployment approval → the CI/CD pipeline → the audit log.`

## Guidelines that bind everyone, assigned by role

Some rules are universal — Code of Conduct, confidentiality, acceptable IT use, data protection, anti-bribery, whistleblowing. But **not every employee should get every guideline with equal weight.** A claims handler needs settlement authority rules; an IT admin needs change-management and privileged-access rules; both need confidentiality and security awareness. So guidelines are **assigned by role** — in my build, your identity's groups decide which governance spaces you see and can edit, the same identity that gates every app. Governance and access are the same control surface.

A small but telling example from building it: the HR governance already *required* employees to sign a "charte informatique" (IT acceptable-use policy) at hiring — but the charte itself had never been written. It was a **mandated-but-missing artifact**: a rule that points at a document that doesn't exist. A guideline isn't "in place" until the thing it requires actually exists. I swept the whole library for that failure mode and closed the gaps.

## Three Lines of Defence, and who owns what

Publishing PDFs isn't governance. The operating model is what makes it real:

- **1st line — operations** (Underwriting, Claims, Finance, IT): own the risk, run the controls, keep the evidence.
- **2nd line — oversight** (Risk, Compliance, Actuarial): set the frameworks, monitor, challenge.
- **3rd line — Internal Audit**: independent assurance.

Every guideline gets an **owner, an approver, applicable roles, regulatory references, a version, a review date, related procedures, associated controls, evidence and an exceptions path** — a governance register, not a folder of files. The review cadence respects the law: Solvency II Article 41, for instance, requires certain written governance policies to be reviewed at least annually.

## Where AI fits — and where it must not

The tempting move is to put an AI model behind a `calculatePremium()` endpoint or let a chatbot answer "am I allowed to do this?" authoritatively. I deliberately didn't. AI's honest role here is to **help a human find and apply the right rule**, never to *be* the rule:

- An underwriter could ask *"Can I insure a chemical plant in Brazil, and what approvals do I need?"* and get the applicable appetite, territorial and sanctions rules plus the authority matrix — **retrieved from the current approved guidelines, source-linked** — but the AI does not authorize the contract or invent an authority limit.
- The pricing model is trained offline and **compiled into an approved, versioned tariff**; the price is always reconstructable without the model. (I wrote that up separately — *["OIDC is not a directory"](./oidc-is-not-a-directory)* and the pricing-evolution ADR.)

That boundary — automate the repeatable control, preserve human accountability for the judgement — is itself the senior design decision.

## The point

Enterprise guidelines serve two needs that an insurer can't fully separate: **employee governance** (how people behave, what they may approve, when they escalate) and **business governance** (how the company accepts risk, prices, pays claims, uses third parties, stays compliant). An underwriting-authority rule is *both* — a business risk control *and* a limit on an individual's decision-making.

The objective is an organization where decisions are **consistent, authorized, traceable, compliant and proportionate to the risk** — without asking every employee to interpret hundreds of documents on their own. Building it for a simulated insurer taught me that the framework is the easy 20%; keeping the human rule, the executable rule and the engineering decision as one living thing is the 80% that actually protects the company.

*ktayl-solution is a fictional insurer used as an engineering laboratory — synthetic data, simulated users, no real customers. The governance framework, and its wiring into the running systems, are real.*
