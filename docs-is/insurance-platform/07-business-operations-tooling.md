---
id: business-operations-tooling
title: Business Operations Tooling — what the business teams use to run the insurer
sidebar_label: 🧰 Business Operations Tooling
---

# Business Operations Tooling

> **The tools the *insurance business* runs on day-to-day** — Production (souscription/émission),
> Claims, Billing/Finance, Servicing, Documents, Risk & Compliance. This is the **business-ops** view,
> grouped by function with each tool's **board** and **status**, so the business side has one reference.

:::note Three different "ops" — don't conflate
- **This page = business operations** — running the *insurance business* (policies, claims, billing…).
- **Platform / SRE tooling** — running the *system* (Grafana, ArgoCD, Vault, Velero…) → live, see the
  [EA Blueprint](./enterprise-architecture-blueprint) *Enterprise IT* note.
- **IT service desk** — supporting *users* (tickets, CMDB) → **ITSM/GLPI #16** (design pass done).

The cross-cutting glue that ties business-ops together (the **Operations Workbench**, workflow
orchestration, intake) is on the [IS Build Roadmap → business-operations completeness](../product-roadmap/is-build-roadmap#business-operations-completeness--the-back-office-layer).
:::

## Status legend

| Badge | Meaning |
|---|---|
| ✅ Live | deployed and operational |
| 🟢 Build-ready | design pass done (gate PASS) — implementation can start |
| 🟡 Partial | platform/primitive up, business capability not configured |
| 📋 Backlog | epic-scoped; needs its design pass before build |
| ⏸ Parked | deliberately deferred (need-first) |
| 🔬 Research | long-horizon, no committed date |

---

## A. Production / Policy operations
*souscription → émission → gestion de contrat*

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Underwriting workbench** | risk assessment, referral, quote, bind | [#12](https://github.com/orgs/andrelair-platform/projects/12) | 🟢 Build-ready |
| **Rating / pricing engine** | premium calculation per LOB | [#12](https://github.com/orgs/andrelair-platform/projects/12) | 🟢 Build-ready |
| **Policy Administration (PAS)** | issuance, endorsements, renewals, cancellations | [#6](https://github.com/orgs/andrelair-platform/projects/6) | ✅ **Live** ([Policy Service](./ktayl-policy-service)) |
| **Product factory** | define LOB products, coverages, tariff grids | [#12](https://github.com/orgs/andrelair-platform/projects/12) | 📋 Backlog |
| **Broker portal + CRM** | submissions intake, pipeline, commissions | [#13](https://github.com/orgs/andrelair-platform/projects/13) | 🟡 ERPNext CRM platform only |
| **Document generation** | contracts, avenants, attestations (+QR verify) | [#24](https://github.com/orgs/andrelair-platform/projects/24) | 🟡 DMS live, generation backlog |

## B. Claims operations
*sinistres*

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Claims management** | FNOL → triage → reserve → settle → close (delivered via the **GlobalCore** legacy wrap) | [#11](https://github.com/orgs/andrelair-platform/projects/11) | 🟢 Build-ready ([Legacy-Core Modernization](./legacy-core-modernization)) |
| **Loss adjuster / expert mgmt** | assign & track experts | [#11](https://github.com/orgs/andrelair-platform/projects/11) | 📋 Backlog |
| **Subrogation / recours** | recover from third parties | [#11](https://github.com/orgs/andrelair-platform/projects/11) | 📋 Backlog |
| **Fraud / SIU** | fraud detection + investigation | [#11](https://github.com/orgs/andrelair-platform/projects/11) | 📋 Backlog |
| **Litigation / contentieux** | legal case management | [#11](https://github.com/orgs/andrelair-platform/projects/11) | 📋 Backlog |
| **Indemnity payment (SEPA)** | pay claimants + accounting entries | [#11](https://github.com/orgs/andrelair-platform/projects/11) | 📋 Backlog |

## C. Billing & finance operations
*encaissement, comptabilité*

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Premium billing + échéancier** | invoicing, instalments | [#14](https://github.com/orgs/andrelair-platform/projects/14) | 🟡 ERPNext up, insurance config pending |
| **Collections / dunning** (recouvrement) | reminders, suspension | [#14](https://github.com/orgs/andrelair-platform/projects/14) | 📋 Backlog |
| **Insurance accounting** | PCG 2025, TSCA, Factur-X | [#8](https://github.com/orgs/andrelair-platform/projects/8) | ✅ Live · IFRS 17 🔬 |
| **Commissions management** | broker commissions | [#13](https://github.com/orgs/andrelair-platform/projects/13) | 📋 Backlog |
| **Reinsurance accounting / bordereaux** | cessions, recoveries | [#22](https://github.com/orgs/andrelair-platform/projects/22) | 📋 Backlog |

## D. Customer & servicing operations

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Servicing / self-service portal** | policyholder & broker self-service | [#13](https://github.com/orgs/andrelair-platform/projects/13) | 📋 Backlog |
| **Contact center / omnichannel intake** | phone/email/chat → task/ticket | [#10](https://github.com/orgs/andrelair-platform/projects/10) | 🟡 mail live · Asterisk + SMS backlog |
| **Operations Workbench (task-inbox)** | AI-native cross-domain cockpit for **exceptions** — one prioritised inbox, not per-app CRUD | — | 📋 **named, not built** (the main missing glue) |
| **Notifications** | email / SMS status alerts | [#10](https://github.com/orgs/andrelair-platform/projects/10) | 🟡 mail live, SMS backlog |

## E. Document & content operations

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Enterprise Document Platform / DMS** | store, archive, retention | [#24](https://github.com/orgs/andrelair-platform/projects/24) | 🟡 Nextcloud/OnlyOffice live; Paperless-ngx backlog |
| **Document-AI / IDP** | extract fields from submission packs | [#24](https://github.com/orgs/andrelair-platform/projects/24) | 🟡 RAG pipeline live substrate |
| **E-signature** | sign contracts / broker agreements | [#10](https://github.com/orgs/andrelair-platform/projects/10) | ✅ Docuseal live |

> Full detail on the ingestion pipeline + metadata schema:
> [Business Applications Catalog §8](./business-applications-catalog).

## F. Risk & compliance operations
*control functions, running daily*

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Risk engineering / prevention** | site audits, inspections, recommendations | [#21](https://github.com/orgs/andrelair-platform/projects/21) | 📋 Backlog |
| **AML/KYC + sanctions screening** | onboarding checks | [#15](https://github.com/orgs/andrelair-platform/projects/15) | 📋 Backlog |
| **GDPR / DPO workflows** | Art. 30 register, DSAR | [#15](https://github.com/orgs/andrelair-platform/projects/15) | 📋 Backlog |
| **Regulatory reporting** | ACPR/COREP, Solvency II, DORA | [#15](https://github.com/orgs/andrelair-platform/projects/15) | 📋 Backlog |
| **Obligations / control register** | compliance-by-design | [#15](https://github.com/orgs/andrelair-platform/projects/15) | ✅ framework built ([Regulatory Operating Model](./regulatory-operating-model)) |

## G. Data & decision-support for the business

| Tool | Purpose | Board | Status |
|---|---|---|---|
| **Operational BI dashboards** | loss ratio, production, claims KPIs + **semantic layer** | [#5](https://github.com/orgs/andrelair-platform/projects/5) | 📋 Backlog (sources-gated) |
| **Actuarial reserving / pricing analytics** | reserves, tariffs | [#5](https://github.com/orgs/andrelair-platform/projects/5) | 📋 Backlog |
| **AI assistants** | Knowledge Assistant (#18) + AI Ops Copilot (#19) | [#4](https://github.com/orgs/andrelair-platform/projects/4) | ⏸ Parked (last) |

---

## The honest read

- **Live today:** Policy Admin (#6), ERPNext finance/HR (#8), e-signature, mail, and the AI/document substrate.
- **Build-ready (start now):** Underwriting (#12), Claims (#11).
- **Everything else is scoped but needs its design pass** — most business-ops tools are ahead of us
  (expected: only Policy Admin runs today).
- **The one genuinely missing cross-cutting product** is the **Operations Workbench** — the AI-native
  task-inbox that turns all of the above into *one prioritised inbox of exceptions* instead of agents
  hopping between apps. Built **need-first** (once ≥2 domains emit real tasks).

**See also:** [🗺 Architecture at a Glance](./architecture-at-a-glance) ·
[🧭 IS Build Roadmap](../product-roadmap/is-build-roadmap) ·
[Business Applications Catalog](./business-applications-catalog) ·
[EA Blueprint](./enterprise-architecture-blueprint).
