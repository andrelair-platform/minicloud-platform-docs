---
id: business-applications-catalog
title: Business Applications Catalog
sidebar_label: Business Applications Catalog
---

# Business Applications Catalog

:::note Authoritative model
The functional target for the ktayl IARD insurer IS — the 12 domains + 4 transversal layers, gap
analysis and build order — is the **[Enterprise Architecture Blueprint](./enterprise-architecture-blueprint)**.
This catalog is the **detailed per-app inventory** that hangs off that blueprint; where the two differ,
the blueprint's domain model is authoritative and this catalog is being reconciled to it.
:::

Complete catalog of all business applications planned or live for the **ktayl-solution IS** — the
simulated commercial insurer's information system (B2B IARD / large risks). It covers the functional
domains of a real French commercial insurer; the authoritative domain model is the
[EA Blueprint](./enterprise-architecture-blueprint) (12 domains + 4 transversal layers).

:::warning Two-layer model — this IS is NOT the certification project
The **ktayl-solution IS** is the **organisational/business context** (the "company" and its systems).
The **RNCP39583 certification deliverable is Retrieva**, a *separate product* that runs on this
infrastructure. So the apps below are **ktayl IS business systems**, **not** cert evidence, and they do
not depend on Retrieva. (Legacy entries that called ktayl microservices "the certification project /
BC02 evidence" are being corrected in this pass.)
:::

Each product now lives on its own **GitHub Project board** (per-product portfolio; the old
`platform-backlog` aggregator was retired). Board numbers are shown in the domain map below.

---

## Legend

Two axes are used: **blueprint status** (in the domain map / coverage — current reality) and the
per-app **build phase** (in the detailed tables — indicative timing).

| Blueprint status (domain map / coverage) | Meaning |
|---|---|
| 🟢 Live | Deployed and operational |
| 🟡 In progress / scaffolded | Has a home (repo/board), not yet built or deployed |
| 🔴 Gap | No home yet — named in the EA Blueprint, board created when work starts |

| Build phase (detailed tables) | Meaning |
|---|---|
| ✅ Live | Deployed |
| 🔨 Qx 2027 | Targeted build window (indicative) |
| 📋 Backlog | Scoped, not yet scheduled |
| 🔬 Research | Advanced / domain-depth — later |

:::note Authoritative build order
The per-app 🔨 Qx phases are **indicative legacy estimates**. The authoritative sequence is the
**[Build Roadmap](#build-roadmap--copilot-driven-thin-slice-authoritative)** below (copilot-driven thin
slice). Claims-side AI (the old `ktayl-ai-claims-assistant`) is now delivered by the **AI Ops Copilot
(#19)** as its v2 — treat that legacy row as superseded.
:::

## Domain map — catalog → EA Blueprint (authoritative)

Aligns this catalog's sections to the blueprint's 12 domains + 4 transversal layers, with the current
board + status. See the [EA Blueprint](./enterprise-architecture-blueprint) for the gap analysis.

| Blueprint domain / layer | Board | Status | Catalog section |
|---|---|---|---|
| 1 Distribution / CRM / Broker portal | #13 | 🟡 | §5 Distribution |
| 2 Underwriting workbench | #12 | 🟡 | §2 Underwriting |
| 3 Pricing / Rating | #12 | 🟡 | §2 / §6 |
| 4 Policy Administration (PAS) | #6 | 🟢 | §1 Core |
| 5 Claims | #11 | 🟡 | §1 / §3 |
| 6 Risk Engineering / Prevention | — | 🔴 | *(gap — add when work starts)* |
| 7 International Programs | — | 🔴 | §4b |
| 8 Billing / Premium & Finance | #14 | 🟡 | §5 / §6 |
| 9 Reinsurance (own domain) | — | 🔴 | §6 |
| 10 Compliance / Legal | #15 | 🟡 | §7 |
| 11 Data / Actuarial | #5 | 🟡 | §10 |
| 12 Enterprise IT | #3/#4/#10/#16/#17 | 🟢 | §11 + platform docs |
| L Documents (GED/OCR/IDP) | — | 🔴 | §8 |
| L Integration (API/ESB/ETL/MFT/EDI) | — | 🔴 | *(gap — biggest)* |
| L Master Data / MDM | #20 | 🟡 | *(new — `ktayl-mdm`)* |
| L AI / Automation | #4 / #18 / #19 | 🟢 | §2a, §9, and the AI products |

**AI products (the OWUI-split):** **ktayl Knowledge Assistant** (#18 — chat-over-docs, Open WebUI
config) and **ktayl AI Ops Copilot** (#19 — beyond-OWUI structured decisions + authorized actions).

---

## 1. Core Insurance Platform (Policy Admin + Claims)

The core ktayl IS insurance services (blueprint domains **4 Policy Administration** + **5 Claims**).
These are **ktayl business systems** — *not* certification evidence (the cert deliverable is Retrieva,
a separate product; see the two-layer warning above).

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **ktayl-policy-service** | Go | #203 (archived) | 🔨 Q1 2027 | Policy lifecycle — create, amend, renew, cancel, document generation |
| **ktayl-claims** | Java 21 / Spring Boot 3 | #198 (archived) | 🔨 Q1 2027 | FNOL → investigation → settlement state machine, Spring Batch COREP bordereau |
| **ktayl-ai-claims-assistant** | Python / LangGraph | #200 (archived) | 🔨 Q2 2027 | AI triage, fraud scoring, human-in-loop via NATS events |
| **ktayl-portal** | Next.js 14 / TS | #202 (archived) | 🔨 Q1 2027 | Unified policyholder + broker portal (Authentik role-based views, SSR, RGAA) |
| **RGAA 4.1 audit** | axe-core / Lighthouse CI | #204 (archived) | 🔨 Q1 2027 | Accessibility audit on ktayl-portal — BC02 mandatory deliverable |

**Integration topology:**
```
ktayl-portal → ktayl-policy-service (Go REST)
             → ktayl-claims (Java REST)
             → ktayl-ai-claims-assistant (Python streaming)

ktayl-claims → NATS JetStream claim.* events
ktayl-ai-claims-assistant ← NATS consumer
ktayl-policy-service → ERPNext HR (employee validation)
ktayl-claims → Paperless-ngx DMS (document archive)
ktayl-claims → ERPNext (premium accounting)
```

---

## 2. Underwriting

### 2a. AI Underwriting Assistant (core system)

The underwriting system follows the principle: **AI prepares the decision, the underwriter makes it.**

The target operating model transforms the underwriter's workload from 60% administration + 40% underwriting judgment to 10–20% administration + 80–90% actual underwriting — multiplying the number of risks one underwriter can handle while improving consistency and auditability.

**Architecture (platform integration map):**

```
Broker / Client
      │
Email / Portal / API
      ↓
n8n  ──────────────────── (existing) intake, classify, route
      ↓
markitdown-proxy ─────── (existing) PDF/Excel/Office → text
      ↓
minicloud-crew-agent ─── (extend) 3 UW agents:
  ├── Document Agent      classify, extract, source-attribute every field
  ├── Risk Agent          exposure analysis, claims history summary, anomaly flags
  └── Compliance Agent    KYC/AML, sanctions screening, missing-doc detection
      ↓
Structured Risk JSON + source attribution (confidence %, page ref)
      ↓
underwriting-workflow ── (Temporal, existing) state machine
  SUBMITTED → INTAKE → DOCS_EXTRACTED → DATA_VALIDATED
  → RISK_ASSESSED → AWAITING_DECISION → QUOTED → BOUND | DECLINED
      ↓
ktayl-underwriting (API) ──────────── (NEW, Go) rules engine + authority routing
  IF revenue > €100M AND limit > €20M → senior_review
  IF industry = "chemical" AND hazard = "high" → specialist_review
  IF claims_freq > threshold → additional_UW_required
      ↓
ktayl-underwriting (UI) ───────────── (NEW, React) Underwriter Workbench — single screen:
  Client | Risk | Request | Claims history | AI findings | [ACCEPT] [MODIFY] [DECLINE]
      ↓
ktayl-underwriting (API) (quote generation + pricing engine)
      ↓
n8n ────────────────────── (existing) auto-generate broker communication
      ↓
ERPNext ────────────────── (existing) policy bind, premium accounting
      ↓
Paperless-ngx ─────────── (#76) audit-trail document archive
```

**Key design constraints:**
- Every AI-extracted field shows: value + source document + page + confidence %
- LLM never writes directly to the core system — always JSON → validation → human approval → system
- Quote ≠ Policy mismatch detection before bind (AI cross-check)
- Underwriter workbench is a task inbox, not a CRUD form

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **ktayl-underwriting (API)** | Go | #81 (archived) | 📋 Backlog | Risk data model, rules engine, authority routing, pricing engine, quote generation, ERPNext policy push |
| **ktayl-underwriting (UI)** | React / TypeScript | #81 (archived) | 📋 Backlog | Underwriter Workbench single-screen: client + risk + AI findings + decision buttons (ACCEPT / MODIFY / DECLINE) |
| **underwriting-workflow** | Temporal (existing) | #81 (archived) | 📋 Backlog | Long-running UW state machine in the existing Temporal cluster — new workflow type, no new infrastructure |
| **UW AI agents** | Python / CrewAI (extend minicloud-crew-agent) | #81 (archived) | 📋 Backlog | 3 specialized agents: Document (extract+classify), Risk (exposure+claims+anomaly), Compliance (KYC+sanctions+missing-docs) |
| **UW broker intake** | n8n (existing) | — | 📋 Backlog | n8n workflows: broker email → doc routing → missing-info auto-request → status updates. No new service. |

### 2b. Underwriting Governance & Tooling

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **UW authority matrix** | Config / API (inside ktayl-underwriting (API)) | #231 (archived) | 📋 Backlog | Binding authority levels per LOB, enforced routing, escalation chain |
| **UW guidelines repository** | Versioned docs | #230 (archived) | 📋 Backlog | LOB rules, prohibited sectors, capacity limits, pricing floors — UW Director approval |
| **Technical UW committee** | Temporal workflow | #232 (archived) | 📋 Backlog | L4 risk escalation, quorum management, digital vote, signed decision |
| **Actuarial pricing engine** | Python / microservice | #101 (archived) | 📋 Backlog | Statistical premium rating per LOB — replaces manual Excel tariff grids, feeds ktayl-underwriting (API) |
| **Risk engineering assessment** | Form / PDF | #208 (archived) | 📋 Backlog | On-site visit report, prevention scoring, UW integration |

### 2c. Advanced / Research

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Corporate risk intelligence agent** | Python / LangGraph | #210 (archived) | 🔬 Research | Pre-UW due diligence for CAC40 B2B prospects (Pappers + OpenSanctions) |
| **Algorithmic Cyber Underwriter** | Python / AI | #150 (archived) | 🔬 Research | AI-driven cyber risk assessment, automated pricing decision support |
| **COBOL actuarial rating engine** | GnuCOBOL + API wrapper | #148 (archived) | 🔬 Research | Legacy rating engine demo — IBM z/OS credential, modern REST wrapper |

---

## 3. Claims — Extended Features

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Claims indemnification payment** | Go / SEPA | #211 (archived) | 📋 Backlog | Outbound SEPA credit transfer to claimants + ERPNext accounting |
| **Loss adjuster management** | Go / React | #212 (archived) | 📋 Backlog | Approved panel registry, mission assignment, report reception, fee management |
| **Subrogation management** | Go | #214 (archived) | 📋 Backlog | Third-party recovery after indemnification (recours subrogatoire) |
| **SIU fraud investigation** | Workflow + ALFA | #217 (archived) | 📋 Backlog | Escalation when AI fraud score > 0.7, ALFA reporting to AGIRA |
| **Contentieux / litigation** | Case management | #226 (archived) | 📋 Backlog | Contested claims, legal proceedings, prescription tracking, lawyer management |

---

## 4. Lines of Business (LOB)

LOB-specific modules extend the core policy and claims services with domain rules.

### 4a. Standard LOBs

| App | Issue | Phase | Description |
|---|---|---|---|
| **IARD AUTO + HAB** | (ERPNext #50 ✅) | ✅ Live | Base IARD products configured in ERPNext (3 products: RC AUTO, MRH, PREV-IND) |
| **Marine & Transport** | #218 (archived) | 📋 Backlog | Cargo policies, Institute Clauses, voyage/open cover, international freight |
| **Construction & Engineering** | #219 (archived) | 📋 Backlog | TRC/TRM project policies, Bris de Machine, renewable energy |
| **Financial Lines (D&O / RC Pro)** | #220 (archived) | 📋 Backlog | RCMS/D&O claims-made, retroactive dates, discovery periods |
| **Collaborateurs** | #221 (archived) | 📋 Backlog | Group personal accident, business travel, Europ Assistance API |
| **Alternative Risk Transfer** | #223 (archived) | 🔬 Research | Captive management, parametric covers, risk financing |

### 4b. International Programs (IP) — GNP equivalent

International Programs is operationally distinct from standard LOBs: it involves **two parties** (Producing Office = ktayl France and Servicing Office = local insurer abroad), a **master policy + local admitted sub-policies** structure, and **cross-entity data exchange** for premiums, reserves, claims and accounting — exactly what HDI's Global Network Portal (GNP) handles.

**Concept:**

```
ktayl France (Producing Office)
        │
        │  master policy terms, capacity, limits
        ↓
ktayl-ip-portal ─────────── GNP equivalent: central coordination hub
        │
        ├── Policy data sync ──→ Servicing Offices (local admitted insurers)
        │                        premium cession, reserve allocation
        │
        ├── Claims data ◄─────── ktayl-claims (direct claims)
        │                        + local SO claim notifications
        │
        ├── IP bordereaux ──────→ ERPNext (cession accounting écritures)
        │                        separate format from reinsurance bordereaux
        │
        └── Network status ─────  Viewer / User / Accountant role access
                                  (mirrors GNP roles 1014444/1014445/1014446)
```

**Integration topology:**
```
ktayl-policy-service  ──► IP data model extension (master + local sub-policies)
ktayl-claims  ──► ktayl-ip-portal (SO claim notifications inbound)
ktayl-ip-portal       ──► ERPNext (IP bordereau → accounting écritures)
ktayl-ip-portal       ──► Paperless-ngx (SO documents archive)
ktayl-ip-portal       ──► n8n (automated SO communication workflows)
```

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **International Programs LOB** | Extension of ktayl-policy-service | #222 (archived) | 📋 Backlog | IP data model in ktayl-policy-service: master policy + local admitted sub-policies, network cession amounts, SO registry |
| **ktayl-ip-portal** | Go / React | #222 (archived) | 📋 Backlog | GNP equivalent — Producing Office ↔ Servicing Office hub: policy sync, reserve/premium coordination, claims notification, network status. Roles: Viewer / User / Accountant |
| **IP bordereau module** | ERPNext / Frappe | #222 (archived) | 📋 Backlog | IP-specific cession bordereaux (distinct format from reinsurance #209): PO → SO premium cession, reserve transfers, accounting écritures in ERPNext PCG |
| **SO claims feed** | Go (in ktayl-ip-portal) | #222 (archived) | 📋 Backlog | Inbound claim data from Servicing Offices — mirrors GNP ↔ ICS (Claims@Global) interface. SO notifies PO of local claims against the master program |

---

## 5. Distribution & Commercial Operations

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Commercial Insurance CRM** | ERPNext CRM | #92 (archived) | 📋 Backlog | Pré-souscription, devis légal, équipes commerciales, AI churn & cross-sell |
| **ERPNext CRM config** | Frappe | #53 (archived) | 📋 Backlog | Prospect pipeline, devis lifecycle, renewal management, broker commissions |
| **ERPNext billing** | Frappe | #54 (archived) | 📋 Backlog | Premium invoicing, payment tracking, claims payment accounting |
| **Premium collection lifecycle** | n8n + ERPNext | #91 (archived) | 📋 Backlog | Underwriting trigger → SEPA mandate → online payment → suspension → AI default prediction |
| **Insurance product factory** | Admin UI | #103 (archived) | 📋 Backlog | Configure products without developer intervention |
| **Insurance attestation PDF** | Python | #116 (archived) | 📋 Backlog | Auto-generate certificates with QR verification at policy bind |
| **ORIAS broker verification** | Python | #104 (archived) | 📋 Backlog | Automated credential check before accepting business from a broker |
| **Delegated underwriting authority** | Workflow | #225 (archived) | 📋 Backlog | Broker binders, delegate register, capacity monitoring, annual audit |
| **Co-insurance / pool management** | Go | #224 (archived) | 📋 Backlog | Lead/following insurer, premium apportionment, co-insurer bordereau |
| **Customer-facing AI chatbot** | Python / LangGraph | #115 (archived) | 📋 Backlog | Policyholder + prospect assistant on devandre.sbs and ktayl-portal |
| **e-Signature platform (Docuseal)** | Docker | #75 (archived) | ✅ Live | Policy & contract signing, eIDAS-compliant |

---

## 6. Reinsurance & Actuarial

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Reinsurance management** | Go | #102 (archived) | 📋 Backlog | Treaty configuration, cession calculation, monthly bordereau |
| **Reinsurer bordereau portal** | Go / React | #209 (archived) | 📋 Backlog | Monthly cession reporting to reinsurers (treaty + facultative) |
| **Actuarial reserving tool** | Python | #207 (archived) | 📋 Backlog | Claims triangle analysis, IBNR calculation, Solvency II technical provisions |
| **Catastrophe modelling** | Python | #215 (archived) | 🔬 Research | Nat cat aggregate exposure — flood, storm, earthquake — Solvency II SCR |

---

## 7. Compliance & Regulatory

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **ACPR COREP pipeline** | Spring Batch (in #198) | #83 (archived) | 🔨 Q1 2027 | Automated COREP/XBRL/ORSA generation — embedded in ktayl-claims |
| **AML/KYC compliance** | Python | #113 (archived) | 📋 Backlog | Anti-money laundering — Code monétaire et financier Art. L561-2 |
| **GDPR Art. 30 register** | ERPNext / doc | #94 (archived) | 📋 Backlog | Registre des activités de traitement |
| **GDPR workflow** | n8n | #84 (archived) | 📋 Backlog | Right-to-be-forgotten, data access requests, audit trail |
| **DDA/IDD training LMS** | Moodle | #114 (archived) | 📋 Backlog | Mandatory 15h/year training per employee — ACPR requirement |
| **IFRS 17 reporting** | ERPNext / dbt | #206 (archived) | 🔬 Research | Insurance contract measurement + P&L disclosure |

---

## 8. Document Management

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Paperless-ngx DMS** | Docker + Longhorn | #76 (archived) | 📋 Backlog | Long-term compliant document archive — replaces eFile/DOXIS |

**Integration:** ktayl-claims archives settled claim documents → Paperless-ngx via API on settlement. ktayl-policy-service archives signed contracts at bind.

---

## 9. Communication & Notifications

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **VoIP / telephony** | Asterisk + FreePBX | #105 (archived) | 📋 Backlog | Insurance call center — claims intake + servicing queues |
| **SMS gateway** | OVH SMS API | #108 (archived) | 📋 Backlog | Payment reminders, dunning, claim status alerts |
| **Global Address List** | Stalwart LDAP | #227 (archived) | 📋 Backlog | Corporate address book — Authentik directory → email autocomplete |
| **Shared mailboxes** | Stalwart IMAP ACL | #228 (archived) | 📋 Backlog | Team inboxes: sinistres, production, comptabilité, courtiers, direction |
| **Distribution lists** | Stalwart virtual aliases | #229 (archived) | 📋 Backlog | Team mailing lists: sinistres@, production@, courtiers@, direction@ |
| **minicloud Copilot** | n8n + LiteLLM + Qdrant + maubot | #260 (archived) | 📋 Backlog | M365 Copilot equivalent — AI layer across mail, chat, meetings, docs and enterprise search. 5 connectors wiring existing services. See [minicloud Copilot](../ai-ml/minicloud-copilot) |

---

## 10. Data Platform & BI

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Global Data Platform** | ClickHouse + dbt + Metabase | #152 (archived) | 📋 Backlog | Bronze/silver/gold data lake — analytical DB + ELT + self-service BI |
| **Insurance KPI dashboard** | Grafana / Metabase | #82 (archived) | 📋 Backlog | Claims ratio, loss ratio, premium volume, NPS |
| **People Analytics** | Metabase | #166 (archived) | 📋 Backlog | Workforce dashboards — headcount, turnover, absenteeism, salary cost |
| **GCP BigQuery** | BigQuery (free tier) | #168 (archived) | 📋 Backlog | Ad-hoc insurance analytics — 10GB storage + 1TB queries/month free |
| **Data Lakehouse** | Apache Iceberg + Nessie | #139 (archived) | 🔬 Research | Iceberg tables on MinIO + Nessie catalog + ClickHouse S3 |
| **Domain-specific LLM fine-tune** | MLflow + vLLM | #123 (archived) | 🔬 Research | French insurance & regulatory data — MLOps pipeline on minicloud |

---

## 11. Identity & Access Management

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Authentik OIDC** | k3s (live) | — | ✅ Live | SSO, RBAC, SCIM — all apps |
| **Vaultwarden** | k3s (live) | — | ✅ Live | Password manager — 15 IS credentials |
| **MidPoint IGA** | Docker | #205 (archived) | 📋 Backlog | Habilitation platform — access request → manager approval → Authentik SCIM |
| **PAM (Teleport + Vault SSH)** | k3s | #151 (archived) | 📋 Backlog | JIT privileged access, dynamic secrets, quarterly access review |
| **GLPI** | Docker + PostgreSQL | — | 📋 Backlog | ITSM / service desk — ticketing, asset management, change management, internal service catalog |

---

## 12. Already Live — Full Platform

| App | Category | Status |
|---|---|---|
| ERPNext (HR, PCG 2025, TSCA, Factur-X) | ERP / Finance | ✅ Live |
| Plane CE | Project management | ✅ Live |
| Open WebUI + LiteLLM + vLLM | AI gateway | ✅ Live |
| Langfuse + MLflow | AI observability | ✅ Live |
| minicloud-agent + minicloud-crew-agent | AI agents | ✅ Live |
| n8n | Business automation | ✅ Live |
| Temporal | Workflow orchestration | ✅ Live |
| Stalwart mail (devandre.sbs) | Corporate mail | ✅ Live |
| Matrix + Element Web | Internal messaging | ✅ Live |
| Jitsi Meet + TURN (Lightsail) | Video conferencing | ✅ Live |
| Backstage IDP | Developer portal | ✅ Live |
| Docuseal | e-Signature | ✅ Live |
| Grafana + Loki + Tempo | Observability | ✅ Live |
| Flowise 2.2.7 | AI workflow builder | ✅ Live |
| Nextcloud | File sharing / collaboration | ✅ Live |
| NATS JetStream | Event streaming | ✅ Live |
| Qdrant | Vector database (RAG) | ✅ Live |
| Vaultwarden | Password management | ✅ Live |
| Authentik | IAM / SSO | ✅ Live |
| Harbor | Container registry | ✅ Live |
| Velero + Longhorn MinIO backups | Backup / DR | ✅ Live |

---

## Build Roadmap — copilot-driven thin slice (authoritative)

Per the [EA Blueprint](./enterprise-architecture-blueprint), we complete the IS **in the order that
delivers value**, driven by the AI Ops Copilot's underwriting-v1 dependencies — **not** breadth-first.

```
NOW      →  ktayl-mdm (Master Data, thin slice)          #20  🟡  ← copilot dependency #1
             Documents/IDP (submission-pack ingestion)    🔴  ← copilot dependency #2
             exposure/accumulation Data (thin)            #5   🟡  ← copilot dependency #3
             UW workbench (appetite, referral)            #12  🟡  ← copilot dependency #4

THEN     →  ktayl-ai-copilot — underwriting v1            #19       (structured decisions + actions)
             ktayl Knowledge Assistant                     #18       (OWUI config: cited staff Q&A)

NEXT     →  Claims (copilot v2) · Billing/Finance · Distribution/CRM

LATER    →  Reinsurance · Risk Engineering · International Programs · Integration layer ·
             Actuarial depth (reserving/cat) · Legal
```

Legacy note: the previous Q1–Q3 2027 plan framed ktayl builds as "certification" work — corrected
(cert = Retrieva, separate product). Live today: ktayl-policy-service, ERPNext, Nextcloud/OnlyOffice,
Docuseal, Stalwart mail, Matrix/Element, the AI Platform.

---

## IS Domain Coverage (aligned to the EA Blueprint)

| Blueprint domain / layer | Board | Status | Current component(s) |
|---|---|---|---|
| 4 Policy Administration (PAS) | #6 | 🟢 | ktayl-policy-service (live) |
| 12 Enterprise IT | #3/#4/#10/#16/#17 | 🟢 | GitOps, AI Platform, Digital Workplace, ITSM, IAM (several live) |
| L Master Data / MDM | #20 | 🟡 | ktayl-mdm (thin slice, in progress) |
| L AI / Automation | #4/#18/#19 | 🟢 | AI Platform + Knowledge Assistant + AI Ops Copilot |
| 2/3 Underwriting & Pricing | #12 | 🟡 | ktayl-underwriting (repo) |
| 5 Claims | #11 | 🟡 | ktayl-claims (repo) |
| 1 Distribution / CRM | #13 | 🟡 | ktayl-distribution (repo) + ERPNext CRM config |
| 8 Billing / Finance | #14 | 🟡 | ktayl-finance (repo) + ERPNext |
| 10 Compliance / Legal | #15 | 🟡 | ktayl-compliance (repo) |
| 11 Data / Actuarial | #5 | 🟡 | Data Platform (minimal) |
| 7 International Programs | — | 🔴 | gap — board when work starts |
| 9 Reinsurance | — | 🔴 | gap |
| 6 Risk Engineering | — | 🔴 | gap |
| L Documents (GED/OCR/IDP) | — | 🔴 | Nextcloud storage only; IDP is a gap |
| L Integration (API/ESB/ETL/MFT/EDI) | — | 🔴 | gap (biggest) |
