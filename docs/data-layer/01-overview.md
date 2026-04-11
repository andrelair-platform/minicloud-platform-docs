---
id: data-layer-overview
title: Data Layer Overview
sidebar_position: 1
---

# Data Layer — Complete Enterprise Data Platform

The data layer transforms raw events from your platform into actionable business intelligence. It covers the full chain: event ingestion → storage → transformation → orchestration → visualization → governance.

---

## Complete Data Chain

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                  │
│  Microservices  │  Databases (CDC)  │  Logs  │  k8s Metrics         │
└────────┬────────┴────────┬──────────┴───┬────┴────────┬─────────────┘
         │                 │              │              │
         ▼                 ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    INGESTION (Kafka / Redpanda)                      │
│   Topics: events.orders  events.users  db.changes  platform.logs    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
┌─────────────────────────┐      ┌──────────────────────────┐
│  Stream Processing      │      │  Batch Loading           │
│  (Kafka Streams / KSQL) │      │  (Airflow → ClickHouse)  │
└────────────┬────────────┘      └─────────────┬────────────┘
             │                                 │
             └──────────────┬──────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STORAGE (ClickHouse)                              │
│   raw_events  │  orders  │  users  │  metrics  │  audit_logs        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  TRANSFORMATION (dbt)                                │
│   staging →  intermediate →  marts (finance, product, ops)          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────────┐   ┌────────────────────────────┐
│   VISUALIZATION         │   │   GOVERNANCE               │
│   Apache Superset       │   │   OpenMetadata             │
│   Dashboards / Alerts   │   │   Catalog / Lineage        │
└─────────────────────────┘   └────────────────────────────┘
```

---

## Stack Components

| Component | Role | Why This One |
|---|---|---|
| **Kafka / Redpanda** | Event streaming backbone + CDC | Industry standard; Redpanda is Kafka-compatible without JVM |
| **ClickHouse** | Columnar analytics warehouse | 100-1000x faster than Postgres for analytics; native Kubernetes support |
| **dbt** | SQL transformation layer | Version-controlled, tested SQL; model dependency DAGs |
| **Apache Airflow** | Pipeline orchestration | Already in Phase 16; reused for data pipeline scheduling |
| **Apache Superset** | Self-hosted BI & dashboards | 40+ chart types; OIDC login via Keycloak |
| **OpenMetadata** | Data catalog, lineage, quality | Unified governance; auto-discovers ClickHouse, dbt, Airflow |

---

## Data Namespace Layout

```bash
kubectl get namespaces | grep data
# data-platform        kafka, redpanda, schema-registry
# data-warehouse       clickhouse
# data-transform       dbt (k8s Job / Airflow tasks)
# data-viz             superset
# data-catalog         openmetadata
```

---

## Kafka Topic Naming Convention

```text
<domain>.<entity>.<event-type>

Examples:
  orders.order.created
  orders.order.fulfilled
  payments.payment.processed
  users.user.registered
  platform.k8s.pod-started
  db.postgres.changes           ← CDC via Debezium
```

---

## Data Flow: Order Processing Example

```text
1. Order service publishes to Kafka topic: orders.order.created
2. ClickHouse Kafka engine ingests rows in real time
3. Airflow triggers dbt daily run at 06:00 UTC
4. dbt builds mart_orders (aggregated, enriched)
5. Superset dashboard "Orders KPIs" auto-refreshes
6. OpenMetadata shows lineage: kafka → clickhouse → dbt → superset
```

---

## Infrastructure Requirements

| Component | CPU | Memory | Storage | Notes |
|---|---|---|---|---|
| Redpanda (3 brokers) | 2 CPU each | 4 Gi each | 50 Gi SSD | Use Longhorn storage class |
| ClickHouse | 4 CPU | 8 Gi | 200 Gi | ReplicatedMergeTree for HA |
| dbt | 0.5 CPU | 512 Mi | — | Runs as k8s Job / Airflow task |
| Superset | 1 CPU | 2 Gi | 10 Gi | Postgres for metadata |
| OpenMetadata | 2 CPU | 4 Gi | 20 Gi | Elasticsearch + MySQL backend |

---

## Done When

```text
✔ Kafka topics receive events from at least one microservice
✔ ClickHouse ingesting from Kafka in real time
✔ dbt models transform raw → mart tables on schedule
✔ Superset dashboard shows live order/user metrics
✔ OpenMetadata catalogs all datasets with lineage
```
