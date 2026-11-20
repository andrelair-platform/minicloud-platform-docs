---
id: data-layer-overview
title: Data Layer Overview
sidebar_position: 1
---

# minicloud Data Platform

A **platform capability of minicloud** — the shared, domain-agnostic data engine (ingest → lake → transform
→ serve → BI/ML). **ktayl-solution is its current consumer, not its owner:** it serves the insurer's data
today, but the platform is independent of the business — change the organisation or the domain and it lives
on. **Live** in the `data-platform` namespace (deployed from the Platform pillar
`minicloud-gitops/platform/…`, not `is/`); this page is the map, the **[Workflow page](./data-platform-workflow)**
has the depth. Decisions: [ADR-006..011](https://github.com/andrelair-platform/ktayl-data-platform/tree/main/docs/architecture/adr).

*minicloud **provides** the engine (**Platform**, the data twin of the [AI Platform](../ai-ml/12-ai-gateway.md));
ktayl **consumes** it (**IS**). The insurance data products (`policy_portfolio` + dashboards) are the
swappable IS layer — see *Domain-agnostic* below.*

---

## The real data chain (what runs today)

**End-to-end workflow — sources → dlt → S3 lake → DuckDB/dbt → CloudNativePG → Cube → Metabase + MLflow, orchestrated by Dagster**

![minicloud Data Platform — end-to-end workflow: sources → dlt → S3 lake → DuckDB/dbt → CloudNativePG → Cube → Metabase + MLflow, orchestrated by Dagster](/img/architecture/data-platform-workflow.png)

*Boxes are grouped by **capability category** (same colour = same category): **Data Ingestion & Pipelines**
(dlt + Dagster) · **Data Lake** (S3 — raw object store) · **Transformation & Semantic Layer** (DuckDB OLAP
engine + dbt + Cube) · **Serving Store** (CNPG — gold marts) · **BI & AI Analytics** (Metabase + MLflow).*

:::note The "data warehouse" is not a single box — it's the lakehouse pattern
A classic warehouse (Snowflake/BigQuery) bundles storage + query engine + serving into one product. Here
that's **unbundled**: **Data Lake** (S3 — storage) + **DuckDB** (the OLAP / lakehouse *query engine*) +
**Serving Store** (CNPG — persistent, concurrent serving marts) **together = the data-warehouse capability**.
No single box is "the warehouse"; DuckDB is the engine, CNPG is the serving tier it materialises into.
:::

---

## Stack Components (as-built)

| Component | Role | Why this one |
|---|---|---|
| **dlt** | Ingest (source → raw lake) | A Python library (zero standing infra); schema inference + incremental; replaces a hand-written script per source. (Over Airbyte/Meltano — adopt those only if broad SaaS-connector coverage becomes the need.) |
| **AWS S3** (eu-west-1) | Raw lake | Parquet, versioned, SSE-encrypted, private. **Keyless** — short-lived STS via the **Vault AWS secrets engine**; no static keys in k8s/Git. The one deliberate cloud dependency. |
| **DuckDB** | OLAP engine (lakehouse warehouse engine) | The analytical **query engine** — reads Parquet from S3 over `httpfs` (real storage/compute separation); runs the dbt transforms. Ephemeral/in-process (runs in the transform Job), so it's the engine, not a standing store. |
| **dbt** (dbt-duckdb / dbt-postgres) | Transformation | Version-controlled, tested SQL; `staging → curated → marts` + MDM conformed dims (`dim_policy/customer/lob/period`) + `fact_policy`. |
| **CloudNativePG** | Serving store (gold marts) | The persistent, concurrent, HA **serving tier** BI connects to — gold marts in `analytics.*` / `lake.*`; R2 PITR. DuckDB is the OLAP engine; CNPG is what it materialises *into* (not "the warehouse" on its own). |
| **Cube** | Semantic layer | Business metrics defined **once** (measures + dimensions over the gold mart); **Metabase consumes it natively via its pg-wire SQL API**; REST/GraphQL for apps + AI. |
| **Metabase** | BI | Dashboards over the semantic layer, behind Authentik SSO. |
| **scikit-learn + MLflow** | ML (MLOps) | **MLflow = experiment tracking + model registry** (the shared MLOps backbone). Today a **demonstration** ML asset proves the loop end-to-end (features → train → track → **register** in MLflow) — *not yet a production model*. The first real use cases (need-first) are **claims-fraud / policy-lapse scoring**; the value is the governed, reproducible, versioned pipeline (EU AI Act / DORA). |
| **Dagster** | Orchestration | dlt + dbt + ML as **one asset graph** with lineage, backfills, run observability; webserver + daemon run a **daily** schedule. |

---

## Where it lives

```bash
# one namespace holds the whole platform
kubectl --context minicloud get all -n data-platform
# the ingest + transform CronJobs
kubectl --context minicloud get cronjob -n data-platform
# Dagster (asset graph + lineage UI; webserver + daemon)
kubectl --context minicloud get deploy dagster -n data-platform
```

GitOps: `minicloud-gitops/platform/data/data-platform/`. Code: the
[`ktayl-data-platform`](https://github.com/andrelair-platform/ktayl-data-platform) repo (dlt sources, the
dbt project, the Cube model, the Dagster definitions).

---

## Architecture pattern — a modern ELT lakehouse

This is a textbook **ELT** architecture (Extract → **Load raw** → Transform), not classic ETL: raw data
lands **first**, and transformation happens **after**, driven by dbt. It also realises the **medallion /
lakehouse** shape (bronze → silver → gold) with real **storage/compute separation** (DuckDB queries the
S3 lake directly), orchestrated as one asset graph.

| Stage | What runs | Pattern signal |
|---|---|---|
| **Extract** | **dlt** pulls from the source Postgres (ktayl-core `policy`, underwriting) | — |
| **Load (raw)** | raw **Parquet → S3** lake (schema-on-read) = *bronze* | load-before-transform → **ELT** |
| **Transform** | **DuckDB + dbt** build `staging → curated → marts` (*silver → gold*) **after** load | dbt-after-load → **ELT** |
| **Serve** | gold marts in **CloudNativePG** → **Cube** metrics → **Metabase** / **MLflow** | — |

## Domain-agnostic — re-homeable to any organisation

The Data Platform is a **Platform** capability, not an insurance thing — it passes the gold litmus test
(*"if ktayl stopped selling insurance tomorrow, would this survive unchanged?"* → **yes**). The **engine**
is generic; only the thin **data-product layer** encodes the insurance domain. To re-home it to another
org/domain (retail, healthcare, logistics…):

| | What it is | Re-home it to a new domain? |
|---|---|---|
| **Engine (Platform)** | dlt · S3 lake · DuckDB · the dbt framework · CloudNativePG · Cube · Metabase · Dagster · Vault-STS access · the GitOps deploy | **unchanged** — none of it knows anything about insurance |
| **Data products (IS)** | dlt source configs · the dbt models (`fact_policy`, `dim_policy/lob`, medallion SQL) · the Cube semantic model · Metabase dashboards · the ML feature/model assets | **swapped** — point at the new sources, write the new models/metrics |

So the whole infrastructure + pipeline framework is portable; only the SQL models, source definitions,
metrics and dashboards are domain-specific. One portability caveat: the single external dependency is
**AWS S3** for the raw lake (keyless via Vault STS) — a one-line swap to an **S3-compatible** store
(**MinIO** / **Cloudflare R2**) if a new org needs full sovereignty or zero cloud; everything else is
already self-hosted and generic.

---

## Alternatives considered but NOT taken

An earlier design targeted a heavier streaming/OLAP stack. Each piece was evaluated and **deliberately
not built** in favour of a lighter, sovereign, need-first equivalent — the decision for each lives in the
ADRs:

| Considered | Planned for | What we run instead | Why | Decision |
|---|---|---|---|---|
| **Kafka / Redpanda** | event streaming backbone | **NATS** (already the platform bus) + **dlt** batch ingest | no second broker to run; need-first, not a streaming platform up-front | ADR-010 |
| **ClickHouse** | columnar OLAP warehouse | **DuckDB** over the **S3** lake + **CNPG** serving | storage/compute separation without a standing analytics cluster | ADR-008 |
| **OpenMetadata** | catalog + lineage | **Dagster assets** (lineage) + **dbt docs** | lineage comes free from the asset graph; no separate catalog service to operate | ADR-010 |

Doctrine throughout: **thin vertical slices per live source, need-first** — not a big OLAP cluster
up-front. These capabilities remain on the shelf with explicit **re-adoption triggers** (e.g. CDC when
tables get large / near-real-time is needed) in the standing
[ADR-011 deferred-capability register](https://github.com/andrelair-platform/ktayl-data-platform/blob/main/docs/architecture/adr/ADR-011-right-sizing-deferred-capability-triggers.md);
the [ADRs](https://github.com/andrelair-platform/ktayl-data-platform/tree/main/docs/architecture/adr) hold the full context.

---

## Read next

- **[Data Platform — Workflow (as-built)](./data-platform-workflow)** — the stage-by-stage detail + the live diagram (start here for depth).
- **[Slice 1](./07-data-platform-slice1.md)** — the first vertical slice (`policy_portfolio`), the historical starting point.
- **[Target Architecture](./08-data-platform-target.md)** — the direction this realises.
- **[dbt](./dbt)** — the transformation layer in detail.
