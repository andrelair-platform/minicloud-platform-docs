---
id: ai-first-operating-model
title: AI-First Insurance Operating Model
sidebar_label: AI-First Operating Model (Vision)
---

# AI-First Insurance Operating Model — the ktayl-solution vision

> **Thesis.** Run the operational insurer on a *governed AI platform*. Humans supervise,
> decide, negotiate and **own accountability**. Volume scales with **compute, not headcount**.

This is the operating-model vision for the **ktayl-solution IS** — the simulated specialty/commercial
insurer this platform implements. It is not "an insurer that uses AI." It is a **machine-first,
human-governed** operating model: the AI platform runs the operational company; a fixed core of
experts governs it and handles exceptions.

:::note Two-layer reminder
**ktayl-solution IS** = the insurance organisation (this vision, this platform). **Retrieva** = a
separate RNCP39583 certification project that *runs on* this IS and serves as its **governance
exhibit** (DORA third-party/ICT risk). Don't conflate them.
:::

## The distinction that carries the whole model

Two words, and dropping either one breaks it:

- **Machine-first (autonomy):** the AI executes everything it is *authorised* to execute — intake,
  triage, document extraction, risk research, pricing support, claims preparation, settlement prep.
- **Human-governed (accountability):** humans retain accountability for decisions where **judgment,
  regulation, empathy or commercial responsibility** matter — and every AI action is auditable.

Full autonomy is a regulatory non-starter in EU insurance; copilots-only is just Gen 2. The model
is the *combination*: **AI autonomy + human accountability.**

## The maturity ladder (and where we are)

| Gen | Model | Human role | Status |
|---|---|---|---|
| 1 | Digital (CRM + Excel + core system) | does everything | legacy |
| 2 | AI Copilot | assisted by an assistant | commodity |
| 3 | Agentic workflows | **manages AI work** end-to-end | **← ktayl-solution is here** |
| 4 | AI-first carrier | **governs + handles exceptions** | **← target** |

Industry direction (2026): McKinsey ("machine-first, human-governed" commercial underwriting),
BCG (underwriter focuses on the 10–15 unusual cases, AI handles the routine population), AIG
(agent orchestration layer with explicit activation/oversight controls), Allianz × Anthropic
(agentic claims with human-in-the-loop for sensitive cases), ISG (P&C moving to decision-centric
operating models), Dei Primus/LUCY (autonomous-carrier startups). The market is moving toward Gen 4.

## The exception-driven engine

Traditional company: **humans process everything → escalate exceptions.**
AI-first company: **AI processes everything → humans handle exceptions.**

The whole economic model reduces to one measurable variable — **Straight-Through-Processing rate (STP%)**:

```
human workload  =  (1 − STP%) × volume        ← the exception queue
marginal cost per policy/claim  →  ~0  as STP% → high
```

You no longer staff for **volume**; you staff for the **exception rate**. That is why the workforce
can stay fixed while the book grows: `More business → more AI capacity → same core workforce.`

## Reference architecture — the ktayl AI Operating System (ktayl-AIOS)

The vision's "Insurance AI OS" is **already running** as this platform. Every layer below maps to a
live component — this is a reference implementation, not a diagram.

```
                     ktayl AI OPERATING SYSTEM (ktayl-AIOS)
                                    │
        ┌───────────────┬──────────┼───────────┬────────────────┐
   AI Gateway      AI Workforce  Orchestration  Enterprise      Governance
   (LiteLLM)       (agents)      (n8n/Temporal) Context         & Trust
        │               │        /NATS          (ERPNext/RAG)   (Retrieva/OPA)
        └───────────────┴──────────┼───────────┴────────────────┘
                                    │
                          WORKFLOW ORCHESTRATION
                                    │
                        HUMAN GOVERNANCE / APPROVAL
                     (approve · modify · reject · escalate)
```

| Layer | Function | Running today |
|---|---|---|
| **AI Gateway** | Multi-model, EU-resident, cost-governed access | **LiteLLM** — per-team keys, spend metrics, residency routing |
| **AI Workforce** | Agents per operational domain | **minicloud-agent** (LangGraph), **minicloud-crew-agent** (CrewAI), **Retrieva** (RAG) |
| **Orchestration** | End-to-end workflows + events | **n8n**, **Temporal**, **NATS** |
| **Enterprise context** | The company's real data + systems | **ERPNext** (HR/finance), **Nextcloud/Plane**, **Qdrant** vector store |
| **Governance & trust** | Regulatory + policy control | **Retrieva** (DORA), **Gatekeeper/OPA**, **Vault**, NetworkPolicies |
| **Observability** | Every AI action logged + auditable | **Langfuse** (LLMOps traces), Prometheus/Grafana/Tempo/Loki |
| **Evaluation** | Quality, hallucination, drift | RAG eval harness, phi3 eval, red-team suite |
| **Human-in-the-loop** | Approve / escalate / override | Task-inbox UX (AI-native design principle) |
| **Identity & security** | Who/what may act on what | Authentik OIDC, PKI, per-namespace isolation |

## Example — a broker submission, machine-first

```
Broker email → AI Intake → Document AI → Risk Extraction → External Intelligence
   → Risk Assessment → Appetite Agent → Pricing Agent → Compliance Agent
   → Quote draft →  HUMAN UNDERWRITER  → approve / modify / reject → Broker
```

The underwriter spends ~15 minutes on what previously took 1–2 hours — and becomes a **manager of
AI work**, not a processor of it. Claims follows the same shape (FNOL → extraction → coverage check
→ fraud signal → severity estimate → settlement recommendation → human decision), with humans
engaged only on high-value, ambiguous-coverage, litigation, fraud, vulnerable-customer or
reputational cases.

## The governance spine — the moat

Anyone can wire agents. In **regulated EU insurance** (DORA, EU AI Act, GDPR, Solvency II, IDD;
DE: BaFin VAIT) "AI autonomy + human accountability" is only adoptable if it is **auditable and
compliant by construction**. This platform already has the hard part:

- **Retrieva → DORA** third-party/ICT + concentration risk (the governance exhibit).
- **Langfuse →** immutable audit trail of every AI decision (EU AI Act Art. 12 logging).
- **Gatekeeper + Vault + NetworkPolicies →** *what an agent may access / when a human must approve*,
  enforced at the platform, not in a prompt.

This is the difference from autonomous-carrier startups: they build **autonomy**; ktayl-AIOS builds
**governed autonomy** — the only kind a BaFin-regulated specialty insurer can actually run.

## The economic thesis (measurable, board-ready)

| Lever | Metric | AI-first target |
|---|---|---|
| Efficiency | Cost per policy / per claim | ↓↓ |
| Speed | Quote turnaround, claims cycle time | hours → minutes |
| Automation | **STP%**, exception rate | ↑ / ↓ |
| Quality | Claims leakage, loss-adjustment expense (LAE) | ↓ |
| Scale | Policies per FTE, GWP per FTE | ↑↑ (the fixed-workforce proof) |
| Risk | Model drift, hallucination rate, override rate | bounded |

The substrate for these is already emitted (Langfuse cost/latency, Prometheus) — the vision's KPIs
are instrumented, not hypothetical.

## Honest risks (what breaks it)

- **Regulatory acceptance** of AI-influenced underwriting/claims decisions (EU AI Act high-risk
  classification for insurance pricing/claims) — the gating constraint, not the tech.
- **Concentration of expertise / skill atrophy** (PwC) — if AI handles all routine cases, how do
  juniors become the experts who own exceptions? Needs a deliberate development path.
- **Model risk & liability** — accountability on a mis-priced risk sits with the human sign-off +
  the audit trail; this must be explicit, never implied.
- **Demo → carrier gap** — a real insurer runs Guidewire/SAP/legacy; the Strangler-Fig + ACL
  approach is the bridge, and it is the hard, unglamorous 80%.

## Why this matters beyond a demo

The end state: **one expert + an AI workforce manages the workload that previously required an
entire operational team.** For a specialty insurer like HDI Global — document-heavy, broker-driven,
expert-judgment-intensive — AI doesn't replace the expert; it removes the operational work
*surrounding* the expert. That is a far stronger claim than "we use AI," and it is the strategic
frame for both the platform and the **IA Integration Lab** thesis: *we design the AI operating
architecture that lets an insurer become AI-first.*
