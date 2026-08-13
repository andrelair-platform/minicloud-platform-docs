---
id: project-governance-standard
title: Project Governance Standard
sidebar_label: Governance Standard
---

# Project Governance Standard

Every project delivered on the minicloud / ktayl-solution platform follows this standard — from the first business idea through production operations and maintenance. The standard defines the roles involved, the phases of delivery, and a RACI matrix that must be produced for each project.

:::tip Why document this for a solo portfolio project?
A senior engineer or architect must demonstrate awareness of the full delivery lifecycle. Documenting roles and accountabilities shows evaluators (RNCP, clients, hiring managers) that you understand not just the code, but the organisational context in which software is built and operated.
:::

---

## 1. The 15 Delivery Roles

Every project engages some subset of these roles. In a startup or solo context, one person may wear several hats simultaneously — but the roles themselves remain distinct.

| Code | Role | Core responsibility |
|------|------|---------------------|
| **STK** | Stakeholder / Client | Owns the business problem and budget. Defines success criteria. Final sign-off authority. |
| **PM** | Product Manager | Translates business objectives into a product roadmap. Owns prioritisation and scope decisions. |
| **BA** | Business Analyst | Elicits and formalises requirements. Produces functional specifications. Bridges business and technical teams. |
| **UX** | UX Designer | Maps user journeys, navigation, and interaction patterns. Produces wireframes and prototypes. |
| **UI** | UI Designer | Defines the visual layer: colours, typography, components. Produces high-fidelity mockups. |
| **SA** | Solution Architect | Defines the technical architecture: services, databases, integrations, cloud/on-prem split. Selects technologies. |
| **TL** | Tech Lead | Leads implementation decisions. Conducts code reviews. Unblocks developers. Owns technical quality. |
| **FE** | Frontend Developer | Implements the user interface. Owns browser/mobile layer. |
| **BE** | Backend Developer | Implements server-side logic, APIs, and business rules. Owns data access and integrations. |
| **DBA** | Database Engineer | Designs schemas, migrations, indexing strategy, backup, and replication. |
| **DO** | DevOps / Platform Engineer | Builds and maintains CI/CD, container orchestration, infrastructure-as-code, and deployment automation. |
| **QA** | QA Engineer | Designs and executes test plans. Owns regression, integration, and E2E test suites. |
| **SEC** | Security Engineer | Reviews authentication, authorisation, vulnerabilities, secrets, supply chain, and compliance. |
| **SRE** | Site Reliability Engineer | Owns production observability, alerting, incident response, SLOs, and on-call. |
| **SUP** | Support / Helpdesk | Handles user-reported issues. Escalates bugs to developers. Owns the support SLA. |

### Role mapping in a solo / startup context

| Enterprise role | Minicloud equivalent |
|---|---|
| STK, PM, BA | Project owner wearing the business hat |
| UX, UI | Project owner designing the product |
| SA, TL | Project owner in the architecture phase |
| FE, BE, DBA | Project owner in the development phase |
| DO | Project owner operating the platform |
| QA | Project owner running the test suite |
| SEC | Project owner doing the security review |
| SRE | Project owner monitoring production |
| SUP | Project owner handling user feedback |

---

## 2. The 6 Delivery Phases

| # | Phase | Key deliverables |
|---|-------|-----------------|
| **P1** | Initiation & Requirements | Business case, functional specifications, CdCF |
| **P2** | Architecture & Design | Technical architecture, UX wireframes, UI mockups, data model |
| **P3** | Development | Frontend, backend, database schema, integrations, AI components |
| **P4** | Infrastructure & CI/CD | Docker images, Helm charts / Kustomize manifests, ArgoCD app, CI pipelines |
| **P5** | Testing & Security | Unit/integration/E2E tests, SAST, AppSec review, UAT |
| **P6** | Release & Operations | Production deployment, monitoring setup, runbooks, support handover |

---

## 3. RACI Matrix Template

Use this template for every new project. Copy the table and fill it in according to which roles are engaged at each activity.

**Legend:** R = Responsible · A = Accountable · C = Consulted · I = Informed · — = not involved

| Activity | STK | PM | BA | UX/UI | SA | TL | FE | BE | DBA | DO | QA | SEC | SRE | SUP |
|----------|-----|----|----|-------|----|----|----|----|-----|----|----|-----|-----|-----|
| **P1 — Initiation & Requirements** | | | | | | | | | | | | | | |
| Define business objectives & scope | A | R | C | — | C | I | — | — | — | — | — | I | — | — |
| Approve budget & project charter | R+A | C | I | — | I | — | — | — | — | — | — | — | — | — |
| Elicit functional requirements | C | A | R | C | C | C | — | — | — | — | C | C | — | — |
| Define non-functional requirements | C | A | R | — | C | C | — | — | — | C | C | C | C | — |
| Produce CdCF / functional spec | C | A | R | C | C | C | — | — | — | — | — | C | — | — |
| **P2 — Architecture & Design** | | | | | | | | | | | | | | |
| Define technical architecture | I | C | C | — | R+A | C | C | C | C | C | — | C | C | — |
| Design UX wireframes & user journeys | C | C | C | R+A | — | C | C | — | — | — | — | — | — | — |
| Design UI mockups | I | C | I | R+A | — | C | C | — | — | — | — | — | — | — |
| Design database schema | I | I | C | — | C | A | — | C | R | — | — | C | — | — |
| **P3 — Development** | | | | | | | | | | | | | | |
| Implement frontend | I | I | C | C | C | A | R | C | — | — | — | — | — | — |
| Implement backend APIs | I | I | C | — | C | A | — | R | C | — | — | — | — | — |
| Implement AI / ML components | I | I | C | — | C | A | — | R | — | — | — | C | — | — |
| Database migrations | I | I | C | — | C | A | — | C | R | — | — | — | — | — |
| Third-party integrations | I | C | C | — | C | A | C | R | C | — | — | C | — | — |
| **P4 — Infrastructure & CI/CD** | | | | | | | | | | | | | | |
| Set up CI/CD pipelines | I | I | — | — | C | A | — | — | — | R | — | C | — | — |
| Write Helm charts / Kustomize manifests | I | I | — | — | C | C | — | — | — | R+A | — | C | C | — |
| Configure ArgoCD application | I | I | — | — | C | C | — | — | — | R+A | — | — | C | — |
| Network policies & RBAC | I | I | — | — | C | C | — | — | — | R | — | A | C | — |
| **P5 — Testing & Security** | | | | | | | | | | | | | | |
| Write unit & integration tests | I | I | C | — | — | A | C | R | C | — | C | — | — | — |
| Write E2E tests (Playwright / httpx) | I | C | C | C | — | A | R | C | — | — | R | — | — | — |
| SAST / dependency scan | I | C | — | — | C | C | — | — | — | C | C | R+A | — | — |
| AppSec / penetration test | I | C | — | — | C | C | — | — | — | C | C | R+A | — | — |
| User Acceptance Testing (UAT) | C | A | R | C | — | C | C | C | — | C | R | C | — | — |
| **P6 — Release & Operations** | | | | | | | | | | | | | | |
| Approve production release | R+A | C | — | — | C | C | — | — | — | C | C | C | C | — |
| Deploy to production | I | I | — | — | C | C | — | — | — | R+A | — | C | C | — |
| Set up monitoring & alerting | I | I | — | — | C | C | — | — | — | R | — | — | A | — |
| Write runbooks & documentation | I | C | C | C | C | A | R | R | C | C | R | C | C | — |
| Support handover | I | C | C | — | — | C | C | C | — | — | — | — | C | R+A |
| Incident response | I | I | — | — | — | C | C | C | — | C | — | C | R+A | C |

---

## 4. How to Use This Standard for Each Project

Every project document must include:

1. **Project card** — name, GitHub issue(s), phase(s), target delivery date
2. **Role mapping** — which enterprise roles are active, and who fills them in the team context
3. **RACI matrix** — instantiated from the template above, trimmed to the active roles and phases
4. **Out-of-scope roles** — explicitly stated (e.g. "No dedicated BA — requirements captured directly by PM+SA")

### Document section template

```markdown
## Project Governance

### Active Roles

| Role | Person / Team | Notes |
|------|--------------|-------|
| STK  | [Name]       | |
| PM   | [Name]       | |
| SA   | [Name]       | |
| TL   | [Name]       | |
| BE   | [Name]       | |
| DO   | [Name]       | |
| QA   | [Name]       | |
| SEC  | [Name]       | |
| SRE  | [Name]       | |

### RACI Matrix

[trimmed version of the template above, rows matching this project's activities]
```

---

## 5. Applied Examples

| Project | Document | RACI status |
|---------|----------|-------------|
| ktayl Claims & Policy Platform | [CdCF — Certification RNCP39583](../certification/cahier-des-charges-fonctionnel) | ✅ Included |

---

## 6. Rationale

**Why RACI and not just a task list?**

A task list tells you *what* gets done. A RACI tells you *who decides* and *who is accountable when it goes wrong*. In a regulated industry (insurance, banking, healthcare), every deliverable must have an identifiable accountable owner — the ACPR, DORA, and ISO 27001 frameworks all require this traceability.

**Why 15 roles and not 5?**

Collapsing "architect + developer + DevOps + security" into "engineer" hides the fact that these are distinct disciplines with different incentives. A developer optimises for feature velocity; a security engineer optimises for attack surface reduction; a DevOps engineer optimises for deployment reliability. The tension between those goals is productive, and the RACI makes it explicit who resolves that tension (the A column).
