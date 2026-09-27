---
id: data-platform-slice1
title: Data Platform — Slice 1 (LIVE)
sidebar_position: 7
---

# Data Platform — Slice 1 (LIVE, ktayl IS #5)

:::tip This is deployed and proven (2026-09-27)
Unlike the heavier design-reference stack in the rest of this section (Kafka/Redpanda → ClickHouse →
Superset → OpenMetadata — still **planned / need-first-deferred**), **Slice 1 is a light-first
implementation that actually runs**: **dbt + CNPG Postgres + Metabase**. It is the first thin vertical
slice of the ktayl IS Data Platform (#5).
:::

> Two-layer model: this is the **ktayl-solution IS** analytics platform, not Retrieva.
>
> **Detailed docs (the library):** [ktayl-data-platform docs site](https://andrelair-platform.github.io/ktayl-data-platform/) —
> architecture, system design (C4 + NFRs + threat model), design patterns, and data model.
> **Code** (dbt + ingest + Metabase provisioner): [`andrelair-platform/ktayl-data-platform`](https://github.com/andrelair-platform/ktayl-data-platform).
> **Deployment** (k8s manifests, CronJobs, ArgoCD): [`minicloud-gitops/manifests/data-platform/`](https://github.com/andrelair-platform/minicloud-gitops/tree/main/manifests/data-platform)
> — the CronJobs git-clone the code repo at runtime (deployment-vs-code separation). This page is the map.

## The doctrine (why light-first, why one slice)

Per the [EA capability map](../insurance-platform/capability-map) roadmap: **use cases drive it · sources
constrain it · technology comes last.** ktayl's sources are its own domain services, and most aren't built
yet — so building a heavy OLAP cluster now would be "a warehouse for empty warehouses." The rule is **one
thin vertical slice against a real live source → just-enough medallion → one data product**, then generalise
from 2–3 real pipelines. Policy Admin is the one fully-live business source, so it's the slice.

## Architecture

```text
ktayl-policy-service (LIVE prod Postgres — the real source)
        │  ingest CronJob (full-refresh COPY; read-only analytics_ro role; CDC later)
        ▼
   raw  ──►  curated (dbt staging)  ──►  business (dbt marts)
   policies/coverages/premiums          stg_*                policy_portfolio  ◄── the data product
        │  dbt build = run + 26 schema tests (fail loudly on source drift)
        ▼
   Metabase  (metabase.10.0.0.200.nip.io — Tailscale + CA)
```

| Layer | Tool | Notes |
|---|---|---|
| Storage (medallion) | **CNPG Postgres** `dp-postgres`, schemas `raw`/`curated`/`business` | derived/rebuildable → 1 instance, no PITR |
| Ingestion | **CronJob** (pg COPY prod→raw) | full-refresh; CDC (Debezium→NATS) is Slice 2 |
| Transform | **dbt-postgres** | staging→marts + tests; custom-schema macro so marts land in `business` |
| BI / serve | **Metabase** | own metadata DB on the same CNPG cluster |

ClickHouse/Kafka/Superset/OpenMetadata remain the **future heavier target** (need-first gate) — not
required for a single-source slice.

## The data product — `business.policy_portfolio` (grain = policy)

- **GWP proxy** `annualised_premium_eur` — attacks **P2 (margin/portfolio)**.
- **TIV** `total_insured_amount_eur` — the exposure seed for **P1/P3 (accumulation)**.
- scheduled/paid premium, `coverage_count`, dims `product_code` / `status` / `inception_year`.

Status: pipeline **proven end-to-end** — a seeded `[TEST]` prod policy flows to the mart (GWP €12k / TIV
€1M, kept as a Metabase demo row). It fills with real data as prod policies are created.

## Operate

```bash
# on-demand run (also runs daily 02:00 ingest / 02:30 dbt via CronJobs)
kubectl create job -n data-platform dp-ingest-manual --from=cronjob/dp-ingest-policy
kubectl create job -n data-platform dp-dbt-manual    --from=cronjob/dp-dbt-build
kubectl exec -n data-platform dp-postgres-1 -- psql -U postgres -d analytics -c \
  "SELECT * FROM business.policy_portfolio;"
```

Metabase is provisioned as code by the idempotent `metabase/provision_dashboard.py` in the
[ktayl-data-platform repo](https://github.com/andrelair-platform/ktayl-data-platform); the access model
(Authentik forward-auth at the ingress) is covered on the
[docs site](https://andrelair-platform.github.io/ktayl-data-platform/).

## Gotchas + hardening TODOs

- **Cilium netpol:** a standard NetworkPolicy `ipBlock` doesn't match the kube-apiserver identity → CNPG
  initdb hangs on `10.43.0.1:443`. data-platform uses Ingress-only netpols; harden later with a
  CiliumNetworkPolicy `toEntities: [kube-apiserver, world]`.
- **dbt schema naming:** dbt concatenates target+custom by default (`business_business`) — overridden via
  a `generate_schema_name` macro so marts land in `business`.
- **TODO:** Metabase Authentik SSO (local admin for now); confirm the money/premium (minor-unit +
  installment) assumptions with the Policy domain before the GWP figure is authoritative.

## Next slices

Slice 2 = add a second real source as the next domain ships (generalise ingestion from 2–3 real
pipelines; CDC over batch), then MDM-keyed Customer 360 once MDM exists. See the
[capability map roadmap](../insurance-platform/capability-map).
