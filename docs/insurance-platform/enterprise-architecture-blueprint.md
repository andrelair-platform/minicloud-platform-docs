---
title: Enterprise Architecture Blueprint — the ktayl IARD Insurer IS
sidebar_label: 🏛 EA Blueprint (Insurer IS)
---

# Enterprise Architecture Blueprint — the ktayl IARD Insurer IS

> **This is the authoritative functional target for the ktayl-solution IS.** It models ktayl as a
> real commercial-lines / large-risk **IARD** insurer, so every
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

## 2b. Modernization architecture — the legacy core & the strangler

The target above is **not** all clean greenfield microservices — that isn't how a real IARD insurer's IS
exists. A real insurer runs a **legacy core that still works** (an old, authoritative, stored-procedure-
heavy system on **Oracle**, SOAP interfaces, nightly batch) with a **modern platform grown around it** that
wraps, intercepts and gradually *strangles* it — but rarely replaces it. This is the **Strangler Fig +
Anti-Corruption Layer** pattern. On the ktayl IS it is delivered as **Track C (Modernization Practice Lab)**
of the [IS Build Roadmap](../product-roadmap/is-build-roadmap), and it produces a **real, needed business
domain** rather than a throwaway.

**Where the legacy sits — a deliberate choice.** Policy Administration is **already modern** (the live
`ktayl-policy-service`, #6), so the legacy is **not** policy. The legacy is a domain we **need but haven't
built** — **Claims (#11)** — so that wrapping it *delivers* a real capability. The legacy engine is
**GlobalCore** (`globalcore-legacy`): a deliberately-legacy carrier we own — **Java 8 · SOAP · nightly
batch · stored procedures · Oracle · outside k8s · frozen** — evolved to hold the Claims domain.

```
┌─ LEGACY CORE (system of record — the domain we NEED, delivered via a legacy) ┐
│  GlobalCore (globalcore-legacy) · Oracle · Java 8 / SOAP / batch / PL/SQL     │
│  OUTSIDE k8s (traditional infra) · FROZEN — wrapped, never modified           │
│  Holds the CLAIMS domain (claims · reserves · payments) + supporting refs     │
└───────────────┬───────────────────────────────────────────────────────────────┘
                │  ACL translates SOAP→JSON + async batch→events (CDC/Debezium → NATS)
┌───────────────┴─── STRANGLER / ACL (the modern wrap = delivers the domain) ────┐
│  ktayl-claims (#11) = the modern Claims capability, built AS the ACL/strangler │
│    over GlobalCore — SOAP→JSON, batch→events, read-model, workbench, AI tools  │
└───────────────┬───────────────────────────────────────────────────────────────┘
                │  clean domain events on NATS
┌───────────────┴─── MODERN PLATFORM (greenfield — NOT wrapped) ─────────────────┐
│  ktayl-policy-service (#6, live PAS) · underwriting #12 · distribution ·        │
│  finance · reinsurance · compliance — Postgres per service · Authentik · Kargo  │
└───────────────┬───────────────────────────────────────────────────────────────┘
                │  consume ONLY via ACL APIs + events (never raw legacy access)
┌───────────────┴─── DATA + AI (read-through the ACL) ───────────────────────────┐
│  Data Platform (#5, OLAP/BI)   ·   AI: RAG(docs) + approved SQL-tools(data)     │
│  AI Ops Copilot (#19) — LAST, once domains hold real data                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**The alignment rules:**
1. **The legacy is the authoritative record for its domain; nothing writes around it** — modern code reaches it only through the ACL (SOAP + CDC).
2. **The legacy delivers a domain we need but haven't built** (Claims) — not a duplicate of something already modern (Policy is modern; don't wrap it).
3. **The legacy is FROZEN** — you wrap/intercept/strangle it (SOAP→JSON, batch→events), you never add modern capability *inside* it.
4. **CDC-over-polling** — legacy changes become NATS events (Debezium); consumers react.
5. **AI reaches structured data only via approved SQL-tools behind the ACL; documents via RAG** — never the LLM on the legacy, never an identity bypass.
6. **Legacy runs on traditional infra (outside k8s)** — GlobalCore + Oracle as containers on the controller, mirroring "legacy core + modern k8s platform" and keeping Oracle off the constrained cluster.

> **Most domains are still greenfield-modern** (underwriting #12, distribution, finance, …). The legacy
> spine is **one deliberate initiative** (Claims via GlobalCore), not the shape of every domain — it exists
> to build the real legacy-integration skill that modernizing enterprises need.

Full detail — the Oracle + GlobalCore evolution, the SOAP/batch wrap, the CDC/ACL seams — is in
**[Legacy-Core Modernization](./legacy-core-modernization)** and the wrapper initiative spec
(`ktayl-integration/docs/legacy-wrapper-initiative-spec.md`).

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
| 5 | Claims | #11 | scaffold — planned as the modern **ACL/strangler** that wraps **GlobalCore** to deliver Claims (§2b) | 🔴 |
| — | **Legacy core** — GlobalCore (`globalcore-legacy`) | Track C | Java 8 / SOAP / batch **built ✅**; evolving to **Oracle + the Claims domain** as the deliberate legacy the modern Claims wrap delivers (§2b, [Legacy-Core Modernization](./legacy-core-modernization)) | 🟡 built, evolving |
| 6 | Risk Engineering / Prevention | #21 | nothing running (repo `ktayl-risk-engineering` scaffold) | 🔴 |
| 7 | International Programs | #23 | nothing running (repo `ktayl-international-programs` scaffold) | 🔴 |
| 8 | Billing / Premium & Finance | #14 | ERPNext finance up, **insurance billing not configured** | 🟡 platform only |
| 9 | Reinsurance | #22 | nothing running (repo `ktayl-reinsurance` scaffold) | 🔴 |
| 10 | Compliance / Legal | #15 | nothing (Presidio PII is a data tool, not a compliance system) | 🔴 |
| 11 | Data / Actuarial | #5 | analytics stack (ClickHouse/dbt/Superset) **not deployed**; only MLflow up | 🔴 |
| 12 | Enterprise IT | #3/#4/#10/#16/#17 | **very strong — see note below** (except ITSM/GLPI + CMDB) | 🟢 |

**Enterprise IT (#12) deployed detail:** 🟢 IAM (Authentik) · M365-alt suite (Nextcloud, OnlyOffice,
Stalwart mail, Matrix/Element, Jitsi, Docuseal, n8n) · cloud/k8s (ArgoCD, Kargo, cert-manager +
trust-manager, ESO, Vault, Harbor, Cilium, Longhorn, KEDA, VPA, Velero) · observability
(Prometheus/Grafana/Loki/Tempo) · security (Falco, Gatekeeper, Polaris, Trivy) · DevPortal (Backstage) ·
project-mgmt (Plane CE). 🔴 **Not deployed: ITSM/GLPI (#16) + CMDB** (Plane covers project-mgmt, not helpdesk).

:::info Scope boundary — BYOD, no managed endpoints (deliberate)
ktayl manages **no company computers, phones, or desk telephony** — employees use their own device,
access is **browser-first**. So **endpoints / MDM-UEM (Intune-equivalent) / device hardening / hardware
asset lifecycle / telephony are OUT of scope** within Enterprise IT for now. This is coherent with the
digital workplace being all **SSO-gated web apps** (Authentik + MFA over Tailscale/Cloudflare) — an
inherently **zero-trust / identity-is-the-perimeter** shape. Accepted risk (no remote wipe / device DLP)
is offset by MFA + SSO + browser-first + app/gateway DLP (Presidio, default-deny egress). Consequently
ITSM/CMDB (#16) scopes to **software/services/logical assets**, not a HW fleet, and IAM/IGA (#17) becomes
the primary control. **Revisit** when real employees + PII-at-volume or a production DORA claim arrive
(successor: Fleet/osquery or a UEM). Full decision: `.claude/rules/project-governance.md` *IS scope boundaries*.
:::

### The 4 transversal layers
| Layer | Board | **Deployed reality** | Status |
|---|---|---|---|
| Documents (GED / OCR / IDP) | #24 | Nextcloud (storage) + OnlyOffice (edit) + **Docuseal** (e-sign) + **Docling + markitdown-proxy** (OCR/conversion) all **live**; missing a records-mgmt DMS + a structured IDP pipeline (repo `ktayl-dms` scaffold) | 🟡 partial |
| Integration (API-GW / ESB / ETL / MFT / EDI) | #25 | **NATS** (events) + **Temporal** (workflow) + **n8n** (low-code integration) **live** as primitives; missing the formal API-GW/ESB/ETL/MFT/EDI insurance fabric (repo `ktayl-integration` scaffold) | 🟡 primitives only |
| Master Data / Référentiels (MDM) | #20 | nothing running (repo scaffold, **parked** — see §5) | 🔴 |
| Data | #5 | only MLflow; analytical Data Platform not deployed | 🔴 |

:::info MDM (#20) vs Data Platform (#5) — different things, not a duplicate
**MDM = operational OLTP** golden records + low-latency lookup (PostgreSQL), consumed by the copilot
and domain services *at transaction time* ("which client/broker/entity is this?"). **Data Platform =
analytical OLAP** (Redpanda → ClickHouse → dbt → BI). **MDM *feeds* the Data Platform** via CDC
(Debezium, `DATA-18i`) — it is a *source* for analytics, not the analytics platform. Keep them separate.
:::

:::note Data Platform (#5) — why it is deferred + the build sequencing
**Three laws of a data platform:** *use cases **drive** it · sources **constrain** it · technology
comes **last**.* The generic **foundation** (medallion: ingest → raw → transform → curated → serve +
cross-cutting governance/lineage/quality) is buildable source-agnostic, but the **data products**
(Customer 360, Loss Ratio, Underwriting Mart) are impossible to build without their specific sources —
a data product is a *contract over specific source fields*.

**The ktayl twist — sources are our own domain services, and most aren't built yet.** Unlike a generic
enterprise whose sources are external unknowns (SAP, mainframe, SharePoint, broker SFTP), **ktayl's
sources are the domain microservices themselves**: Loss Ratio needs `ktayl-claims` + Policy + Finance;
Customer 360 needs Claims ↔ Policy ↔ CRM joined (i.e. MDM). Today only Policy Admin (#6) + ERPNext (#8)
run — Claims/#11, Underwriting/#12, Distribution/#13, Finance/#14 are board-only. **So #5 is 🔴 not
because the tech is unchosen, but because the sources are unbuilt.** Building the OLAP layer now = a
warehouse for empty warehouses.

**Consequence for build order:** this is *why* §5 sequences **business domains first, Data Platform
after** — the domain services *are* the sources. When the first domain ships (e.g. Claims), do **one
thin vertical slice** end-to-end (that source → just-enough foundation → one data product, e.g. Loss
Ratio), then generalize the ingestion framework from 2-3 real pipelines — never design a generic
connector framework up-front for sources that never arrive (the classic "impressive data lake nobody
uses"). Same need-first discipline as the rest of the IS: a capability with no inputs waits.
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
#19, **Risk Engineering #21, Reinsurance #22, International Programs #23, Documents/DMS #24, Integration
#25** (boards + home repos created 2026-09-15 so the full IARD SI is represented; build not started).
(Retrieva #2 is a *separate product*, not ktayl.)

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
    → REGULATORY IMPACT → CONTROLS REQUIRED → AUDIT EVIDENCE → MONITORING
```

:::info The regulatory tail is mandatory — compliance by design (insurance FDE standard)
ktayl is a **regulated insurer**: a **Solvency II** spine + transversal EU/FR frameworks (DORA, GDPR,
EU AI Act, IDD/DDA, AML/sanctions, IFRS 17, SFDR…). *(Insurer ≠ bank — CRR/CRD/PSD2 don't apply.)*
**Regulation is not a silo** — one capability (e.g. an AI Underwriting Assistant) fires **AI Act + GDPR
+ DORA + Solvency II + IDD + Sanctions/AML + Outsourcing at once**, so the design lists **all** triggered
frameworks and the **combined** control set. Controls are declared **at design time** (verified at the
security/architecture gate), evidence accrues to the control library owned by **Regulatory & Compliance
(#15)**, and every AI use case gets an **AI-Act risk tier** (controls spike the moment AI influences a
decision about a person). Reference: the *Regulatory impact* section of the underwriting FDE playbook;
standard: `bmad-compliance.md` *The regulatory layer*. Framework→domain ownership: Solvency II spans
UW→Pricing→Claims→Reserves→Reinsurance→Finance (not just Finance); DORA → Enterprise IT + Retrieva;
IDD → Distribution; IFRS 17 → Finance; AML/Sanctions → Compliance.
:::

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

**Next decisions (in flight):** **Underwriting (#12)** is planned (BMAD set done, binds the live PAS) and
is the current greenfield build. In parallel, the **legacy spine (§2b, Track C)** is being aligned: evolve
**GlobalCore** (`globalcore-legacy`) to **Oracle + the Claims domain**, and build **`ktayl-claims` (#11)**
as the modern **ACL/strangler that delivers Claims by wrapping it** (SOAP→JSON, batch→events). Policy stays
modern (live PAS) — the legacy is the domain we *need but haven't built* (Claims), not a duplicate. Each
missing domain gets its board/repo **when its work starts** (portfolio discipline — no empty boards).
The parked copilot/MDM/KA briefs remain valid plans. Detail: [Legacy-Core Modernization](./legacy-core-modernization).

## 6. Governance

- Each domain/layer = a **product board** (one Project per product; see the GitHub Projects rules).
  New boards are created **when work starts**, not pre-emptively.
- This blueprint is **BC01 (piloter) governance evidence** for the ktayl IS. It is reviewed at
  architecture gates and kept current as domains move 🔴→🟡→🟢.
- Detailed per-app inventory + sprint state: [Business Applications Catalog](./business-applications-catalog).
