# Gap Analysis — ktayl-solution IS vs the B2B Industrial-Insurer Blueprint

**Date:** 2026-09-27 · **Updated:** 2026-10-30 (capability registry reconciled with the committed SI Delivery Board; this proves repository/GitOps declared state, not live health, maturity or tested recovery) · **Author:** platform/EA
**Target (direction):** the greenfield blueprint in this folder — 19 L1 domains, 7 architecture layers, Wave 0→6 roadmap, capability registry.
**North star (why):** the 4 existential problems facing the major corporate / industrial insurers. A capability earns priority by how much it attacks these, not by parity with a generic map.

> Two-layer reminder (never conflate): **ktayl-solution IS** = the insurer's information system (this gap analysis). **Retrieva** = the RNCP39583 DORA-compliance *product* that runs on the IS. Retrieva's **graph engine is also a reusable pattern** for the IS (see Problem 3).

---

## 0. The reframe — from "build 19 domains" to "solve 4 problems"

| # | Existential problem | The capability/data/AI that actually attacks it | Our status |
|---|---|---|---|
| **P1** | **Insurability crisis** (climate, secondary perils blowing past actuarial models) | Risk Engineering (**prevention**), CAT modelling, Exposure & **Accumulation** analysis, NatCat data, Portfolio steering (geo-concentration) | 🔴 **largely GAP** — our weakest area vs the #1 problem |
| **P2** | **Margin squeeze** (soft market + claims/social inflation) | **Pricing Engine** (technical + experience rating), Portfolio analytics (loss/combined ratio), Underwriting discipline (referral/authority), claims-severity tracking, **Data Platform** | 🔴 **largely GAP** |
| **P3** | **Systemic cyber/AI accumulation** (one vuln → cascade of claims) | **Accumulation across the portfolio** (shared cloud/software dependency graph), exposure aggregation, Cyber LOB, scenario analysis | 🟡 **GAP as a product — but we own the exact pattern** (Retrieva's provider→dependency→nth-party graph) |
| **P4** | **Legacy tech + talent gap** (silver tsunami, skills shortage) | A modern, automated core (no legacy debt) + **AI copilots** (do more with fewer people) + straight-through automation | 🟢 **our STRENGTH** — we *are* the modern core; AI platform is mature. The lever is real; the apps it sits on aren't built yet |

**The shape of the gap in one line:** we have an **exceptional bottom-of-stack + AI platform** (answers P4, and is the launchpad for everything), a **unique graph asset** (answers P3), and we are **missing almost the entire insurance business core + data platform** (which is exactly what attacks P1 and P2).

### P1 target programme — Climate & Secondary Perils Insurability

P1 is a named cross-domain transformation programme, not a single application. It covers **flash flood, river flood, hail, severe convective storm, wildfire, drought/subsidence, heat and coastal flood**, in addition to conventional NatCat modelling. The programme must connect the following operating capabilities:

1. Governed peril taxonomy, hazard catalogue, external data ingestion and forward-looking climate scenarios.
2. Address mastering, geocoding, site-level multi-peril scoring and explainable vulnerability assessment.
3. Climate-adjusted CAT modelling, portfolio accumulation scenarios and geographic capacity zones.
4. Insurability decisions: insure, insure with prevention/coverage conditions, refer, defer or decline.
5. Risk-engineering prevention recommendations, evidence, due dates, validation and residual-risk tracking.
6. Peril pricing loads, prevention credits, deductibles, sub-limits and governed parametric complements.
7. Early warning, exposed-client outreach, post-event claims triage and portfolio monitoring.
8. Reinsurance treaty adequacy and gross-to-net stress analysis under changing frequency and severity.

The authoritative capability registry now decomposes this programme into `CAP-615`–`CAP-630`. These are architectural target capabilities with status **NOT DESIGNED / NOT ASSESSED**. Their presence identifies the required solution; it does not claim implementation, vendor selection, model validation or live operating evidence.

---

## 1. Layer-by-layer status (the blueprint's 7 layers)

| Layer | Blueprint expectation | Our actual state | Verdict |
|---|---|---|---|
| **7. Infrastructure** | Cloud/K8s, network, observability, backup, security, IaC | k3s 6-node · Cilium · Prometheus/Grafana/Tempo/Loki/OTel · Velero+Longhorn+MinIO+R2 (3-2-1, age-encrypted, DR-rehearsed) · Vault(KMS auto-unseal)+cert-manager+Gatekeeper+netpols · OpenTofu+ArgoCD+Kargo GitOps | 🟢 **EXCEEDS** |
| **6. Security & Governance** | IAM, PAM, DLP, GRC, DORA, audit | Authentik (workforce SSO+MFA) · **ktayl-iam** custom IGA dual-approval (live dev) · Presidio+default-deny egress (DLP) · **Retrieva** (DORA 3rd-party-ICT) · Regulatory obligations register (#15) | 🟢 **STRONG** (gaps: ABAC per business-object, DORA RTO/RPO per *business* capability, full GRC tooling) |
| **5. AI Platform** | LLM gateway, RAG, agents, eval, guardrails, cost | LiteLLM gateway · Langfuse LLMOps · Qdrant · RAG pipeline · LangGraph+CrewAI agents · Open WebUI · model-governance matrix · AI-Act gate · PII/guardrails/cost | 🟢 **EXCEEDS** (the *business copilots* on top are parked — correct, they need the apps first) |
| **4. Data Platform** | Lakehouse/DWH, MDM, BI, actuarial | **Slice 1 LIVE:** `data-platform` ns with CNPG + **Metabase BI** (`metabase.10.0.0.200.nip.io`) + dbt medallion (policy_portfolio). Still **no lakehouse/DWH, no MDM, no actuarial layer** | 🟡 **PARTIAL** (was 🔴; BI foundation now live — blueprint Wave 1, foundational to P1/P2/P3; MDM + warehouse still the gap) |
| **3. Workflow & Integration** | BPM, API mgmt, event bus, rules | NATS (bus, no domain-event catalogue) · Temporal (durable engine, no approval/SLA/task-inbox layer) · n8n · ingress-nginx (no business API mgmt/catalogue) · #25 scaffold | 🟡 **PARTIAL** (engines exist; the *integration product*, API catalogue, event taxonomy, BPM-with-approvals do not) |
| **2. Business Applications** | CRM, Submission, UW, Pricing, Policy, Billing, Claims, … | **Policy Service (live prod)** · **Claims (live prod** — ACL+CDC+read-model+adjuster workbench) · **Underwriting (live dev** — intake→bind + UI) · **ERPNext** HR/Finance (live) · everything else = board/scaffold | 🟡 **PARTIAL** (was 🔴; 2 core domains now in prod + 1 on dev — but Submission/Pricing/CRM/Billing/Claims-depth still gap) |
| **1. Channels** | Broker portal, client portal, employee UI | Public marketing site (ktayl-solution-web) · Homer app-launcher portals · **no broker/client portal** | 🔴 **GAP** (blueprint Wave 5 — correctly later) |

---

## 2. Domain-by-domain — the 19 L1 capabilities

Status legend: 🟢 LIVE · 🟡 PARTIAL/scaffold/stack-decided · 🔴 GAP (nothing built) · ⬛ PLATFORM (shared service provides it)

| # | L1 domain (blueprint) | Board | Our actual system | Status | What's missing | Serves |
|---|---|---|---|---|---|---|
| 01 | Distribution & Client Mgmt | #13 | — (no CRM app) | 🔴 | A CRM / account & broker mgmt system | P2 |
| 02 | **Submission & Opportunity** | #27 | — | 🔴 | **Submission Hub** — the #1 transformation area; **board #27 opened 2026-09-30** (build not started) | P2,P4 |
| 03 | **Underwriting** | #12 | Python/FastAPI ADR-007 — dev+prod deployment declared (intake→appetite→rating→quote→bind + workbench UI) | 🟢 declared | live health and risk/exposure/claims/capacity/referral depth remain to verify | P1,P2,P4 |
| 04 | **Pricing & Portfolio** | #12 | — | 🔴 | **Pricing Engine** + **Portfolio analytics** (loss/combined ratio, concentration) | **P2** |
| 05 | Policy Administration | #6 | **ktayl-policy-service** (live prod) | 🟢 | endorsements/lifecycle depth, doc generation | — |
| 06 | International Programmes | #23 | scaffold | 🟡 | Master↔local coordination, DIC/DIL, admitted/tax | — |
| 07 | Billing & Premium | #14 | ERPNext (general finance only) | 🔴 | **Insurance billing** (premium/installments/commission/IPT/cash-matching) — ERPNext ≠ insurance billing | P2 |
| 08 | Claims Management | #11 | **ktayl-claims (live prod)** — legacy-core (GlobalCore) ACL + Debezium CDC + CQRS read-model + adjuster workbench | 🟢 | lifecycle depth (reserve→payment→recovery breadth), fraud/SIU, litigation | P2,P4 |
| 09 | **Risk Engineering** | #21 | scaffold | 🟡→🔴 | Survey/recommendation/risk-quality platform — **prevention is the strategic pivot for P1** | **P1** |
| 10 | Reinsurance & Captive | #22 | scaffold | 🟡 | Treaty/fac/cession/captive-fronting | P1,P3 (capacity relief) |
| 11 | Finance & Actuarial | #8/#14 | ERPNext (GL/AP/AR live) | 🟡 | **Actuarial/reserving** (triangles, IBNR), technical accounting, capital/Solvency II | P1,P2 |
| 12 | Data & Reporting | #5 | **Slice 1 live** — CNPG + Metabase BI + dbt medallion (policy_portfolio) | 🟡 | warehouse/DWH depth, MDM, regulatory reporting, actuarial | **P1,P2,P3** |
| 13 | Compliance & Enterprise Risk | #15 | obligations register (doc) + Retrieva (DORA) | 🟡 | Operational-risk/AML/sanctions/internal-controls tooling | — |
| 14 | Document & Knowledge Mgmt | #24 | scaffold (Docuseal/Nextcloud exist) | 🟡 | A real DMS (classification/retention/legal-hold/records) + enterprise search | P4 |
| 15 | Digital Channels | — | public web only | 🔴 | Broker Portal + Client Portal | — |
| 16 | Integration & Automation | #25 | NATS/Temporal/n8n (platform) | 🟡 | API mgmt+catalogue, event catalogue, BPM/approvals | all |
| 17 | IT & Digital Operations (ITSM) | #16 | GLPI scaffold | 🟡 | GLPI ITIL/CMDB/SLA live | — |
| 18 | Cybersecurity & IAM | #17 | **ktayl-iam** (live dev) + Authentik + Vault | 🟢 | ABAC per business-object, SOC/vuln-mgmt | P3 |
| 19 | AI & Intelligent Automation | #4 | **mature AI platform** ⬛ | 🟢 | the *business copilots* (UW/Claims/Submission/Risk) — parked | **P4** |

**Also live (blueprint "corporate/shared"):** Digital Workplace #10 (Nextcloud, Stalwart mail, Matrix/Element, Jitsi, Docuseal, n8n, OnlyOffice, Vaultwarden, Homer) — the M365 alternative. HR = ERPNext.

---

## 3. Cross-cutting foundations the blueprint says do *early* (Wave 0/1)

| Foundation | Blueprint | Our state | Gap |
|---|---|---|---|
| **EA / Capability registry** | the master blueprint (this xlsx) | **630 capabilities** reconciled to actual app, SoR, board/repo, declared environment and target DORA/RTO/RPO. **Canonical source = the committed CSV `minicloud-platform-docs/data/capability-register.csv`** (plain-text, versioned, VSCode-editable); the B2BAssurance `.xlsx` is a derived presentation view (do not hand-edit both). Per-board maturity is surfaced live on the [SI Delivery Board](https://andrelair-platform.github.io/minicloud-platform-docs/is/delivery-board). | 🟡 evidence structure populated; **maturity scores (0/630 filled — NOT ASSESSED)**, vendors and measured recovery remain open |
| **System-of-Record registry** | one authoritative source per object | implicit, not declared | 🔴 declare SoR per business object (Customer/Policy/Claim/…) |
| **Canonical Insurance Data Model** | Customer→LegalEntity→Policy→Coverage→Claim… | Retrieva has a *DORA* graph; policy-service has its own model | 🔴 no cross-domain canonical model |
| **Event catalogue** | domain events (PolicyBound, ClaimCreated…) | NATS bus exists, no taxonomy | 🔴 define the event catalogue |
| **API catalogue** | every capability API-accessible | Backstage can hold it | 🟡 populate business APIs |
| **Service catalogue (fiches)** | criticality/SLA/RTO/RPO/DORA per service | Backstage entities | 🟡 add the DORA/RTO/RPO fields |
| **MDM** | Customer/Entity/Broker/Country/Currency/Industry… | — (#20 parked) | 🔴 the keystone for P1/P2/P3 analytics |
| **DORA-by-design per capability** | RTO/RPO/criticality/deps on every capability | Retrieva (3rd-party ICT) + obligations register | 🟡 extend to *business* capabilities |
| **Accumulation / systemic-risk graph** | (implicit in P3) | **Retrieva graph pattern exists** | 🟡 **apply the graph to the portfolio** = a differentiator |

---

## 4. Our differentiators against the four problems

1. **P4 (legacy + talent) is inverted into an advantage.** We have *no* legacy core — the platform is GitOps, cloud-native, AI-native from day one. The blueprint's hardest, slowest layer (Wave 0/1 tech foundation) is our *done* strength. The AI platform means copilots (the answer to the talent gap) are a build-on-top, not a research project.
2. **P3 (systemic accumulation) — we already own the exact engine.** Retrieva models `provider → dependency → nth-party` graphs for the insurer's *own* ICT third-party (DORA). The **same graph applied to the policyholder portfolio** answers "one AWS/CrowdStrike outage → which policies, which limits, what total exposure?" — the accumulation question that threatens solvency. Few insurers have this; we have the pattern running.
3. **P1 (insurability) is a *prevention* play, and prevention = Risk Engineering + data.** The pivot the whole industry is making (from risk transfer to prevention) maps onto Risk Engineering (#21) + Exposure/CAT/Accumulation + the Data Platform — all buildable on our stack, and all currently gaps we can turn into strengths.

---

## 5. Build vs Buy — where we deviate (deliberately)

The blueprint says **buy** IAM/CRM/ITSM/DMS/ERP/Finance. We **build** several of these — deliberately, because ktayl is a **learning / portfolio** vehicle, not a cost-minimising real carrier (a real carrier would buy these):
- **IAM → BUILD** (ktayl-iam) instead of buy — to exercise IGA/dual-approval. ✔ justified for our purpose.
- **Finance/HR → ERPNext** (buy-ish OSS) ✔ aligns.
- **ITSM → GLPI** (buy OSS) ✔ aligns.
- **Core PAS/Claims/Billing → the blueprint says buy/hybrid; we build** — justified for learning, but flag the effort: a real carrier would buy these. Keep the *modular-monolith-per-domain* discipline so we don't drown.

**Guard:** don't build all 15 bounded contexts as 15 services at once (blueprint §7). Modular monoliths per domain; extract only when a domain earns it (the same discipline that grew Retrieva out of a board).

---

## 6. Completion roadmap — problem-prioritised (adapts the blueprint waves to our reality)

We're **past Wave 0's tech foundation and past the AI-platform (Wave 6 infra)** already. So our real backlog re-sequences around P1–P4:

> ⚠️ **VERY IMPORTANT — the P2 sequencing trap.** When P2 (margin / pricing) is picked up, the honest
> **first slice is NOT the Pricing Engine — it is the Data Platform depth it depends on** (a warehouse +
> curated loss-ratio / portfolio analytics). Technical/experience rating, portfolio steering and
> loss/combined-ratio monitoring all *read from* that data layer; building the Pricing Engine before the
> warehouse exists means building against stubs for zero real value (the same "don't build the automation
> before its foundation" lesson as the parked copilot/MDM). **Order: Stage B Data Platform depth → then
> Stage C Pricing Engine.** Same dependency shape as **P1** (its CAT/secondary-peril models need the
> hazard/climate data layer first) and **P3** (see below).
>
> ⚠️ **P3 (systemic cyber/AI accumulation) — identified + planned-later, and the CHEAPEST differentiator
> to turn into a strength.** The `provider → dependency → nth-party` **graph engine already exists**
> (Retrieva, for the insurer's *own* DORA ICT third-party). P3 = **reuse that graph over the policyholder
> portfolio** to answer *"one AWS/CrowdStrike outage → which policies, what total limit/exposure?"* — the
> accumulation question that threatens solvency. **But same data-foundation-first dependency:** it needs
> the **Data Platform depth + MDM** (to resolve which policies share a cloud/software provider) + captured
> policy-exposure data **before** the graph can be applied. `CAP-209` Exposure & Accumulation Analytics =
> **PARTIAL**. Order: Stage B (Data Platform + MDM) → Stage D (apply the Retrieva graph for portfolio
> accumulation). Don't build the accumulation product before the data layer + MDM exist.

**Stage A — Complete Wave 0 (cheap, unlocks everything, literally "fill what's missing"):**
- Maintain the populated **capability registry** (this xlsx): actual apps + status + SoR + board/repository + declared environment + target DORA/RTO/RPO. Complete vendor mapping, evidence-based maturity and measured recovery fields.
- Declare the **System-of-Record registry** + a first **canonical data model** + **event catalogue** skeleton.
- One EA graph view (reuse the Retrieva/graph idea) linking capability→app→infra→vendor→DORA.

**Stage B — Wave 1 foundations that unlock P1/P2/P3 analytics:**
- **Data Platform** (the keystone — pricing, portfolio, CAT, accumulation all need it) — ingestion (events/CDC) → raw→curated→business → **BI**.
- **MDM** (Customer/Entity/Broker/Country/Industry) — de-duplicated identifiers the analytics depend on.
- (IAM already strong; DMS + CRM as capacity allows.)

**Stage C — the operational core + the AI showcase (P2 + P4):**
- **Submission Hub** (the #1 transformation area, **board #27 opened 2026-09-30** — build not started) → the flagship "AI automates intake, human validates," and the entry point that feeds everything.
- **Underwriting Workbench** + **Pricing Engine** (P2 margin discipline) — UW Copilot lands here (P4).

**Stage D — the P1/P3 differentiators:**
- **Climate & Secondary Perils Insurability Programme** (`CAP-615`–`CAP-630`) — hazard/climate data, site scoring, CAT/secondary-peril models, capacity zones, insurability decisions, prevention, pricing, early warning, event response and treaty adequacy.
- **Risk Engineering** platform (prevention → P1) — survey/recommendation/risk-quality, with the AI "risk evolution over years" assistant.
- **Exposure / Accumulation / Portfolio + CAT** analytics — **reuse the Retrieva graph** for portfolio accumulation (P3) + geo-concentration (P1) + portfolio steering (P2).

**Stage E — the rest of the core + channels:** Claims, Insurance Billing, International Programmes/DIC-DIL, Reinsurance/Captive, Actuarial/reserving; then Broker + Client Portals.

---

## 7. Recommended immediate next step

**Do Stage A first** — it's low-cost, it makes the whole IS navigable, it's the honest "complete the registry with what exists vs what's missing," and it produces the artifact (populated registry + SoR + canonical model + DORA-per-capability) that every later build references.

Then the first *net-new build* should be **either** the **Data Platform** (unlocks P1/P2/P3 — highest strategic leverage) **or** the **Submission Hub** (fastest visible P4 AI win + feeds the operational core). Both are defensible; pick by whether you want *strategic leverage* (Data Platform) or a *visible flagship* (Submission Hub) next.

*(Open decision for the owner — see the question I'll ask.)*

---

## 8. Blind spots — functions missing from BOTH the 19-domain map AND ktayl's boards (2026-10-30)

§2 maps the blueprint's **19 L1 domains**, so those gaps are *identified* (each has a board/scaffold). This
section is the **differential**: functions a real corporate carrier runs that are **absent from the blueprint
itself AND had no ktayl board** — the true blind spots. Method: a term-frequency sweep across this folder
(`ALM`, `treasury`, `complaint`, `contract lifecycle`, `SIEM`, `premium tax`, `coverholder`, `KYC`, `model
risk`, …) cross-checked against product boards #2–#28. (A function already flagged in §2 is **not** re-counted.)

### Tier 1 — genuinely unidentified anywhere → **boards opened 2026-10-30**

| # | Function | Why a corporate insurer needs it | Evidence of absence | New board |
|---|---|---|---|---|
| T1 | **Investment Management / ALM / Treasury** | An insurer has **two businesses: underwriting and investing**. Premiums fund a bond/equity portfolio backing reserves; **ALM** matches asset duration to claim liabilities; **treasury** runs cash/FX/liquidity. Drives a large share of profit and a whole **Solvency II market-risk capital** charge. | blueprint `ALM=0, treasury=0`; "Asset Management" in the map is **IT** asset-mgmt (ITSM), not financial. ktayl: no board; ERPNext = GL/AP/AR only. The market primer even notes a combined ratio <100% is profitable *"before financial result"* — it knows investment income matters, yet nothing manages it. | **#29** ktayl Investment & Treasury (ALM) |
| T2 | **Complaints & Dispute Management** | Hard **ACPR/EIOPA/IDD** obligation: complaints register, statutory deadlines, ombudsman escalation, root-cause reporting. | blueprint `complaint=0, ombudsman=0`; not in Claims #11, Distribution #13, or Compliance #15. | **#30** ktayl Complaints & Disputes |
| T3 | **Business Procurement + Vendor Mgmt + Contract Lifecycle (CLM)** *(non-ICT)* | Broker agreements, coverholder/TPA contracts, reinsurance-treaties-as-contracts, general supplier contracts need a **system of record**. | The SoR registry itself draws the line: **Retrieva owns the ICT-third-party graph only, "NOT business Vendors/Procurement generally."** `contract lifecycle=0`. No board. | **#31** ktayl Procurement & Contract Management |

### Tier 2 — present only as a *sub-capability*; no first-class tool/board (effectively unidentified as a system)

| # | Function | Status |
|---|---|---|
| T4 | **IPT / Premium-Tax determination engine** (multi-jurisdiction, Sovos/TMF class) | blueprint buries it as one line under Billing (`premium tax=0, IPT=1`); ktayl folds it into #14. No tool identified. |
| T5 | **SIEM / SOC — security detection & response** | ktayl has Falco (runtime) + Trivy (images) + Gatekeeper, but **no log-SIEM, no correlation/alerting, no security-incident mgmt** (`SIEM=0`). §1 flags "SOC/vuln-mgmt" in passing — no tool/board. Notable for a DORA entity. |
| T6 | **Delegated Authority / Coverholder / MGA + Bordereaux** | `coverholder=0, delegated authority=0, bordereau=1`. Only loosely touched by Distribution #13 / Reinsurance #22. No dedicated capability. |
| T7 | **KYC / customer onboarding due diligence** | Distinct from AML *screening* (#15 has that). `KYC=0`. The onboarding workflow (UBO, PEP, sanctions-at-onboarding) isn't identified. |
| T8 | **Model Risk Management** (actuarial & pricing models) | ktayl's AI-Act gate + model-governance-matrix cover *AI* models only. The actuarial/statistical model-risk discipline (SR 11-7 / Solvency-II internal-model validation, versioning, back-testing) isn't identified. |

### Already identified in §2 (NOT re-counted as new)
CAT modelling, actuarial/reserving, enterprise search, MDM, sanctions/AML screening, API-management/event-catalogue.

### Build decision deferred (boards track the DOMAIN; the *how* comes at onboarding)
Opening a board **identifies** the domain and gives its backlog a home — it is **not** a commitment to build a
bespoke service. Each respects `architecture-strategy.md` (modular-monolith-first) + the adopt-vs-build test at
onboarding: **Investment/ALM/Treasury** almost certainly **adopts** specialist tooling (portfolio/ALM engines
are not something to hand-build); **Complaints** is a natural **ktayl-core module**; **Procurement/CLM** is
adopt-or-module. Tier-2 items stay as sub-capabilities until one earns its own board. Follow-up: add the three
new boards (#29–#31) to the *Product boards* table in `minicloud-gitops/.claude/rules/github-projects.md`.

---

## 9. Lifecycle build backlog — the complete to-build checklist (DO NOT FORGET)

Everything still to build to make the **industrial-contract lifecycle** (submission → UW → pricing → quote →
bind → policy → billing → contract-life → renewal) run end-to-end. Priority-ordered. `[ ]` = not built.
Status source: the capability register (`capability-register.csv`), reconciled live 2026-10-31.

### A. Missing whole stages — these break the end-to-end chain (build first)
- [ ] **Submission Hub** (#27) — dossier intake + exposure-data extraction; the *front door*. `20/20 GAP`. (P2/P4)
- [ ] **Pricing Engine** (#04/#12) — base/exposure/experience rating, CAT/expense/capital loads, technical premium. `26/29 GAP`. (P2) — **needs Data Platform depth first (§6 flag).**
- [ ] **Insurance Billing** (#14) — premium/installments/commission/IPT/cash-matching. `25/25 GAP`. (P2) — ERPNext ≠ insurance billing.
- [ ] **Coinsurance Settlement** (`CAP-634`–`637`) — ingest the periodic coinsurance clearing bordereau → compute lead/follower (apériteur/coassureur) share of every premium/commission/claim/recovery/fee → emit ledger-ready accounting flux + claims register. `GAP`. Pervasive on large industrial coinsured risks; only co-insurance *setup* (CAP-138/477) exists today, not *settlement*. Feeds Insurance Billing + Technical Accounting + the Claims register.

### B. Scaffold → build
- [ ] **Risk Engineering** (#21) — survey/recommendation/risk-quality `scaffold`; **+ the prevention→pricing loop** (`CAP-638` loss-reduction/cost-benefit quantification, `CAP-639` reco→renewal/coverage-condition/pricing linkage) + `CAP-640` Cyber-OT survey dimension — `GAP`. (P1 prevention; the economic engine that turns inspections into pricing/insurability)

### C. Depth within the "live" domains (live core, missing depth — reconciled 2026-10-31)
- [ ] **Underwriting** (#12): Exposure Analysis `GAP` (BI/geo/NatCat/supply-chain/accumulation/multi-peril); the **loss-estimation core `GAP`** — **TIV aggregation, PML, MFL/EML** (`CAP-631/632/633`, the numbers that drive capacity/premium/deductible/retention/reinsurance); Capacity, Referral, Risk-Assessment depth, Claims-Experience, Renewal `PARTIAL`. (live core = Quote + Coverage Design)
- [ ] **Policy** (#6): endorsement lifecycle + **document generation** (certificates/attestations). (live core = issuance)
- [ ] **Document↔Record Linkage + Client Policy Dossier** (`CAP-648`/`649`, DMS #24) — link every document to its policy/client/claim + a consolidated electronic case file ('all docs for client X policy Y'). `GAP` — docs currently sit in Nextcloud/Qdrant unlinked. Depends on MDM (client key) + the canonical data model.
- [ ] **Document OCR/IDP + Template Assembly** (`CAP-646`/`647`, DMS #24) — structured field extraction from scanned docs (`CAP-646` PARTIAL: Docling/markitdown parse-for-RAG live, structured IDP not) + document template management/assembly for certificates/schedules/endorsements (`CAP-647` GAP). DMS domain is otherwise PARTIAL (Nextcloud storage + Docuseal + parse live; records-mgmt/retention/legal-hold thin).
- [ ] **Insurance E-Signature & Sealing** (`CAP-641`–`645`, Document/DMS #24) — multi-party signing **circuits** (broker→client SMS-OTP→PAS), **form-field layering**, **eIDAS electronic seal (cachet électronique)**, signed-doc **structured intake→PAS**, **délégation de signature**. `GAP` — only generic Docuseal e-sign exists. Spans Distribution + Policy + DMS.
- [ ] **Claims** (#11): Reserving, Payment, Recovery, Fraud/SIU, Litigation `GAP`; Investigation, Closure `PARTIAL`. (live core = FNOL + Coverage Review)

- [ ] **UW tool-equivalents** (`CAP-659`–`661`, UW #12) — **AI Risk-Analysis Assistant** (engineering-report analysis, limits extraction, authority, capacity — HITL), **Coverage & Wording Analysis**, **Wording Compliance Check** (red/amber/green vs house standard). `GAP` — manual today. (the ktayl equivalents of the carrier's UW-assistant / coverage-analysis / wording-check tools)
- [ ] **Clause & Wording Management / Orchestration** (`CAP-650`–`657`, UW #12) — approved-clause **library**, **external-clause ingestion**, **federated search**, **comparison/deviation analysis**, **restriction/blacklist rules**, **versioning/traceability**, **approval workflow** (peer/four-eyes/Legal/Compliance), **contract wording assembly**. `GAP` — ktayl has only clause *selection* (CAP-473/474). *For a carrier with existing clause tools this is orchestrate-not-rebuild; ktayl must build/adopt.* **+ `CAP-658` Mandatory Compliance-Clause Determination** (sanctions/cyber/terrorism/war/SRCC/communicable/ESG clause applicability — distinct from sanctions screening).

### D. Differentiator programmes — identified, planned later (see the §6 ⚠️ flag)
- [ ] **P1 Climate & Secondary-Perils** (`CAP-615`–`630`) — build the hazard/climate **data layer first**.
- [ ] **P3 Systemic accumulation** — reuse the **Retrieva graph** over the portfolio, **after Data Platform + MDM**.

### E. Foundations that unblock most of the above (Stage A/B — do before C/D)
- [ ] **Data Platform depth** (warehouse) — unblocks Pricing, Portfolio analytics, Claims-Experience, Accumulation.
- [ ] **MDM** (Customer/Entity/Broker/Country/Industry) — the keystone for accumulation + a Customer SoR.
- [ ] **CRM / Distribution** (#13) — broker/account mgmt (feeds Submission + renewal).

> **Sequencing rule (from §6):** foundations (E) unblock the data-dependent builds — don't build Pricing/
> Accumulation/Claims-Experience before the Data Platform + MDM exist. Close the **chain breaks (A)** to make
> the lifecycle *run*; add **depth (C)** to make it *good*; the **differentiators (D)** are the moat.

### F. Product-line (LOB) portfolio — a DIFFERENT axis from capabilities (§15)
The L3 capabilities (UW, pricing, policy, claims, clause, reinsurance…) are **LOB-agnostic** — they serve
*any* line. Which **lines of business** ktayl offers is a separate **product-portfolio** dimension (board
#9 *Product Lines* + the register's `Line of Business` column + the Product Catalogue). Today that axis is
**coarse** (~6 lines in the catalogue; a 3-bucket LOB column). The full corporate-insurer target taxonomy
to flesh out (NOT capability gaps — product-portfolio scope decisions):
- **Property** (Fire · NatCat · Machinery · Business Interruption)
- **Casualty / Liability** (General · Product · Environmental · Employers)
- **Marine** (Cargo · Hull · Marine Liability)
- **Engineering** (CAR · EAR · Machinery Breakdown · Infrastructure)
- **Cyber** · **Credit & Political Risk** · **Aviation** · **Energy** · **Specialty**
- **Financial Lines** (D&O · Professional Indemnity · Crime · Financial Institutions)
Each line reuses the same capability stack; "offering a line" = a product-catalogue + rating/wording
configuration, not new capabilities. Flesh out per `product-portfolio` scope, need-first.
