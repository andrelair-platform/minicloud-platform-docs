---
id: business-applications-catalog
title: Business Applications Catalog
sidebar_label: Business Applications Catalog
---

# Business Applications Catalog

Complete catalog of all business applications planned or live for the **ktayl solution IS** — the simulated insurance company information system. This IS covers the same functional domains as a mid-sized French commercial insurer (B2B IARD, Vie & Prévoyance, International Programs).

Each entry links to its GitHub issue in `andrelair-platform/platform-backlog`.

---

## Legend

| Badge | Meaning |
|---|---|
| ✅ Live | Deployed and operational |
| 🔨 Q1 2027 | Certification core — build October 2026 → March 2027 |
| 🔨 Q2 2027 | Certification phase 2 — build April → September 2027 |
| 📋 Backlog | Scoped, not yet scheduled |
| 🔬 Research | Advanced / domain-depth — post-certification |

---

## 1. Core Insurance Platform (GERAS equivalent)

The four microservices that form the ktayl-solution certification project. These are the primary BC02 evidence for RNCP39583.

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **ktayl-policy-service** | Go | [#203](https://github.com/andrelair-platform/platform-backlog/issues/203) | 🔨 Q1 2027 | Policy lifecycle — create, amend, renew, cancel, document generation |
| **ktayl-claims-service** | Java 21 / Spring Boot 3 | [#198](https://github.com/andrelair-platform/platform-backlog/issues/198) | 🔨 Q1 2027 | FNOL → investigation → settlement state machine, Spring Batch COREP bordereau |
| **ktayl-ai-claims-assistant** | Python / LangGraph | [#200](https://github.com/andrelair-platform/platform-backlog/issues/200) | 🔨 Q2 2027 | AI triage, fraud scoring, human-in-loop via NATS events |
| **ktayl-portal** | Next.js 14 / TS | [#202](https://github.com/andrelair-platform/platform-backlog/issues/202) | 🔨 Q1 2027 | Unified policyholder + broker portal (Authentik role-based views, SSR, RGAA) |
| **RGAA 4.1 audit** | axe-core / Lighthouse CI | [#204](https://github.com/andrelair-platform/platform-backlog/issues/204) | 🔨 Q1 2027 | Accessibility audit on ktayl-portal — BC02 mandatory deliverable |

**Integration topology:**
```
ktayl-portal → ktayl-policy-service (Go REST)
             → ktayl-claims-service (Java REST)
             → ktayl-ai-claims-assistant (Python streaming)

ktayl-claims-service → NATS JetStream claim.* events
ktayl-ai-claims-assistant ← NATS consumer
ktayl-policy-service → ERPNext HR (employee validation)
ktayl-claims-service → Paperless-ngx DMS (document archive)
ktayl-claims-service → ERPNext (premium accounting)
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
ktayl-uwb-api ──────────── (NEW, Go) rules engine + authority routing
  IF revenue > €100M AND limit > €20M → senior_review
  IF industry = "chemical" AND hazard = "high" → specialist_review
  IF claims_freq > threshold → additional_UW_required
      ↓
ktayl-uwb-ui ───────────── (NEW, React) Underwriter Workbench — single screen:
  Client | Risk | Request | Claims history | AI findings | [ACCEPT] [MODIFY] [DECLINE]
      ↓
ktayl-uwb-api (quote generation + pricing engine)
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
| **ktayl-uwb-api** | Go | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | 📋 Backlog | Risk data model, rules engine, authority routing, pricing engine, quote generation, ERPNext policy push |
| **ktayl-uwb-ui** | React / TypeScript | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | 📋 Backlog | Underwriter Workbench single-screen: client + risk + AI findings + decision buttons (ACCEPT / MODIFY / DECLINE) |
| **underwriting-workflow** | Temporal (existing) | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | 📋 Backlog | Long-running UW state machine in the existing Temporal cluster — new workflow type, no new infrastructure |
| **UW AI agents** | Python / CrewAI (extend minicloud-crew-agent) | [#81](https://github.com/andrelair-platform/platform-backlog/issues/81) | 📋 Backlog | 3 specialized agents: Document (extract+classify), Risk (exposure+claims+anomaly), Compliance (KYC+sanctions+missing-docs) |
| **UW broker intake** | n8n (existing) | — | 📋 Backlog | n8n workflows: broker email → doc routing → missing-info auto-request → status updates. No new service. |

### 2b. Underwriting Governance & Tooling

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **UW authority matrix** | Config / API (inside ktayl-uwb-api) | [#231](https://github.com/andrelair-platform/platform-backlog/issues/231) | 📋 Backlog | Binding authority levels per LOB, enforced routing, escalation chain |
| **UW guidelines repository** | Versioned docs | [#230](https://github.com/andrelair-platform/platform-backlog/issues/230) | 📋 Backlog | LOB rules, prohibited sectors, capacity limits, pricing floors — UW Director approval |
| **Technical UW committee** | Temporal workflow | [#232](https://github.com/andrelair-platform/platform-backlog/issues/232) | 📋 Backlog | L4 risk escalation, quorum management, digital vote, signed decision |
| **Actuarial pricing engine** | Python / microservice | [#101](https://github.com/andrelair-platform/platform-backlog/issues/101) | 📋 Backlog | Statistical premium rating per LOB — replaces manual Excel tariff grids, feeds ktayl-uwb-api |
| **Risk engineering assessment** | Form / PDF | [#208](https://github.com/andrelair-platform/platform-backlog/issues/208) | 📋 Backlog | On-site visit report, prevention scoring, UW integration |

### 2c. Advanced / Research

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Corporate risk intelligence agent** | Python / LangGraph | [#210](https://github.com/andrelair-platform/platform-backlog/issues/210) | 🔬 Research | Pre-UW due diligence for CAC40 B2B prospects (Pappers + OpenSanctions) |
| **Algorithmic Cyber Underwriter** | Python / AI | [#150](https://github.com/andrelair-platform/platform-backlog/issues/150) | 🔬 Research | AI-driven cyber risk assessment, automated pricing decision support |
| **COBOL actuarial rating engine** | GnuCOBOL + API wrapper | [#148](https://github.com/andrelair-platform/platform-backlog/issues/148) | 🔬 Research | Legacy rating engine demo — IBM z/OS credential, modern REST wrapper |

---

## 3. Claims — Extended Features

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Claims indemnification payment** | Go / SEPA | [#211](https://github.com/andrelair-platform/platform-backlog/issues/211) | 📋 Backlog | Outbound SEPA credit transfer to claimants + ERPNext accounting |
| **Loss adjuster management** | Go / React | [#212](https://github.com/andrelair-platform/platform-backlog/issues/212) | 📋 Backlog | Approved panel registry, mission assignment, report reception, fee management |
| **Subrogation management** | Go | [#214](https://github.com/andrelair-platform/platform-backlog/issues/214) | 📋 Backlog | Third-party recovery after indemnification (recours subrogatoire) |
| **SIU fraud investigation** | Workflow + ALFA | [#217](https://github.com/andrelair-platform/platform-backlog/issues/217) | 📋 Backlog | Escalation when AI fraud score > 0.7, ALFA reporting to AGIRA |
| **Contentieux / litigation** | Case management | [#226](https://github.com/andrelair-platform/platform-backlog/issues/226) | 📋 Backlog | Contested claims, legal proceedings, prescription tracking, lawyer management |

---

## 4. Lines of Business (LOB)

LOB-specific modules extend the core policy and claims services with domain rules.

| App | Issue | Phase | Description |
|---|---|---|---|
| **IARD AUTO + HAB** | (ERPNext #50 ✅) | ✅ Live | Base IARD products configured in ERPNext (3 products: RC AUTO, MRH, PREV-IND) |
| **Marine & Transport** | [#218](https://github.com/andrelair-platform/platform-backlog/issues/218) | 📋 Backlog | Cargo policies, Institute Clauses, voyage/open cover, international freight |
| **Construction & Engineering** | [#219](https://github.com/andrelair-platform/platform-backlog/issues/219) | 📋 Backlog | TRC/TRM project policies, Bris de Machine, renewable energy |
| **Financial Lines (D&O / RC Pro)** | [#220](https://github.com/andrelair-platform/platform-backlog/issues/220) | 📋 Backlog | RCMS/D&O claims-made, retroactive dates, discovery periods |
| **Collaborateurs** | [#221](https://github.com/andrelair-platform/platform-backlog/issues/221) | 📋 Backlog | Group personal accident, business travel, Europ Assistance API |
| **International Programs** | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | 📋 Backlog | Master + local admitted policies, international network, 130-country coverage |
| **Alternative Risk Transfer** | [#223](https://github.com/andrelair-platform/platform-backlog/issues/223) | 🔬 Research | Captive management, parametric covers, risk financing |

---

## 5. Distribution & Commercial Operations

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Commercial Insurance CRM** | ERPNext CRM | [#92](https://github.com/andrelair-platform/platform-backlog/issues/92) | 📋 Backlog | Pré-souscription, devis légal, équipes commerciales, AI churn & cross-sell |
| **ERPNext CRM config** | Frappe | [#53](https://github.com/andrelair-platform/platform-backlog/issues/53) | 📋 Backlog | Prospect pipeline, devis lifecycle, renewal management, broker commissions |
| **ERPNext billing** | Frappe | [#54](https://github.com/andrelair-platform/platform-backlog/issues/54) | 📋 Backlog | Premium invoicing, payment tracking, claims payment accounting |
| **Premium collection lifecycle** | n8n + ERPNext | [#91](https://github.com/andrelair-platform/platform-backlog/issues/91) | 📋 Backlog | Underwriting trigger → SEPA mandate → online payment → suspension → AI default prediction |
| **Insurance product factory** | Admin UI | [#103](https://github.com/andrelair-platform/platform-backlog/issues/103) | 📋 Backlog | Configure products without developer intervention |
| **Insurance attestation PDF** | Python | [#116](https://github.com/andrelair-platform/platform-backlog/issues/116) | 📋 Backlog | Auto-generate certificates with QR verification at policy bind |
| **ORIAS broker verification** | Python | [#104](https://github.com/andrelair-platform/platform-backlog/issues/104) | 📋 Backlog | Automated credential check before accepting business from a broker |
| **Delegated underwriting authority** | Workflow | [#225](https://github.com/andrelair-platform/platform-backlog/issues/225) | 📋 Backlog | Broker binders, delegate register, capacity monitoring, annual audit |
| **Co-insurance / pool management** | Go | [#224](https://github.com/andrelair-platform/platform-backlog/issues/224) | 📋 Backlog | Lead/following insurer, premium apportionment, co-insurer bordereau |
| **Customer-facing AI chatbot** | Python / LangGraph | [#115](https://github.com/andrelair-platform/platform-backlog/issues/115) | 📋 Backlog | Policyholder + prospect assistant on devandre.sbs and ktayl-portal |
| **e-Signature platform (Docuseal)** | Docker | [#75](https://github.com/andrelair-platform/platform-backlog/issues/75) | ✅ Live | Policy & contract signing, eIDAS-compliant |

---

## 6. Reinsurance & Actuarial

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Reinsurance management** | Go | [#102](https://github.com/andrelair-platform/platform-backlog/issues/102) | 📋 Backlog | Treaty configuration, cession calculation, monthly bordereau |
| **Reinsurer bordereau portal** | Go / React | [#209](https://github.com/andrelair-platform/platform-backlog/issues/209) | 📋 Backlog | Monthly cession reporting to reinsurers (treaty + facultative) |
| **Actuarial reserving tool** | Python | [#207](https://github.com/andrelair-platform/platform-backlog/issues/207) | 📋 Backlog | Claims triangle analysis, IBNR calculation, Solvency II technical provisions |
| **Catastrophe modelling** | Python | [#215](https://github.com/andrelair-platform/platform-backlog/issues/215) | 🔬 Research | Nat cat aggregate exposure — flood, storm, earthquake — Solvency II SCR |

---

## 7. Compliance & Regulatory

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **ACPR COREP pipeline** | Spring Batch (in #198) | [#83](https://github.com/andrelair-platform/platform-backlog/issues/83) | 🔨 Q1 2027 | Automated COREP/XBRL/ORSA generation — embedded in ktayl-claims-service |
| **AML/KYC compliance** | Python | [#113](https://github.com/andrelair-platform/platform-backlog/issues/113) | 📋 Backlog | Anti-money laundering — Code monétaire et financier Art. L561-2 |
| **GDPR Art. 30 register** | ERPNext / doc | [#94](https://github.com/andrelair-platform/platform-backlog/issues/94) | 📋 Backlog | Registre des activités de traitement |
| **GDPR workflow** | n8n | [#84](https://github.com/andrelair-platform/platform-backlog/issues/84) | 📋 Backlog | Right-to-be-forgotten, data access requests, audit trail |
| **DDA/IDD training LMS** | Moodle | [#114](https://github.com/andrelair-platform/platform-backlog/issues/114) | 📋 Backlog | Mandatory 15h/year training per employee — ACPR requirement |
| **IFRS 17 reporting** | ERPNext / dbt | [#206](https://github.com/andrelair-platform/platform-backlog/issues/206) | 🔬 Research | Insurance contract measurement + P&L disclosure |

---

## 8. Document Management

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Paperless-ngx DMS** | Docker + Longhorn | [#76](https://github.com/andrelair-platform/platform-backlog/issues/76) | 📋 Backlog | Long-term compliant document archive — replaces eFile/DOXIS |

**Integration:** ktayl-claims-service archives settled claim documents → Paperless-ngx via API on settlement. ktayl-policy-service archives signed contracts at bind.

---

## 9. Communication & Notifications

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **VoIP / telephony** | Asterisk + FreePBX | [#105](https://github.com/andrelair-platform/platform-backlog/issues/105) | 📋 Backlog | Insurance call center — claims intake + servicing queues |
| **SMS gateway** | OVH SMS API | [#108](https://github.com/andrelair-platform/platform-backlog/issues/108) | 📋 Backlog | Payment reminders, dunning, claim status alerts |
| **Global Address List** | Stalwart LDAP | [#227](https://github.com/andrelair-platform/platform-backlog/issues/227) | 📋 Backlog | Corporate address book — Authentik directory → email autocomplete |
| **Shared mailboxes** | Stalwart IMAP ACL | [#228](https://github.com/andrelair-platform/platform-backlog/issues/228) | 📋 Backlog | Team inboxes: sinistres, production, comptabilité, courtiers, direction |

---

## 10. Data Platform & BI

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Global Data Platform** | ClickHouse + dbt + Metabase | [#152](https://github.com/andrelair-platform/platform-backlog/issues/152) | 📋 Backlog | Bronze/silver/gold data lake — analytical DB + ELT + self-service BI |
| **Insurance KPI dashboard** | Grafana / Metabase | [#82](https://github.com/andrelair-platform/platform-backlog/issues/82) | 📋 Backlog | Claims ratio, loss ratio, premium volume, NPS |
| **People Analytics** | Metabase | [#166](https://github.com/andrelair-platform/platform-backlog/issues/166) | 📋 Backlog | Workforce dashboards — headcount, turnover, absenteeism, salary cost |
| **GCP BigQuery** | BigQuery (free tier) | [#168](https://github.com/andrelair-platform/platform-backlog/issues/168) | 📋 Backlog | Ad-hoc insurance analytics — 10GB storage + 1TB queries/month free |
| **Data Lakehouse** | Apache Iceberg + Nessie | [#139](https://github.com/andrelair-platform/platform-backlog/issues/139) | 🔬 Research | Iceberg tables on MinIO + Nessie catalog + ClickHouse S3 |
| **Domain-specific LLM fine-tune** | MLflow + vLLM | [#123](https://github.com/andrelair-platform/platform-backlog/issues/123) | 🔬 Research | French insurance & regulatory data — MLOps pipeline on minicloud |

---

## 11. Identity & Access Management

| App | Stack | Issue | Phase | Description |
|---|---|---|---|---|
| **Authentik OIDC** | k3s (live) | — | ✅ Live | SSO, RBAC, SCIM — all apps |
| **Vaultwarden** | k3s (live) | — | ✅ Live | Password manager — 15 IS credentials |
| **MidPoint IGA** | Docker | [#205](https://github.com/andrelair-platform/platform-backlog/issues/205) | 📋 Backlog | Habilitation platform — access request → manager approval → Authentik SCIM |
| **PAM (Teleport + Vault SSH)** | k3s | [#151](https://github.com/andrelair-platform/platform-backlog/issues/151) | 📋 Backlog | JIT privileged access, dynamic secrets, quarterly access review |

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
| GLPI | ITSM | ✅ Live |
| Vaultwarden | Password management | ✅ Live |
| Authentik | IAM / SSO | ✅ Live |
| Harbor | Container registry | ✅ Live |
| Velero + Longhorn MinIO backups | Backup / DR | ✅ Live |

---

## Build Roadmap Summary

```
Q1 2027  →  ktayl-policy-service (Go)
             ktayl-claims-service (Java 21)
             ktayl-portal (Next.js 14) + RGAA audit

Q2 2027  →  ktayl-ai-claims-assistant (Python/LangGraph)
             ERPNext CRM + billing config
             Paperless-ngx DMS
             CLM-PAY-1 SEPA payment
             Insurance attestation PDF

Q3 2027  →  ktayl-uwb-api + ktayl-uwb-ui (Underwriting Workbench)
             underwriting-workflow (Temporal) + UW AI agents (CrewAI)
             UW authority matrix + actuarial pricing engine
             Premium collection lifecycle
             ORIAS verification
             SMS gateway + shared mailboxes

Post-cert →  Reinsurance, actuarial, LOB extensions,
             Data platform, MidPoint IGA, Contentieux
```

---

## IS Domain Coverage

| Domain | ktayl-solution component |
|---|---|
| Claims & policy lifecycle | ktayl-claims-service + ktayl-policy-service |
| Underwriting | UW workbench (#81) + authority matrix (#231) |
| Customer portal | ktayl-portal (#202) |
| Document management | Paperless-ngx (#76) |
| Task & project management | Plane CE (live) |
| CRM & partner management | ERPNext CRM (#53, #92) |
| Data platform | Global Data Platform (#152) |
| IAM & governance | Authentik + MidPoint IGA (#205) |
