# Capability Register — Scoring Guide

> **Reconstructed 2026-10-31.** The original "Scoring Guide" sheet lived only in the derived
> `insurance_enterprise_capability_registry.xlsx`, which was deleted during cleanup **before** it was
> captured. This guide is reconstructed faithfully from the **surviving authoritative sources** — the
> Capability Map (§26–31), the committed register's own scoring columns (`capability-register.csv`), and
> the board maturity rubric (`maturity-assessment.csv`). It is now the **canonical, git-tracked rubric**;
> the xlsx is not coming back. Rule from the Capability Map §27: *a score must have measurable criteria —
> never arbitrary.*

Companion files (same folder): `capability-register.csv` (the 630-capability master) ·
`maturity-assessment.csv` (per-domain first-pass maturity). Consumed by `scripts/gen-si-delivery.py`.

---

## 1. Criticality (business)
How much the business depends on the capability. CSV column **`Criticality`**.

| Value | Meaning |
|---|---|
| **Critical** | Business stops / regulatory breach / financial loss if unavailable (e.g. Policy, Claims payment, IAM). |
| **High** | Material disruption; workarounds painful. |
| **Medium** | Degraded but tolerable short-term. |

## 2. DORA classification (resilience)
Is the capability a DORA **Critical/Important Function (CIF)**? CSV column **`DORA`**.

| Value | Meaning |
|---|---|
| **CIF — Critical** | A Critical or Important Function under DORA → full resilience obligations (RTO/RPO, testing, 3rd-party, incident reporting). |
| **Important** | Important but not top-tier critical; proportionate controls. |
| **Supporting** | Supporting function; baseline controls. |

Each CIF capability must carry: target **RTO/RPO**, **tested** RTO/RPO (recovery evidence), dependencies,
single-points-of-failure, BCP/DR, last resilience test, and vendor/third-party links (Capability Map §16–18).

## 3. Priority score (what to modernise first)
Priority is **not** "oldest first" (Capability Map §29). It is the product of five 1–5 drivers, in the
CSV columns `Business Value (1-5)` · `Pain (1-5)` · `Risk/DORA (1-5)` · `Automation Value (1-5)` ·
`AI Value (1-5)` → `Priority Score` → **`Priority Band`**.

```
Priority = Business Value × Operational Pain × Risk/DORA × Automation Value × AI Value
```

Each driver, 1 (low) → 5 (high):

| Driver | 1 | 3 | 5 |
|---|---|---|---|
| **Business Value** | nice-to-have | useful | core revenue/decision capability |
| **Operational Pain** | smooth today | friction/rework | manual, error-prone, Excel-bound |
| **Risk / DORA** | supporting | important | CIF / regulatory / solvency exposure |
| **Automation Value** | little to automate | partial | high straight-through potential |
| **AI Value** | no fit | assists | document-AI / decision-support transforms it |

**Priority Band:** `P1 - Transform` (highest) … down to `To Assess` (not yet scored — the current default
for most rows). *Cost, Complexity, Dependencies and Change-Risk are weighed **separately** (§29), not folded
into the score.*

## 4. Capability health / maturity (how complete it is)
Two layers — a **per-domain first-pass** (what the board shows today) and a **per-capability** detail
(future EA pass). Maturity is a **separate axis from deployment** — a capability can be LIVE yet immature.

### 4a. Board maturity rubric (per domain — `maturity-assessment.csv`)
Five dimensions, 1–5; **Maturity % = mean × 20**.

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| **Functional depth** | stub | core flows only | the domain's full capability set |
| **Process maturity** | ad-hoc | happy path | full lifecycle incl. exceptions/approvals |
| **Integration maturity** | isolated | point-to-point | event-driven, contract-tested |
| **Data maturity** | none/ad-hoc | a schema exists | modelled, ERD, quality, ownership |
| **Operational maturity** | dev only | prod, basic monitoring | prod HA + DR + SLOs + tested recovery |

A dimension may also be **0 = absent / not started** (no code, workflow, wiring, schema or deployment).
A domain scored 0 across all five → **0% "not started"** on the board (shown with its capability count as
the gap size), e.g. the greenfield blind-spot boards #29/#30/#31. 0% is a *positive* assessment ("we looked;
nothing is built"), distinct from `not assessed` ("we haven't scored it").

### 4b. Per-capability health (Capability Map §27 — future detailed pass; CSV columns, today empty)
Eight measurable 1–5 scores per capability: *Business maturity · Process maturity · Application health ·
Data quality · Integration maturity · Automation maturity · DORA resilience · AI opportunity.* The CSV's
per-cap `Maturity %` / `Functional Depth (1-5)` stay **NOT ASSESSED** until a detailed pass fills them.

## 5. Deployment & delivery status (what actually runs)
| CSV column | Values |
|---|---|
| **Application Deployment Status** | `LIVE` · `PARTIAL` · `IN PROGRESS` · `SCAFFOLD` · `NOT DEPLOYED` · `GAP` |
| **Capability Delivery Status** | `NOT DESIGNED / NOT ASSESSED` · `UNKNOWN / NOT ASSESSED` (honest placeholders — nothing claimed built without evidence) |

> **Honesty rule:** deployment status = *declared / observed*; it is **not** a claim of functional
> completeness or tested recovery. Those are the maturity (§4) and DORA-tested-recovery (§2) axes.

## 6. Application lifecycle (Capability Map §26)
CSV column **`Application Lifecycle`**.

| Value | Action |
|---|---|
| **TARGET** | the intended future application for this capability (not yet there) |
| **STRATEGIC** | invest / modernise |
| **TACTICAL** | keep medium-term |
| **LEGACY** | reduce dependency |
| **CONTAIN** | no new development |
| **REPLACE** | find a replacement |
| **RETIRE** | remove |

## 7. Sourcing strategy
CSV column **`Sourcing Strategy`**: `BUILD` · `BUY` · `HYBRID` · `PLATFORM` (and combinations, e.g.
`BUY / HYBRID`). "PLATFORM" = provided by a shared platform capability rather than a per-domain app.

## 8. Complexity & implementation wave
- **Estimated Complexity:** `MEDIUM` · `HIGH` · `VERY HIGH` — build/integration effort + risk.
- **Implementation Wave:** `Wave 0/1` (foundations) → `Wave 5` (channels/last), per the EA-blueprint roadmap.

## 9. The target decision matrix (Capability Map §30)
Plot each capability on **Business Value × Technical Debt** to pick the move:

```
                       BUSINESS VALUE
                    LOW              HIGH
                ┌──────────────┬──────────────┐
      HIGH      │ Simplify /   │ MODERNISE    │
  TECHNICAL     │ Retire       │ FIRST        │
  DEBT          ├──────────────┼──────────────┤
      LOW       │ Maintain     │ INVEST       │
                │ cheaply      │              │
                └──────────────┴──────────────┘
```

---

### Provenance
Capability Map §26–31 (`B2BAssurance/Insurance Enterprise Capability Map …md`) · the register's own
columns (`capability-register.csv`, 68 cols) · the board rubric (`maturity-assessment.csv`). Scales in
§1–§8 are the **actual distinct values present in the register** as of 2026-10-31.
