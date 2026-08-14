---
title: Product Roadmap
sidebar_label: Overview
---

# Organisation Product Roadmap

Complete delivery timeline for the **ktayl solution IS** — the simulated insurance company information system built on the minicloud platform. Organised by quarter with dependency chains and ownership.

**Full application catalogue →** [Business Applications Catalog](../insurance-platform/business-applications-catalog)

---

## Legend

| Badge | Meaning |
|---|---|
| ✅ Live | Deployed and operational |
| 🔨 Q1 2027 | Certification core — October 2026 → March 2027 |
| 🔨 Q2 2027 | Certification phase 2 — April → September 2027 |
| 📋 Q3 2027 | Post-cert expansion — Underwriting, IP, Distribution |
| 📋 Backlog | Scoped, not yet scheduled |
| 🔬 Research | Advanced / domain-depth — post-certification |

---

## Platform Foundation (Live)

All infrastructure underpinning every business application.

```
5-node k3s (4× ThinkPad + 1× MacBook Pro)
├── ArgoCD app-of-apps (54 applications)
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

## Roadmap Timeline

```
                         NOW
                          │
          ┌───────────────┼───────────────────────────────────┐
          │               │                                   │
     Oct 2026        Apr 2027                            Oct 2027+
          │               │                                   │
    ┌─────▼─────┐  ┌──────▼──────┐  ┌────────▼────────┐  ┌──▼──────────┐
    │  Q1 2027  │  │   Q2 2027   │  │    Q3 2027      │  │  Post-cert  │
    │   CERT    │  │   CERT P2   │  │   UW + IP + Dist│  │  IS Expan.  │
    └───────────┘  └─────────────┘  └─────────────────┘  └─────────────┘
```

---

## Q1 2027 — Certification Core (RNCP39583 BC02)

Primary evidence for the RNCP39583 certification. Four microservices + accessibility audit.

**Dependency chain:**
```
ERPNext HR (✅ live)
      └──► ktayl-policy-service (Go)  ────────────────────┐
                │                                          │
                └──► ktayl-claims-service (Java 21)        │
                              │                            │
                              └──► ACPR COREP pipeline     │
                                                           ▼
Authentik OIDC (✅ live) ──────────────────► ktayl-portal (Next.js 14)
                                                    │
                                                    └──► RGAA 4.1 audit
```

| Deliverable | Stack | Issue | Description |
|---|---|---|---|
| **ktayl-policy-service** | Go | [#203](https://github.com/andrelair-platform/platform-backlog/issues/203) | Policy lifecycle: create, amend, renew, cancel, document generation |
| **ktayl-claims-service** | Java 21 / Spring Boot 3 | [#198](https://github.com/andrelair-platform/platform-backlog/issues/198) | FNOL → investigation → settlement state machine + COREP bordereau |
| **ktayl-portal** | Next.js 14 / TypeScript | [#202](https://github.com/andrelair-platform/platform-backlog/issues/202) | Unified policyholder + broker portal, Authentik role-based views, SSR |
| **RGAA 4.1 accessibility audit** | axe-core / Lighthouse CI | [#204](https://github.com/andrelair-platform/platform-backlog/issues/204) | Mandatory BC02 deliverable on ktayl-portal |
| **ACPR COREP pipeline** | Spring Batch (in claims-service) | [#83](https://github.com/andrelair-platform/platform-backlog/issues/83) | Automated COREP/XBRL/ORSA generation |

---

## Q2 2027 — Certification Phase 2

AI layer, billing, and supporting infrastructure that complete the certification scope.

**Dependency chain:**
```
ktayl-claims-service (Q1)
      └──► ktayl-ai-claims-assistant (Python/LangGraph) ──► NATS JetStream (✅ live)
      └──► Paperless-ngx DMS  ──► claims document archive
      └──► CLM-PAY-1 SEPA payment  ──► ERPNext accounting (✅ live)

ERPNext CRM + billing config ──► premium invoicing + renewal
Insurance attestation PDF  ──► QR-code verification at bind
```

| Deliverable | Stack | Issue | Description |
|---|---|---|---|
| **ktayl-ai-claims-assistant** | Python / LangGraph | [#200](https://github.com/andrelair-platform/platform-backlog/issues/200) | AI triage, fraud scoring, human-in-loop via NATS events |
| **ERPNext CRM config** | Frappe | [#53](https://github.com/andrelair-platform/platform-backlog/issues/53) | Prospect pipeline, devis lifecycle, renewal management, broker commissions |
| **ERPNext billing** | Frappe | [#54](https://github.com/andrelair-platform/platform-backlog/issues/54) | Premium invoicing, payment tracking, claims payment accounting |
| **Paperless-ngx DMS** | Docker + Longhorn | [#76](https://github.com/andrelair-platform/platform-backlog/issues/76) | Compliant document archive — policy contracts + settled claim documents |
| **Claims indemnification SEPA** | Go / SEPA | [#211](https://github.com/andrelair-platform/platform-backlog/issues/211) | Outbound SEPA credit transfer to claimants + ERPNext entries |
| **Insurance attestation PDF** | Python | [#116](https://github.com/andrelair-platform/platform-backlog/issues/116) | Auto-generate certificates with QR verification at policy bind |

---

## Q3 2027 — Underwriting, International Programs & Distribution

The three major IS gaps closed in this phase. See dedicated pages for architecture detail.

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
| **ktayl-ip-portal** | Go / React | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | GNP equivalent — PO ↔ SO hub, IP policy sync, reserve coordination |
| **IP bordereau module** | ERPNext / Frappe | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | IP cession bordereaux → ERPNext accounting écritures |
| **SO claims feed** | Go (in ip-portal) | [#222](https://github.com/andrelair-platform/platform-backlog/issues/222) | Inbound claim notifications from Servicing Offices |
| **Premium collection lifecycle** | n8n + ERPNext | [#91](https://github.com/andrelair-platform/platform-backlog/issues/91) | UW trigger → SEPA mandate → online payment → suspension |
| **ORIAS broker verification** | Python | [#104](https://github.com/andrelair-platform/platform-backlog/issues/104) | Automated credential check before accepting broker business |
| **UW authority matrix** | Go (in uwb-api) | [#231](https://github.com/andrelair-platform/platform-backlog/issues/231) | Binding authority per LOB, enforced routing, escalation chain |
| **Actuarial pricing engine** | Python | [#101](https://github.com/andrelair-platform/platform-backlog/issues/101) | Statistical premium rating per LOB — replaces manual Excel tariff grids |

---

## Post-Certification — IS Expansion

After RNCP39583 is complete. No fixed dates — ordered by IS priority.

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
| Platform engineering | 88 |
| Research pipeline | 8 |
| **Total active backlog** | **149** |

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
| 20 | International Programs LOB (data model) | IP / GNP |
| 21 | ktayl-ip-portal (GNP equivalent) | IP / GNP |
| 22 | IP bordereau module (ERPNext) | IP / GNP |
| 23 | SO claims feed | IP / GNP |
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
| 52 | GLPI | IAM / IT Ops |
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
| IP / GNP | 4 |
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

| IS Domain | Component | Status |
|---|---|---|
| Claims & policy lifecycle | ktayl-claims-service + ktayl-policy-service | 🔨 Q1 2027 |
| Policyholder / broker portal | ktayl-portal | 🔨 Q1 2027 |
| AI claims assistant | ktayl-ai-claims-assistant | 🔨 Q2 2027 |
| Underwriting (UWWB) | ktayl-uwb-api + ktayl-uwb-ui + UW AI agents | 📋 Q3 2027 |
| International Programs (GNP) | ktayl-ip-portal + IP bordereau module | 📋 Q3 2027 |
| Document management (DMS) | Paperless-ngx | 🔨 Q2 2027 |
| CRM & partner management | ERPNext CRM | 🔨 Q2 2027 |
| Reinsurance | Reinsurance management + bordereau portal | 📋 Post-cert |
| Actuarial | Reserving tool + pricing engine | 📋 Post-cert |
| Compliance (ACPR/COREP) | Spring Batch in claims-service | 🔨 Q1 2027 |
| Regulatory (AML/KYC, GDPR) | Python + n8n workflows | 📋 Post-cert |
| Data platform & BI | ClickHouse + Metabase + dbt | 📋 Post-cert |
| IAM & governance | Authentik (✅) + MidPoint IGA | ✅ / Post-cert |
| ERP & finance | ERPNext PCG 2025 + TSCA | ✅ Live |
| AI platform | LiteLLM + vLLM + agents + RAG | ✅ Live |
| Communication | Stalwart + Matrix + Jitsi | ✅ Live |
| e-Signature | Docuseal | ✅ Live |
