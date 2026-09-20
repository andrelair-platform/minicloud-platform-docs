---
title: Product Roadmap
sidebar_label: Overview
---

# Organisation Product Roadmap (detailed backlog)

The detailed backlog behind the **ktayl-solution IS** — the simulated commercial-lines (IARD) insurer's
information system on the minicloud platform. **This is the inventory view;** for the *shape* of the plan
start with the two pages below.

**Start here →** [🗺 Architecture at a Glance](../insurance-platform/architecture-at-a-glance) · **What to build next (the 3 tracks) →** [🧭 IS Build Roadmap](../product-roadmap/is-build-roadmap) · **Full catalogue →** [Business Applications Catalog](../insurance-platform/business-applications-catalog) · **Functional target + deployed reality →** [EA Blueprint](../insurance-platform/enterprise-architecture-blueprint)

:::warning Read this before the tables — the framing changed
1. **This IS is *not* the certification.** The RNCP39583 deliverable is **Retrieva** (a separate product
   that only *runs on* this platform). The old "CERT core/phase" quarter labels are **retired** — work is
   now organised by the **three-track model** (see [IS Build Roadmap](./is-build-roadmap)), **not** by cert quarters.
2. **Product boards are authoritative, not this page.** Each domain has its own GitHub Project (#2–#25);
   there is **no roll-up**. The `platform-backlog#NNN` issue links below are **legacy** (old Project #1,
   deleted 2026-09-10) — kept only as a historical inventory; live tracking is on each product board.
3. **Authoritative deployed status = the EA Blueprint gap analysis.** As of 2026-09 only **Policy Admin
   #6** + the platform/AI foundations + ERPNext truly run; most insurance domains are not yet deployed.
:::

## Build-ready now (design done → implementation can start)

Three domains have passed their design pass (readiness gate PASS) and can be built today:

| Domain | Board | What it is | Design |
|---|---|---|---|
| **Claims #11** | #11 | modern Claims built **AS the ACL/strangler** over the **GlobalCore** legacy (Oracle + SOAP + batch), Java 21 + Spring Boot, CDC→NATS, read-model, governed AI tool | `ktayl-claims/docs/` — Path-C set, gate PASS |
| **Underwriting & Pricing #12** | #12 | underwriting workbench + rating, binds the live PAS | `ktayl-underwriting/docs/` — Path-C set, gate PASS |
| **ITSM (GLPI) #16** | #16 | IT service desk + BYOD-scoped CMDB + SLAs (closes the one run-the-system gap) | `ktayl-itsm/docs/` — Path-B set, gate PASS |

Everything below is the **broader inventory** — most items are epic-scoped and need their own design pass
(the [per-domain recipe](./is-build-roadmap#how-they-interlock-one-repeatable-recipe-per-domain)) before build.

---

## Legend

| Badge | Meaning |
|---|---|
| ✅ Live | Deployed and operational (verify against the EA Blueprint) |
| 🟢 Build-ready | Design pass done (gate PASS) — implementation can start |
| 🔨 Near-term | Next in the Track-A / Track-C sequence |
| 📋 Backlog | Epic-scoped; needs its design pass before build |
| 🔬 Research | Advanced / domain-depth, no committed date |

> The old **quarter labels (Q1/Q2/Q3 "CERT")** are retired — sequencing now follows the
> [three tracks + per-domain recipe](./is-build-roadmap), not cert quarters. The tables below keep their
> original grouping as a **historical inventory**; treat the badges above as the current status vocabulary.

---

## Platform Foundation (Live)

All infrastructure underpinning every business application.

```
6-node k3s (5× ThinkPad + 1× MacBook Pro) — 44 cores / ~84 GiB
├── ArgoCD app-of-apps (~93 applications)
├── Authentik OIDC (SSO for all apps)
├── Harbor registry (all CI images)
├── Vault (secrets, PKI)
├── Longhorn + MinIO (storage + backups)
├── Grafana + Loki + Tempo (observability)
├── Temporal (workflow orchestration)
├── n8n (business automation)
├── LiteLLM + vLLM + minicloud-agent + minicloud-crew-agent (AI stack)
├── ERPNext — HR, PCG 2025, TSCA, Factur-X (ERP)
├── Stalwart mail, Matrix, Jitsi (communication)
└── Docuseal (e-signature)
```

---

## The value chain (Track A build order)

Sequencing follows the insurance value chain + the legacy spine, **not** cert quarters:

```
   FOUNDATIONS (live): platform #3 · AI #4 · digital workplace #10 · Policy Admin #6 · ERPNext #8
        │
   TRACK A — value chain:
   Distribution #13 → Underwriting #12 → Policy Admin #6 (LIVE) → Claims #11 → Billing #14 → Reinsurance #22
        │                 (🟢 build-ready)                          (🟢 build-ready)
   TRACK C — legacy spine (parallel): GlobalCore (Oracle/SOAP/batch) ──wrapped by──► Claims #11 ACL
   TRACK B — governance gate: every build clears regulatory impact · AI-Act tier · NFR/security/resilience
   RUN-THE-SYSTEM: ITSM (GLPI) #16 🟢 build-ready — IT service desk + CMDB
```

Full explanation: [🧭 IS Build Roadmap](./is-build-roadmap). Cross-cutting completeness pieces —
the **[Enterprise Document Platform #24](../insurance-platform/business-applications-catalog)**, the
**[Operations Workbench](./is-build-roadmap#business-operations-completeness--the-back-office-layer)** (AI-native
back-office task-inbox), the **[semantic/metrics layer](./is-build-roadmap#net-new-items-this-blueprint-adds-to-the-roadmap)**
(Data #5), and the **Level-7 hardening** posture — are named on the IS Build Roadmap.

---

## Core lifecycle build (Policy · Claims · portal)

> The four services below were previously grouped as "Certification Core" — **that framing is retired**
> (the cert is Retrieva). They remain the **core policy/claims lifecycle** of the IS. **Note the corrected
> Claims design:** Claims is delivered by **wrapping the GlobalCore legacy** (ACL/strangler), not a
> standalone COREP state machine. Issue links are legacy `platform-backlog` refs (historical).

**Dependency chain:**
```
ERPNext HR (✅ live)
      └──► ktayl-policy-service (Go, ✅ LIVE #6) ──────────┐
                                                            │
GlobalCore legacy (Oracle/SOAP/batch, Track C) ──ACL──► ktayl-claims (#11, Java 21 + Spring Boot)
                                                            │
Authentik OIDC (✅ live) ──────────────────► ktayl-portal (Next.js)
                                                    │
                                                    └──► RGAA 4.1 accessibility audit
```

| Deliverable | Stack | Board / issue | Description |
|---|---|---|---|
| **ktayl-policy-service** | Go | **#6 · ✅ live** | Policy lifecycle: create, amend, renew, cancel, document generation |
| **ktayl-claims** | Java 21 / Spring Boot | **#11 · 🟢 build-ready** | modern Claims built **AS the ACL/strangler** over GlobalCore (SOAP→JSON, batch→events/CDC→NATS, read-model, workbench, governed AI tool) |
| **ktayl-portal** | Next.js / TypeScript | `platform-backlog#202` | Unified policyholder + broker portal, Authentik role-based views, SSR |
| **RGAA 4.1 accessibility audit** | axe-core / Lighthouse CI | `platform-backlog#204` | Accessibility audit on the portal |
| **ACPR COREP pipeline** | Spring Batch | `platform-backlog#83` | Automated COREP/XBRL/ORSA generation (a Finance/Compliance capability) |

---

## AI, billing & documents

**Dependency chain:**
```
ktayl-claims (#11)
      └──► claims AI tool (governed SQL-tool, read-only) ──► NATS JetStream (✅ live)
      └──► Enterprise Document Platform (#24) ──► claims document archive + RAG
      └──► SEPA payment ──► ERPNext accounting (✅ live)

ERPNext CRM + billing config ──► premium invoicing + renewal
```

| Deliverable | Stack | Board / issue | Description |
|---|---|---|---|
| **Claims governed AI tool** | Python / LiteLLM | #11 (story S007) | read-only SQL-tool + RAG, PII-masked, identity-scoped (full copilot = #19, parked) |
| **ERPNext CRM config** | Frappe | `platform-backlog#53` | Prospect pipeline, devis lifecycle, renewal, broker commissions |
| **ERPNext billing** | Frappe | `platform-backlog#54` | Premium invoicing, payment tracking, claims payment accounting |
| **Enterprise Document Platform** | Nextcloud/OnlyOffice/Docuseal/Docling live + Paperless-ngx backlog | **#24** | DMS + the parse→chunk→metadata→embed→vector-DB ingestion pipeline (see [catalog §8](../insurance-platform/business-applications-catalog)) |
| **Claims indemnification SEPA** | Go / SEPA | `platform-backlog#211` | Outbound SEPA credit transfer to claimants + ERPNext entries |
| **Insurance attestation PDF** | Python | `platform-backlog#116` | Auto-generate certificates with QR verification at policy bind |

---

## Underwriting, International Programs & Distribution

Major IS domains. Underwriting **#12 is build-ready**; see dedicated pages for architecture detail.

**Dependency chain:**
```
minicloud-crew-agent (✅ live) ──► UW AI agents (Document/Risk/Compliance)
markitdown-proxy (✅ live) ──────► UW document extraction
n8n (✅ live) ───────────────────► broker intake + missing-doc requests
Temporal (✅ live) ──────────────► underwriting-workflow state machine
                                          │
                                          ▼
                               ktayl-uwb-api (Go)  ──► ERPNext policy bind
                                          │
                                          ▼
                               ktayl-uwb-ui (React)  ── Underwriter Workbench

ktayl-policy-service (Q1) ──► IP data model extension
                                    │
                                    ▼
                            ktayl-ip-portal (Go/React)  ── PO ↔ SO hub
                                    │
                                    ▼
                            ERPNext IP bordereau module
```

| Deliverable | Stack | Issue | Description |
|---|---|---|---|
| **ktayl-uwb-api** | Go | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | Rules engine, authority routing, pricing, quote generation |
| **ktayl-uwb-ui** | React / TypeScript | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | Underwriter Workbench single-screen — AI findings + decision buttons |
| **UW AI agents** | Python / CrewAI | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | Document + Risk + Compliance agents (extends minicloud-crew-agent) |
| **underwriting-workflow** | Temporal | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | State machine: SUBMITTED → INTAKE → EXTRACTED → ASSESSED → BOUND |
| **ktayl-ip-portal** | Go / React | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | International programs portal — PO ↔ SO hub, IP policy sync, reserve coordination |
| **IP bordereau module** | ERPNext / Frappe | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | IP cession bordereaux → ERPNext accounting écritures |
| **SO claims feed** | Go (in ip-portal) | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | Inbound claim notifications from Servicing Offices |
| **Premium collection lifecycle** | n8n + ERPNext | [#91](https://github.com/andrelair-platform/platform-backlog/issues/91) | UW trigger → SEPA mandate → online payment → suspension |
| **ORIAS broker verification** | Python | [#104](https://github.com/andrelair-platform/platform-backlog/issues/104) | Automated credential check before accepting broker business |
| **UW authority matrix** | Go (in uwb-api) | [#231](https://github.com/andrelair-platform/platform-backlog/issues/231) | Binding authority per LOB, enforced routing, escalation chain |
| **Actuarial pricing engine** | Python | [#101](https://github.com/andrelair-platform/platform-backlog/issues/101) | Statistical premium rating per LOB — replaces manual Excel tariff grids |

---

## Later — IS Expansion

Beyond the core lifecycle + build-ready domains. No fixed dates — ordered by IS priority (each still
needs its own design pass before build).

### Claims Extended

| Deliverable | Stack | Issue |
|---|---|---|
| Loss adjuster management | Go / React | [#212](https://github.com/andrelair-platform/platform-backlog/issues/212) |
| Subrogation management | Go | [#214](https://github.com/andrelair-platform/platform-backlog/issues/214) |
| SIU fraud investigation | Workflow + ALFA | [#217](https://github.com/andrelair-platform/platform-backlog/issues/217) |
| Contentieux / litigation | Case management | [#226](https://github.com/andrelair-platform/platform-backlog/issues/226) |

### Reinsurance & Actuarial

| Deliverable | Stack | Issue |
|---|---|---|
| Reinsurance management | Go | [#102](https://github.com/andrelair-platform/platform-backlog/issues/102) |
| Reinsurer bordereau portal | Go / React | [#209](https://github.com/andrelair-platform/platform-backlog/issues/209) |
| Actuarial reserving tool | Python | [#207](https://github.com/andrelair-platform/platform-backlog/issues/207) |

### LOB Extensions

| Deliverable | Issue |
|---|---|
| Marine & Transport | [#218](https://github.com/andrelair-platform/platform-backlog/issues/218) |
| Construction & Engineering | [#219](https://github.com/andrelair-platform/platform-backlog/issues/219) |
| Financial Lines (D&O / RC Pro) | [#220](https://github.com/andrelair-platform/platform-backlog/issues/220) |
| Collaborateurs | [#221](https://github.com/andrelair-platform/platform-backlog/issues/221) |

### Data Platform & BI

| Deliverable | Stack | Issue |
|---|---|---|
| Global Data Platform | ClickHouse + dbt + Metabase | [#152](https://github.com/andrelair-platform/platform-backlog/issues/152) |
| Insurance KPI dashboard | Grafana / Metabase | [#82](https://github.com/andrelair-platform/platform-backlog/issues/82) |
| GCP BigQuery | BigQuery (free tier) | [#168](https://github.com/andrelair-platform/platform-backlog/issues/168) |

### Identity & Compliance

| Deliverable | Stack | Issue |
|---|---|---|
| MidPoint IGA | Docker | [#205](https://github.com/andrelair-platform/platform-backlog/issues/205) |
| AML/KYC compliance | Python | [#113](https://github.com/andrelair-platform/platform-backlog/issues/113) |
| GDPR workflows | n8n | [#84](https://github.com/andrelair-platform/platform-backlog/issues/84) |
| DDA/IDD training LMS | Moodle | [#114](https://github.com/andrelair-platform/platform-backlog/issues/114) |
| PAM (Teleport + Vault SSH) | k3s | [#151](https://github.com/andrelair-platform/platform-backlog/issues/151) |

### Distribution & Commercial

| Deliverable | Stack | Issue |
|---|---|---|
| Commercial Insurance CRM | ERPNext CRM | [#92](https://github.com/andrelair-platform/platform-backlog/issues/92) |
| Delegated underwriting authority | Workflow | [#225](https://github.com/andrelair-platform/platform-backlog/issues/225) |
| Co-insurance / pool management | Go | [#224](https://github.com/andrelair-platform/platform-backlog/issues/224) |
| Customer-facing AI chatbot | Python / LangGraph | [#115](https://github.com/andrelair-platform/platform-backlog/issues/115) |
| VoIP / call center | Asterisk + FreePBX | [#105](https://github.com/andrelair-platform/platform-backlog/issues/105) |

---

## Research Pipeline

Long-horizon items. No delivery date committed.

| Item | Stack | Issue | Why it matters |
|---|---|---|---|
| Domain-specific LLM fine-tune | MLflow + vLLM | [#123](https://github.com/andrelair-platform/platform-backlog/issues/123) | French insurance & regulatory corpus — specialist model |
| Catastrophe modelling | Python | [#215](https://github.com/andrelair-platform/platform-backlog/issues/215) | Nat cat aggregate exposure, Solvency II SCR |
| COBOL actuarial rating engine | GnuCOBOL + REST wrapper | [#148](https://github.com/andrelair-platform/platform-backlog/issues/148) | Legacy system demo — IBM z/OS credential evidence |
| Algorithmic Cyber Underwriter | Python / AI | [#150](https://github.com/andrelair-platform/platform-backlog/issues/150) | AI-driven cyber risk assessment + pricing |
| Corporate risk intelligence agent | Python / LangGraph | [#210](https://github.com/andrelair-platform/platform-backlog/issues/210) | Pre-UW due diligence for CAC40 B2B prospects |
| Alternative Risk Transfer | TBD | [#223](https://github.com/andrelair-platform/platform-backlog/issues/223) | Captive management, parametric covers, risk financing |
| IFRS 17 reporting | ERPNext / dbt | [#206](https://github.com/andrelair-platform/platform-backlog/issues/206) | Insurance contract measurement + P&L disclosure |
| Data Lakehouse | Apache Iceberg + Nessie | [#139](https://github.com/andrelair-platform/platform-backlog/issues/139) | Iceberg tables on MinIO + Nessie catalog |

---

## Backlog Scorecard

Quick-scan of IS domain items not yet scheduled. Full detail per item is in the [Business Applications Catalog](../insurance-platform/business-applications-catalog).

**Platform engineering items (DevSecOps, FinOps, SRE, IaC, AI hardening, HR, intranet) are tracked separately → [Platform Engineering Backlog](../platform-engineering/platform-backlog)**

| Scope | Count |
|---|---|
| Insurance IS domain (this page) | 53 |
| Platform engineering | 100 |
| Research pipeline | 8 |
| **Total active backlog** | **161** |

### 51 Backlog items (📋)

| # | Item | Domain |
|---|---|---|
| 1 | ktayl-uwb-api | Underwriting |
| 2 | ktayl-uwb-ui | Underwriting |
| 3 | underwriting-workflow (Temporal) | Underwriting |
| 4 | UW AI agents (CrewAI) | Underwriting |
| 5 | UW broker intake (n8n) | Underwriting |
| 6 | UW authority matrix | Underwriting |
| 7 | UW guidelines repository | Underwriting |
| 8 | Technical UW committee workflow | Underwriting |
| 9 | Actuarial pricing engine | Underwriting |
| 10 | Risk engineering assessment | Underwriting |
| 11 | Claims indemnification SEPA payment | Claims Extended |
| 12 | Loss adjuster management | Claims Extended |
| 13 | Subrogation management | Claims Extended |
| 14 | SIU fraud investigation | Claims Extended |
| 15 | Contentieux / litigation | Claims Extended |
| 16 | Marine & Transport LOB | LOB |
| 17 | Construction & Engineering LOB | LOB |
| 18 | Financial Lines (D&O / RC Pro) LOB | LOB |
| 19 | Collaborateurs LOB | LOB |
| 20 | International Programs LOB (data model) | IP |
| 21 | ktayl-ip-portal (international programs portal) | IP |
| 22 | IP bordereau module (ERPNext) | IP |
| 23 | SO claims feed | IP |
| 24 | Commercial Insurance CRM | Distribution |
| 25 | ERPNext CRM config | Distribution |
| 26 | ERPNext billing | Distribution |
| 27 | Premium collection lifecycle | Distribution |
| 28 | Insurance product factory | Distribution |
| 29 | Insurance attestation PDF | Distribution |
| 30 | ORIAS broker verification | Distribution |
| 31 | Delegated underwriting authority | Distribution |
| 32 | Co-insurance / pool management | Distribution |
| 33 | Customer-facing AI chatbot | Distribution |
| 34 | Reinsurance management | Reinsurance |
| 35 | Reinsurer bordereau portal | Reinsurance |
| 36 | Actuarial reserving tool | Actuarial |
| 37 | AML/KYC compliance | Compliance |
| 38 | GDPR Art. 30 register | Compliance |
| 39 | GDPR workflow (n8n) | Compliance |
| 40 | DDA/IDD training LMS (Moodle) | Compliance |
| 41 | Paperless-ngx DMS | Document Mgmt |
| 42 | VoIP / call center (Asterisk) | Communication |
| 43 | SMS gateway (OVH) | Communication |
| 44 | Global Address List (Stalwart LDAP) | Communication |
| 45 | Shared mailboxes (Stalwart IMAP ACL) | Communication |
| 46 | Global Data Platform (ClickHouse + dbt + Metabase) | Data & BI |
| 47 | Insurance KPI dashboard | Data & BI |
| 48 | People Analytics (Metabase) | Data & BI |
| 49 | GCP BigQuery | Data & BI |
| 50 | MidPoint IGA | IAM |
| 51 | PAM (Teleport + Vault SSH) | IAM |
| 52 | GLPI ITSM 🟢 **build-ready** (#16 design pass done — CMDB + incident/SLA) | IT Ops |
| 53 | Distribution lists (Stalwart virtual aliases) | Communication |

### 8 Research items (🔬)

| # | Item | Why it matters |
|---|---|---|
| 1 | Domain-specific LLM fine-tune | French insurance corpus on vLLM — specialist model |
| 2 | Catastrophe modelling | Nat cat aggregate exposure, Solvency II SCR |
| 3 | COBOL actuarial rating engine | Legacy demo — IBM z/OS credential evidence |
| 4 | Algorithmic Cyber Underwriter | AI-driven cyber risk assessment + pricing |
| 5 | Corporate risk intelligence agent | Pre-UW due diligence for CAC40 B2B prospects |
| 6 | Alternative Risk Transfer | Captive management, parametric covers |
| 7 | IFRS 17 reporting | Insurance contract measurement + P&L |
| 8 | Data Lakehouse (Iceberg + Nessie) | Iceberg tables on MinIO, analytical layer |

### Domain weight

| Domain | Backlog count |
|---|---|
| Underwriting | 10 |
| Distribution & Commercial | 10 |
| Claims Extended | 5 |
| International Programs | 4 |
| Data & BI | 4 |
| Communication | 5 |
| LOB extensions | 4 |
| Compliance | 4 |
| Reinsurance / Actuarial | 3 |
| IAM / IT Ops | 3 |
| Document Mgmt | 1 |

Underwriting and Distribution are the two heaviest domains — together 20 of the 53 IS backlog items.

---

## IS Domain Coverage Map

| IS Domain | Board | Component | Status |
|---|---|---|---|
| Policy administration (PAS) | #6 | ktayl-policy-service (Go) | ✅ **Live** |
| Claims (via legacy wrap) | #11 | ktayl-claims ACL over **GlobalCore** (Oracle/SOAP/batch) | 🟢 Build-ready |
| Underwriting & Pricing | #12 | uw workbench + rating (binds PAS) | 🟢 Build-ready |
| ITSM / IT service desk | #16 | GLPI (incident/request/SLA + CMDB) | 🟢 Build-ready |
| Legacy core (Track C) | — | GlobalCore (`globalcore-legacy`), evolving to Oracle + Claims | 🟡 built, evolving |
| Policyholder / broker portal | #13 | ktayl-portal (Next.js) | 📋 Backlog |
| Enterprise Document Platform | #24 | Nextcloud/OnlyOffice/Docuseal/Docling live; Paperless-ngx + IDP pipeline backlog | 🟡 partial |
| International Programs | #23 | ktayl-ip-portal + bordereau | 📋 Backlog |
| CRM & partner management | #13 | ERPNext CRM | 🟡 platform only |
| Billing / Finance | #14 | ERPNext billing (insurance config) | 🟡 platform only |
| Reinsurance | #22 | treaty/fac + bordereau portal | 📋 Backlog |
| Data / Actuarial + BI | #5 | ClickHouse + dbt + Metabase + **semantic layer** | 📋 Backlog (sources-gated) |
| Compliance / Regulatory | #15 | AML/KYC, GDPR, ACPR/COREP, DORA | 📋 Backlog |
| Operations Workbench (back-office) | — | AI-native cross-domain task-inbox | 📋 named, need-first |
| IAM & governance | #17 | Authentik (✅) + MidPoint IGA | ✅ / 📋 |
| ERP & finance | #8 | ERPNext PCG 2025 + TSCA + Factur-X | ✅ Live |
| AI platform | #4 | LiteLLM + vLLM + agents + RAG | ✅ Live |
| Communication | #10 | Stalwart + Matrix + Jitsi | ✅ Live |
| e-Signature | #10 | Docuseal | ✅ Live |
