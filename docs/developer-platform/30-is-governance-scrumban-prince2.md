---
id: is-governance-scrumban-prince2
title: IS Governance — Scrumban + PRINCE2 Stage-Gates
sidebar_position: 30
---

# IS Governance — Scrumban + PRINCE2 Stage-Gates

## DSI Recommendation

No single project management framework fits ktayl perfectly. The right model is **Scrumban as the operating model** for the DSI delivery team, with **PRINCE2 stage-gate principles** applied to regulatory and compliance streams only.

This document explains the reasoning, the two-layer model, the tool split between GitHub Projects and Plane, and how the framework maps to the RNCP39583 certification requirements.

---

## Why Not the Other Frameworks

| Framework | Why it does not fit ktayl |
|---|---|
| **Pure Scrum** | The platform operations stream (minicloud, security patches, monitoring) is continuous — it cannot wait for sprint boundaries. Emergency patches and ACPR deadlines do not respect sprint cycles. |
| **Pure Kanban** | No sprint commitment means no delivery accountability. CAC40 clients and ACPR expect predictable delivery dates, not "we will get to it when capacity frees up." |
| **Waterfall** | Insurance IS requirements evolve constantly — regulatory changes, new LOBs, AI capabilities. Scope cannot be frozen for 12 months. |
| **SAFe** | Designed for 50+ teams running in parallel. ktayl DSI is a small team. SAFe adds more ceremony than value — PI planning, ARTs, Solution Trains are pure overhead at this scale. |
| **Lean Six Sigma** | Useful for process optimisation (claims handling cycle time, UW turnaround) but not an IS delivery framework. Apply it inside operational processes, not as the IS delivery model. |
| **PRINCE2 alone** | Too rigid for software development. But its stage-gate and business justification principles are exactly what ACPR and DORA expect for IT project governance. |

---

## The Two-Layer Model

### Layer 1 — Scrumban for IS Delivery

Two parallel tracks run simultaneously on the same GitHub Projects board.

```
Sprint track:  [Sprint N: claims-service] → [Sprint N+1: policy-service] → ...
                2 weeks                       2 weeks

Kanban track:  [security patch] → [ACPR update] → [infra alert] → (continuous)
               no sprint boundary — picked from board as capacity frees
```

#### Sprint Track (planned IS features)

- **Cadence:** 2-week sprints (Sprint 2–39, covering July 2026 → December 2027)
- **Scope:** All planned IS components — claims-service, policy-service, portal, LOB modules, AI features, data platform
- **Sprint planning:** Every second Monday — Product Owner (DSI) selects issues from backlog into "This Sprint"
- **Sprint review:** Every second Friday — business stakeholders (UW, Claims, Finance leads) validate delivered features
- **WIP limit:** Maximum 2 sprint issues per engineer in "In Progress" simultaneously
- **Product Owner:** DSI — prioritises backlog against business value, regulatory deadlines, and IS maturity goals

#### Kanban Track (continuous operations)

- **Scope:** Platform incidents, security patches (Renovate/GitLeaks alerts), ACPR circular responses, monitoring alerts, infrastructure changes
- **WIP limit:** Maximum 3 items in progress across the whole team at any time
- **Flow:** Issues tagged `Track = Kanban` enter the board and are picked immediately when capacity exists — no sprint assignment required
- **SLA:** P1 — Critical items must enter In Progress within 4 hours; P2 — High within 24 hours

#### Why Scrumban Specifically Fits Insurance

| Insurance reality | Scrumban response |
|---|---|
| ACPR issues a circular requiring IS change within 60 days | Kanban track absorbs it without disrupting sprint commitments |
| CAC40 client requests a new feature mid-sprint | Product Owner adds to backlog; scheduled in next sprint — not mid-sprint |
| Platform incident at 3am | Kanban track handles it — no sprint boundary, P1 SLA applies |
| Quarterly milestone review with DG | Sprint reviews accumulate → stage gate = formal presentation to Direction |
| RNCP39583 certification deliverables | Each stage gate produces documented evidence (BC01–BC04) |
| New ACPR/FFA regulation published | Tagged `Track = Regulatory`, enters board immediately, SLA tracked |

---

### Layer 2 — PRINCE2 Stage-Gates for Compliance and Governance

The five backlog milestones are PRINCE2 stages in disguise. Each milestone end is a formal stage gate where the DSI presents business justification, delivery evidence, and ACPR/DORA governance artefacts to the Direction.

| PRINCE2 stage | ktayl milestone | Gate criteria |
|---|---|---|
| Stage 1 | **Q3 2026 — Legal deadlines** | Factur-X (Factur-X + PDP mandatory Sept 2026) live, RNCP39583 documentation submitted to certification body |
| Stage 2 | **Q4 2026 — Core IS foundations** | GLPI ITSM live, SonarQube quality gates green across all repos, BCP documented and tested, AI governance framework published |
| Stage 3 | **Q1 2027 — Insurance capabilities** | claims-service, policy-service, and ktayl-portal in production; UW guidelines, authority matrix, and committee workflow operational; ACPR regulatory pipeline running |
| Stage 4 | **Q2 2027 — AI and Data platform** | AI fraud engine live, data platform (ClickHouse + dbt + Metabase) operational, MidPoint IGA provisioning employees, all compliance AI Act assessments complete |
| Stage 5 | **H2 2027 — Advanced and deferred** | LOB modules (Marine, Construction, Financial Lines, Collaborateurs, International Programs) live; actuarial reserving tools operational; co-insurance and delegated authority modules in production |

#### Stage Gate Ceremony (at each milestone end)

1. **Business justification review** — Is the IS still delivering the expected value? Were the benefits of the previous stage realised?
2. **ACPR/DORA governance evidence** — Project documented, change management followed, tests passed, risks managed and mitigated
3. **Go / no-go decision** — Direction formally approves progression to the next stage
4. **Artefacts archived** — Stage gate report, test evidence, and signed decision stored in Paperless-ngx tagged `prince2-gate`, `stage-N`

This governance trail is exactly what the RNCP39583 jury expects for **BC01 (Cadrer)** and **BC03 (Piloter)**.

---

## Tool Split — GitHub Projects vs Plane

### GitHub Projects — DSI IS Delivery

All IS delivery work lives in GitHub. GitHub Projects is not a separate tool — it is a view on top of what already exists.

| Capability | Why it matters for DSI |
|---|---|
| Native link to PRs and commits | Every "In Progress" issue links automatically to the branch and PR implementing it |
| CI status on issues | Sprint board shows green/red CI status without leaving the board |
| Auto-close issue on PR merge | `Fixes #198` in a PR description closes the issue and moves it to Done automatically |
| No separate login for engineers | Same GitHub account — zero context switch |
| 162+ backlog issues already there | GitHub Projects activated on top of existing `platform-backlog` repo — no migration |

**Project:** `andrelair-platform/platform-backlog` → [minicloud platform roadmap](https://github.com/orgs/andrelair-platform/projects/1)

#### GitHub Projects Field Configuration

| Field | Type | Values | Purpose |
|---|---|---|---|
| **Status** | Single select | Backlog → This Sprint → In Progress → Blocked → In Review → Done | Sprint board columns |
| **Track** | Single select | Sprint / Kanban / Regulatory | Identifies which workflow the issue follows |
| **Priority** | Single select | P1 — Critical / P2 — High / P3 — Medium / P4 — Low / P5 — Deferred | Backlog triage and SLA assignment |
| **Sprint** | Iteration | Sprint 2–39 (2026-07-28 → 2027-12-28, 2-week cadence) | Sprint assignment for sprint-track issues |
| **Domain** | Single select | 15 domains (see below) | Filter by business area in roadmap view |
| **Effort** | Single select | XS (1-2h) / S (half day) / M (1-2 days) / L (1 week) / XL (2+ weeks) | Sprint capacity planning |
| **Milestone** | GitHub milestone | Q3 2026 / Q4 2026 / Q1 2027 / Q2 2027 / H2 2027 | PRINCE2 stage mapping |

#### Domain Taxonomy (15 domains)

| Domain | What it covers |
|---|---|
| Platform Infra | Kubernetes, Longhorn, ArgoCD, networking, minicloud |
| AI & ML | LiteLLM, RAG, vLLM, LangGraph, MLOps, AI governance |
| Data Platform | ClickHouse, dbt, Metabase, Airflow, data lake, lineage |
| Security | SIEM, DAST, PAM, secrets scanning, CVE management, ISO 27001 |
| HR & People | ERPNext HR, payroll, LMS, recruiting, succession, MidPoint IGA |
| Developer Experience | Backstage, scaffolder, SonarQube, API catalog, GitLeaks, Renovate |
| IaC & Tofu | OpenTofu, Terragrunt, Atlantis, multi-cloud |
| Collaboration & Comms | Stalwart mail, Nextcloud, Matrix, Jitsi, GAL, shared mailboxes |
| Regulatory & Compliance | ACPR, Solvency II, GDPR, AML/KYC, EU AI Act, FFA, IFRS 17, BCP |
| Operations / SRE | SLO, synthetic monitoring, incident management, DR, ITSM/GLPI |
| UW & Pricing | UW workbench, pricing engine, guidelines, authority matrix, risk intelligence |
| Claims & Fraud | Claims service, AI triage, fraud/SIU, expert management, payment, subrogation, litigation |
| LOB Modules | Marine, Construction, Financial Lines, Collaborateurs, International Programs, ART |
| Finance & Billing | ERPNext billing, premium collection, reinsurance, Factur-X, co-insurance |
| Distribution & CRM | CRM, broker portal, commissions, ORIAS, delegated authority, e-signature |

#### Track Assignment Rules

| Track | Assigned to | Who assigns it |
|---|---|---|
| **Regulatory** | Issues with a hard legal or ACPR deadline | Pre-assigned at issue creation |
| **Kanban** | Platform operations, security patches, monitoring, incident responses | Pre-assigned for ops issues; any engineer can flag an issue as Kanban when an unplanned need arises |
| **Sprint** | All planned IS features and improvements | Default — assigned at sprint planning |

---

### Plane — Business Department Project Management

Plane is deployed at `plane.devandre.sbs` and is the right tool for the 10 business departments. The key advantage: **Plane does not require a GitHub account**. Business users (underwriters, claims managers, finance team, compliance officers) have no reason to be in GitHub.

| Department | Example Plane project |
|---|---|
| Sinistres | Process improvement: reduce claims cycle time from 45 to 30 days |
| Souscription | Annual UW guidelines review (30-day review + approval workflow) |
| RH | New hire onboarding checklist, annual training plan tracking |
| Conformité | GDPR Art.30 register update campaign, annual ISO 27001 audit |
| Finance | Factur-X migration project managed by finance team side |
| Commercial | Broker recruitment campaign, quarterly business review preparation |
| Prévention | Site visit scheduling and prevention report tracking |
| Direction | Strategic initiative tracking, board presentation preparation |

**Rule:** If the work produces code or a GitHub PR → GitHub Projects. If not → Plane.

---

## Sprint Ceremonies

| Ceremony | When | Duration | Who |
|---|---|---|---|
| Sprint planning | Monday of sprint start | 1h | DSI + team |
| Daily stand-up | Every day | 15 min | DSI team only |
| Sprint review | Friday of sprint end | 45 min | DSI + business stakeholders |
| Sprint retrospective | Friday of sprint end (after review) | 30 min | DSI team only |
| Backlog refinement | Mid-sprint (Wednesday) | 30 min | DSI + Product Owner |
| Stage gate review | At each milestone end | 2h | DSI + Direction + ACPR evidence |

---

## Process Quality — Lean Six Sigma Thinking

Lean Six Sigma is not the IS delivery framework but its **DMAIC thinking** applies to operational processes running on the IS:

| Process | Metric to optimise | Tool |
|---|---|---|
| Claims handling cycle time | Days from FNOL to settlement | Grafana KPI dashboard (#82 INS-8) |
| UW turnaround | Hours from submission to quote | UW workbench #81 analytics |
| Premium collection default rate | % of mandates failing within 30 days | ACC-1 #91 dashboard |
| IT incident MTTR | Minutes to resolve P1 incidents | GLPI #119 + Grafana |

These metrics feed the **insurance KPI dashboard (#82)** and are reviewed at each stage gate as evidence of IS impact on business performance.

---

## RNCP39583 Alignment

| Bloc de compétences | How this framework provides evidence |
|---|---|
| **BC01 — Cadrer la transformation numérique** | Stage gate reviews = formal IS strategy presentations with business justification. GitHub Projects roadmap = visual IS trajectory against business goals. |
| **BC02 — Développer les services numériques** | Sprint reviews = iterative delivery demonstrations. CI/CD pipeline on every PR = documented quality assurance process. |
| **BC03 — Piloter la transformation numérique** | PRINCE2 stage gate artefacts = governance documentation. ACPR/DORA compliance trail = regulatory evidence. Retrospectives = continuous improvement documentation. |
| **BC04 — Maintenir en condition opérationnelle** | Kanban track = documented operational process. SLO dashboards = RTO/RPO evidence. DR GameDay results = BCP test documentation. |

Every sprint review, stage gate, and retrospective produces documentation that maps directly to one of the four blocs. The framework is not just a delivery method — it is the certification evidence engine.

---

## Summary

| Stream | Framework | Tool | Ceremonies |
|---|---|---|---|
| IS feature delivery | Scrum (2-week sprints) | GitHub Projects — Sprint track | Planning, review, retro every 2 weeks |
| Platform operations | Kanban (continuous, WIP ≤ 3) | GitHub Projects — Kanban track | Daily stand-up, P1 SLA 4h |
| Compliance/regulatory | PRINCE2 stage-gates | GitHub Projects — Milestones as stages | Formal stage gate at each milestone end |
| Business department projects | Lightweight Scrum/Kanban | Plane (no GitHub account needed) | Department-managed |
| Process quality | Lean Six Sigma (DMAIC) | Grafana KPI dashboards | Reviewed at stage gates |

> **Scrumban gives speed and adaptability. PRINCE2 gates give the governance trail that ACPR, DORA, and the RNCP39583 jury require. Neither alone is sufficient for a regulated B2B insurer.**
