---
title: Platform Engineering Backlog
sidebar_label: Platform Engineering Backlog
---

# Platform Engineering Backlog

All platform-layer items not yet scheduled — distinct from the [Insurance IS catalog](../insurance-platform/business-applications-catalog) which covers business domain applications.

Full issue tracker: [andrelair-platform/platform-backlog](https://github.com/andrelair-platform/platform-backlog)

**90 items across 7 domains.** No hallucination — every row below links to a real open GitHub issue.

---

## 1. AI Platform Hardening (25 items)

Hardening, governance and developer tooling on top of the live AI stack (LiteLLM + vLLM + Langfuse + RAG + agents).

| Item | Issue | Description |
|---|---|---|
| **LiteLLM enterprise hardening** | [#37](https://github.com/andrelair-platform/platform-backlog/issues/37) | Redis cache, HA multi-replica, PII masking, Prometheus metrics |
| **RAG Evaluation — Ragas** | [#39](https://github.com/andrelair-platform/platform-backlog/issues/39) | Faithfulness + answer relevance scoring per collection via Langfuse |
| **Prompt Management** | [#40](https://github.com/andrelair-platform/platform-backlog/issues/40) | Langfuse prompt registry, version-linked Ragas scores, A/B routing |
| **AI data sovereignty** | [#42](https://github.com/andrelair-platform/platform-backlog/issues/42) | Provider blocklist, department allowlist, data residency enforcement |
| **AI Evaluation Framework** | [#43](https://github.com/andrelair-platform/platform-backlog/issues/43) | Human feedback loop, LLM-as-judge, quality alerting, dataset versioning |
| **Hallucination prevention** | [#44](https://github.com/andrelair-platform/platform-backlog/issues/44) | Retrieval gate, citation controls, confidence thresholding |
| **Bias detection** | [#45](https://github.com/andrelair-platform/platform-backlog/issues/45) | Counterfactual CI gate, EU AI Act neutrality checks |
| **Prompt injection defence** | [#46](https://github.com/andrelair-platform/platform-backlog/issues/46) | Input sanitisation hook, RAG chunk scanning, PromptGuard |
| **Data poisoning defence** | [#47](https://github.com/andrelair-platform/platform-backlog/issues/47) | Chunk provenance tracking, collection access control, integrity scoring |
| **Model inversion defence** | [#48](https://github.com/andrelair-platform/platform-backlog/issues/48) | Enumeration detection, response filtering, extraction rate limits |
| **Membership inference defence** | [#49](https://github.com/andrelair-platform/platform-backlog/issues/49) | Identifier stripping, neutral error messages, GDPR access logging |
| **EU AI Act compliance audit** | [#85](https://github.com/andrelair-platform/platform-backlog/issues/85) | Transparency report for AI Gateway — high-risk classification |
| **Enterprise AI Platform EPIC** | [#89](https://github.com/andrelair-platform/platform-backlog/issues/89) | Capability-first architecture across 13 AI domains |
| **AI anti-fraud detection** | [#100](https://github.com/andrelair-platform/platform-backlog/issues/100) | Risk scoring on claim intake + investigation workflow trigger |
| **AI Governance dashboard** | [#120](https://github.com/andrelair-platform/platform-backlog/issues/120) | Cost-per-query, model usage, ROI metrics via Langfuse + Grafana |
| **RAG document governance** | [#122](https://github.com/andrelair-platform/platform-backlog/issues/122) | Metadata tagging, versioning, expiry enforcement in Qdrant |
| **AI Governance Framework** | [#156](https://github.com/andrelair-platform/platform-backlog/issues/156) | Policy, risk classification matrix, model card registry |
| **EU AI Act conformity assessments** | [#157](https://github.com/andrelair-platform/platform-backlog/issues/157) | All high-risk systems + post-market monitoring |
| **AI training & awareness** | [#158](https://github.com/andrelair-platform/platform-backlog/issues/158) | EU AI Act literacy, developer ethics, mandatory org training |
| **Innovation lab** | [#160](https://github.com/andrelair-platform/platform-backlog/issues/160) | Quarterly hackathons, tech radar activation, AI workshop program |
| **MCP Enterprise Tool Layer** | [#187](https://github.com/andrelair-platform/platform-backlog/issues/187) | One MCP interface for ERPNext, GLPI, Plane, matrix — all enterprise systems |
| **AI Skills Catalog** | [#188](https://github.com/andrelair-platform/platform-backlog/issues/188) | Reusable AI skills registry in Backstage, composable by any agent |
| **AI Agent Golden Path** | [#189](https://github.com/andrelair-platform/platform-backlog/issues/189) | Backstage scaffolder template for LangGraph agents with CI + gitops |
| **Unified AI Platform Andon Dashboard** | [#191](https://github.com/andrelair-platform/platform-backlog/issues/191) | LiteLLM + vLLM + Langfuse + RAG in one operator view |
| **vLLM upgrade v0.6.6 → v0.8+** | [#194](https://github.com/andrelair-platform/platform-backlog/issues/194) | Fix CPU backend sliding_window crash, add structured output support |

---

## 2. DevSecOps (12 items)

Shift-left security tooling integrated into the CI pipeline and cluster runtime.

| Item | Issue | Description |
|---|---|---|
| **Harbor Trivy + Kyverno** | [#27](https://github.com/andrelair-platform/platform-backlog/issues/27) | CI-side image scanning + admission control policy enforcement |
| **Trivy host scanning** | [#95](https://github.com/andrelair-platform/platform-backlog/issues/95) | Host vulnerability scanner + Trivy Operator CRDs in cluster |
| **SonarQube** | [#109](https://github.com/andrelair-platform/platform-backlog/issues/109) | Static analysis, security hotspots, code quality gates in CI |
| **WAF — Coraza/ModSecurity** | [#117](https://github.com/andrelair-platform/platform-backlog/issues/117) | Application-layer WAF on NGINX ingress (OWASP CRS ruleset) |
| **Wazuh SIEM** | [#174](https://github.com/andrelair-platform/platform-backlog/issues/174) | Threat detection, log correlation, DORA incident classification |
| **OWASP ZAP DAST** | [#175](https://github.com/andrelair-platform/platform-backlog/issues/175) | Dynamic application security testing in CI against staging |
| **GitLeaks** | [#176](https://github.com/andrelair-platform/platform-backlog/issues/176) | Secrets scanning pre-commit + CI across all repos |
| **Falco runtime** | [#177](https://github.com/andrelair-platform/platform-backlog/issues/177) | Container threat detection and behavioural anomaly alerts |
| **Renovate bot** | [#178](https://github.com/andrelair-platform/platform-backlog/issues/178) | Automated dependency update PRs across all repos |
| **DefectDojo** | [#179](https://github.com/andrelair-platform/platform-backlog/issues/179) | Centralised vulnerability management, deduplication, SLA tracking |
| **DevSecOps Grafana dashboard** | [#180](https://github.com/andrelair-platform/platform-backlog/issues/180) | CVE counts, compliance score, pipeline security metrics |
| **GOV-3 compliance automation gate** | [#181](https://github.com/andrelair-platform/platform-backlog/issues/181) | DORA/VAIT checklist as CI enforcement — blocks merge if gate fails |

---

## 3. SRE & Platform Operations (9 items)

Reliability engineering, compliance operations and incident management.

| Item | Issue | Description |
|---|---|---|
| **SLO management — Sloth** | [#96](https://github.com/andrelair-platform/platform-backlog/issues/96) | Error budget dashboards + burn rate alerts for all services |
| **Synthetic monitoring — Uptime Kuma** | [#97](https://github.com/andrelair-platform/platform-backlog/issues/97) | External probing of all devandre.sbs endpoints + public status page |
| **Scheduled DR GameDay** | [#99](https://github.com/andrelair-platform/platform-backlog/issues/99) | Quarterly disaster recovery test with documented RTO/RPO evidence |
| **Incident management pipeline** | [#145](https://github.com/andrelair-platform/platform-backlog/issues/145) | Alertmanager → auto-ticket (GLPI) → on-call → post-mortem |
| **ISO 27001:2022 gap assessment** | [#154](https://github.com/andrelair-platform/platform-backlog/issues/154) | Controls gap analysis + minicloud coverage mapping |
| **GLPI → Grafana KPI bridge** | [#155](https://github.com/andrelair-platform/platform-backlog/issues/155) | SLA compliance dashboard: MTTR, MTBF, SLA breach rate |
| **CISO Assistant — GRC platform** | [#193](https://github.com/andrelair-platform/platform-backlog/issues/193) | IT audit lifecycle, risk register, DORA/VAIT evidence collection |
| **PIA / AIPD** | [#213](https://github.com/andrelair-platform/platform-backlog/issues/213) | Privacy Impact Assessment process for AI systems and high-risk data processing |
| **Business Continuity Plan (PCA)** | [#216](https://github.com/andrelair-platform/platform-backlog/issues/216) | ACPR-mandated BCP documentation, annual test, RTO/RPO commitments |

---

## 4. FinOps (5 items)

Cost visibility and optimisation across the multi-cloud estate.

| Item | Issue | Description |
|---|---|---|
| **OpenCost** | [#169](https://github.com/andrelair-platform/platform-backlog/issues/169) | Kubernetes cost allocation per namespace / pod / team |
| **Multi-cloud cost aggregation** | [#170](https://github.com/andrelair-platform/platform-backlog/issues/170) | AWS + Azure + GCP costs → single Grafana view |
| **Infracost** | [#171](https://github.com/andrelair-platform/platform-backlog/issues/171) | Cloud cost estimation on every OpenTofu PR before apply |
| **Resource tagging enforcement** | [#172](https://github.com/andrelair-platform/platform-backlog/issues/172) | Gatekeeper + OpenTofu tagging module — no tag = no deploy |
| **FinOps dashboard + monthly report** | [#173](https://github.com/andrelair-platform/platform-backlog/issues/173) | Grafana cost dashboard + n8n automated monthly PDF report |

---

## 5. Platform / IaC / Backstage / DevEx (19 items)

Platform engineering improvements: infrastructure automation, developer portal, identity hardening, developer experience tooling.

| Item | Issue | Description |
|---|---|---|
| **MAAS SSO via Authentik** | [#6](https://github.com/andrelair-platform/platform-backlog/issues/6) | Authentik Proxy Outpost protecting the MAAS UI |
| **Backstage Grafana plugin** | [#7](https://github.com/andrelair-platform/platform-backlog/issues/7) | Service-level dashboards embedded in Backstage catalog pages |
| **HA Authentik** | [#28](https://github.com/andrelair-platform/platform-backlog/issues/28) | Multi-replica Authentik server + Redis Sentinel for SSO HA |
| **Authentik FIDO2 / Passwordless** | [#29](https://github.com/andrelair-platform/platform-backlog/issues/29) | WebAuthn + Conditional Access + SCIM provisioning |
| **Backstage GitHub Actions plugin** | [#25](https://github.com/andrelair-platform/platform-backlog/issues/25) | CI pipeline status embedded in Backstage service pages |
| **Backstage Notifications + Search** | [#26](https://github.com/andrelair-platform/platform-backlog/issues/26) | Cross-catalog search + notification backend |
| **Backstage ERPNext catalog entry** | [#55](https://github.com/andrelair-platform/platform-backlog/issues/55) | ERPNext as a Backstage Component with API, owner, dependencies |
| **IT self-service onboarding** | [#86](https://github.com/andrelair-platform/platform-backlog/issues/86) | Backstage scaffolder template for new employee provisioning |
| **Backstage full IS catalog** | [#87](https://github.com/andrelair-platform/platform-backlog/issues/87) | All ktayl-solution apps + owners registered as catalog entities |
| **Developer portal golden path** | [#88](https://github.com/andrelair-platform/platform-backlog/issues/88) | One-click deploy template for a new insurance microservice |
| **Flagsmith feature flags** | [#110](https://github.com/andrelair-platform/platform-backlog/issues/110) | OpenFeature-compatible feature flags for progressive rollout |
| **Technology radar** | [#111](https://github.com/andrelair-platform/platform-backlog/issues/111) | Backstage tech radar plugin (Adopt/Trial/Assess/Hold) |
| **Architecture Decision Records** | [#112](https://github.com/andrelair-platform/platform-backlog/issues/112) | ADR process: template + Backstage TechDocs integration |
| **API documentation portal** | [#118](https://github.com/andrelair-platform/platform-backlog/issues/118) | OpenAPI catalog for all internal microservices, versioned |
| **Terragrunt refactor** | [#130](https://github.com/andrelair-platform/platform-backlog/issues/130) | DRY modules + remote state on MinIO for minicloud-opentofu |
| **Atlantis** | [#131](https://github.com/andrelair-platform/platform-backlog/issues/131) | GitOps-driven OpenTofu: plan on PR, apply on merge |
| **Terratest suite** | [#132](https://github.com/andrelair-platform/platform-backlog/issues/132) | Real deploy + verify + teardown tests for opentofu modules |
| **GOV-3 Definition of Done** | [#149](https://github.com/andrelair-platform/platform-backlog/issues/149) | System modernisation + quality & compliance gate — all new services |
| **Vault PKI engine** | [#192](https://github.com/andrelair-platform/platform-backlog/issues/192) | Intermediate CA, cert-manager VaultIssuer, CRL/OCSP, cert rotation |

---

## 6. Data Engineering Extended (6 items)

Components that extend the live Global Data Platform (ClickHouse + dbt + Metabase) to full analytical capability.

| Item | Issue | Description |
|---|---|---|
| **Apache Airflow** | [#153](https://github.com/andrelair-platform/platform-backlog/issues/153) | Data pipeline orchestration: dbt DAGs, bronze ingestion schedules |
| **dbt Core (GDP-4)** | [#182](https://github.com/andrelair-platform/platform-backlog/issues/182) | Version-controlled SQL transformation layer for ClickHouse mart |
| **Debezium CDC (GDP-5)** | [#183](https://github.com/andrelair-platform/platform-backlog/issues/183) | PostgreSQL → NATS JetStream → ClickHouse real-time ingestion |
| **OpenMetadata (GDP-6)** | [#184](https://github.com/andrelair-platform/platform-backlog/issues/184) | Data catalog, lineage graph, quality scoring, business glossary |
| **Data quality framework (GDP-7)** | [#185](https://github.com/andrelair-platform/platform-backlog/issues/185) | dbt tests + Great Expectations + freshness SLA monitoring |
| **Data platform enablement (GDP-8)** | [#186](https://github.com/andrelair-platform/platform-backlog/issues/186) | Scaffolder template, access model, data mesh governance guide |

---

## 7. HR, Intranet & Internal Tools (14 items)

Workforce systems and internal productivity tools that make the simulated company operationally complete.

| Item | Issue | Description |
|---|---|---|
| **HumHub intranet** | [#10](https://github.com/andrelair-platform/platform-backlog/issues/10) | Corporate intranet: org chart, staff directory, news, social feed |
| **Outline wiki** | [#11](https://github.com/andrelair-platform/platform-backlog/issues/11) | Knowledge base: policies, handbooks, runbooks — Authentik SSO |
| **Automated employee provisioning** | [#74](https://github.com/andrelair-platform/platform-backlog/issues/74) | New hire → Authentik + Nextcloud + Matrix + Stalwart auto-provisioning |
| **ERPNext full HR l10n_fr** | [#90](https://github.com/andrelair-platform/platform-backlog/issues/90) | French payroll (DPAE, DSN, BTP, cotisations), leave management |
| **Excalidraw whiteboard** | [#106](https://github.com/andrelair-platform/platform-backlog/issues/106) | Self-hosted collaborative whiteboard for workshops and architecture |
| **IT AI helpdesk chatbot** | [#107](https://github.com/andrelair-platform/platform-backlog/issues/107) | Dify agent answering from Outline + Backstage + GLPI knowledge base |
| **MeiliSearch unified search** | [#161](https://github.com/andrelair-platform/platform-backlog/issues/161) | Cross-system search: Outline + HumHub + Nextcloud + Backstage |
| **Compensation & Variable Pay** | [#162](https://github.com/andrelair-platform/platform-backlog/issues/162) | Salary bands, merit cycles, variable pay engine in ERPNext |
| **Performance & Goals (PMGM)** | [#163](https://github.com/andrelair-platform/platform-backlog/issues/163) | Goal cascading, AI performance summary, calibration workflow |
| **Succession & Development** | [#164](https://github.com/andrelair-platform/platform-backlog/issues/164) | Talent pools, succession plans, individual development plans |
| **Recruiting / ATS** | [#165](https://github.com/andrelair-platform/platform-backlog/issues/165) | Job requisitions, candidate pipeline, AI screening, offer management |
| **Azure Entra External Identities** | [#167](https://github.com/andrelair-platform/platform-backlog/issues/167) | B2C customer portal SSO — external policyholders and brokers |

---

## Domain Weight

| Domain | Items |
|---|---|
| AI Platform hardening | 25 |
| Platform / IaC / Backstage / DevEx | 19 |
| DevSecOps | 12 |
| HR + Intranet + Internal tools | 12 |
| SRE & Platform Ops | 9 |
| Data Engineering extended | 6 |
| FinOps | 5 |
| **Total** | **88** |

---

## Full Backlog — Combined View

| Scope | Items |
|---|---|
| Insurance IS domain ([catalog](../insurance-platform/business-applications-catalog)) | 53 |
| Platform engineering (this page) | 88 |
| Research pipeline (no committed date) | 8 |
| **Total active backlog** | **149** |
