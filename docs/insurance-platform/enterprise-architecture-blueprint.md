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

## 3. Gap analysis — target vs **deployed reality** (verified on-cluster, 2026-09-14)

This is the honest status from **what's actually running** (every Deployment/StatefulSet across all
namespaces), not just what has a repo/board. Status: 🟢 deployed & serving · 🟡 partial (platform up or
repo exists, business capability not built/configured) · 🔴 nothing running.

### The 12 domains
| # | Domain | Board | **Deployed reality** | Status |
|---|---|---|---|---|
| 1 | Distribution / CRM / Broker portal | #13 | ERPNext platform up (`erp/`) but **CRM not configured**; no broker portal | 🟡 platform only |
| 2 | Underwriting workbench | #12 | nothing running (repo scaffold) | 🔴 |
| 3 | Pricing / Rating engine | #12 | nothing running | 🔴 |
| 4 | **Policy Administration (PAS)** | #6 | **`ktayl-policy-service` + `ktayl-postgres`** (ktayl + ktayl-prod) | 🟢 **live** |
| 5 | Claims | #11 | nothing running (repo scaffold) | 🔴 |
| 6 | Risk Engineering / Prevention | — | nothing | 🔴 |
| 7 | International Programs | — | nothing | 🔴 |
| 8 | Billing / Premium & Finance | #14 | ERPNext finance up, **insurance billing not configured** | 🟡 platform only |
| 9 | Reinsurance | — | nothing | 🔴 |
| 10 | Compliance / Legal | #15 | nothing (Presidio PII is a data tool, not a compliance system) | 🔴 |
| 11 | Data / Actuarial | #5 | analytics stack (ClickHouse/dbt/Superset) **not deployed**; only MLflow up | 🔴 |
| 12 | Enterprise IT | #3/#4/#10/#16/#17 | **very strong — see note below** (except ITSM/GLPI + CMDB) | 🟢 |

**Enterprise IT (#12) deployed detail:** 🟢 IAM (Authentik) · M365-alt suite (Nextcloud, OnlyOffice,
Stalwart mail, Matrix/Element, Jitsi, Docuseal, n8n) · cloud/k8s (ArgoCD, Kargo, cert-manager +
trust-manager, ESO, Vault, Harbor, Cilium, Longhorn, KEDA, VPA, Velero) · observability
(Prometheus/Grafana/Loki/Tempo) · security (Falco, Gatekeeper, Polaris, Trivy) · DevPortal (Backstage) ·
project-mgmt (Plane CE). 🔴 **Not deployed: ITSM/GLPI (#16) + CMDB** (Plane covers project-mgmt, not helpdesk).

### The 4 transversal layers
| Layer | Board | **Deployed reality** | Status |
|---|---|---|---|
| Documents (GED / OCR / IDP) | — | Nextcloud (storage) + OnlyOffice (edit) + **Docuseal** (e-sign) + **Docling + markitdown-proxy** (OCR/conversion) all **live**; missing a records-mgmt DMS + a structured IDP pipeline | 🟡 partial |
| Integration (API-GW / ESB / ETL / MFT / EDI) | — | **NATS** (events) + **Temporal** (workflow) + **n8n** (low-code integration) **live** as primitives; missing the formal API-GW/ESB/ETL/MFT/EDI insurance fabric | 🟡 primitives only |
| Master Data / Référentiels (MDM) | #20 | nothing running (repo scaffold, **parked** — see §5) | 🔴 |
| Data | #5 | only MLflow; analytical Data Platform not deployed | 🔴 |

:::info MDM (#20) vs Data Platform (#5) — different things, not a duplicate
**MDM = operational OLTP** golden records + low-latency lookup (PostgreSQL), consumed by the copilot
and domain services *at transaction time* ("which client/broker/entity is this?"). **Data Platform =
analytical OLAP** (Redpanda → ClickHouse → dbt → BI). **MDM *feeds* the Data Platform** via CDC
(Debezium, `DATA-18i`) — it is a *source* for analytics, not the analytics platform. Keep them separate.
:::
| AI / Automation | #4/#18/#19 | **very strong platform** — LiteLLM, Qdrant, RAG-ingest/Docling, Open WebUI, minicloud-agent, minicloud-crew-agent, Presidio, MLflow, Langfuse, vLLM, Flowise all **live**; but **zero insurance AI use-cases** deployed (#18/#19 parked) | 🟢 platform / 🔴 use-cases |

:::warning The headline finding
**The PLATFORM (Enterprise IT) and AI foundations are mature and heavily deployed. The CORE INSURANCE
BUSINESS is almost entirely NOT deployed — only Policy Admin (#4) actually runs.** ktayl has an
excellent *technology substrate* but is **not yet a runnable *insurer*** (no underwriting, claims,
billing, reinsurance, compliance, actuarial running). The gap is **the insurance business domains
themselves** — which is exactly why the build order (§5) is *business tools first, AI/automation last*.
:::

**Deployed vs board (quick read):** deployed → Policy #6 🟢, ERPNext #8 🟡, AI Platform #4 🟢, GitOps #3 🟢,
Digital Workplace #10 🟢. Board/repo only, nothing running → Underwriting #12, Claims #11, Distribution #13,
Finance #14, Compliance #15, ITSM #16, Data Platform #5, MDM #20, Knowledge Assistant #18, AI Ops Copilot
#19. (Retrieva #2 is a *separate product*, not ktayl.)

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
