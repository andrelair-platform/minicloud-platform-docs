---
id: loki
title: Phase 21 — Loki + Promtail (logs)
sidebar_position: 1
---

# Phase 21 — Logs: Loki + Promtail

Phase 8 gave us metrics (Prometheus). Phase 21 adds the second leg of
the observability triangle: **logs**. Loki ingests, stores, and
indexes log streams; Promtail ships container logs from each node;
Grafana queries it via LogQL alongside the existing Prometheus
datasource.

The third leg — **traces** (Jaeger / Tempo) — is deliberately deferred.
Single-service apps like podinfo emit single-span trees; tracing only
earns its keep when there's a distributed call graph to follow.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│  All 3 nodes (set-hog, fast-skunk, fast-heron)          │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ kubelet writes container logs to:                │    │
│  │   /var/log/pods/<ns>_<pod>_<uid>/<container>/<n>.log │ │
│  └─────────────────────────────────────────────────┘    │
│                          │                               │
│                          ▼                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ promtail (DaemonSet, 1 per node)                 │    │
│  │   tails the log files                            │    │
│  │   parses CRI format, attaches k8s labels         │    │
│  │   batches + ships to Loki via /loki/api/v1/push  │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  observability namespace                                 │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ loki-0 (single-binary, 1 replica)                │    │
│  │   ingests, indexes, stores log chunks            │    │
│  │   filesystem store: /var/loki/{chunks,rules}     │    │
│  │   30 GiB Longhorn PVC                            │    │
│  │   7-day retention                                │    │
│  └────────────┬────────────────────────────────────┘    │
└───────────────┼─────────────────────────────────────────┘
                │ http://loki.observability.svc:3100
                │
                ▼
        Grafana datasource (provisioned via
        kube-prometheus-stack values)
```

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Loki deploy mode** | `deploymentMode: SingleBinary` | At 3 nodes / ~48 GiB cluster, distributed mode would add 6+ extra pods (distributor, ingester, querier, query-frontend, compactor, index-gateway) for zero benefit. Loki 3.x explicitly recommends single-binary for small clusters. |
| **Log shipper** | `grafana/promtail` DaemonSet | Standard pairing. Lighter than Fluent Bit / Vector at our scale; reads CRI-formatted pod logs directly. |
| **Storage backend** | `filesystem` with 30 GiB Longhorn PVC | Object storage (S3 / GCS) overkill for 3-node cluster. Filesystem on the StatefulSet's PVC is clean. |
| **Retention** | 7 days (`limits_config.retention_period: 168h`) | Fits comfortably in 30 GiB at our log volume. Bumpable later if needed. |
| **Loki Ingress** | None (cluster-internal only) | Loki is queried via Grafana datasource. No reason to expose. |
| **Datasource provisioning** | `grafana.additionalDataSources` in kube-prometheus-stack values | Same auto-provisioning pattern as the existing Prometheus + Alertmanager datasources. |
| **Multi-tenancy** | Disabled (`auth_enabled: false`) | Single-tenant cluster. Multi-tenancy adds X-Scope-OrgID handling for marginal value. |
| **Self-monitoring** | Disabled | Adds Grafana Agent + extra components. ServiceMonitor on the loki Service itself is enough — kube-prometheus-stack picks it up. |

### What's deliberately deferred

| Component | Why deferred | Future home |
|---|---|---|
| **Loki distributed mode** | Single-binary is the right tool at our scale | When/if cluster grows past ~10 nodes |
| **LogQL alerts** (alert on log patterns) | Adds a second alerting source — complicates routing tree. Metrics-based alerts cover the validated pattern. | Future "log-based SLO" phase |
| **Object-store backend (S3/MinIO)** | Filesystem is fine on Longhorn at this scale | When PVC pressure becomes the bottleneck |
| **Multi-tenant routing** | Single-operator cluster | When multi-team workloads exist |
| **Loki's own Helm-bundled Grafana** | We already have Grafana from Phase 8 — wired Loki as an additional datasource | N/A |

---

## Install

`loki-values.yaml`:

```yaml
deploymentMode: SingleBinary

loki:
  auth_enabled: false
  schemaConfig:
    configs:
      - from: 2025-01-01
        store: tsdb
        object_store: filesystem
        schema: v13
        index:
          prefix: loki_index_
          period: 24h
  storage:
    type: filesystem
  commonConfig:
    replication_factor: 1
    path_prefix: /var/loki
  limits_config:
    retention_period: 168h           # 7 days
    allow_structured_metadata: true
    volume_enabled: true
  compactor:
    working_directory: /var/loki/compactor
    delete_request_store: filesystem
    retention_enabled: true
    retention_delete_delay: 2h

singleBinary:
  replicas: 1
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: "1",   memory: 1Gi }
  persistence:
    enabled: true
    storageClass: longhorn
    size: 30Gi

# Disable distributed-mode components.
read:        { replicas: 0 }
write:       { replicas: 0 }
backend:     { replicas: 0 }
chunksCache: { enabled: false }
resultsCache: { enabled: false }
gateway:     { enabled: false }
test:        { enabled: false }
lokiCanary:  { enabled: false }

monitoring:
  selfMonitoring:
    enabled: false
    grafanaAgent: { installOperator: false }
  serviceMonitor: { enabled: true }
  lokiCanary:     { enabled: false }

minio: { enabled: false }
```

`promtail-values.yaml`:

```yaml
config:
  # In single-binary mode (no gateway), point at the loki Service
  # directly. The chart default 'loki-gateway' would 404.
  clients:
    - url: http://loki.observability.svc:3100/loki/api/v1/push
  serverPort: 3101
  positions:
    filename: /run/promtail/positions.yaml
  snippets:
    pipelineStages:
      - cri: {}

resources:
  requests: { cpu: 50m,  memory: 128Mi }
  limits:   { cpu: 200m, memory: 256Mi }

# Promtail must run on every node, including any tainted control planes.
tolerations:
  - operator: Exists
    effect: NoSchedule
  - operator: Exists
    effect: NoExecute

serviceMonitor: { enabled: true }
```

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update grafana

kubectl create namespace observability

helm install loki grafana/loki \
  -n observability -f loki-values.yaml \
  --version 7.0.0 --wait --timeout 6m

helm install promtail grafana/promtail \
  -n observability -f promtail-values.yaml \
  --version 6.17.1 --wait --timeout 4m
```

Expected after install:

```bash
$ kubectl get pods -n observability
NAME             READY   STATUS    RESTARTS
loki-0           2/2     Running   0
promtail-...     1/1     Running   0   ← DaemonSet
promtail-...     1/1     Running   0
promtail-...     1/1     Running   0

$ kubectl get pvc -n observability
storage-loki-0   30Gi   Longhorn  Bound
```

---

## Wire Loki as a Grafana datasource

In `kube-prometheus-stack-values.yaml` add under `grafana:`:

```yaml
grafana:
  ...
  additionalDataSources:
    - name: Loki
      type: loki
      access: proxy
      url: http://loki.observability.svc:3100
      isDefault: false
      editable: false
      jsonData:
        maxLines: 1000
        timeout: 60
```

Then `helm upgrade kube-prometheus-stack`. Verify in Grafana → Configuration → Datasources, or via API:

```bash
GRAFANA_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana -o name | head -1)
kubectl exec -n monitoring $GRAFANA_POD -c grafana -- \
  curl -sf "http://localhost:3000/api/datasources" \
  -u "admin:$(cat ~/.grafana-admin)" | jq '[.[] | {name, type}]'
# [
#   {"name":"Alertmanager","type":"alertmanager"},
#   {"name":"Loki","type":"loki"},
#   {"name":"Prometheus","type":"prometheus"}
# ]
```

---

## Two real install gotchas

### 1. Loki 3.6 schema rejects `chunks_directory` / `rules_directory`

```text
failed parsing config: line 75: field chunks_directory not found in
type local.FSConfig
```

Older docs and AI suggestions write:
```yaml
storage_config:
  filesystem:
    chunks_directory: /var/loki/chunks
    rules_directory: /var/loki/rules
```

In Loki 3.6 those keys moved. The minimal config that works:

```yaml
loki:
  storage: { type: filesystem }
  commonConfig:
    replication_factor: 1
    path_prefix: /var/loki
```

The chart resolves the rest from `path_prefix`.

### 2. Promtail's chart default `client.url` is `loki-gateway` — wrong for single-binary

When `gateway.enabled: false` (which we set, because the gateway is overkill at our scale), the `loki-gateway` Service doesn't exist and Promtail gets:

```text
error="Post http://loki-gateway.observability.svc/loki/api/v1/push:
dial tcp: lookup loki-gateway... : no such host"
```

Fix: override the client URL to hit the loki Service directly:

```yaml
config:
  clients:
    - url: http://loki.observability.svc:3100/loki/api/v1/push
```

---

## Verification

```bash
# Port-forward Loki briefly
kubectl port-forward -n observability svc/loki 3100:3100 &

# What labels exist?
curl -s http://localhost:3100/loki/api/v1/labels | jq '.data'
# ["app","component","container","filename","instance","job","namespace",
#  "node_name","pod","service_name","stream"]

# Which namespaces have logs?
curl -s http://localhost:3100/loki/api/v1/label/namespace/values | jq '.data'
# ["ai","argocd","backstage","cert-manager","chaos-mesh","harbor",
#  "ingress-nginx","keda","kube-system","longhorn-system","messaging",
#  "metallb-system","monitoring","observability","velero"]

# Ingestion metrics
curl -s http://localhost:3100/metrics | \
  grep -E "^loki_distributor_lines_received_total|^loki_ingester_streams_created_total"
# loki_distributor_lines_received_total{...} 316155
# loki_ingester_streams_created_total{tenant="fake"} 83
```

### Useful LogQL queries

| Goal | Query |
|---|---|
| All NGINX Ingress logs | `{namespace="ingress-nginx"}` |
| HTTP 4xx/5xx responses | `{namespace="ingress-nginx"} \|~ "(?i) (4\|5)\\d\\d "` |
| Upstream / connection errors | `{namespace="ingress-nginx"} \|~ "upstream\|connect.*failed\|timed out"` |
| Application errors anywhere | `{namespace=~".+"} \|= "level=error"` |
| Container restart events | `{namespace="kube-system", app="coredns"} \|= "Restarting"` |
| Volume per namespace (5m) | `sum by (namespace) (rate({namespace=~".+"}[5m]))` |
| Error rate per app | `sum by (app) (rate({namespace=~".+"} \|= "error"[5m]))` |

In Grafana, navigate to **Explore → Loki**, paste any query, and click "Run query."

---

## Done When

```text
✔ 1 loki-0 + 3 promtail pods Running in observability namespace
✔ 30 GiB Longhorn PVC Bound
✔ /loki/api/v1/labels returns >= 8 labels
✔ /loki/api/v1/label/namespace/values lists every cluster namespace
✔ Grafana shows 3 datasources: Prometheus, Alertmanager, Loki
✔ Grafana Explore → Loki returns log lines for {namespace="ingress-nginx"}
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Single-binary vs distributed mode tradeoff** | Senior infra interview question. Choosing single-binary on a 3-node cluster — and being able to articulate why distributed mode adds 6+ pods for no gain at this scale — is the kind of right-sized decision senior engineers make. |
| **DaemonSet log shipping pattern** | Same shape as Fluent Bit, Vector, Datadog Agent, Splunk Universal Forwarder. The host/container log-tailing pattern is universal. |
| **LogQL fluency** | LogQL is structurally similar to PromQL but for logs. `{label="value"} \|= "string"` / `\|~ "regex"` / `\|= "" \| json` chains are the daily bread-and-butter of any production logging shop. |
| **Schema gotcha debugging** | The "chunks_directory not found" error is a real-world version-skew gap. Reading the upstream config docs vs the chart's rendered values is a senior debugging skill. |
| **Three-datasource correlation in Grafana** | Modern Grafana lets you click a span in a trace, jump to the matching log, jump to the matching metric. Even without Jaeger we have two-of-three: metrics ↔ logs correlated via `{namespace=...}` labels. |
| **Senior scope reduction (defer Jaeger)** | Distributed tracing without distributed services = single-span boxes. Knowing not to install Jaeger here is the same call as deferring MLflow without ML pipelines. |
