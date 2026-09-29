---
id: ktayl-underwriting
title: ktayl Underwriting & Pricing
sidebar_label: ktayl Underwriting & Pricing
---

# ktayl Underwriting & Pricing

Python **modular-monolith** service (FastAPI) that owns the **underwriting lifecycle** — submission intake → appetite/eligibility → rating → quote → **bind** — plus a **Next.js underwriter workbench**. It binds into the live [ktayl Policy Service](./ktayl-policy-service) and emits a `bound-risk` event for downstream reinsurance/actuarial.

Board **#12** (Insurance LOB). The full lifecycle + the workbench are **LIVE on dev** (dev-only by a need-first decision; prod is deliberately parked behind the Authentik auth gate).

**Full documentation (in-repo):** [github.com/andrelair-platform/ktayl-underwriting](https://github.com/andrelair-platform/ktayl-underwriting) — see [Solution Architecture](https://github.com/andrelair-platform/ktayl-underwriting/blob/main/docs/architecture/solution-architecture.md), [ADR log](https://github.com/andrelair-platform/ktayl-underwriting/blob/main/docs/architecture/adr/000-index.md), [Threat model](https://github.com/andrelair-platform/ktayl-underwriting/blob/main/docs/architecture/threat-model.md), [NFR register](https://github.com/andrelair-platform/ktayl-underwriting/blob/main/docs/architecture/nfr-register.md), and [UX DESIGN / EXPERIENCE](https://github.com/andrelair-platform/ktayl-underwriting/tree/main/docs/ux).
See also the [Underwriting FDE Playbook](./underwriting-fde-playbook) for the domain + regulatory framing.

---

## Responsibility

| In scope | Out of scope |
|---|---|
| Submission intake + local counterparty (ADR-002) | Master data (MDM #20 — parked) |
| Appetite / eligibility (accept · refer · decline + reason codes) | Claims ([ktayl-claims](https://github.com/andrelair-platform/ktayl-claims) #11) |
| Rating — versioned, immutable rate tables → explainable premium | Policy admin / billing (Policy Service + ERPNext) |
| Bind → create/submit/activate a policy in the PAS + `bound-risk` event | Reinsurance / actuarial (downstream consumers) |
| Underwriter workbench (triage referrals, price, bind) | Autonomous AI action (assistive + human-verified only, ADR-003) |

## Stack

| | |
|---|---|
| Backend | Python 3.12 + FastAPI + Pydantic (SQLAlchemy + Alembic) — ADR-007 |
| Frontend | Next.js 16 + React 19 + Tailwind v4 — a **BFF** (server components + server actions), ADR-008 |
| Database | CNPG PostgreSQL (per-service); app **self-migrates on startup** |
| Registry | `harbor.10.0.0.200.nip.io/library/ktayl-underwriting` (+ `-frontend`); prod → ghcr, cosign-signed |
| Delivery | GitOps (ArgoCD) + **Kargo git-Warehouse** (two images pinned to one source commit) |

## The underwriter workbench (frontend)

An **AI-native task inbox**: the appetite engine auto-decides the rule (accept / decline); underwriters work the **referrals**. Inbox (outcome-tab triage) → submission detail (appetite decision + **explainable rating breakdown** + binding + audit trail) → assess / quote / bind actions → intake form.

It is a **Backend-for-Frontend, not a browser SPA** — the browser talks same-origin to Next.js; Next reaches the API **server-side** via a runtime `API_URL`, so the underwriting API is never exposed to the browser and one env-agnostic image serves dev and prod (ADR-008).

## Lifecycle (summary)

```
intake → assess (appetite) → rate → quote → bind (PAS: create → submit → activate) → bound-risk event
```

All money is **eurocents** (`int64` minor units); the rating breakdown reconciles to the premium. The bind is idempotent (deterministic `policy_number`, 409-as-success). Proven end-to-end: active policy `UW-369188ABE405` (€400) in the PAS.

## Sprint status

| Story | Status | Deliverable |
|---|---|---|
| UW-01-S01 | ✅ Done | Intake → appetite decision + append-only audit |
| UW-04-S01 | ✅ Done | Rating — versioned rate tables → explainable quote |
| UW-01-S02 | ✅ Done | Bind (ADR-006) — live PAS handoff + `bound-risk` event |
| Workbench | ✅ Done | Next.js BFF inbox / detail / actions — live on dev |
| Testing | ✅ Done | Full L0–L4 pyramid + a live L5 QA gate (backend + frontend) |
| Prod | ⏸ Parked | Need-first; blocked on the Authentik prod-auth gate |

## Quality & delivery notes

- **Full test pyramid enforced** — L2 integration (real Postgres), L3 contract (against the Policy Service OpenAPI), L4 smoke, and a live **L5 QA gate** against the running dev service before any prod promotion. "Unit-only" is treated as an anti-pattern.
- **Governance:** the Path-C artefact set (PRD, solution architecture, NFR register, threat model, ADR log, UX DESIGN/EXPERIENCE) lives in the repo; this page is the map.
