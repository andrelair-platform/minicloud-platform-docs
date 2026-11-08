---
id: data-platform-target
title: Data Platform — Target Architecture
sidebar_position: 8
---

# Data Platform — Target Architecture (ktayl IS #5)

:::info This is the TARGET, not yet built
[Slice 1](./data-platform-slice1) (dbt + CNPG + Metabase) is **live**. This page is the **target
system design** the next slices build toward — a **hybrid lakehouse**: an AWS **S3 raw lake**, a
**DuckDB** transform engine, **CNPG** as the serving store, **Metabase** for BI. Authoritative
decisions: `ktayl-data-platform` **ADR-006** (governed lakehouse), **ADR-007** (Data-Platform-first
gating), **ADR-008** (this S3 + DuckDB + CNPG hybrid).
:::

[![Data Platform — Target Architecture](/img/architecture/data-platform-target.svg)](/img/architecture/data-platform-target.svg)

> **Edge legend:** solid teal = principal data flow · solid green = materialise/serve · dashed slate =
> backing dependency (provisions · tracks · lineage · issues-creds). [Open full SVG →](/img/architecture/data-platform-target.svg)

## The one-line shape

**S3 = lake (storage) · DuckDB = transform engine · CNPG = serving store · Metabase = BI.**
Source OLTP databases export Parquet to an S3 raw lake; DuckDB reads that Parquet **directly** (no
custom loader) and runs the dbt medallion; the conformed marts land in CNPG, which Metabase serves.

## Layer by layer

| Layer | Responsibility | Tech |
|---|---|---|
| **Source systems** | per-domain **OLTP** records (current state, one domain each) | Policy / Claims / Underwriting / Billing·GL Postgres |
| **S3 raw lake** | durable, versioned, **replayable** raw archive — decoupled from the warehouse | Amazon S3 (Parquet · manifest · checksums) |
| **DuckDB transform** | reads S3 Parquet directly, runs `staging → curated → marts` with dbt tests | DuckDB + `dbt-duckdb` (ephemeral in-cluster Job) |
| **CNPG serving** | conformed, **MDM-keyed** fact/dim marts the BI tool queries | CloudNativePG (Postgres) |
| **Metabase** | dashboards, KPIs, decision support | Metabase |
| **Catalog & governance** | model catalog + lineage, dataset inventory, dynamic cloud creds | dbt docs · YAML dataset registry · Vault (STS) |

## Why these choices (the forks)

- **Why a warehouse separate from the source Postgres?** Sources are **OLTP silos** — you cannot join
  earned premium (billing) + incurred claims (claims) + expenses (ERP) *in place*. The warehouse is the
  one **cross-domain, conformed, historical** place those meet. A warehouse is a **role**, not a
  technology. (Same pattern `ktayl-claims` already uses at domain level via its CQRS read-model.)
- **Why DuckDB for transform (not Athena / Redshift / CNPG-only)?** DuckDB is a columnar engine that
  **reads Parquet from S3 natively** — which **eliminates a custom S3→CNPG loader**. Athena/Glue are
  deferred (no second managed SQL engine); Redshift is rejected (always-on ≈ $180/mo would exhaust the
  credits).
- **Why CNPG for serving (not DuckDB)?** DuckDB is **embedded/single-process** — a great transform
  engine but a poor concurrent serving store. Metabase wants a live Postgres endpoint.
- **Why a cloud lake at all?** A **replayable raw archive** + storage/compute separation + real AWS
  data-engineering experience — stated honestly, not an urgent functional need at this data scale.

## Ingestion contract (reliability by design)

Batch-oriented and **idempotent**: each domain exports an incremental batch to a unique, non-overwritten
S3 key; a **manifest is written only after all files upload + validate** (atomic completion marker); an
**ingestion-control table** (in CNPG) tracks `batch_id / dataset / status / counts / schema_version`, so
a retry never duplicates records and the warehouse is **fully replayable from S3**.

## Guardrails & boundaries

- **Cost:** AWS **Budget $10/mo** with alerts at $5 / $8 / $10 (alerts are *not* hard caps). S3 Standard
  first, measure, add lifecycle tiers only when justified.
- **Egress:** producers are in-cluster, so data round-trips cloud↔cluster (S3 download = billable egress).
  Cheap at this scale; reconsider at volume.
- **Security:** **no static AWS keys** — the DuckDB Job gets **short-lived STS credentials** (Vault AWS
  secrets engine, or IAM Roles Anywhere — decision pending in ADR-008).
- **DR boundary:** the S3 raw lake is **NOT** the CNPG backup/DR strategy. CNPG keeps its own WAL
  archiving, backups, and restore drills; the lake enables *dataset replay*, not *database recovery*.
- **IaC vs runtime:** AWS resources via **OpenTofu** (`minicloud-cloud`); the DuckDB Job + config via
  **ArgoCD**; loader/transform **code** in `ktayl-data-platform`.

## Deferred (revisit-when)

AWS **Athena**, **Glue** crawlers, **Redshift**, and a full metadata platform (OpenMetadata/DataHub) are
deferred — revisit when multiple engines need the same raw data, cross-system discovery/governance is
required, or Postgres serving exceeds acceptable limits.

## Status

**Slice 1 live** (dbt + CNPG + Metabase over `policy_portfolio`). **Slice 2** builds this target in
dependency order (per ADR-007): **MDM keys → ingest claims/billing/finance → conformed fact/dim marts →
governance spine → Combined Ratio** as the first real cross-domain KPI.
