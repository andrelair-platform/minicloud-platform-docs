---
id: ai-act-gate
title: EU AI Act — Risk-Classification Gate
sidebar_label: AI Act Gate
---

# EU AI Act — Risk-Classification Gate

> **Every AI use case on the ktayl-solution IS is classified by EU AI Act risk tier *before* it is
> built, and the tier dictates the controls.** This is the operational enforcement of "not all AI use
> cases carry the same regulatory weight." It is the insurance-FDE differentiator: a generic AI engineer
> ships a model; here we ship a model **with a proportionate, by-design control set and audit evidence**.

**Where it fits:** a control in the [compliance-by-design method](https://andrelair-platform.github.io/minicloud-platform-docs/insurance-platform/enterprise-architecture-blueprint) (the regulatory tail of the discovery chain), owned by AI Platform (#4) + Regulatory & Compliance (#15). It **reuses infrastructure already deployed** — Langfuse (logging/monitoring), the [Model Governance Matrix](./model-governance-matrix) (the system card), Presidio (data governance/PII). Rule: `bmad-compliance.md` *The regulatory layer*.

## 1. The four risk tiers

| Tier | What it means | ktayl example |
|---|---|---|
| **Prohibited** | banned practices (social scoring, manipulative/subliminal, untargeted scraping…) | none — do not build |
| **High-risk** | Annex III areas + safety components; heavy obligations | *narrow for ktayl — see §3* |
| **Limited-risk** | transparency duties (user knows it's AI; AI-generated content marked) | most ktayl assistive AI |
| **Minimal-risk** | no specific obligation beyond good practice | internal RAG knowledge assistant |

## 2. The classification rubric (run this per AI use case)

```
1. Is it a PROHIBITED practice?                          → STOP. Do not build.
2. Is it in an Annex III HIGH-RISK area (see §3)          → HIGH-RISK: full control set (§4)
   OR a safety component of a regulated product?
3. Does it interact with people / generate content        → LIMITED-RISK: transparency + §4-limited
   (chatbot, synthetic text/media)?
4. Otherwise                                              → MINIMAL-RISK: logging + good practice
```
Plus a **parallel test that often bites harder than the Act for ktayl:** **GDPR Art. 22** — does the AI
produce a **decision with legal or similarly significant effect on a natural person** with **no
meaningful human involvement**? If yes → Art. 22 safeguards (human review, contest, explanation) apply
**regardless** of the AI-Act tier.

## 3. The ktayl scoping nuance — most UW/pricing AI is NOT high-risk (get this right)

The Annex III high-risk insurance item is specifically **"risk assessment and pricing in relation to
natural persons in the case of *life and health* insurance."** **ktayl is commercial-lines / IARD / B2B
grands risques** — it insures **companies (legal entities)**, and **not life/health**. Therefore:

- **Most ktayl underwriting & pricing AI is *not* Annex-III high-risk** → it lands in **limited-risk**.
  Over-classifying every pricing model as high-risk would be **wrong and wasteful**.
- **The real attention vectors are narrow and specific:**
  - anything touching a **natural person** — a **claimant**, a **sole trader / individual insured**,
    **employee-facing HR AI** — where **GDPR Art. 22** (and sometimes high-risk) applies;
  - **fraud / SIU** scoring that materially affects a person's claim;
  - any **autonomous decision** (bind/decline/price) with no human in the loop.
- Precision *is* the deliverable: the gate exists to classify **proportionately**, not to stamp
  "high-risk" on everything.

## 4. Tier → controls (attach these by design)

| Control | Minimal | Limited | High |
|---|---|---|---|
| Logging / traceability (**Langfuse**) | ✅ | ✅ | ✅ (extended) |
| Transparency (user knows it's AI) | — | ✅ | ✅ |
| Human oversight / in-the-loop | — | ✅ (assistive) | ✅ (+ contestability) |
| Data governance + PII (**Presidio**, GDPR) | corpus GDPR | ✅ | ✅ (+ DPIA) |
| Evaluation / accuracy + robustness | good practice | ✅ | ✅ (documented) |
| Technical documentation / **system card** | light | ✅ | ✅ (full) |
| Monitoring + incident process | ✅ | ✅ | ✅ (+ registration/conformity where required) |

## 5. The AI System Card (the per-use-case artifact)

Every AI use case registers a card (formalises the [Model Governance Matrix](./model-governance-matrix) row):

```yaml
ai_system: <name>
business_purpose: <what decision/task it serves>
tier: minimal | limited | high            # from §2 rubric
annex_iii: <area or "n/a — B2B/IARD, no natural-person life/health">
gdpr_art22: <yes/no — decision w/ significant effect on a natural person?>
data_used: <sources; PII? classes>
model_provider: <model + provider>         # provider also → DORA ICT third-party register
human_oversight: <mechanism>
evaluation: <how accuracy/robustness is measured>
logging: langfuse://<project>
monitoring: <drift/accuracy watch + alerts>
incident_owner: <role>
owner: <SA/Compliance>
```

## 6. Reference classification — ktayl's current/planned AI use cases

| Use case | Tier | Why | Key controls |
|---|---|---|---|
| **Knowledge Assistant** (RAG over internal docs, #18) | **minimal** | no decision, internal | logging, corpus GDPR |
| **Submission extraction** (UW playbook §7a) | **limited** | assistive, human-verified; PII present | transparency, human sign-off, Presidio |
| **Guideline check assist** (RAG) | **limited** | assistive, cited | citations, logging |
| **Fraud / SIU signals** (future, Claims) | **limited→high** | affects a person's claim → Art. 22 watch | human review, bias eval, explainability |
| **AI Ops Copilot** *acting on terms* (#19, parked) | **high (if autonomous)** | decision with effect; the capstone to watch | full: oversight + contestability, DPIA, eval, monitoring, incident mgmt — **gated before any autonomous action** |
| **Automated pricing/eligibility *decision*** (natural-person insured) | **high** | Art. 22 + decision effect | full set + human review |

## 7. The gate (how it's enforced)

An AI capability **cannot pass its Path-C security/architecture review** without: (1) a completed **AI
System Card**, (2) a **tier** from the §2 rubric, and (3) the tier's **controls present in the design**.
This is verified at the governance gate (`bmad-compliance.md`), enforced downstream by CODEOWNERS + CI.
**Living control:** the Act's timelines/GPAI rules are still settling — the rubric is pinned to the
stable core (Annex III areas + the decision-effect + Art. 22 tests) and reviewed as guidance firms up.

**Cert mapping:** BC02 (concevoir — the design-time control), BC03 (déployer & sécuriser — the gate + evidence).
