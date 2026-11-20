---
id: data-layer-overview
title: Data Layer Overview
sidebar_position: 1
---

:::info Status — the as-built platform is LIVE (this page is the map; the detail is the Workflow page)
The data platform runs an end-to-end **hybrid lakehouse**, live in the `data-platform` namespace:
**dlt** ingest → **AWS S3** raw lake → **DuckDB + dbt** transform → **CloudNativePG** serving → **Cube**
semantic layer → **Metabase** BI, with **Dagster** orchestration (webserver + daemon, a daily schedule) +
**MLflow** ML. The stage-by-stage detail lives on **[Data Platform — Workflow (as-built)](./data-platform-workflow)** —
this page is the orientation map. Decisions: [ADR-006..011](https://github.com/andrelair-platform/ktayl-data-platform/tree/main/docs/architecture/adr).
:::


# Data Layer — the ktayl Data Platform (as-built)

The data layer turns the insurer's live operational data into governed business intelligence and ML. It
covers the full chain — **ingest → raw lake → transform → serving warehouse → semantic layer →
BI / ML**, orchestrated as one asset graph.

:::note Two-layer model — this is a **Platform** capability
The Data Platform (ingest, OLAP lake, transformation, semantic layer, orchestration) is a **shared,
domain-agnostic infrastructure capability** — the data equivalent of the [AI Platform](../ai-ml/12-ai-gateway.md).
The **business data products** built on it (e.g. the `policy_portfolio` mart + dashboards) belong to the
**Information System** — they are the *consumers* of this capability. Engine → Platform; data products → IS.
:::

---

## The real data chain (what runs today)

![ktayl Data Platform — end-to-end workflow: sources → dlt → S3 lake → DuckDB/dbt → CloudNativePG → Cube → Metabase + MLflow, orchestrated by Dagster](/img/architecture/data-platform-workflow.svg)

*Diagram-as-code — [`ktayl-data-platform/docs/diagrams/data_platform_workflow.py`](https://github.com/andrelair-platform/ktayl-data-platform/blob/main/docs/diagrams/data_platform_workflow.py)
(mingrammer `diagrams` + Graphviz), regenerated from source, not hand-drawn. Solid = data flow · green = serving · dashed amber = Dagster orchestration.*

---

## Stack Components (as-built)

| Component | Role | Why this one |
|---|---|---|
| **dlt** | Ingest (source → raw lake) | A Python library (zero standing infra); schema inference + incremental; replaces a hand-written script per source. (Over Airbyte/Meltano — adopt those only if broad SaaS-connector coverage becomes the need.) |
| **AWS S3** (eu-west-1) | Raw lake | Parquet, versioned, SSE-encrypted, private. **Keyless** — short-lived STS via the **Vault AWS secrets engine**; no static keys in k8s/Git. The one deliberate cloud dependency. |
| **DuckDB** | OLAP engine | Reads Parquet from S3 over `httpfs` — real storage/compute separation; the analytical engine, no always-on warehouse cluster. |
| **dbt** (dbt-duckdb / dbt-postgres) | Transformation | Version-controlled, tested SQL; `staging → curated → marts` + MDM conformed dims (`dim_policy/customer/lob/period`) + `fact_policy`. |
| **CloudNativePG** | Serving warehouse | Gold marts land in `analytics.*` / `lake.*`; HA (2 instances) + R2 PITR. DuckDB is the OLAP engine; CNPG is the low-latency **serving** tier. |
| **Cube** | Semantic layer | Business metrics defined **once** (measures + dimensions over the gold mart); **Metabase consumes it natively via its pg-wire SQL API**; REST/GraphQL for apps + AI. |
| **Metabase** | BI | Dashboards over the semantic layer, behind Authentik SSO. |
| **scikit-learn + MLflow** | ML | Models are Dagster assets, trained + tracked + **registered** in the platform MLflow (governed, reproducible — EU AI Act / DORA). |
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
