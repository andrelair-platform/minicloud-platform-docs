---
id: data-platform-workflow
title: Data Platform — Workflow (as-built)
sidebar_position: 9
---

# Data Platform — Workflow (as-built, ktayl IS #5)

:::info This is the LIVE end-to-end process
Supersedes the [Slice 1](./data-platform-slice1) snapshot and realises most of the
[Target Architecture](./data-platform-target). The hybrid lakehouse + semantic layer + orchestration are
**running in the live cluster** (`data-platform` namespace). Decisions:
[ADR-006..010](https://github.com/andrelair-platform/ktayl-data-platform/tree/main/docs/architecture/adr).
:::

![Data Platform workflow](/img/architecture/data-platform-workflow.png)

*Diagram-as-code (`ktayl-data-platform/docs/diagrams/data_platform_workflow.py`, mingrammer `diagrams` +
Graphviz) — regenerated from source, not hand-drawn.*

## The pipeline, stage by stage

| Stage | Tool | What runs |
|---|---|---|
| **Ingest** | **dlt** (ADR-010) + a Vault-STS producer (ADR-008) | `sql_table` from the live source (ktayl-core `policy.policy`, underwriting) → schema-inferred load. **Replaces the hand-written COPY/DuckDB scripts.** |
| **Raw lake** | **AWS S3** eu-west-1 (ADR-008) | Parquet, versioned, SSE-encrypted, private. **Keyless** — the workload assumes a scoped role via the **Vault AWS secrets engine** (short-lived STS); no static keys in k8s/Git. |
| **Transform (OLAP)** | **DuckDB** + **dbt** (ADR-006/008) | DuckDB reads Parquet from S3 directly (httpfs) — real **storage/compute separation**; dbt builds `staging → curated → marts` + the MDM conformed dims (`dim_policy/customer/lob/period`) + `fact_policy`. |
| **Serving warehouse** | **CloudNativePG** (ADR-008) | gold marts land in `analytics.business.* / lake.* / dlt_marts.*`. HA (2 instances) + R2 PITR. DuckDB is the OLAP engine; **CNPG is the serving tier** (good at concurrent low-latency queries). |
| **Semantic layer** | **Cube** (ADR-009) | business metrics defined **once** (measures + dimensions over the gold mart). **Metabase consumes Cube natively via its pg-wire SQL API** (Cube looks like a database); REST/GraphQL for apps + AI. |
| **BI** | **Metabase** | dashboards over the semantic layer, behind Authentik SSO. |
| **ML (MLOps)** | **scikit-learn + MLflow** (ADR-010) | a **demonstration** ML asset (`features → model → evaluation`, a Dagster asset) proves the MLOps loop — train, track + **register in the platform MLflow** (experiment tracking + model registry). **Not yet a production model**; first real use cases (need-first) = **claims-fraud / policy-lapse scoring**. The value is the governed, reproducible, versioned pipeline (EU AI Act / DORA). |
| **Orchestration** | **Dagster** (ADR-010) | dlt + dbt + ML as **one asset graph** with lineage, partition backfills, and run observability. |

## The daily flow

```
ktayl-core policy / underwriting (live CNPG)
   │  dlt ingest  (schema-inferred; replaces COPY scripts)
   ▼
S3 raw lake (Parquet, Vault-STS keyless)
   │  DuckDB reads Parquet (httpfs) → dbt staging → curated → marts (+ MDM dims + fact_policy)
   ▼
CloudNativePG — gold marts (analytics.*)
   │                         │
   │  Cube SQL API           │  features
   ▼                         ▼
Metabase (BI, SSO)        MLflow (model registry)
        ▲                     ▲
        └──── Dagster orchestrates + lineage ─ dlt · dbt · ML ────┘
```

## Why these tools (verified 2026 landscape)

The stack is **industry-standard, self-hosted, and right-sized** — not a vendor-SaaS data platform:

- **Ingest = dlt** over Airbyte/Meltano: a **Python library** (zero standing infra), schema inference +
  incremental, native DuckDB/Postgres/S3 — it *replaces* writing a script per source. (Airbyte = heavy
  self-host; adopt only if broad SaaS-connector coverage becomes the need.)
- **Orchestration = Dagster** over Airflow/Prefect: **asset-centric**, best for a dbt-heavy stack (one
  asset per dbt model + partition backfills), lighter than Airflow. **ML is covered by Dagster assets +
  MLflow — no Prefect needed.**
- **Semantic layer = Cube** over the dbt Semantic Layer: Cube **self-hosts** and Metabase consumes it
  **natively**; the dbt Semantic Layer's governed *serving API* is dbt-Cloud-bound (fails the
  sovereign/Metabase-native test).
- **Warehouse = CNPG Postgres**, not Snowflake/BigQuery: sovereign, self-hosted, zero cloud-SaaS cost;
  the OLAP engine is **DuckDB** over the **S3** lake (the one deliberate cloud dependency).

## Operate / verify

```bash
# the pipeline CronJobs
kubectl --context minicloud get cronjob -n data-platform
# Cube serves governed metrics (the Metabase SQL-API path)
#   SELECT product_code, MEASURE(total_policies) FROM policy_portfolio GROUP BY product_code;
# Dagster asset graph + lineage UI
kubectl --context minicloud get deploy dagster -n data-platform
# the full Dagster asset graph (dlt→dbt→ml) runs to RUN_SUCCESS; MLflow registers the model
```

## Status + what's deferred (need-first)

**Production-adopted (right-sized)** — runs in the live `data-platform` namespace. What's deliberately
deferred, and the **exact trigger** for each, is the standing
**[ADR-011 deferred-capability trigger register](https://github.com/andrelair-platform/ktayl-data-platform/blob/main/docs/architecture/adr/ADR-011-right-sizing-deferred-capability-triggers.md)**:

| Deferred | Category | Trigger (not before) |
|---|---|---|
| Cube **Store** (HA + pre-aggs) | tooling | multi-consumer load (≳10 concurrent) **or** heavy SQL expressions — watch latency + concurrency, *not* row-count alone |
| Dagster **daemon** (schedules/sensors) | tooling | you want the graph to run itself — **the designated next move** (cheap, in-process) |
| Dagster **K8sRunLauncher / HA** | tooling | runs become heavy/parallel or risk UI contention (separate trigger from the daemon) |
| **CDC** (Debezium→NATS) | tooling | tables large / near-real-time need — then handle deletes + late updates + schema drift in dbt |
| **GWP / combined ratio** (cross-domain KPIs) | **data-blocked** | ktayl-core **Phase-1b** (premiums/coverages) + claims in the warehouse — [issue #28](https://github.com/andrelair-platform/ktayl-data-platform/issues/28). *Not* a tooling trigger. |

The one upgrade that already earned its place — **persistent run history on CNPG** — is built.
