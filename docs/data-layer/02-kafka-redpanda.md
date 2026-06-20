---
id: kafka-redpanda
title: Kafka / Redpanda (Event Streaming)
sidebar_position: 2
---

:::caution Not yet deployed — planned for a future phase
Kafka / Redpanda has **not been deployed** on this cluster. This is a design reference doc.
:::


# Kafka / Redpanda — Event Streaming Backbone

Redpanda is a Kafka-compatible streaming platform written in C++ — no JVM, no ZooKeeper, 10x lower latency. It speaks the Kafka protocol natively, so every Kafka client, connector, and tool works without modification.

---

## Why Redpanda Over Kafka

| | Apache Kafka | Redpanda |
|---|---|---|
| Runtime | JVM (high memory) | Native C++ (low overhead) |
| ZooKeeper | Required (Kafka < 3.x) | Not needed |
| Latency | ~5-10ms p99 | ~1ms p99 |
| Kafka API compat | ✅ (it is Kafka) | ✅ full compatibility |
| k8s operator | Strimzi | Redpanda Operator (official) |
| Management UI | Kafka UI / Kowl | Redpanda Console (built-in) |

Use Redpanda for new clusters. Use Kafka if you have existing Strimzi deployments.

---

## Install Redpanda Operator

```bash
# Add Redpanda Helm repo
helm repo add redpanda https://charts.redpanda.com
helm repo update

# Install the CRD operator
helm install redpanda-operator redpanda/operator \
  --namespace redpanda \
  --create-namespace \
  --set image.tag=latest
```

---

## Deploy a 3-Broker Redpanda Cluster

```yaml
# redpanda-cluster.yaml
apiVersion: cluster.redpanda.com/v1alpha1
kind: Redpanda
metadata:
  name: redpanda
  namespace: data-platform
spec:
  chartRef: {}
  clusterSpec:
    statefulset:
      replicas: 3
    resources:
      cpu:
        cores: 2
      memory:
        container:
          max: 4Gi
        redpanda:
          reserveMemory: 512Mi
          memory: 3Gi
    storage:
      persistentVolume:
        enabled: true
        size: 50Gi
        storageClass: longhorn
    external:
      enabled: false
    tls:
      enabled: true
    auth:
      sasl:
        enabled: true
        mechanism: SCRAM-SHA-512
        secretRef: redpanda-superuser
```

```bash
kubectl apply -f redpanda-cluster.yaml

# Wait for all brokers
kubectl rollout status statefulset/redpanda -n data-platform

# Verify cluster health
kubectl exec -n data-platform redpanda-0 -- rpk cluster info
```

---

## Create Topics

```bash
# Exec into a broker pod
kubectl exec -it -n data-platform redpanda-0 -- bash

# Create topics
rpk topic create orders.order.created \
  --partitions 12 \
  --replicas 3

rpk topic create payments.payment.processed \
  --partitions 12 \
  --replicas 3

rpk topic create users.user.registered \
  --partitions 6 \
  --replicas 3

rpk topic create db.postgres.changes \
  --partitions 6 \
  --replicas 3

# List all topics
rpk topic list
```

---

## Produce and Consume (Test)

```bash
# Produce test messages
rpk topic produce orders.order.created << EOF
{"order_id": "ord-001", "user_id": "usr-123", "amount": 99.99, "ts": "2024-01-15T10:00:00Z"}
{"order_id": "ord-002", "user_id": "usr-456", "amount": 249.00, "ts": "2024-01-15T10:01:00Z"}
EOF

# Consume from beginning
rpk topic consume orders.order.created --from-beginning --num 5
```

---

## CDC with Debezium (Database Change Data Capture)

Debezium captures every INSERT/UPDATE/DELETE from PostgreSQL and publishes it as a Kafka event.

### Deploy Debezium Connector

```yaml
# debezium-connector.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: debezium
  namespace: data-platform
spec:
  replicas: 1
  selector:
    matchLabels:
      app: debezium
  template:
    metadata:
      labels:
        app: debezium
    spec:
      containers:
        - name: connect
          image: debezium/connect:2.5
          ports:
            - containerPort: 8083
          env:
            - name: BOOTSTRAP_SERVERS
              value: "redpanda-0.redpanda.data-platform.svc:9093"
            - name: GROUP_ID
              value: "debezium-cluster"
            - name: CONFIG_STORAGE_TOPIC
              value: "debezium.connect.configs"
            - name: OFFSET_STORAGE_TOPIC
              value: "debezium.connect.offsets"
            - name: STATUS_STORAGE_TOPIC
              value: "debezium.connect.status"
```

### Register Postgres Connector

```bash
curl -X POST http://debezium:8083/connectors -H 'Content-Type: application/json' -d '{
  "name": "postgres-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres.myteam-prod.svc",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${POSTGRES_PASSWORD}",
    "database.dbname": "orders",
    "database.server.name": "db",
    "table.include.list": "public.orders,public.payments",
    "plugin.name": "pgoutput",
    "topic.prefix": "db.postgres"
  }
}'

# Check connector status
curl http://debezium:8083/connectors/postgres-connector/status
```

CDC events land in topics like `db.postgres.public.orders` with full before/after row snapshots.

---

## Schema Registry

Enforce Avro/JSON schema compatibility so producers and consumers never break each other:

```bash
# Redpanda includes a built-in Schema Registry
# Available at: http://redpanda-0.redpanda.data-platform.svc:8081

# Register a schema
curl -X POST http://redpanda-schema-registry:8081/subjects/orders.order.created-value/versions \
  -H 'Content-Type: application/json' \
  -d '{
    "schema": "{\"type\":\"record\",\"name\":\"Order\",\"fields\":[{\"name\":\"order_id\",\"type\":\"string\"},{\"name\":\"user_id\",\"type\":\"string\"},{\"name\":\"amount\",\"type\":\"double\"},{\"name\":\"ts\",\"type\":\"string\"}]}"
  }'
```

---

## Redpanda Console (Management UI)

```yaml
# redpanda-console.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redpanda-console
  namespace: data-platform
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redpanda-console
  template:
    metadata:
      labels:
        app: redpanda-console
    spec:
      containers:
        - name: console
          image: redpandadata/console:latest
          env:
            - name: KAFKA_BROKERS
              value: "redpanda-0.redpanda.data-platform.svc:9093"
            - name: KAFKA_SCHEMAREGISTRY_ENABLED
              value: "true"
            - name: KAFKA_SCHEMAREGISTRY_URLS
              value: "http://redpanda-schema-registry:8081"
          ports:
            - containerPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: redpanda-console
  namespace: data-platform
  annotations:
    nginx.ingress.kubernetes.io/auth-url: "https://keycloak.yourdomain.com/auth"
spec:
  ingressClassName: nginx
  rules:
    - host: kafka.yourdomain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: redpanda-console
                port:
                  number: 8080
```

---

## KEDA Integration — Scale on Kafka Lag

Scale consumers automatically based on consumer group lag:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-consumer-scaler
  namespace: myteam-prod
spec:
  scaleTargetRef:
    name: order-consumer
  minReplicaCount: 1
  maxReplicaCount: 20
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: "redpanda-0.redpanda.data-platform.svc:9093"
        consumerGroup: order-processors
        topic: orders.order.created
        lagThreshold: "100"         # scale up when lag > 100 msgs per partition
```

---

## Done When

```text
✔ 3-broker Redpanda cluster running with persistent storage
✔ Topics created with correct partition / replication settings
✔ Debezium capturing changes from Postgres into Kafka topics
✔ Schema Registry enforcing schema compatibility
✔ Redpanda Console accessible at kafka.yourdomain.com
✔ KEDA scales consumers based on topic lag
```
