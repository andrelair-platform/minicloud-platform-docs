---
id: dbt
title: dbt (Data Transformation)
sidebar_position: 4
---

:::caution Not yet deployed — planned for a future phase
dbt has **not been deployed** on this cluster. This is a design reference doc.
:::


# dbt — SQL Transformation Layer

dbt (data build tool) turns raw ClickHouse tables into clean, tested, documented data marts using version-controlled SQL. Every transformation is a SELECT statement — dbt handles the CREATE TABLE/VIEW, testing, and documentation automatically.

---

## How dbt Fits in the Stack

```text
ClickHouse raw tables          dbt models               Superset dashboards
─────────────────────    ──────────────────────    ─────────────────────────
raw.kafka_orders      →  stg_orders            →  mart_orders (KPI dash)
raw.kafka_payments    →  stg_payments          →  mart_revenue (Finance)
raw.kafka_users       →  stg_users             →  mart_user_growth (Product)
                         int_order_enriched
```

---

## dbt Project Structure

```text
dbt/
├── dbt_project.yml           ← project config
├── profiles.yml              ← ClickHouse connection
├── models/
│   ├── staging/              ← 1:1 with source tables, light cleaning
│   │   ├── stg_orders.sql
│   │   ├── stg_payments.sql
│   │   └── stg_users.sql
│   ├── intermediate/         ← joins, enrichments
│   │   └── int_order_enriched.sql
│   └── marts/                ← final aggregated tables for BI
│       ├── finance/
│       │   └── mart_revenue.sql
│       ├── product/
│       │   └── mart_user_growth.sql
│       └── ops/
│           └── mart_orders.sql
├── tests/
│   ├── generic/
│   └── singular/
│       └── assert_revenue_positive.sql
├── macros/
│   └── generate_schema_name.sql
└── seeds/
    └── country_codes.csv
```

---

## Connection Profile (ClickHouse)

```yaml
# profiles.yml (stored as k8s Secret in production)
minicloud:
  target: prod
  outputs:
    prod:
      type: clickhouse
      host: clickhouse-clickhouse.data-warehouse.svc
      port: 8123
      user: dbt_user
      password: "{{ env_var('DBT_PASSWORD') }}"
      schema: analytics
      secure: false
      verify: false
```

---

## Staging Model Example

```sql
-- models/staging/stg_orders.sql
{{
  config(
    materialized='incremental',
    unique_key='order_id',
    incremental_strategy='delete+insert'
  )
}}

SELECT
    order_id,
    user_id,
    amount,
    lower(trim(status))   AS status,
    toDate(created_at)    AS order_date,
    created_at
FROM {{ source('raw', 'kafka_orders') }}
WHERE status IS NOT NULL
  AND amount > 0

{% if is_incremental() %}
  AND created_at > (SELECT max(created_at) FROM {{ this }})
{% endif %}
```

---

## Intermediate Model Example

```sql
-- models/intermediate/int_order_enriched.sql
{{
  config(materialized='view')
}}

SELECT
    o.order_id,
    o.user_id,
    o.amount,
    o.status,
    o.order_date,
    u.country,
    u.user_segment,
    p.payment_method
FROM {{ ref('stg_orders') }} o
LEFT JOIN {{ ref('stg_users') }}    u USING (user_id)
LEFT JOIN {{ ref('stg_payments') }} p USING (order_id)
```

---

## Mart Model Example

```sql
-- models/marts/ops/mart_orders.sql
{{
  config(
    materialized='table',
    engine='ReplacingMergeTree(order_date)',
    order_by='(order_date)'
  )
}}

SELECT
    order_date,
    country,
    user_segment,
    count()                        AS total_orders,
    countIf(status = 'fulfilled')  AS fulfilled_orders,
    sum(amount)                    AS total_revenue,
    avg(amount)                    AS avg_order_value,
    uniqExact(user_id)             AS unique_buyers
FROM {{ ref('int_order_enriched') }}
GROUP BY order_date, country, user_segment
```

---

## Schema Tests

```yaml
# models/staging/schema.yml
version: 2

models:
  - name: stg_orders
    description: "Cleaned orders from Kafka raw table"
    columns:
      - name: order_id
        description: "Unique order identifier"
        tests:
          - unique
          - not_null
      - name: amount
        tests:
          - not_null
          - dbt_utils.expression_is_true:
              expression: ">= 0"
      - name: status
        tests:
          - accepted_values:
              values: ['pending', 'processing', 'fulfilled', 'cancelled', 'refunded']

  - name: mart_orders
    description: "Daily aggregated order metrics by country and segment"
    columns:
      - name: total_revenue
        tests:
          - dbt_utils.expression_is_true:
              expression: ">= 0"
```

---

## Singular Test Example

```sql
-- tests/singular/assert_revenue_positive.sql
-- This test FAILS if any negative revenue exists in the mart

SELECT
    order_date,
    country,
    total_revenue
FROM {{ ref('mart_orders') }}
WHERE total_revenue < 0
```

---

## Run dbt as a Kubernetes Job

```yaml
# dbt-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: dbt-run-daily
  namespace: data-transform
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: dbt
          image: harbor.local/data/dbt-clickhouse:1.7.0
          command: ["dbt", "run", "--profiles-dir", "/profiles", "--project-dir", "/dbt"]
          env:
            - name: DBT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: dbt-secrets
                  key: clickhouse-password
          volumeMounts:
            - name: dbt-source
              mountPath: /dbt
            - name: profiles
              mountPath: /profiles
      volumes:
        - name: dbt-source
          configMap:
            name: dbt-project
        - name: profiles
          secret:
            secretName: dbt-profiles
```

---

## Schedule with Airflow (Phase 16)

```python
# dags/dbt_daily.py
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.job import KubernetesJobOperator
from datetime import datetime

with DAG(
    dag_id='dbt_daily_run',
    schedule_interval='0 6 * * *',    # 06:00 UTC daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    dbt_run = KubernetesJobOperator(
        task_id='dbt_run',
        namespace='data-transform',
        image='harbor.local/data/dbt-clickhouse:1.7.0',
        cmds=['dbt'],
        arguments=['run', '--profiles-dir', '/profiles', '--target', 'prod'],
        env_vars={'DBT_PASSWORD': '{{ var.value.dbt_password }}'},
    )

    dbt_test = KubernetesJobOperator(
        task_id='dbt_test',
        namespace='data-transform',
        image='harbor.local/data/dbt-clickhouse:1.7.0',
        cmds=['dbt'],
        arguments=['test', '--profiles-dir', '/profiles', '--target', 'prod'],
        env_vars={'DBT_PASSWORD': '{{ var.value.dbt_password }}'},
    )

    dbt_run >> dbt_test
```

---

## Generate Documentation

```bash
# Generate and serve dbt docs locally
dbt docs generate
dbt docs serve --port 8080

# In Kubernetes — build and push to Nginx
dbt docs generate
kubectl cp target/manifest.json data-transform/dbt-docs:/usr/share/nginx/html/
kubectl cp target/catalog.json  data-transform/dbt-docs:/usr/share/nginx/html/
```

dbt Docs shows the full DAG of model dependencies and column-level descriptions.

---

## Done When

```text
✔ dbt project connects to ClickHouse analytics database
✔ stg_orders, stg_payments, stg_users models run clean
✔ int_order_enriched joins all three sources
✔ mart_orders populated with daily aggregations
✔ All schema tests pass (unique, not_null, accepted_values)
✔ Airflow DAG runs dbt daily at 06:00 UTC
✔ dbt docs accessible for data team reference
```
