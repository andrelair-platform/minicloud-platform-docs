---
id: otelcol-log-pipeline-gaps
title: OTel Log Pipeline — Gap Analysis & Fixes
sidebar_position: 13
---

# OTel Log Pipeline — Gap Analysis & Fixes

The Phase 21 log pipeline shipped Promtail as the log collector. After migrating
to the OTel Collector DaemonSet (for the traces pipeline, Gap B in the
[distributed tracing work](./distributed-tracing-gaps)), seven gaps in the log
pipeline were identified and closed.

The migration principle: **the pipeline below the exporter is backend-agnostic**.
Only the final `otlphttp/loki` exporter block changes when switching backends.
Everything above it — file collection, container log parsing, k8s attribute
enrichment, OTTL transformations — is standard OTel and requires no changes when
the sink changes.

---

## Gap inventory

| # | Gap | Files changed | Status |
|---|-----|---------------|--------|
| 1 | Kopia CronJob cardinality bomb | `helm-values/otelcol-values.yaml` (OTTL `replace_match`) | ✅ |
| 2 | No `level` stream label in Loki | `helm-values/otelcol-values.yaml` (OTTL `ParseJSON` + `ExtractPatterns`) | ✅ |
| 3 | No log-based alerting (Loki ruler) | `manifests/loki/00-loki-rules.yaml`, `helm-values/loki-values.yaml` | ✅ |
| 4 | No log exploration dashboards | `manifests/monitoring/16/17/18-*.yaml` | ✅ |
| 5 | Workload Health dashboard has no link to logs | `manifests/monitoring/05-workload-health-dashboard.yaml` | ✅ |
| 6 | Controller node has no log coverage | Promtail Docker container on controller, Loki Ingress + cert | ✅ |
| 7 | Log retention too short (7 days) | `helm-values/loki-values.yaml` | ✅ |

---

## Architecture overview

```
Cluster pods (all namespaces)
  │  /var/log/pods/*/*/*.log  (read by hostPath volume, root:root 640)
  ▼
OTel Collector DaemonSet  (observability ns, otelcol-contrib 0.156.0)
  │  filelog receiver → container log parser → k8sattributes → transform (OTTL) → batch
  │
  ▼
Loki single-binary  (observability ns, port 3100)
  │  native OTLP ingest at /otlp/v1/logs
  │  stream labels: namespace, pod, container, node_name, app, job, level
  ▼
Grafana  (3 log dashboards + Workload Health dataLinks)

Controller node  (10.0.0.1)
  │  Docker containers + systemd journal
  ▼
Promtail 3.3.2  (Docker, --net=host)
  │  push to https://loki.10.0.0.200.nip.io/loki/api/v1/push
  ▼
Loki  (via minicloud CA-signed Ingress)
  stream labels: host=controller, job=controller-docker / controller-journald
```

---

## Before the migration — Promtail limits

Promtail worked for basic log shipping but had two structural problems:

1. **No OTTL**: Promtail pipeline stages use a proprietary regex/JSON DSL.
   Any label extraction logic is locked in. OTel OTTL is a vendor-neutral
   expression language that works the same regardless of which backend receives the logs.

2. **Receiver coupling**: Promtail's Loki push API is Loki-specific.
   Changing backends requires rewriting the agent config. OTel's `otlphttp`
   exporter swaps the backend by changing one URL.

The four deployment gotchas are documented below, in the order they were hit.

---

## Gotcha 1 — `lokiexporter` removed in 0.150+

The first OTel Collector config draft used the `lokiexporter`:

```yaml
exporters:
  loki:
    endpoint: http://loki.observability.svc:3100/loki/api/v1/push
```

This fails silently at startup — the `lokiexporter` component was removed from
`otelcol-contrib` in version 0.150.0. Loki 3.x added native OTLP ingest at
`/otlp/v1/logs`. Use the standard `otlphttp` exporter instead:

```yaml
exporters:
  otlphttp/loki:
    logs_endpoint: http://loki.observability.svc:3100/otlp/v1/logs
    tls:
      insecure: true
```

The `/v1/logs` suffix is appended automatically when `logs_endpoint` is set.
Do not use `endpoint:` (generic) — it omits the path and returns HTTP 404.

---

## Gotcha 2 — OTTL regex backslash escaping

OTTL regex literals in YAML values go through two escaping passes:

1. YAML parses single-quoted strings: backslashes pass through literally
2. OTTL then processes the string: `\d` is an unknown escape → rejected

The fix is to double-escape in YAML so OTTL sees a single backslash:

| What you want | YAML value | OTTL processes | RE2 sees |
|---|---|---|---|
| digit class `\d` | `\\d` | `\d` → RE2 `\d` | `\d` ✓ |
| whitespace `\s` | `\\s` | `\s` → RE2 `\s` | `\s` ✓ |

This applies to every regex in OTTL `replace_match`, `replace_pattern`,
`ExtractPatterns`, and `IsMatch` calls when written in a YAML values file.

---

## Gotcha 3 — OTel Collector needs `runAsUser: 0`

The default `otelcol-contrib` container runs as UID 10001 (the `otelcol`
group). Pod log files at `/var/log/pods/` are owned `root:root` mode `640`.
UID 10001 cannot read them. The checkpoint directory (`/var/lib/otelcol`)
is created by kubelet as `root:root 755` — also unreadable.

The `observability` namespace is **excluded from `k8srequirenonroot`**
(the Gatekeeper constraint that blocks `runAsUser: 0`). It is NOT excluded
from `k8snoprivilegeescalation` or `k8sblocknetraw`, so those must be
explicitly satisfied:

```yaml
securityContext:
  runAsUser: 0
  allowPrivilegeEscalation: false   # satisfies k8snoprivilegeescalation
  capabilities:
    drop: [NET_RAW]                 # satisfies k8sblocknetraw
```

---

## Gotcha 4 — Loki `log_attributes` is a flat list, not a struct

The Loki `otlp_config` section has two distinct shapes for its two subsections:

```yaml
# loki-values.yaml → loki.limits_config
otlp_config:
  resource_attributes:       # ← this IS a struct with an attributes_config key
    attributes_config:
      - action: index_label
        attributes: [namespace, pod, ...]

  log_attributes:            # ← this is a FLAT LIST — no attributes_config wrapper
    - action: index_label
      attributes: [level]
```

Adding `attributes_config:` under `log_attributes:` causes Loki to fail at
startup with:

```
cannot unmarshal !!map into []push.AttributesConfig
```

The asymmetry is not documented in the Loki chart README. The only way to
discover it is from the error message at startup.

---

## Gap 1 — Kopia CronJob cardinality bomb

### Problem

Velero uses Kopia for PVC backup. Each Kopia maintenance CronJob creates
a pod named `<namespace>-default-kopia-maintain-job-<unix_milliseconds>`.
The timestamp suffix is different for every pod.

The `k8sattributesprocessor` sets `resource.attributes["app"]` from the pod
label `app=<pod-name>`. When the OTTL copies this to a Loki stream label,
Loki creates a new stream for every single backup run. With daily backups
across multiple namespaces and a 30-day retention, this generates thousands
of unique stream labels.

High stream cardinality degrades Loki query performance and, if left
unchecked, can cause Loki to reject new streams with `too many outstanding
requests`.

### Fix

An OTTL `replace_match` statement in the `transform` processor collapses all
Kopia pod names to the static string `"kopia-job"` before the label is
written to Loki:

```yaml
# otelcol-values.yaml → config.processors.transform.log_statements
- 'replace_match(resource.attributes["app"], "^.+-kopia-[a-z]+-job-\\d+$", "kopia-job")'
```

The regex matches the pattern `<anything>-kopia-<word>-job-<digits>`.
After normalisation, all Kopia maintenance runs share one Loki stream
`{app="kopia-job"}` regardless of when they ran or which namespace they
belong to.

The `job` attribute is derived from `namespace/app` after this normalisation
runs, so the job label is also stable:

```yaml
- 'set(resource.attributes["job"], Concat([resource.attributes["namespace"], resource.attributes["app"]], "/")) where resource.attributes["namespace"] != nil and resource.attributes["app"] != nil'
```

Order matters — the `job` derivation must run after the `replace_match`.

---

## Gap 2 — `level` stream label

### Problem

Promtail shipped logs with `{namespace="...", pod="...", container="..."}` stream
labels but no `level` label. Every Grafana query that wanted to filter by log
level had to use a log-line regex filter (`|~ "level=error"`), which is slower
than a stream label matcher (`{level="error"}`). Stream selectors are indexed;
regex filters are not.

The problem was compounded by different services using different log formats:

| Service | Format | Level field |
|---------|--------|-------------|
| Backstage, Authentik | newline-delimited JSON | `{"level":"info", ...}` |
| ArgoCD (zerolog) | logfmt | `level=info msg="..."` |
| platform-demo, minicloud-plane | logfmt | `level=info ...` |
| Plain Go stdlib | unstructured | no level field |

### Fix

Three OTTL statements handle the three cases:

**JSON services** (Backstage, Authentik):

```yaml
- 'set(attributes["level"], ParseJSON(body)["level"])
   where IsMatch(resource.attributes["namespace"], "^(backstage|authentik)$")'
```

`ParseJSON` returns `nil` on non-JSON lines (because `error_mode: ignore`);
`nil["level"]` is `nil`; setting an attribute to `nil` is a no-op. Mixed-format
pods are safe — lines that aren't JSON simply don't get a level attribute.

**logfmt services** (ArgoCD, own Go services):

```yaml
- 'set(attributes["level"], ExtractPatterns(body, "level=(?P<level>[^\\s\"]+)")["level"])
   where IsMatch(body, "level=") and IsMatch(resource.attributes["namespace"], "^(argocd|minicloud-plane-dev|platform-demo-dev|...)$")'
```

The `IsMatch(body, "level=")` guard prevents running `ExtractPatterns` on every
log line — only lines that contain the substring `level=` are processed.

**Normalisation** (runs after both extraction steps):

```yaml
- 'set(attributes["level"], ConvertCase(attributes["level"], "lower"))
   where attributes["level"] != nil'
- 'replace_pattern(attributes["level"], "^warning$", "warn")'
```

Python/Authentik emit `"WARNING"` (all caps). ArgoCD and Go services emit
`"warn"`. Lowercasing and aliasing ensures `{level="warn"}` matches both
without regex alternation in every Grafana query.

### Loki stream label promotion

Setting `attributes["level"]` in OTTL creates a log-scoped OTel attribute.
For Loki to index it as a stream label, it must appear in `otlp_config`:

```yaml
# loki-values.yaml
otlp_config:
  log_attributes:
    - action: index_label
      attributes: [level]
```

Resource-scoped attributes (namespace, pod, etc.) go under
`resource_attributes.attributes_config`. Log-scoped attributes (level) go
directly under `log_attributes` as a flat list. See Gotcha 4.

### Backward compatibility

The OTel semantic attribute names (`k8s.namespace.name`, `k8s.pod.name`, etc.)
differ from the Promtail label names (`namespace`, `pod`, etc.) that all
existing Grafana dashboards query. The `transform` processor copies each OTel
name to its short Promtail equivalent before the log reaches Loki:

```yaml
- 'set(resource.attributes["namespace"], resource.attributes["k8s.namespace.name"])'
- 'set(resource.attributes["pod"],       resource.attributes["k8s.pod.name"])'
- 'set(resource.attributes["node_name"], resource.attributes["k8s.node.name"])'
- 'set(resource.attributes["container"], resource.attributes["k8s.container.name"])'
```

All 29 existing Grafana dashboards kept working without any query changes
after the Promtail → OTel migration.

---

## Gap 3 — Loki ruler (log-based alerting)

### Problem

Prometheus alerts fire on metric conditions. Some failure modes only appear
in logs — a background job traceback, an SMTP bounce, an authentication failure
burst — and have no Prometheus metric that captures them.

### Implementation

Loki's ruler evaluates LogQL expressions on a schedule and pushes firing alerts
to Alertmanager, exactly like Prometheus PrometheusRules. The 6 rules are stored
in a ConfigMap (`manifests/loki/00-loki-rules.yaml`) mounted into the Loki pod
via `subPath`.

**Key LogQL pattern** — all 6 rules use `count_over_time` to count matching log
lines in a window:

```logql
sum by (namespace, pod, app) (
  count_over_time(
    {namespace=~".+", namespace!~"kube-system|longhorn-system|observability|monitoring"}
      |~ `(?i)(FATAL|panic:|runtime error:)`
    [5m]
  )
) > 0
```

The `namespace=~".+"` matcher is **required**. Loki rejects stream selectors
that use only negative matchers (e.g., `{namespace!~"kube-system"}`). A
positive matcher must appear before any exclusion.

**The 6 rules:**

| Alert | Signal | Threshold |
|-------|--------|-----------|
| `AppFatalError` | FATAL/panic/runtime error in application logs | >0 in 5 min, `for: 0m` |
| `StalwartSmtpDeliveryFailure` | SMTP 5xx / bounce in mail namespace | >3 in 10 min, `for: 5m` |
| `AuthentikAuthFailureBurst` | Login failed events in authentik namespace | >10 in 5 min, `for: 2m` |
| `ContainerCrashIndicator` | panic/OOM/exit 137/segfault in pod logs | >5 in 10 min, `for: 5m` |
| `AIServiceHTTPErrors` | HTTP 5xx / LiteLLM exceptions in ai namespace | >5 in 5 min, `for: 5m` |
| `ERPNextJobFailure` | Traceback / job failed in erp namespace | >0 in 10 min, `for: 0m` |

### Three deployment gotchas

**Alertmanager URL via CLI flag, not values.yaml**

The Loki chart v7.0.0 generates its own `ruler:` config block in the Helm
template and overwrites any `loki.ruler.*` values set in `values.yaml`.
Setting `loki.ruler.alertmanager_url` has no effect. The workaround:

```yaml
# loki-values.yaml
singleBinary:
  extraArgs:
    - -ruler.alertmanager-url=http://kps-alertmanager.monitoring.svc:9093
```

**`subPath` mount required — directory vs file**

The Loki ruler expects `<storage_dir>/<tenant>/<namespace>` where the last
segment is a **file**. A plain ConfigMap volume mount creates a **directory**
at that path. Mounting a directory where a file is expected causes `runc`
to fail with a path error.

`subPath` mounts only the named key from the ConfigMap as a file:

```yaml
extraVolumeMounts:
  - name: loki-rules
    mountPath: /var/loki/rules/fake/minicloud-alerts
    subPath: app-alerts.yaml   # mounts as a file, not a directory
```

**Stale directory blocks the mount path**

An earlier PR attempt (PR #233) left an empty directory at
`/var/loki/rules/fake/minicloud` on the Loki PVC. A subsequent PR tried to
mount the rules file at `/var/loki/rules/fake/minicloud` (same path) —
`runc` cannot mount a file over an existing directory.

Fix: rename the namespace to `minicloud-alerts`. The ruler silently skips
directories when listing the tenant directory (`fi.IsDir() → continue`), so
the stale `minicloud/` directory is harmlessly ignored. API path becomes
`GET /loki/api/v1/rules/minicloud-alerts`.

Verify rules are loaded:

```bash
kubectl exec -n observability statefulset/loki \
  -- wget -qO- http://localhost:3100/loki/api/v1/rules/minicloud-alerts \
  | python3 -c "import yaml,sys; d=yaml.safe_load(sys.stdin); print([g['name'] for g in d])"
# ['app-fatal-errors', 'stalwart-smtp-failures', 'authentik-brute-force',
#  'container-crash-indicators', 'ai-service-errors', 'erpnext-job-failures']
```

:::caution Loki ruler API returns YAML, not JSON
`wget -qO- .../rules/...` returns YAML. Use `yaml.safe_load()`, not
`json.load()`. `json.load()` fails silently on valid YAML with a
`JSONDecodeError`.
:::

---

## Gap 4 — Log exploration dashboards

Three Grafana dashboards added to `manifests/monitoring/` (picked up by the
Grafana sidecar via Watch API — no restart required):

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| Application Logs Explorer | `minicloud-app-logs` | Namespace → pod → level drill-down with error rate panel |
| Error Rate by Service | `minicloud-error-rate` | Stat panels for total error and FATAL lines per hour |
| Pod Crash & Restart Events | `minicloud-crash-events` | 24h crash event table with log-line evidence |

All three use Loki datasource UID `P8E80F9AEF21F6940` and Loki label-value
variables for `namespace` and `pod` (populated from the stream label index).

The `level` stream label (Gap 2) is what makes the "Log Volume by Level"
panel in Application Logs Explorer viable — filtering by `{level="error"}`
uses the indexed label rather than a per-line regex scan.

---

## Gap 5 — Workload Health dashboard dataLinks

### Problem

The Workload Health dashboard showed pod status (Pending, Failed, CrashLoop,
OOMKill) but clicking a row had no action. An operator seeing a crash-looping
pod had to copy the name, open a new tab, navigate to Loki Explore, and
reconstruct the query manually.

### Fix

`dataLinks` added to 5 panels in `05-workload-health-dashboard.yaml`.
Each link opens Loki Explore pre-filtered to the relevant stream:

**Table panels** (Pending/Failed/CrashLoop/OOMKill) use `${__data.fields.*}`
to read the `namespace` and `pod` columns from the selected table row:

```json
{
  "url": "/explore?orgId=1&left={\"datasource\":\"P8E80F9AEF21F6940\",\"queries\":[{\"refId\":\"A\",\"expr\":\"{namespace=\\\"${__data.fields.namespace}\\\",pod=\\\"${__data.fields.pod}\\\"}\"}],\"range\":{\"from\":\"${__from}\",\"to\":\"${__to}\"}}"
}
```

**Timeseries panels** (restart rate graph) use `${__field.labels.*}` to read
the label from the currently-hovered series:

```json
{
  "url": "/explore?...\"expr\":\"{namespace=\\\"${__field.labels.namespace}\\\"}\"}..."
}
```

The URL embeds a JSON Loki query object, which requires two levels of escaping
inside the JSON string: `\"` for the JSON property quotes, and `\\\"` for the
inner LogQL string delimiters. Getting one level wrong produces a URL that
opens Explore with an empty or broken query.

---

## Gap 6 — Controller node log coverage

### Problem

The OTel Collector DaemonSet runs inside the Kubernetes cluster — it cannot
collect logs from the controller node (`ktayl-ThinkPad-X390`, `100.88.123.8`),
which is outside the cluster. The controller runs:

- Docker containers: MinIO, cloudflared, node_exporter, Promtail itself
- systemd units: k3s-related scripts, UFW, network services

Without controller log coverage, a MinIO crash or cloudflared tunnel failure
would be invisible to Loki.

### Implementation

Grafana Promtail `3.3.2` runs as a Docker container on the controller and
pushes directly to Loki's cluster-internal IP via a TLS Ingress.

**The Docker bridge networking gotcha**

The first attempt ran Promtail with default Docker bridge networking:

```bash
docker run -d grafana/promtail:3.3.2 ...  # no --net flag
```

Promtail received `context deadline exceeded` when pushing to
`https://loki.10.0.0.200.nip.io`. The Docker bridge network (`172.17.0.0/16`)
cannot route to MetalLB addresses (`10.0.0.200`) — the bridge is isolated
from the physical network. The host network can.

Fix: `--net=host`:

```bash
docker run -d --name promtail --net=host \
  -v /home/ktayl/.promtail:/etc/promtail:ro \
  -v /var/log/journal:/var/log/journal:ro \
  -v /run/log/journal:/run/log/journal:ro \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  grafana/promtail:3.3.2 \
  -config.file=/etc/promtail/config.yaml
```

The same pattern applies to any Docker container on the controller that needs
to reach the cluster's MetalLB IP — MinIO already uses it.

**Loki Ingress and certificate**

Promtail on the controller pushes to `https://loki.10.0.0.200.nip.io`
(the internal MetalLB address with a minicloud-CA-signed cert):

```yaml
# manifests/loki/01-loki-ingress.yaml
spec:
  ingressClassName: nginx
  tls:
    - hosts: [loki.10.0.0.200.nip.io]
      secretName: loki-tls
  rules:
    - host: loki.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: {name: loki, port: {number: 3100}}
```

The CA cert at `~/.promtail/minicloud-ca.crt` on the controller is the same
cert used by `crane`, `/usr/bin/curl`, and Harbor pushes. The Promtail config
points to it:

```yaml
clients:
  - url: https://loki.10.0.0.200.nip.io/loki/api/v1/push
    tls_config:
      ca_file: /home/ktayl/.promtail/minicloud-ca.crt
```

**ArgoCD SSA field manager conflict**

Applying the Loki Ingress and Certificate directly via `kubectl apply` (to
unblock a Gatekeeper TLS rejection that ArgoCD was retrying in a loop) created
field manager entries that ArgoCD could not override on the next sync. ArgoCD
reconciled both resources correctly on the next auto-sync — the field managers
merged without conflict. This is the expected behaviour when `ServerSideApply`
is enabled on an app.

Verified streams from the controller:

```bash
# In Grafana Explore:
{host="controller", job="controller-docker"}
{host="controller", job="controller-journald", unit="cloudflared.service"}
```

---

## Gap 7 — Log retention extended to 30 days

### Before

```yaml
loki:
  limits_config:
    retention_period: 168h   # 7 days
```

Seven days is insufficient for post-incident analysis. A power failure over
a weekend could wipe all evidence before the on-call engineer reviews it.

### After

```yaml
loki:
  limits_config:
    retention_period: 720h   # 30 days
  compactor:
    retention_enabled: true
    delete_request_store: filesystem
    retention_delete_delay: 2h
```

`compactor.retention_enabled: true` and `delete_request_store: filesystem`
were already present from the initial Loki deployment. Only `retention_period`
needed to change.

---

## Full pipeline config reference

The complete `otelcol-values.yaml` pipeline (logs section):

```yaml
receivers:
  filelog:
    include: [/var/log/pods/*/*/*.log]
    exclude: [/var/log/pods/observability_otelcol*/*.log]   # avoid self-loop
    start_at: beginning
    include_file_path: true
    storage: file_storage
    operators:
      - type: container    # parses k3s containerd CRI format + extracts k8s metadata from path
        id: container-parser
        max_log_size: 102400

processors:
  k8sattributes:
    auth_type: serviceAccount
    extract:
      metadata: [k8s.namespace.name, k8s.pod.name, k8s.pod.uid, k8s.node.name, k8s.container.name]
      labels:
        - {tag_name: app, key: app, from: pod}
        - {tag_name: app, key: app.kubernetes.io/name, from: pod}
    pod_association:
      - sources:
          - {from: resource_attribute, name: k8s.pod.uid}

  transform:
    error_mode: ignore    # parse failures are silent — correct for mixed-format pods
    log_statements:
      - context: log
        statements:
          # Backward compat: short names for existing Grafana dashboards
          - 'set(resource.attributes["namespace"], resource.attributes["k8s.namespace.name"])'
          - 'set(resource.attributes["pod"],       resource.attributes["k8s.pod.name"])'
          - 'set(resource.attributes["node_name"], resource.attributes["k8s.node.name"])'
          - 'set(resource.attributes["container"], resource.attributes["k8s.container.name"])'
          # Gap 1: Kopia cardinality fix
          - 'replace_match(resource.attributes["app"], "^.+-kopia-[a-z]+-job-\\d+$", "kopia-job")'
          - 'set(resource.attributes["job"], Concat([resource.attributes["namespace"], resource.attributes["app"]], "/")) where resource.attributes["namespace"] != nil and resource.attributes["app"] != nil'
          # Gap 2a: JSON level extraction (Backstage, Authentik)
          - 'set(attributes["level"], ParseJSON(body)["level"]) where IsMatch(resource.attributes["namespace"], "^(backstage|authentik)$")'
          # Gap 2b: logfmt level extraction (ArgoCD, own Go services)
          - 'set(attributes["level"], ExtractPatterns(body, "level=(?P<level>[^\\s\"]+)")["level"]) where IsMatch(body, "level=") and IsMatch(resource.attributes["namespace"], "^(argocd|minicloud-plane-dev|platform-demo-dev|...)$")'
          # Gap 2c: normalisation
          - 'set(attributes["level"], ConvertCase(attributes["level"], "lower")) where attributes["level"] != nil'
          - 'replace_pattern(attributes["level"], "^warning$", "warn")'

exporters:
  otlphttp/loki:
    logs_endpoint: http://loki.observability.svc:3100/otlp/v1/logs
    tls:
      insecure: true

service:
  pipelines:
    logs:
      receivers:  [filelog]
      processors: [memory_limiter, k8sattributes, transform, batch]
      exporters:  [otlphttp/loki]
```

---

## Verification

```bash
# All 5 DaemonSet pods running
kubectl -n observability get pods -l app.kubernetes.io/name=opentelemetry-collector

# Collector health
kubectl -n observability exec daemonset/otelcol-opentelemetry-collector \
  -- wget -qO- http://localhost:13133/

# Loki stream labels present (run from Grafana Explore or kubectl port-forward)
kubectl port-forward svc/loki -n observability 3100:3100 &
curl -s 'http://localhost:3100/loki/api/v1/labels' | python3 -m json.tool
# should include: namespace, pod, container, node_name, app, job, level

# Controller logs in Loki
# In Grafana Explore:
#   {host="controller", job="controller-docker"}
#   {host="controller", job="controller-journald"}

# Ruler rules loaded
kubectl exec -n observability statefulset/loki \
  -- wget -qO- http://localhost:3100/loki/api/v1/rules/minicloud-alerts
```
