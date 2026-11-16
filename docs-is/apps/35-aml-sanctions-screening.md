---
id: aml-sanctions-screening
title: AML / Sanctions Screening — yente engine (S0) + screening module (S1)
sidebar_label: AML / Sanctions Screening
---

# AML / Sanctions Screening — the yente engine (S0) + the `screening` module (S1)

The **sanctions/PEP screening capability** (epic **RC-02**, board [#15](https://github.com/orgs/andrelair-platform/projects/15)) closes the one **genuine control gap** in the ktayl IS: today a party can be **bound and paid with no sanctions screen** — a real compliance failure for a regulated insurer, not mere incompleteness. The design is an **adopt-the-engine + build-the-gate** split (ADR-001): adopt **yente** (OpenSanctions' matching API) as the engine; build a **`screening` module in `ktayl-core`** as the gate + workflow + audit.

:::note S0 (engine) + S1 (module) are BOTH live on dev. The bind/payment HOLD gates (S2/S4) are next.
**S0 (live):** yente + a dedicated OpenSearch index + the official free lists + a freshness monitor. **S1 (live):** the `ktayl-core` `screening` module — `ScreenParty` (fail-closed + idempotent), append-only audit, and the **published `ScreeningGate`** interface other modules call. **S2/S4 (next):** wire `ScreeningGate` at **bind** (HOLD blocks bind) and before **payment** + asset-freeze; then nightly re-screen (S5) + governed-AI triage (S6). Planning of record: [`ktayl-compliance/docs/architecture/rc02-screening-architecture.md`](https://github.com/andrelair-platform/ktayl-compliance/blob/main/docs/architecture/rc02-screening-architecture.md) + ADR-001 + the SPEC.
:::

## What's deployed (S0)

| Piece | As-built |
|---|---|
| **yente** | `ghcr.io/opensanctions/yente:4.3.1` — the matching API (`POST /match/default`, `/search`, `/catalog`, `/readyz`). Standalone chart `services/yente/helm`, ns `yente` (dev-only — no prod consumer until the `screening` module ships). ArgoCD app `apps/is/compliance/yente-dev.yaml`. |
| **Index** | a dedicated **single-node OpenSearch** (`opensearchproject/opensearch:2.17.1`, Longhorn PVC) — no shared ES/OpenSearch existed on the cluster. |
| **Lists** | the **official FREE lists only** (OFAC SDN · EU consolidated · UN SC · UK OFSI) — licence-clean even in a production-shaped demo (ADR-001 §8), via a `catalogs` manifest. `YENTE_AUTO_REINDEX` keeps them fresh. |
| **Freshness** | a stdlib exporter emits `yente_sanctions_dataset_age_hours`; a **PrometheusRule** alarms at stale > 48h (critical) / > 24h (warn) / catalog-down — *"how do you know the lists were current when you screened?"* (SEC-SCR-04). |
| **Egress** | ingress default-deny + egress default-deny + DNS + cluster-internal + controlled external HTTPS to `data.opensanctions.org` only (SEC-SCR-03). Gatekeeper-clean (non-root, no-priv-esc, drop-caps, seccomp). |

## Verified live (2026-11-16)

- OpenSearch `green`; yente `/readyz` = **200**; `/catalog` lists the four free lists (OFAC **72,994** entities + EU 16,045 + UN + UK).
- **Acceptance proof** — `POST /match/default` a known sanctioned name → **"Vladimir Putin" matched at score 1.0** from `us_ofac_sdn`; an obvious non-name (control) → **0 matches** (no false positive).
- Freshness gauge live: `yente_sanctions_dataset_age_hours ≈ 0.2` (well under the 24h target); `yente_catalog_up = 1`.
- Egress confirmed to `data.opensanctions.org`; default-deny holds otherwise.

## Adoption gotchas (yente on a hardened cluster)

Four fixes, each caught by **live verification** (not unit tests), worth knowing for any yente/OpenSearch adopt:
1. **`enableServiceLinks: false`** — a Service named `yente` makes K8s inject `YENTE_PORT=tcp://<ip>:8000`, which yente reads as its listen port → `int()` crash.
2. **`YENTE_INDEX_TYPE=opensearch`** — yente defaults to the Elasticsearch client, whose product-check **rejects** OpenSearch (`UnsupportedProductError`).
3. **manifest via `catalogs` (not `url`/`entities_url`)** — a per-dataset `url: …/index.json` mis-parses; `entities_url` hits a `307` yente's httpx won't follow. The native mechanism reads the main catalog's **absolute artifact URLs**.
4. **freshness parse** — yente `/catalog` exposes recency as `version=YYYYMMDDHHMMSS` (compact, not ISO).

## What's deployed (S1 — the `screening` module in `ktayl-core`)

The gate + workflow + audit, as a **module inside the `ktayl-core` modular monolith** (not a new service — the modular-monolith decision), schema-per-module (`screening` schema, Flyway `V11`), hexagonal (domain ports + a `YenteClient` adapter):

| Piece | As-built |
|---|---|
| **`ScreenParty`** (application) | the use case: resolve/De-dupe the party (idempotent by `external_ref`), screen once per `(party, gate, UTC-day)`, persist the screening + any alerts, write an **append-only audit** row. **Fail-CLOSED:** any engine error → persist a `HOLD` screening (null `dataset_version`) + a `SCREEN_FAILCLOSED` audit → return `HOLD` (never a silent allow, NFR-SCR-02). |
| **`ScreeningGate`** (`@NamedInterface`) | the **published, in-process interface** other `ktayl-core` modules call — `screen(PartyRef, gate) → ScreeningOutcome {verdict, alertId, datasetVersion}`. A match → `HOLD`; no hit → `ALLOW`. This is what S2/S4 wire at bind/payment. |
| **Audit** | `screening_audit` — `bigint IDENTITY`, append-only (no update/delete), one row per screen/decision, actor from the JWT (`preferred_username`/subject). The DORA/AML evidence trail. |
| **HITL decision** | `POST /alerts/{id}/decision` — **`@PreAuthorize("hasAuthority('GROUP_Compliance')")`**; every alert is a human review (the AI triage S6 never auto-clears a true hit). Authority is **server-side**. |
| **Engine adapter** | `YenteClient` → `POST /match/default` on the S0 yente; score ≥ threshold → a `SANCTION` `Hit`; `GET /catalog` → the `dataset_version` logged as "the lists were current when we screened". |
| **Network** | ktayl-core egress → ns `yente` :8000; yente ingress ← ns `ktayl-core`(+`-prod`). Both default-deny + explicit allow. |

## Verified live (2026-11-16) — the full gate path, end-to-end on dev

Screened via the `ktayl-core` API with a real M2M (Authentik client-credentials) token:
- **`POST /v1/screening/screen` "Vladimir Putin" → `{"verdict":"HOLD", "alert_id":"eeabc8cb-…", "dataset_version":"20261116210012"}`** — a real alert, `bucket: SANCTION, score: 100, matched_entry: "Vladimir Vladimirovich Putin"`.
- A **clean control name → `{"verdict":"ALLOW", …}`** (dataset_version stamped on both — the "lists were current" evidence).
- **`GET /v1/screening/alerts`** lists the open alert; the fail-closed invariant proven separately (engine-unavailable → `HOLD` + null alert; unauthenticated → `401`).

### S1 gotcha (worth knowing for any Spring-Boot → FastAPI/uvicorn call)

The `ktayl-core` `YenteClient` (Spring Boot 3 `RestClient`) got **`400 "Invalid HTTP request received"` / `422 "body required"`** from yente while an identical `curl` from the same namespace worked. Cause: Spring Boot 3.2+'s default `RestClient` factory is the **JDK `java.net.http.HttpClient`**, which sends an **h2c upgrade** on cleartext `http://`. nginx/ERPNext tolerate it; **yente's uvicorn/h11 rejects it and drops the body**. Fix: `RestClient.builder().requestFactory(new SimpleClientHttpRequestFactory())` — `HttpURLConnection` speaks clean HTTP/1.1, no h2c. (And: a rollout leaves old+new pods briefly — verify on the pod matching the **new image digest**, not just the deploy tag; a stale pod gives a false fail-closed.)

## The invariant

The gate **fails CLOSED**: if yente is down/stale, a screen returns **HOLD**, never a silent allow (NFR-SCR-02). Authority is **server-side**; every match that could block a bind/payment goes to **human review** (HITL) — the AI triage (S6) never auto-clears a true hit.

Detailed design lives with the code: [`ktayl-compliance/docs`](https://github.com/andrelair-platform/ktayl-compliance) — ADR-001 (adopt-vs-build), the screening architecture (C4 + threat model + the gates), the SPEC (the S0→S6 slice plan). The module source is in [`ktayl-core`](https://github.com/andrelair-platform/ktayl-core) (`src/main/java/com/ktayl/core/screening`).
