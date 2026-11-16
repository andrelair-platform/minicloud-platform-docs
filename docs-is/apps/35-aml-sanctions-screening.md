---
id: aml-sanctions-screening
title: AML / Sanctions Screening — yente engine (RC-02 S0)
sidebar_label: AML / Sanctions Screening
---

# AML / Sanctions Screening — the yente engine (RC-02 S0)

The **sanctions/PEP screening capability** (epic **RC-02**, board [#15](https://github.com/orgs/andrelair-platform/projects/15)) closes the one **genuine control gap** in the ktayl IS: today a party can be **bound and paid with no sanctions screen** — a real compliance failure for a regulated insurer, not mere incompleteness. The design is an **adopt-the-engine + build-the-gate** split (ADR-001): adopt **yente** (OpenSanctions' matching API) as the engine; build a **`screening` module in `ktayl-core`** as the gate + workflow + audit.

:::note This page = the ENGINE (S0, live). The GATE (S1+) is next.
**S0 (this, live on dev):** yente + a dedicated OpenSearch index + the official free lists + a freshness monitor. **S1+ (next, `ktayl-core` modules):** the `screening` module (`ScreenParty`, append-only audit, the published `ScreeningGate`) → the **bind HOLD** gate → the **payment HOLD** + freeze → nightly re-screen → governed-AI triage. Planning of record: [`ktayl-compliance/docs/architecture/rc02-screening-architecture.md`](https://github.com/andrelair-platform/ktayl-compliance/blob/main/docs/architecture/rc02-screening-architecture.md) + ADR-001 + the SPEC.
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

## The invariant (carried into S1)

The gate (built in S1) must **fail CLOSED**: if yente is down/stale, a screen returns **HOLD**, never a silent allow (NFR-SCR-02). Authority is **server-side**; every match that could block a bind/payment goes to **human review** (HITL) — the AI triage (S6) never auto-clears a true hit.

Detailed design lives with the code: [`ktayl-compliance/docs`](https://github.com/andrelair-platform/ktayl-compliance) — ADR-001 (adopt-vs-build), the screening architecture (C4 + threat model + the gates), the SPEC (the S0→S6 slice plan).
