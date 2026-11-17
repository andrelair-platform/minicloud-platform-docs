---
id: submission-hub
title: Submission Hub — broker intake → triage → route (ktayl-core module)
sidebar_label: Submission Hub (#27)
---

# Submission Hub — the corporate broker-submission front door

The **Submission Hub** (board [#27](https://github.com/orgs/andrelair-platform/projects/27)) is the **corporate front door** of the insurer: a broker submits a risk, the exposure dossier is captured, it is triaged for completeness/appetite, and qualified submissions are routed on to [Underwriting (#12)](https://github.com/orgs/andrelair-platform/projects/12). It is built as a **module inside `ktayl-core`** — the modular-monolith decision (a new *business domain* is a module, not a new service) — schema-per-module (`submission`, Flyway `V12`), hexagonal, boundaries enforced by `ApplicationModules.verify()`.

:::note SUB-01 (this) is the first slice: intake → exposure dossier → triage → route, with sanctions screening at the front door. The live M2M handoff to the underwriting service is SUB-02.
:::

## What's deployed (SUB-01)

| Piece | As-built |
|---|---|
| **State machine** | `Submission` aggregate: `RECEIVED → TRIAGED → ROUTED | DECLINED`, transitions enforced in the domain (an illegal transition → `409`). |
| **Exposure dossier** | `exposure_item` rows per submission — site, country, **TIV**/currency, occupancy, loss-history, **CAT flag** (the #27 scope: sites/values/loss-history/geo-CAT). |
| **Triage** | an append-only `submission_triage` log (decision `ROUTE`/`DECLINE`/`RETURN`, completeness score, appetite flag, actor) — the auditable intake decision. |
| **Published interface** | `submission.api` — `SubmissionIntake` (register/addExposure/triage/route/clearScreeningHold) + `SubmissionQuery` (findById/list) + `SubmissionView`, a `@NamedInterface` so Distribution (#13) / Underwriting (#12) consume it **in-process** (no intra-monolith HTTP). |
| **REST** | `/v1/submissions` (register `POST /`, `POST /{id}/exposures`, `/triage`, `/route`, `/clear-hold`, list, get) — `GROUP_Underwriting`-gated; `clear-hold` needs `GROUP_Compliance`. |

## Sanctions screening at the front door (compounds RC-02)

The headline control: **the insured is screened at the earliest possible point — intake.** `register()` calls the [S1 `ScreeningGate`](./aml-sanctions-screening) at a new `intake` gate (in-process, via `screening.api` only):

- a **`HOLD`** (a sanctions/PEP match **or** a fail-closed engine outage) → the submission is **still captured** but **flagged** (`screening_hold`, with the audit `alertId`), and **`route()` is refused with `409`** until a compliance officer clears it (`clear-hold`, `GROUP_Compliance`) — **HITL**, the gate never auto-clears.
- an **`ALLOW`** → the submission flows normally.

This is the same `ScreeningGate` proven live at **bind** (S2) and wired at **payment** (S4) — the screening investment now guards the funnel from its very first touch (intake) through bind and payment. Fail-closed is inherited: a yente outage holds the submission rather than letting an unscreened party through.

## Verified live (2026-11-17)

Deployed to dev (`ktayl-core:4bbc7cd`, 1/1 healthy — so **Flyway `V12` migrated on boot**; a failed migration crashes the pod). Smoke-probed from in-cluster:

- `GET /v1/submissions` **without a token → `401`** (authentication enforced).
- `GET /v1/submissions` **with a valid but wrong-group token → `403`** — the `GROUP_Underwriting` gate is live (an ungated `/v1/policies` with the same token returns `200`, confirming the token + routing are sane, so the `403` is the gate, not a transport error).

> **Gotcha (same stale-pod race as S1/S2):** during the rollout overlap the probe briefly hit the *old* image (which has no `/v1/submissions` route) and got a misleading `404`; on the converged new-digest pod it is the correct `403`. Always verify the group-gate on the pod matching the **new image digest**.

The behavioral flow (register → exposure → triage → route; and **a `HOLD` at intake blocks `route`**) is covered by the **L2 Testcontainers integration** + the **L3 contract** tests (`mvn verify` = 165 tests, 37 new) that gate every merge.

## Boundaries & invariants

- **Server-side authority** (the gate is in the application layer), **fail-CLOSED**, **HITL** to clear a hold, **append-only** triage log.
- In-process cross-module calls via the published `@NamedInterface` **only** (submission → `screening.api`) — `ApplicationModules.verify()` + `HexagonalArchitectureTests` green; no boundary weakening.

## Next (SUB-02)

Route currently records the routing locally; **SUB-02** wires the live M2M handoff to the underwriting service (#12) — creating a UW submission from the dossier — which also provides the authenticated `GROUP_Underwriting` driver for an end-to-end live walk of the gated workbench flow.

Module source: [`ktayl-core`](https://github.com/andrelair-platform/ktayl-core) (`src/main/java/com/ktayl/core/submission`). The modular-monolith rationale lives in `ktayl-core/docs` (ADR-004..011).
