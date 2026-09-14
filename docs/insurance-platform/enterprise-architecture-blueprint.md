---
title: Enterprise Architecture Blueprint — the ktayl IARD Insurer IS
sidebar_label: 🏛 EA Blueprint (Insurer IS)
---

# Enterprise Architecture Blueprint — the ktayl IARD Insurer IS

> **This is the authoritative functional target for the ktayl-solution IS.** It models ktayl as a
> real commercial-lines / large-risk **IARD** insurer (reference: HDI Global SE France), so every
> product board, repo and roadmap item hangs off a named domain here. The detailed inventory lives in
> the [Business Applications Catalog](./business-applications-catalog); the AI vision in the
> [AI-First Operating Model](./ai-first-operating-model). **This page is the map.**

:::note Two-layer model — do not conflate
**ktayl-solution IS** = the insurer's own information system (this blueprint). **Retrieva** is a
*separate product* (RNCP cert / DORA third-party-risk) that merely *runs on* ktayl infrastructure — it
is **not** a ktayl org system and appears nowhere in this blueprint.
:::

## 1. Why a full functional architecture

An IARD/large-risk insurer does not run on a policy system alone. Its IS is **12 business domains**
plus **4 transversal layers**. Mapping them explicitly is what turns "we have some apps" into "the
business can actually run" — and it is where AI automation use-cases are found (per-domain pain points,
not "where can we put a chatbot").

## 2. Functional architecture (target)

```
                        ASSUREUR IARD / GRANDS RISQUES (ktayl)

                          ┌────────────────────┐
                          │ DISTRIBUTION / CRM  │   Broker portal · pipeline · DUA/binders
                          │ Portals / API       │   commissions
                          └──────────┬──────────┘
                                     │
                        ┌────────────▼────────────┐
                        │ UNDERWRITING / PRICING  │   Risk assessment · appetite · rating/quote
                        │ Underwriting Workbench  │   referral / approval · portfolio compare
                        └────────────┬────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │ POLICY ADMINISTRATION   │   Contracts · endorsements · renewals
                        │ (PAS)                   │
                        └────────────┬────────────┘
                                     │
             ┌───────────────────────┼───────────────────────┐
             ▼                       ▼                       ▼
         CLAIMS              BILLING / FINANCE        RISK ENGINEERING
      FNOL · triage         Premium · échéancier       Prevention · site audits
      reserves · recours    encaissement · commissions inspections · recommendations
             │                       │
             └──────────┬────────────┘
                        ▼
                   REINSURANCE
             Facultative / Treaty · cessions
             recoveries · bordereaux

  ────────────────────────────────────────────────────────────────────
        INTERNATIONAL PROGRAM MANAGEMENT
     Master policy · local policies · network partners · cross-border premium/claims flows

  ────────────────────────────────────────────────────────────────────
   DATA / ACTUARIAL        COMPLIANCE / LEGAL       ENTERPRISE IT
   Reporting · Solvency II  AML/KYC · sanctions      IAM/SSO · ITSM/CMDB
   reserving · exposure     DORA · contract analysis M365-alt · cloud/k8s
   accumulation · cat model                          observability · security · DevOps

  ══════════════ TRANSVERSAL LAYERS (serve every domain) ══════════════
   DOCUMENTS (GED/OCR/IDP) · INTEGRATION (API GW/ESB/events/ETL/MFT/EDI)
   MASTER DATA / RÉFÉRENTIELS (MDM) · AI / AUTOMATION
```

## 3. Gap analysis — target vs current (as of 2026-09)

Status: 🟢 live · 🟡 has a home (repo/board) but not built/deployed · 🔴 no home yet.

### The 12 domains
| # | Domain | ktayl home (board) | Status |
|---|---|---|---|
| 1 | Distribution / CRM / Broker portal | #13 ktayl-distribution | 🟡 repo only |
| 2 | Underwriting workbench | #12 ktayl-underwriting | 🟡 repo only |
| 3 | Pricing / Rating engine | within #12 | 🟡 not explicit |
| 4 | **Policy Administration (PAS)** | #6 ktayl-policy-service | 🟢 **live** |
| 5 | Claims | #11 ktayl-claims | 🟡 repo only |
| 6 | Risk Engineering / Prevention | — | 🔴 no home |
| 7 | International Programs | — | 🔴 no home |
| 8 | Billing / Premium & Finance | #14 ktayl-finance | 🟡 repo only |
| 9 | Reinsurance (own domain) | folded in #14 | 🔴 no own home |
| 10 | Compliance / Legal | #15 Regulatory & Compliance | 🟡 repo only (Legal thin) |
| 11 | Data / Actuarial | #5 Data Platform | 🟡 minimal (no reserving/exposure/cat) |
| 12 | Enterprise IT | #3/#4/#10/#16/#17 | 🟢 strongest (several live) |

### The 4 transversal layers
| Layer | ktayl state | Status |
|---|---|---|
| Documents (GED / OCR / IDP) | Nextcloud = storage only; Paperless planned | 🔴 no IDP capability |
| Integration (API GW / ESB / events / ETL / MFT / EDI) | NATS + Temporal + n8n exist as platform bits; no insurance integration fabric | 🔴 biggest gap |
| Master Data / Référentiels (MDM) | #20 ktayl-mdm | 🟡 thin slice in progress |
| Data | #5 Data Platform | 🟡 partial (OLAP: ClickHouse/dbt/BI) |

:::info MDM (#20) vs Data Platform (#5) — different things, not a duplicate
**MDM = operational OLTP** golden records + low-latency lookup (PostgreSQL), consumed by the copilot
and domain services *at transaction time* ("which client/broker/entity is this?"). **Data Platform =
analytical OLAP** (Redpanda → ClickHouse → dbt → BI). **MDM *feeds* the Data Platform** via CDC
(Debezium, `DATA-18i`) — it is a *source* for analytics, not the analytics platform. Keep them separate.
:::
| AI / Automation | #4 AI Platform + #18 Knowledge Assistant + #19 AI Ops Copilot | 🟢 being built |

**Summary:** PAS + Enterprise IT are the mature core. Most insurance domains have a *home* but are not
*built*. **No home at all:** Risk Engineering, International Programs, standalone Reinsurance, MDM,
Integration Layer, Documents/IDP.

## 4. AI / Automation is a transversal *capability*, not a domain

AI does not sit "next to" Claims or Underwriting — it serves every domain:

```
Underwriting     ──► submission analysis · risk summary · referral scoring
Claims           ──► triage · document extraction · fraud signals
Risk Engineering ──► report analysis · recommendation extraction
Broker/Distrib.  ──► email / submission-pack classification
Compliance       ──► screening · document analysis
Finance          ──► invoice / reconciliation automation
Legal            ──► contract analysis
Knowledge        ──► enterprise RAG / search / assistant
Enterprise IT    ──► support / incident automation
```

The two AI products realise this split cleanly (the "if Open WebUI already does it, don't rebuild it" test):

- **ktayl Knowledge Assistant** (#18) — *chat-over-docs* (grounded, cited Q&A over ktayl corpora).
  This is **Open WebUI + curated content, config not code**.
- **ktayl AI Ops Copilot** (#19) — everything Open WebUI **cannot** do: **structured decisions,
  authorized actions into ktayl systems, multi-agent workflows.** *Makes and executes* validated,
  audited insurance decisions.

**Use-case discovery method** (not "where can we put a chatbot?"):

```
business process → pain point → data/documents → existing systems
    → decision/task → automation opportunity → AI capability → measurable outcome
```

## 5. Build order — business tools first; AI/automation last

:::warning Corrected sequencing (2026-09-14)
Build the **business tools (domains) first**; the **AI/automation layer comes last**. An earlier plan
front-loaded the plumbing (*"MDM → Documents → Data → UW → Copilot thin slice"*) — that is **reversed**.
The **AI Ops Copilot (#19)** is an automation *layer*: it only delivers value once real business
systems exist to reason over and act on. **MDM (#20)** is a foundation, but only pays off once a
consumer exists. So **#18 (Knowledge Assistant), #19 (AI Ops Copilot) and #20 (MDM) are PARKED** —
their briefs are captured as plans, not the next thing to build.
:::

**The correct order:**

```
1. Build a real BUSINESS DOMAIN end-to-end   (the thing that actually runs)
2. MDM emerges as that first domain needs shared entities (client/broker/…)
3. Documents/IDP + exposure-Data added as a domain needs them
4. The AI Ops Copilot LAST — the capstone, once there are real systems to automate
```

**Why:** the copilot automates *over* systems — no systems, nothing to automate. MDM with no consumer
is infrastructure with no payoff. So value comes from standing up domains, not from building the
automation layer against stubs.

**Next decision:** pick the first business domain to stand up. Policy Admin (#6) is already live;
strong candidates are **GLPI/ITSM (#16)** (direction already locked, self-contained quick win) or
**Underwriting (#12)** (highest insurance value). Each missing domain gets its board/repo **when its
work starts** (portfolio discipline — no empty boards); breadth-first (12 half-built domains) is
rejected too. The parked copilot/MDM/KA briefs remain valid plans for when the systems exist.

## 6. Governance

- Each domain/layer = a **product board** (one Project per product; see the GitHub Projects rules).
  New boards are created **when work starts**, not pre-emptively.
- This blueprint is **BC01 (piloter) governance evidence** for the ktayl IS. It is reviewed at
  architecture gates and kept current as domains move 🔴→🟡→🟢.
- Detailed per-app inventory + sprint state: [Business Applications Catalog](./business-applications-catalog).
