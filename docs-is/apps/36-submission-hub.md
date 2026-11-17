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

## SUB-02 — live handoff to underwriting (#12), dev + prod

Route no longer just records locally — it **hands the ROUTED submission off to the underwriting service** (`POST /v1/submissions`), creating a real UW submission from the exposure dossier. `route()` transitions + saves locally **first**, then maps the dossier and calls underwriting via the `UnderwritingPort` (hexagonal); on a handoff failure the submission stays `ROUTED` with a null `uw_submission_ref` (retryable, the call returns `502`), on success it records the returned `uw_submission_ref`.

- **Increment 1 (dev)** — the handoff, unauthenticated (dev underwriting's API auth is OFF). Live-verified: a routed dev submission creates a UW submission in the dev underwriting service.
- **Increment 2 (prod M2M)** — underwriting's API auth is **ON in prod**, so the handoff authenticates with an **OAuth2 client-credentials bearer**. A `UnderwritingTokenProvider` mints + caches an Authentik token scoped `underwriting:write` (client `ktayl-core-uw-m2m`), enabled only when `underwriting.oauth2.client-id` is set → **dev stays unauthenticated** (no client-id), the **same artifact** authenticates in prod. The token endpoint is the Authentik **ingress** host (reuses the existing egress allowance — no netpol change); underwriting validates **signature + scope**, so the issuer host is irrelevant. Creds come from Vault (`secret/platform/ktayl-core-underwriting`) via an ESO `ExternalSecret` → `UNDERWRITING_OAUTH_*` env. The M2M pattern mirrors underwriting→ktayl-core (ADR-016).

**Prod acceptance (live):** from `ktayl-core-prod`, the `ktayl-core-uw-m2m` client mints a token and `POST /v1/submissions` against **underwriting-prod** returns **`201`** (a real UW submission created); the same call **without** a bearer returns **`401`** — proving the handoff is authenticated and auth is enforced. Prod is on `ktayl-core:604c7d3`, 2/2, `Synced/Healthy`.

Module source: [`ktayl-core`](https://github.com/andrelair-platform/ktayl-core) (`src/main/java/com/ktayl/core/submission`). The modular-monolith rationale lives in `ktayl-core/docs` (ADR-004..011).
