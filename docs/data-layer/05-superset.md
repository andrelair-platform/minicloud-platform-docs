---
id: superset
title: Apache Superset (BI Dashboards)
sidebar_position: 5
---

# Apache Superset — Self-Hosted Business Intelligence

Apache Superset is a modern data visualization platform that connects directly to ClickHouse, provides 40+ chart types, SQL Lab for ad-hoc queries, and row-level security. All dashboards are version-controlled and can be exported as JSON.

---

## Deploy Superset on Kubernetes

```bash
# Add Superset Helm chart
helm repo add superset https://apache.github.io/superset
helm repo update
```

### values-superset.yaml

```yaml
# values-superset.yaml
replicaCount: 2

image:
  tag: "3.1.0"

supersetNode:
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "1"
      memory: "2Gi"

configOverrides:
  secret: |
    SECRET_KEY = '{{ env("SUPERSET_SECRET_KEY") }}'
  my_override: |
    SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://superset:{{ env("SUPERSET_DB_PASS") }}@postgres.data-viz.svc/superset'

    # Enable Keycloak OIDC login
    from flask_appbuilder.security.manager import AUTH_OAUTH
    AUTH_TYPE = AUTH_OAUTH
    OAUTH_PROVIDERS = [
      {
        'name': 'keycloak',
        'token_key': 'access_token',
        'icon': 'fa-key',
        'remote_app': {
          'client_id': 'superset',
          'client_secret': '{{ env("KEYCLOAK_CLIENT_SECRET") }}',
          'server_metadata_url': 'https://keycloak.yourdomain.com/realms/platform/.well-known/openid-configuration',
          'api_base_url': 'https://keycloak.yourdomain.com/realms/platform/',
          'client_kwargs': {'scope': 'openid profile email roles'},
        },
      }
    ]
    AUTH_ROLES_MAPPING = {
      "platform-admin": ["Admin"],
      "platform-analyst": ["Alpha"],
      "platform-viewer": ["Gamma"],
    }
    AUTH_USER_REGISTRATION = True
    AUTH_USER_REGISTRATION_ROLE = "Gamma"

    # ClickHouse connection
    ADDITIONAL_DATABASES = {
      'clickhouse': {
        'sqlalchemy_uri': 'clickhouse+http://superset:SupersetPass123!@clickhouse-clickhouse.data-warehouse.svc:8123/analytics',
      }
    }

    CACHE_CONFIG = {
      'CACHE_TYPE': 'RedisCache',
      'CACHE_DEFAULT_TIMEOUT': 300,
      'CACHE_KEY_PREFIX': 'superset_',
      'CACHE_REDIS_URL': 'redis://redis.data-viz.svc:6379/0',
    }

    DATA_CACHE_CONFIG = CACHE_CONFIG

postgresql:
  enabled: false   # use external Postgres

redis:
  enabled: true

ingress:
  enabled: true
  ingressClassName: nginx
  hosts:
    - host: superset.yourdomain.com
      paths:
        - path: /
          pathType: Prefix

extraEnv:
  SUPERSET_SECRET_KEY:
    valueFrom:
      secretKeyRef:
        name: superset-secrets
        key: secret-key
  SUPERSET_DB_PASS:
    valueFrom:
      secretKeyRef:
        name: superset-secrets
        key: db-password
```

```bash
kubectl create namespace data-viz

# Create secrets
kubectl create secret generic superset-secrets \
  --from-literal=secret-key=$(openssl rand -base64 42) \
  --from-literal=db-password=SupersetDbPass123 \
  --namespace data-viz

# Install
helm upgrade --install superset superset/superset \
  --namespace data-viz \
  --values values-superset.yaml \
  --wait
```

---

## Add ClickHouse as a Database

Via Superset UI:

```text
Settings → Database Connections → + Database
  → Choose: ClickHouse Connect
  → Host:   clickhouse-clickhouse.data-warehouse.svc
  → Port:   8123
  → Database: analytics
  → Username: superset
  → Password: SupersetPass123!
  → Test Connection → Connect
```

Or via CLI:

```bash
kubectl exec -n data-viz deploy/superset -- \
  superset set-database-uri \
    --database-name "ClickHouse Analytics" \
    --uri "clickhouse+http://superset:SupersetPass123!@clickhouse-clickhouse.data-warehouse.svc:8123/analytics"
```

---

## Create a Dataset from a dbt Mart

```text
Datasets → + Dataset
  → Database: ClickHouse Analytics
  → Schema: analytics
  → Table: mart_orders
  → Create Dataset and Create Chart
```

---

## Example Charts

### Revenue Over Time (Line Chart)

```text
Chart type: Line Chart
Dataset:    mart_orders
Metrics:    SUM(total_revenue)
Dimension:  order_date
Filters:    order_date >= DATEADD(DAY, -30, NOW())
```

### Orders by Country (World Map)

```text
Chart type: World Map
Dataset:    mart_orders
Metric:     SUM(total_orders)
Country:    country
```

### KPI Scorecards

```text
Chart type: Big Number with Trendline
Dataset:    mart_orders
Metric:     SUM(total_revenue)
Time grain: Day
Comparison period: 1 week ago
```

---

## SQL Lab — Ad-Hoc Queries

```sql
-- Available at: superset.yourdomain.com/superset/sqllab

-- Top 10 countries by revenue this week
SELECT
    country,
    SUM(total_revenue) AS revenue,
    SUM(total_orders)  AS orders
FROM analytics.mart_orders
WHERE order_date >= today() - 7
GROUP BY country
ORDER BY revenue DESC
LIMIT 10;
```

---

## Dashboard JSON Export / Import

All dashboards can be exported as JSON for version control:

```bash
# Export dashboard to JSON
kubectl exec -n data-viz deploy/superset -- \
  superset export-dashboards \
    --dashboard-ids 1,2,3 \
    --output /tmp/dashboards.json

kubectl cp data-viz/$(kubectl get pod -n data-viz -l app=superset -o jsonpath='{.items[0].metadata.name}'):/tmp/dashboards.json ./dashboards.json

# Import from JSON (on new environment)
kubectl cp ./dashboards.json data-viz/superset-0:/tmp/dashboards.json
kubectl exec -n data-viz deploy/superset -- \
  superset import-dashboards --path /tmp/dashboards.json
```

Store `dashboards.json` in your GitOps repo — ArgoCD can apply it on every sync.

---

## Alerts and Reports

```text
Manage → Alerts & Reports → + Alert
  → Alert name: "Low Order Volume"
  → Chart: Orders KPI (Big Number)
  → Condition: Less than 100
  → Schedule: Every 1 hour
  → Notification: Slack #data-alerts
```

Requires SMTP or Slack webhook configured in `superset_config.py`:

```python
ALERT_REPORTS_NOTIFICATION_DRY_RUN = False
SLACK_API_TOKEN = "{{ env('SLACK_TOKEN') }}"
SMTP_HOST = "smtp.yourdomain.com"
SMTP_PORT = 587
SMTP_USER = "alerts@yourdomain.com"
```

---

## Row-Level Security

Restrict data by user role — each team only sees their own data:

```text
Security → Row Level Security → + Rule
  → Tables: mart_orders
  → Roles: myteam-analyst
  → Clause: country = 'FR'
```

This appends `WHERE country = 'FR'` to every query for users in `myteam-analyst`.

---

## Done When

```text
✔ Superset running at superset.yourdomain.com
✔ Login via Keycloak SSO (roles mapped to Superset roles)
✔ ClickHouse Analytics database connected and tested
✔ mart_orders dataset added
✔ Revenue/Orders/Users dashboards created
✔ Alerts configured for anomaly detection
✔ Dashboards exported to JSON in GitOps repo
```
