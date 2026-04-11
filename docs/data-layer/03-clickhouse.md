---
id: clickhouse
title: ClickHouse (Analytics Warehouse)
sidebar_position: 3
---

# ClickHouse — Columnar Analytics Warehouse

ClickHouse is a column-oriented database built for real-time analytics. It can ingest millions of rows per second from Kafka, execute complex aggregations in milliseconds, and serves as the single source of truth for all analytical workloads.

---

## Why ClickHouse

| Capability | PostgreSQL | ClickHouse |
|---|---|---|
| 1B row aggregation | ~60s | ~0.5s |
| Kafka native ingestion | Via Debezium | Built-in Kafka table engine |
| Columnar storage | ❌ | ✅ (10-50x better compression) |
| Real-time + batch | Batch only | Both |
| SQL dialect | Standard | Extended (array functions, time-series) |
| k8s support | Zalando/CNPG operator | Altinity Operator |

---

## Install Altinity ClickHouse Operator

```bash
# Install the operator
kubectl apply -f https://raw.githubusercontent.com/Altinity/clickhouse-operator/master/deploy/operator/clickhouse-operator-install-bundle.yaml

# Verify
kubectl get pods -n kube-system | grep clickhouse
```

---

## Deploy ClickHouse Cluster

```yaml
# clickhouse-cluster.yaml
apiVersion: clickhouse.altinity.com/v1
kind: ClickHouseInstallation
metadata:
  name: clickhouse
  namespace: data-warehouse
spec:
  configuration:
    clusters:
      - name: data
        layout:
          shardsCount: 1
          replicasCount: 2          # 2 replicas for HA
    users:
      admin/password: ""            # set via secret
      admin/networks/ip: "::/0"
    settings:
      max_memory_usage: 10000000000 # 10 GB per query
      max_concurrent_queries: 100
      background_pool_size: 8
  templates:
    podTemplates:
      - name: clickhouse-pod
        spec:
          containers:
            - name: clickhouse
              image: clickhouse/clickhouse-server:24.1
              resources:
                requests:
                  cpu: "2"
                  memory: "4Gi"
                limits:
                  cpu: "4"
                  memory: "8Gi"
    volumeClaimTemplates:
      - name: data-volume
        spec:
          accessModes:
            - ReadWriteOnce
          storageClassName: longhorn
          resources:
            requests:
              storage: 200Gi
```

```bash
kubectl apply -f clickhouse-cluster.yaml

# Wait for pods
kubectl get pods -n data-warehouse -w

# Connect to ClickHouse
kubectl exec -it -n data-warehouse chi-clickhouse-data-0-0-0 -- \
  clickhouse-client --user admin --password $ADMIN_PASSWORD
```

---

## Create Databases and Tables

```sql
-- Create analytics database
CREATE DATABASE IF NOT EXISTS analytics;
CREATE DATABASE IF NOT EXISTS raw;

-- Raw events table (ingested from Kafka)
CREATE TABLE raw.kafka_orders
(
    order_id    String,
    user_id     String,
    amount      Float64,
    status      String,
    created_at  DateTime,
    _kafka_ts   DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (created_at, order_id)
PARTITION BY toYYYYMM(created_at)
TTL created_at + INTERVAL 90 DAY;   -- auto-expire after 90 days

-- Aggregated orders mart (populated by dbt)
CREATE TABLE analytics.mart_orders
(
    date            Date,
    hour            UInt8,
    total_orders    UInt64,
    total_revenue   Float64,
    avg_order_value Float64,
    unique_users    UInt64
)
ENGINE = ReplacingMergeTree(date)
ORDER BY (date, hour);
```

---

## Kafka Table Engine — Real-Time Ingestion

ClickHouse can read directly from Kafka topics without an ETL job:

```sql
-- Step 1: Kafka source table (reads from topic)
CREATE TABLE raw.kafka_orders_queue
(
    order_id   String,
    user_id    String,
    amount     Float64,
    status     String,
    created_at String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'redpanda-0.redpanda.data-platform.svc:9093',
    kafka_topic_list  = 'orders.order.created',
    kafka_group_name  = 'clickhouse-consumer',
    kafka_format      = 'JSONEachRow',
    kafka_num_consumers = 4;

-- Step 2: Materialized view to move rows into the real table
CREATE MATERIALIZED VIEW raw.kafka_orders_mv TO raw.kafka_orders AS
SELECT
    order_id,
    user_id,
    amount,
    status,
    parseDateTimeBestEffort(created_at) AS created_at
FROM raw.kafka_orders_queue;
```

Once created, ClickHouse continuously consumes from Kafka — no Airflow job needed for real-time data.

---

## Useful ClickHouse Queries

```sql
-- Orders per hour (last 24h)
SELECT
    toStartOfHour(created_at) AS hour,
    count()                   AS orders,
    sum(amount)               AS revenue
FROM raw.kafka_orders
WHERE created_at >= now() - INTERVAL 24 HOUR
GROUP BY hour
ORDER BY hour;

-- Top users by spend
SELECT
    user_id,
    count()     AS order_count,
    sum(amount) AS total_spent
FROM raw.kafka_orders
WHERE created_at >= today() - 30
GROUP BY user_id
ORDER BY total_spent DESC
LIMIT 20;

-- Check Kafka consumer lag
SELECT * FROM system.kafka_consumers;
```

---

## ClickHouse HTTP Interface (for Superset)

```bash
# Test HTTP interface
curl -u admin:$ADMIN_PASSWORD \
  "http://clickhouse-clickhouse.data-warehouse.svc:8123/?query=SELECT+count()+FROM+raw.kafka_orders"

# Create Superset user with read-only access
kubectl exec -it -n data-warehouse chi-clickhouse-data-0-0-0 -- clickhouse-client << 'EOF'
CREATE USER superset
  IDENTIFIED WITH sha256_password BY 'SupersetPass123!'
  HOST ANY;

GRANT SELECT ON analytics.* TO superset;
GRANT SELECT ON raw.* TO superset;
EOF
```

---

## Backup with Clickhouse Backup

```bash
# Install clickhouse-backup sidecar
# Backs up to MinIO (already running for Velero)

# Manual backup
kubectl exec -n data-warehouse chi-clickhouse-data-0-0-0 -- \
  clickhouse-backup create --tables "analytics.*"

# List backups
kubectl exec -n data-warehouse chi-clickhouse-data-0-0-0 -- \
  clickhouse-backup list
```

---

## Ingress / UI Access

ClickHouse ships with a built-in Play UI at port 8123:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: clickhouse-ui
  namespace: data-warehouse
spec:
  ingressClassName: nginx
  rules:
    - host: clickhouse.yourdomain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: clickhouse-clickhouse
                port:
                  number: 8123
```

---

## Done When

```text
✔ 2-replica ClickHouse cluster running with Longhorn storage
✔ Kafka Materialized View consuming orders.order.created in real time
✔ raw.kafka_orders table growing with events
✔ analytics.mart_orders table exists for dbt output
✔ Superset user created with SELECT grants
✔ HTTP interface accessible at clickhouse.yourdomain.com
```
