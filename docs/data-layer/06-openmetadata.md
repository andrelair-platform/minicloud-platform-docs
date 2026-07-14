---
id: openmetadata
title: OpenMetadata (Data Catalog)
sidebar_position: 6
---

:::caution Not yet deployed — planned for a future phase
OpenMetadata has **not been deployed** on this cluster. This is a design reference doc.
:::


# OpenMetadata — Data Catalog, Lineage & Governance

OpenMetadata is the unified data catalog that auto-discovers all data assets (ClickHouse tables, dbt models, Airflow pipelines, Kafka topics), builds an automatic lineage graph, tracks data quality, and provides a searchable catalog for the entire data team.

---

## What OpenMetadata Provides

| Feature | Description |
|---|---|
| **Asset Discovery** | Auto-crawls ClickHouse, Kafka, dbt, Airflow, Superset |
| **Data Lineage** | Visual graph: Kafka → ClickHouse → dbt → Superset |
| **Data Quality** | Define and run tests on table columns |
| **Glossary** | Business terms linked to physical columns |
| **Ownership** | Every table has an owner team and contact |
| **PII Classification** | Auto-tags columns containing PII data |
| **Data Contracts** | Define expectations for producer/consumer agreements |

---

## Install OpenMetadata

```bash
# Add Helm repo
helm repo add open-metadata https://helm.open-metadata.org
helm repo update
```

### values-openmetadata.yaml

```yaml
# values-openmetadata.yaml
openmetadata:
  config:
    authentication:
      provider: "custom-oidc"
      publicKeyUrls:
        - "https://auth.devandre.sbs/application/o/openmetadata/jwks/"
      authority: "https://auth.devandre.sbs/application/o/openmetadata/"
      clientId: "openmetadata"
      callbackUrl: "https://catalog.yourdomain.com/callback"

    authorizer:
      className: "org.openmetadata.service.security.DefaultAuthorizer"
      containerRequestFilter: "org.openmetadata.service.security.JwtFilter"
      initialAdmins:
        - "platform-admin@yourdomain.com"

  ingress:
    enabled: true
    className: nginx
    hosts:
      - host: catalog.yourdomain.com
        paths:
          - path: /
            pathType: Prefix

# OpenMetadata requires MySQL + Elasticsearch
mysql:
  enabled: true
  auth:
    rootPassword: "OpenMetaRoot123!"
    database: openmetadata_db
    username: openmetadata
    password: "OpenMetaPass123!"

elasticsearch:
  enabled: true
  replicas: 1
  resources:
    requests:
      memory: "2Gi"
    limits:
      memory: "3Gi"
```

```bash
kubectl create namespace data-catalog

helm upgrade --install openmetadata open-metadata/openmetadata \
  --namespace data-catalog \
  --values values-openmetadata.yaml \
  --wait --timeout 15m
```

---

## Connect Data Sources (Ingestion Connectors)

### ClickHouse Connector

```yaml
# Via OpenMetadata UI: Settings → Services → Databases → Add New Service
# Or via API:

source:
  type: clickhouse
  serviceName: clickhouse-warehouse
  serviceConnection:
    config:
      type: Clickhouse
      hostPort: "clickhouse-clickhouse.data-warehouse.svc:8123"
      username: superset
      password: "{{ env('CLICKHOUSE_PASSWORD') }}"
      database: analytics

  sourceConfig:
    config:
      type: DatabaseMetadata
      markDeletedTables: true
      includeTables: true
      includeViews: true
      schemaFilterPattern:
        includes:
          - analytics
          - raw

sink:
  type: metadata-rest
  config: {}

workflowConfig:
  openMetadataServerConfig:
    hostPort: "http://openmetadata.data-catalog.svc:8585/api"
    authProvider: openmetadata
    securityConfig:
      jwtToken: "{{ env('OM_JWT_TOKEN') }}"
```

### Kafka/Redpanda Connector

```yaml
source:
  type: redpanda
  serviceName: redpanda-platform
  serviceConnection:
    config:
      type: Redpanda
      bootstrapServers: "redpanda-0.redpanda.data-platform.svc:9093"
      schemaRegistryURL: "http://redpanda-schema-registry.data-platform.svc:8081"

  sourceConfig:
    config:
      type: MessagingMetadata
      topicFilterPattern:
        includes:
          - "orders.*"
          - "payments.*"
          - "users.*"
```

### dbt Connector

```yaml
source:
  type: dbt
  serviceName: dbt-clickhouse
  serviceConnection:
    config:
      type: dbt
      dbtConfigSource:
        dbtConfigType: local
        dbtCatalogFilePath: /dbt/target/catalog.json
        dbtManifestFilePath: /dbt/target/manifest.json
        dbtRunResultsFilePath: /dbt/target/run_results.json
```

### Airflow Connector

```yaml
source:
  type: airflow
  serviceName: airflow-platform
  serviceConnection:
    config:
      type: Airflow
      hostPort: "http://airflow-webserver.automation.svc:8080"
      numberOfStatus: 10
      connection:
        type: Backend
```

---

## Run Ingestion Pipelines

```bash
# Run all connectors via OpenMetadata ingestion framework
kubectl run om-ingestion \
  --image=openmetadata/ingestion:1.3.0 \
  --namespace=data-catalog \
  --restart=Never \
  --rm -it \
  -- python main.py --config /configs/clickhouse-ingestion.yaml
```

Or schedule via the OpenMetadata UI:

```text
Settings → Services → clickhouse-warehouse
→ Ingestion → Add Ingestion
→ Type: Metadata Ingestion
→ Schedule: Every 6 hours
→ Deploy
```

---

## Automatic Data Lineage

After ingesting ClickHouse + dbt + Superset, OpenMetadata auto-builds lineage:

```text
[Kafka Topic]         orders.order.created
        │
        ▼ (Kafka Engine)
[ClickHouse Table]    raw.kafka_orders
        │
        ▼ (dbt stg_orders)
[dbt Model]           analytics.stg_orders
        │
        ▼ (dbt int_order_enriched)
[dbt Model]           analytics.int_order_enriched
        │
        ▼ (dbt mart_orders)
[dbt Model]           analytics.mart_orders
        │
        ▼ (Superset Dataset)
[Superset Dashboard]  Orders KPIs
```

Visible at: `catalog.yourdomain.com → Explore → mart_orders → Lineage`

---

## Data Quality Tests

```yaml
# Via UI: Table → Profiler → Add Test

testSuite:
  name: "orders-quality-suite"
  executableEntityReference: "analytics.mart_orders"

testCases:
  - name: "total_revenue_non_negative"
    testDefinitionName: columnValuesToBeBetween
    columnName: total_revenue
    parameterValues:
      - name: minValue
        value: "0"

  - name: "orders_freshness"
    testDefinitionName: tableRowCountToBeBetween
    parameterValues:
      - name: minValue
        value: "1"
    description: "At least 1 row ingested today"
```

---

## Business Glossary

Link business terms to physical columns:

```text
Glossary → Platform Glossary → + Term
  → Name: "Revenue"
  → Description: "Sum of fulfilled order amounts in USD, excluding refunds"
  → Tag: Finance
  → Related Terms: GMV, Net Revenue

Then: analytics.mart_orders → total_revenue column → Add Glossary Term: "Revenue"
```

---

## PII Auto-Classification

OpenMetadata auto-tags columns matching PII patterns:

```text
user_id     → PII.NonSensitive (identifier)
email       → PII.Sensitive
ip_address  → PII.Sensitive
amount      → Financial
```

These tags feed into OPA policies that restrict direct SELECT access to PII columns.

---

## Done When

```text
✔ OpenMetadata running at catalog.yourdomain.com
✔ Authentik SSO login working
✔ ClickHouse, Kafka, dbt, Airflow all ingested
✔ Full lineage visible: Kafka → ClickHouse → dbt → Superset
✔ Data quality tests passing for mart_orders
✔ Business glossary terms linked to mart columns
✔ PII columns auto-tagged across all datasets
```
