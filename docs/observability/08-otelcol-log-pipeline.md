---
id: otelcol-log-pipeline
title: OTel Collector Log Pipeline — Stack-Agnostic Log Shipping
sidebar_position: 8
---

# OTel Collector Log Pipeline — Stack-Agnostic Log Shipping

Phase 21 deployed Promtail as the log shipping DaemonSet. Promtail works, but it is Loki-specific: its pipeline stages, tenant configuration, and label mapping are all written against Loki's push API. Switching to Elasticsearch, Datadog, or a different Loki deployment requires rewriting the agent config from scratch.

This page documents the migration to **OpenTelemetry Collector contrib** as the log collection agent. All parsing, enrichment, and normalization logic now lives in the OTel `transformprocessor` using OTTL (OpenTelemetry Transformation Language). The only backend-specific block is the exporter — swapping Loki for any OTLP-compatible sink requires changing one YAML stanza.

The migration also resolves two observability gaps:

- **Gap 1 — Kopia cardinality bomb:** Kopia maintenance CronJobs produce a unique pod name per run (`<ns>-default-kopia-maintain-job-<unix_ms>`), creating a new Loki stream per execution. OTTL normalizes these to the static label `kopia-job`.
- **Gap 2 — Structured level extraction:** Services emit JSON (`backstage`, `authentik`) or logfmt (`argocd`, Go services) with a `level` field, but Promtail had no pipeline stage extracting it to a Loki stream label. OTTL extracts, normalizes, and promotes `level` to a stream label so Grafana queries like `{namespace="argocd",level="error"}` work natively.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Each cluster node (5/5: set-hog, fast-skunk, fast-heron,          │
│                     star-kitten, swift-mac)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ /var/log/pods/<ns>_<pod>_<uid>/<container>/0.log             │  │
│  │   containerd CRI format: <rfc3339> <stream> F <json-body>    │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                               │                                     │
│  ┌────────────────────────────▼─────────────────────────────────┐  │
│  │ otelcol DaemonSet (otel/opentelemetry-collector-contrib)      │  │
│  │                                                               │  │
│  │  filelogreceiver                                              │  │
│  │    container operator → parses CRI format, extracts           │  │
│  │      k8s.namespace.name, k8s.pod.name, k8s.pod.uid,          │  │
│  │      k8s.container.name from file path                        │  │
│  │  k8sattributesprocessor                                       │  │
│  │    enriches records with pod metadata via k8s API             │  │
│  │    extracts pod labels: app, app.kubernetes.io/name           │  │
│  │  transformprocessor (OTTL)                                    │  │
│  │    ① copy OTel semantic names to short names (namespace,      │  │
│  │       pod, container, node_name) — Grafana compat             │  │
│  │    ② Gap 1: normalize Kopia pod names → "kopia-job"           │  │
│  │    ③ Gap 2: extract level from JSON / logfmt, normalize       │  │
│  │  batchprocessor                                               │  │
│  │  otlphttp/loki exporter                                       │  │
│  │    → http://loki.observability.svc:3100/otlp/v1/logs          │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  OTLP (HTTP/protobuf)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  observability namespace                                            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ loki-0 (single-binary, 1 replica)                            │  │
│  │   OTLP endpoint: /otlp/v1/logs (native Loki 3.x)            │  │
│  │   limits_config.otlp_config promotes resource attributes     │  │
│  │   to stream labels: namespace, pod, container, node_name,    │  │
│  │   app, job, level                                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Why this is stack-agnostic

The key architectural property is the **separation of concerns**:

```
filelogreceiver   → collects raw log bytes
k8sattributes     → enriches with k8s metadata (never changes)
transform (OTTL)  → parses, normalizes, derives labels (never changes)
batchprocessor    → buffers for efficiency (never changes)
otlphttp/loki     ← the only backend-specific block
```

To migrate from Loki to Elasticsearch:

```yaml
# Before
exporters:
  otlphttp/loki:
    logs_endpoint: http://loki.observability.svc:3100/otlp/v1/logs

# After
exporters:
  elasticsearch:
    endpoints: [https://elasticsearch.svc:9200]
    index: minicloud-logs-%{+yyyy.MM.dd}
```

Every processor above stays identical.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Collector** | `otelcol-contrib 0.156.0` | Contrib distribution includes `filelogreceiver`, `k8sattributesprocessor`, `transformprocessor` — the three components this pipeline needs. Contrib vs core is a distribution choice, not a version choice. |
| **Receiver** | `filelogreceiver` with `container` operator | The `container` operator understands the k3s containerd CRI log format (`<rfc3339> <stream> F <body>`) and parses k8s metadata from the file path — same data Promtail extracted, same files. |
| **Pod metadata enrichment** | `k8sattributesprocessor` | Looks up pod labels from the k8s API using the `k8s.pod.uid` resource attribute extracted from the file path. Avoids duplicating pod metadata in the OTel config. |
| **Transformation language** | OTTL (`transformprocessor`) | OTTL is the OTel standard. `replace_match`, `ParseJSON`, `ExtractPatterns`, `ConvertCase` cover everything this pipeline needs. Error handling via `error_mode: ignore`. |
| **Exporter** | `otlphttp/loki` | `lokiexporter` was removed in otelcol-contrib 0.150+. Loki 3.x has a native OTLP endpoint (`/otlp/v1/logs`) that accepts logs directly — no translation layer needed. |
| **Stream labels** | `loki.limits_config.otlp_config` | Loki's `otlp_config` block declares which OTel resource/log attributes become Loki stream labels when logs arrive via OTLP. Cleaner than the Promtail `relabel_configs` / `pipeline_stages` equivalent. |
| **runAsUser** | `0` (root) | `/var/log/pods/` files are `root:root 640`; `/var/lib/otelcol` (file_storage checkpoint dir) is created `root:root 755` by kubelet. `observability` ns is excluded from the `k8srequirenonroot` Gatekeeper constraint. `allowPrivilegeEscalation: false` + `capabilities.drop: [NET_RAW]` still apply. |

---

## Configuration

### otelcol-values.yaml

```yaml
mode: daemonset
image:
  repository: otel/opentelemetry-collector-contrib
  tag: "0.156.0"

serviceAccount:
  create: true
  name: otelcol

clusterRole:
  create: false  # managed manually in manifests/otelcol/00-rbac.yaml

resources:
  limits: {cpu: 200m, memory: 256Mi}
  requests: {cpu: 50m, memory: 128Mi}

tolerations:
  - operator: Exists  # run on all nodes including tainted ones

# observability is excluded from k8srequirenonroot — root required for log access
# allowPrivilegeEscalation:false + NET_RAW drop satisfy the remaining constraints
securityContext:
  runAsUser: 0
  allowPrivilegeEscalation: false
  capabilities:
    drop: [NET_RAW]

ports:
  otlp:           {enabled: false}
  otlp-http:      {enabled: false}
  jaeger-compact: {enabled: false}
  jaeger-thrift:  {enabled: false}
  jaeger-grpc:    {enabled: false}
  zipkin:         {enabled: false}
  metrics:        {enabled: true, containerPort: 8888, servicePort: 8888, protocol: TCP}

podMonitor:
  enabled: true
  metricsEndpoints:
    - {port: metrics, interval: 30s}

extraVolumes:
  - name: varlogpods
    hostPath: {path: /var/log/pods}
  - name: filestore
    hostPath: {path: /var/lib/otelcol, type: DirectoryOrCreate}

extraVolumeMounts:
  - {name: varlogpods, mountPath: /var/log/pods, readOnly: true}
  - {name: filestore,  mountPath: /var/lib/otelcol}

config:
  extensions:
    health_check: {endpoint: 0.0.0.0:13133}
    file_storage: {directory: /var/lib/otelcol}  # checkpoint positions (replaces Promtail's positions.yaml)

  receivers:
    filelog:
      include: [/var/log/pods/*/*/*.log]
      exclude: [/var/log/pods/observability_otelcol*/*.log]  # prevent self-loop
      start_at: beginning
      include_file_path: true
      storage: file_storage
      operators:
        - type: container  # parses CRI format + extracts k8s.namespace.name, pod.name, pod.uid, container.name from file path
          id: container-parser
          max_log_size: 102400

  processors:
    memory_limiter:
      check_interval: 5s
      limit_mib: 200
      spike_limit_mib: 50

    k8sattributes:
      auth_type: serviceAccount
      extract:
        metadata: [k8s.namespace.name, k8s.pod.name, k8s.pod.uid, k8s.node.name, k8s.container.name]
        labels:
          - {tag_name: app, key: app,                     from: pod}  # Kustomize services (platform-demo, minicloud-plane)
          - {tag_name: app, key: app.kubernetes.io/name,  from: pod}  # Helm services (backstage, argocd, authentik)
      pod_association:
        - sources: [{from: resource_attribute, name: k8s.pod.uid}]  # uid parsed from file path by container operator

    transform:
      error_mode: ignore  # parse failures on non-JSON/non-logfmt lines are silent — no level label is set (correct behavior)
      log_statements:
        - context: log
          statements:
            # ── 1. Short-name attributes (Grafana backward compat) ──────────────
            # Promtail used "namespace", "pod", etc. as stream label names.
            # Copy OTel semantic names to those short names so Grafana queries work
            # unchanged after the migration.
            - 'set(resource.attributes["namespace"], resource.attributes["k8s.namespace.name"])'
            - 'set(resource.attributes["pod"],       resource.attributes["k8s.pod.name"])'
            - 'set(resource.attributes["node_name"], resource.attributes["k8s.node.name"])'
            - 'set(resource.attributes["container"], resource.attributes["k8s.container.name"])'

            # ── 2. Gap 1: Kopia CronJob name normalization ──────────────────────
            # Kopia maintenance runs produce: "<ns>-default-kopia-maintain-job-<unix_ms>"
            # Each run creates a unique stream → cardinality bomb.
            # Collapse to "kopia-job" regardless of namespace or timestamp.
            # Note: \\d in YAML → \\d in config → OTTL processes → \d in RE2 (digit class)
            - 'replace_match(resource.attributes["app"], "^.+-kopia-[a-z]+-job-\\d+$", "kopia-job")'
            # Derive "job" = "namespace/app" (must run after normalization above)
            - 'set(resource.attributes["job"], Concat([resource.attributes["namespace"], resource.attributes["app"]], "/")) where resource.attributes["namespace"] != nil and resource.attributes["app"] != nil'

            # ── 3. Gap 2a: JSON services (backstage, authentik) ────────────────
            # ParseJSON returns nil on non-JSON lines; nil["level"] = nil;
            # set(attr, nil) is a no-op → safe for mixed-format pods.
            - 'set(attributes["level"], ParseJSON(body)["level"]) where IsMatch(resource.attributes["namespace"], "^(backstage|authentik)$")'

            # ── 3. Gap 2b: logfmt services (argocd, own Go services) ───────────
            # ArgoCD zerolog emits: time="..." level=info msg="..."
            # Own Go services: logfmt on request paths, stdlib on startup (no level= → nil → no-op)
            # \\s in YAML → \s in RE2 (whitespace class)
            - 'set(attributes["level"], ExtractPatterns(body, "level=(?P<level>[^\\s\"]+)")["level"]) where IsMatch(body, "level=") and IsMatch(resource.attributes["namespace"], "^(argocd|minicloud-plane-dev|platform-demo-dev|platform-demo-staging|platform-demo-prod)$")'

            # ── 3. Gap 2c: normalize level values ─────────────────────────────
            # Python/structlog uses "WARNING" (uppercase); normalize everything to lowercase.
            # "warning" → "warn" so {level="warn"} catches both conventions.
            - 'set(attributes["level"], ConvertCase(attributes["level"], "lower")) where attributes["level"] != nil'
            - 'replace_pattern(attributes["level"], "^warning$", "warn")'

    batch:
      send_batch_size: 1000
      timeout: 5s

  exporters:
    # Only this block is backend-specific. Replace with elasticsearch, otlp, datadog, etc.
    # to change backends without touching any processor above.
    otlphttp/loki:
      logs_endpoint: http://loki.observability.svc:3100/otlp/v1/logs
      tls: {insecure: true}

  service:
    extensions: [health_check, file_storage]
    pipelines:
      logs:
        receivers:  [filelog]
        processors: [memory_limiter, k8sattributes, transform, batch]
        exporters:  [otlphttp/loki]
    telemetry:
      logs: {level: warn}
```

### Loki otlp_config (in loki-values.yaml)

When logs arrive via OTLP, Loki promotes the attributes declared in `otlp_config` to stream labels:

```yaml
loki:
  limits_config:
    allow_structured_metadata: true
    otlp_config:
      resource_attributes:
        attributes_config:
          - action: index_label
            attributes:
              - namespace    # short name set by OTTL from k8s.namespace.name
              - pod
              - node_name
              - container
              - app          # extracted from pod label by k8sattributes
              - job          # derived by OTTL: "namespace/app"
      log_attributes:        # note: flat list, NOT a map with attributes_config
        - action: index_label
          attributes:
            - level          # extracted and normalized by OTTL Gap 2
```

### RBAC (manifests/otelcol/00-rbac.yaml)

The `k8sattributesprocessor` calls the k8s API to look up pod metadata. It needs a ClusterRole:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: otelcol-k8s-attributes
rules:
  - apiGroups: [""]
    resources: [pods, namespaces, nodes, replicationcontrollers, services, endpoints]
    verbs: [get, list, watch]
  - apiGroups: [apps]
    resources: [replicasets, deployments, statefulsets, daemonsets]
    verbs: [get, list, watch]
  - apiGroups: [batch]
    resources: [jobs, cronjobs]
    verbs: [get, list, watch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: otelcol-k8s-attributes
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: otelcol-k8s-attributes
subjects:
  - kind: ServiceAccount
    name: otelcol
    namespace: observability
```

---

## Gap 1 — Kopia cardinality

### The problem

Velero uses Kopia for volume backups. Each Kopia maintenance CronJob creates a pod named:

```
<namespace>-default-kopia-maintain-job-1753091234567
```

The `app` label is set to this full pod name. Each backup run adds a new unique value to the `app` Loki stream label, creating one new stream per execution — indefinitely. Across all namespaces with Longhorn PVCs, this compounds quickly.

### The fix

One OTTL `replace_match` statement:

```
replace_match(resource.attributes["app"], "^.+-kopia-[a-z]+-job-\\d+$", "kopia-job")
```

All Kopia maintenance pods across all namespaces now produce the stream `{app="kopia-job"}`. Before this, each individual run produced its own stream.

:::note OTTL regex escape in YAML
`\\d` in YAML single-quoted strings → `\\d` in the parsed config → OTTL processes `\\` → `\` → RE2 receives `\d` (digit character class). Writing `\d` (single backslash) causes OTTL to reject it as an unrecognized escape sequence at startup. Same rule applies to `\s` → `\\s`.
:::

---

## Gap 2 — Structured level extraction

### Log format inventory

| Namespace | Format | level field |
|-----------|--------|-------------|
| `backstage` | NDJSON (winston) | `{"level":"info","message":"..."}` |
| `authentik` | NDJSON (structlog) | `{"level":"warning","event":"..."}` |
| `argocd` | logfmt (zerolog) | `time="..." level=info msg="..."` |
| `minicloud-plane-dev` | logfmt (Go) | `time="..." level=info method=GET ...` |
| `platform-demo-*` | logfmt (Go) | same |
| `nats`, `vault`, `harbor` | Custom bracket/mixed | skipped — no `level=` key or insufficient signal |

### OTTL extraction

**JSON services** — `ParseJSON` returns nil on non-JSON lines; `nil["level"]` = nil; `set(attr, nil)` is a no-op. No guard clause needed — `error_mode: ignore` makes parse failures silent:

```
set(attributes["level"], ParseJSON(body)["level"])
  where IsMatch(resource.attributes["namespace"], "^(backstage|authentik)$")
```

**logfmt services** — `ExtractPatterns` returns nil when the named group does not match, so startup lines (`2024/01/01 init complete`) without a `level=` token produce no level label:

```
set(attributes["level"], ExtractPatterns(body, "level=(?P<level>[^\\s\"]+)")["level"])
  where IsMatch(body, "level=")
  and IsMatch(resource.attributes["namespace"], "^(argocd|minicloud-plane-dev|...)$")
```

**Normalization** — Authentik's structlog emits `"WARNING"` (Python convention). Two OTTL statements normalize everything:

```
set(attributes["level"], ConvertCase(attributes["level"], "lower")) where attributes["level"] != nil
replace_pattern(attributes["level"], "^warning$", "warn")
```

### Result

Grafana LogQL queries that were previously impossible or required regex workarounds:

```logql
# Errors in any namespace
{level="error"}

# ArgoCD warnings
{namespace="argocd", level="warn"}

# Error rate per namespace (metric query)
sum by (namespace) (count_over_time({level="error"}[5m]))
```

---

## Verification

```bash
# 1. DaemonSet pods — all 5 nodes
kubectl get pods -n observability -l app.kubernetes.io/name=opentelemetry-collector
# NAME                                          READY   STATUS    RESTARTS
# otelcol-opentelemetry-collector-agent-4pdgw   1/1     Running   0
# otelcol-opentelemetry-collector-agent-77qs2   1/1     Running   0
# otelcol-opentelemetry-collector-agent-8kgzp   1/1     Running   0
# otelcol-opentelemetry-collector-agent-b7b9q   1/1     Running   0
# otelcol-opentelemetry-collector-agent-gwtks   1/1     Running   0

# 2. Loki stream labels — verify all expected labels present
kubectl port-forward -n observability svc/loki 3100:3100 &
curl -s http://localhost:3100/loki/api/v1/labels | jq '.data'
# ["app","container","job","level","namespace","node_name","pod","stream",...]
kill %1

# 3. Gap 1 — kopia label (not kopia-maintain-job-<timestamp>)
curl -s http://localhost:3100/loki/api/v1/label/app/values | jq '.data | map(select(test("kopia")))'
# ["kopia-job"]

# 4. Gap 2 — level values
curl -s http://localhost:3100/loki/api/v1/label/level/values | jq '.data'
# ["debug","error","info","warn"]

# 5. Gap 2 — logfmt extraction (ArgoCD)
curl -sg 'http://localhost:3100/loki/api/v1/query_range?query=\{namespace="argocd",level="info"\}&limit=1&since=5m' \
  | jq '.data.result[0].stream.level'
# "info"
```

---

## Gotchas

### 1. lokiexporter removed in otelcol-contrib 0.150+

The `lokiexporter` component was removed from opentelemetry-collector-contrib in version 0.150.0. Any config using `exporters: loki:` will fail at startup with:

```
exporters: unknown type: "loki"
(valid values: [azure_blob, faro, otlp, elasticsearch, ...])
```

Loki 3.x accepts native OTLP — use `otlphttp/loki` instead:

```yaml
exporters:
  otlphttp/loki:
    logs_endpoint: http://loki.observability.svc:3100/otlp/v1/logs
    tls: {insecure: true}
```

The `otlphttp` exporter type appends `/v1/logs` automatically when only `logs_endpoint` is set (as opposed to `endpoint` which would need the full path).

### 2. OTTL regex escapes in YAML

In YAML (both single-quoted and double-quoted strings), `\d` and `\s` are passed literally to the OTTL config parser. OTTL treats `\d` as an unrecognized escape sequence and fails at startup:

```
invalid configuration: processors::transform: statement has invalid syntax:
1:43: invalid quoted string "...": invalid syntax
```

The chain: **YAML `\\d`** → config string `\\d` → **OTTL processes `\\` → `\`** → RE2 receives `\d` → digit class ✓

Always write `\\d`, `\\s`, `\\w` in OTTL regex literals inside YAML.

### 3. otelcol non-root user cannot read pod logs

otelcol-contrib images run as user 10001 by default. Pod log files at `/var/log/pods/` are `root:root 640`. The `file_storage` checkpoint directory created by kubelet at `/var/lib/otelcol` is `root:root 755`. Both are inaccessible to non-root.

```
storage client: open /var/lib/otelcol/receiver_filelog_: permission denied
```

Set `securityContext.runAsUser: 0` in the DaemonSet. The `observability` namespace is excluded from the `k8srequirenonroot` Gatekeeper constraint. Continue setting `allowPrivilegeEscalation: false` and `capabilities.drop: [NET_RAW]` — those constraints apply regardless.

### 4. Loki otlp_config schema: log_attributes is a flat list

Loki's `OTLPConfig` type has asymmetric sub-types:

```go
type OTLPConfig struct {
    ResourceAttributes ResourceAttributesConfig   // struct with ignore_defaults + attributes_config
    LogAttributes      []AttributesConfig          // direct list — no wrapper
    ScopeAttributes    []AttributesConfig          // direct list — no wrapper
}
```

Using `attributes_config:` under `log_attributes` as if it were a struct causes Loki to fail at startup:

```
cannot unmarshal !!map into []push.AttributesConfig
```

Correct format:

```yaml
otlp_config:
  resource_attributes:
    attributes_config:          # ← wrapper required here (it's a struct)
      - action: index_label
        attributes: [namespace, pod, ...]
  log_attributes:               # ← direct list, no wrapper
    - action: index_label
      attributes: [level]
```

### 5. service.telemetry.metrics.address deprecated in 0.150+

If you have `service.telemetry.metrics.address: 0.0.0.0:8888` from an older config, remove it. The field was removed in 0.150+ and causes startup failure. The Helm chart handles port 8888 exposure via `ports.metrics` without needing a config reference.

---

## Done When

```text
✔ 5/5 otelcol DaemonSet pods Running (one per node)
✔ /loki/api/v1/labels returns namespace, pod, container, node_name, app, job, level
✔ {namespace="argocd",level="info"} returns ArgoCD log lines
✔ label/app/values contains "kopia-job" (not timestamp-suffixed names)
✔ label/level/values contains info, warn (error/debug appear when those levels are present)
✔ Promtail DaemonSet absent from cluster (ArgoCD pruned after apps/promtail.yaml deleted)
✔ Grafana existing dashboards work unchanged (namespace, pod labels preserved)
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|-------|-----------------|
| **Stack-agnostic pipeline design** | Decoupling parsing from the sink is the standard pattern in production log pipelines (Fluent Bit → multiple outputs, Vector → sinks, OTel Collector → exporters). The ability to swap Loki for Elasticsearch without rewriting parsing logic is directly transferable to any enterprise observability stack. |
| **OTTL transformation language** | OTTL is the vendor-neutral standard for in-flight telemetry manipulation. The same syntax works across logs, metrics, and traces in any OpenTelemetry pipeline. |
| **Cardinality management** | Unbounded stream label cardinality is one of the most common production Loki failure modes (high memory usage, slow queries, eventually OOM). Identifying the Kopia job-name pattern and normalizing it at the agent layer — not by post-hoc cleanup — is the correct architectural approach. |
| **Structured log normalization** | Cross-service `level` inconsistency (JSON `"level"`, logfmt `level=`, Python `WARNING` vs Go `warn`) is universal in polyglot environments. Normalizing at the pipeline layer rather than in every Grafana query is the production pattern. |
| **DaemonSet security hardening** | Satisfying two independent constraint sets simultaneously (Gatekeeper prohibits privilege escalation and NET_RAW; the task requires root for file access; `observability` is partially excluded) requires understanding which exemptions apply to which constraints. Not guessing. |
| **Loki OTLP integration** | Loki 3.x native OTLP ingest is the forward-looking integration path (Grafana is deprecating the Loki push API in favor of OTLP). Implementing it now avoids a future forced migration. |
