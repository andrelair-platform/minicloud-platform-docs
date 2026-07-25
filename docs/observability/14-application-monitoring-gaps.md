---
id: application-monitoring-gaps
title: Application Monitoring — Gap Analysis & Fixes
sidebar_position: 14
---

# Application Monitoring — Gap Analysis & Fixes

After the infrastructure monitoring layer (node-exporter, kube-state-metrics,
kube-prometheus-stack) was in place, the cluster had zero visibility into
what the applications themselves were doing. No request rates, no error rates,
no latency distributions.

The work was structured in three waves: **P1** (own Go services),
**P2** (third-party services with native `/metrics` disabled by default),
**P3** (services requiring custom instrumentation). A final RED signal audit
then identified which services still lacked PrometheusRules.

---

## Gap inventory

| # | Wave | Service | Gap | Status |
|---|------|---------|-----|--------|
| 1 | P1 | platform-demo, minicloud-plane | No RED metrics | ✅ |
| 2 | P1 | minicloud-plane | `/health` probe not instrumented → `promauto` metrics absent | ✅ |
| 3 | P1 | NGINX Ingress | No per-route latency histogram (F5 OSS vs community chart) | ✅ |
| 4 | P1 | platform-demo Argo Rollouts | AnalysisTemplate DNS name wrong + NetworkPolicy blocks query | ✅ |
| 5 | P2 | Authentik | Metrics disabled by default | ✅ |
| 6 | P2 | Harbor | Metrics disabled + manual restart required + Longhorn RWO risk | ✅ |
| 7 | P2 | Vault | No telemetry HCL + ServiceMonitor selector too specific | ✅ |
| 8 | P2 | LiteLLM | Success metrics never emit (no successful request to seed them) | ✅ |
| 9 | P3 | Matrix Synapse | Port 9090 generated but not exposed in chart-managed Service | ✅ |
| 10 | P3 | Backstage | `plugin-app-backend` catch-all intercepts `/metrics` on port 7007 | ✅ |
| 11 | P3 | Open WebUI | No `/metrics` endpoint in upstream image | ✅ |
| 12 | RED | Harbor, NATS, Vault | No service-level PrometheusRules | ✅ |

**Accepted as N/A:** Stalwart CE (no `/metrics` binary), ERPNext/Frappe (404 on all metric paths).

**Upstream limitations (no fix without patching source):** Harbor/Vault use `prometheus.Summary`
(no `_bucket`, so no p99); Vault CE has no HTTP status code counters; NATS prometheus-exporter
polls `/varz` only (no per-message latency).

---

## Final target state

| Service | Targets | Port | How |
|---------|---------|------|-----|
| Authentik | 1 | 9300 | Chart `server.metrics.serviceMonitor.enabled: true` |
| Backstage | 1 | 9464 | Separate `http.createServer` + `prom-client` |
| Harbor | 4 | 8001 | Chart `metrics.serviceMonitor.enabled: true` (core, registry, jobservice, exporter) |
| LiteLLM | 1 | 8080 | `success_callback: ["prometheus"]` already set |
| Matrix Synapse | 1 | 9090 | Standalone Service + custom ServiceMonitor |
| minicloud-plane | 1 | 8080 | Custom `promauto` instrumentation |
| NATS | 3 | 7777 | Chart `promExporter.podMonitor.enabled: true` (already configured) |
| NGINX Ingress | 1 | 10254 | Chart ServiceMonitor, `enable-latency-metrics: "true"` |
| Open WebUI | 1 | 8080 | `sitecustomize.py` + `prometheus-fastapi-instrumentator` |
| platform-demo | 1 | 9898 | Custom `promauto` instrumentation |
| Vault | 2 | 8200 | Telemetry HCL stanza + custom ServiceMonitor |
| **Total** | **17** | | **All `up` — 64/64 total Prometheus targets** |

---

## P1 — Gap 1: Go services have no RED metrics

### Problem

`platform-demo` and `minicloud-plane` had no Prometheus instrumentation.
The Argo Rollouts canary analysis (Phase 73) required a success-rate query on
`http_requests_total` — which did not exist.

### Fix

Both services define the same two metrics via `promauto` so they are
registered at process start:

```go
httpRequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
    Name: "http_requests_total",
}, []string{"method", "handler", "code"})

httpRequestDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
    Name:    "http_request_duration_seconds",
    Buckets: []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5},
}, []string{"method", "handler", "code"})
```

A `statusWriter` wrapper captures the HTTP response code, which is only
available after `WriteHeader` returns — it cannot be read from `http.ResponseWriter`
directly:

```go
func Instrument(pattern string, h http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        sw := &statusWriter{ResponseWriter: w, code: http.StatusOK}
        start := time.Now()
        h.ServeHTTP(sw, r)
        code := strconv.Itoa(sw.code)
        httpRequestsTotal.WithLabelValues(r.Method, pattern, code).Inc()
        httpRequestDuration.WithLabelValues(r.Method, pattern, code).Observe(time.Since(start).Seconds())
    })
}
```

`promhttp.Handler()` serves the registry at `/metrics`.

ServiceMonitors live in the kustomize `base/` (no `namespaceSelector`) so
prometheus-operator defaults to scraping in the ServiceMonitor's own
namespace — the kustomize namespace transformer writes it to the correct
overlay namespace without any per-overlay SM override.

---

## P1 — Gap 2: `promauto` metrics absent until first `.WithLabelValues()` call

### Problem

After deploying the instrumented `minicloud-plane` image, the Prometheus target
showed `up=1` but `http_requests_total` returned zero series. The metric existed
in the Go binary but had never been observed with a label combination — `promauto`
registers the descriptor but emits nothing until `.WithLabelValues().Inc()` is
called at least once.

In a distroless container with no initial traffic, this could take minutes or
never happen if the service sits idle.

### Fix

Wrap the liveness probe endpoint (`/health`) with `Instrument()`:

```go
mux.Handle("/health", metrics.Instrument("/health", http.HandlerFunc(healthHandler)))
```

The kubelet hits `/health` every 15 seconds. Within one scrape cycle (30 seconds)
the counter and histogram have been seeded with probe traffic. Prometheus shows
174 probe observations within minutes of deployment.

`/metrics` itself must NOT be wrapped — instrumenting the scrape endpoint adds
one observation per scrape to every bucket, corrupting the latency signal.

---

## P1 — Gap 3: No per-route latency histogram on NGINX Ingress

### Problem

The cluster was running the F5 nginx-ingress-plus-operator chart. The F5 OSS
variant's `-enable-latency-metrics=true` flag is **NGINX Plus-only** — in OSS
mode it is silently a no-op. The F5 chart only exposed 20 aggregate metrics with
no per-request breakdown, making it impossible to know which ingress routes were
slow or erroring.

### Fix

Migrated to community `ingress-nginx/ingress-nginx` 4.15.1. The community chart
exposes `nginx_ingress_controller_request_duration_seconds_bucket` natively in
OSS mode via a ConfigMap key:

```yaml
# helm-values/nginx-ingress-values.yaml
controller:
  config:
    enable-latency-metrics: "true"    # ConfigMap key — NOT a CLI flag
    allow-snippet-annotations: "true"
    annotations-risk-level: "Critical"
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
      namespace: monitoring
```

216 histogram samples materialized immediately. Labels: `ingress`, `host`,
`method`, `status`, `path`, `le` — full per-route breakdown.

:::caution `annotations-risk-level` is a ConfigMap key, not a CLI flag
`server-snippet` and `configuration-snippet` annotations are risk level
`Critical` in community ingress-nginx v1.12+. Setting only
`allow-snippet-annotations: "true"` is insufficient — add
`annotations-risk-level: "Critical"` in `controller.config`.
Adding it under `extraArgs` causes CrashLoopBackOff (`unknown flag`).
Without it, Authentik forward-auth ingresses silently drop snippet
locations → HTTP 404 on protected routes.
:::

The full NGINX Ingress migration (annotation prefix changes, IngressClass
immutability, NetworkPolicy pod label mismatch, Flannel webhook routing)
is documented in the Kubernetes monitoring gaps runbook.

---

## P1 — Gap 4: Canary AnalysisTemplate blocked

### Problem

The Phase 73 Argo Rollouts canary analysis for `platform-demo` uses a
PrometheusRule query to gate the rollout. Two separate issues blocked it:

**Issue A — Wrong Prometheus service name:**
The `kube-prometheus-stack` was installed with Helm release name `kps`.
All services are prefixed `kps-*`. The AnalysisTemplate had:

```yaml
address: http://kube-prometheus-stack-prometheus.monitoring.svc:9090
```

`kube-prometheus-stack-prometheus` does not resolve. The real service is
`kps-prometheus`. DNS failure → AnalysisRun immediately errors → rollout
aborts before any canary traffic is measured.

**Issue B — NetworkPolicy blocks Argo Rollouts → Prometheus:**
The `monitoring` namespace has `default-deny-ingress`. The Argo Rollouts
controller (in `argo-rollouts` namespace) queries `kps-prometheus:9090` to
evaluate AnalysisRuns. Without an explicit allow rule, the connection is
refused — the error looks like a network error, not a DNS error, making it
harder to diagnose.

### Fixes

**Fix A:** Always verify with `kubectl get svc -n monitoring` before writing
any AnalysisTemplate or custom ServiceMonitor:

```bash
kubectl get svc -n monitoring | grep prometheus
# kps-prometheus    ClusterIP  10.43.x.x  9090/TCP
```

Updated `AnalysisTemplate` in `services/platform-demo/base/`:
```yaml
address: http://kps-prometheus.monitoring.svc:9090
```

**Fix B:** Added `allow-argo-rollouts` NetworkPolicy in
`manifests/network-policies/monitoring.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-argo-rollouts
  namespace: monitoring
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: prometheus
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: argo-rollouts
      ports:
        - protocol: TCP
          port: 9090
```

Both fixes are required together. A wrong DNS name errors immediately;
a correct DNS name that is network-blocked errors slightly later with
`connection refused` — the symptom looks identical from the AnalysisRun
status.

---

## P2 — Gap 5: Authentik metrics disabled by default

One Helm values change, one ServiceMonitor from the chart:

```yaml
# helm-values/authentik-values.yaml
server:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
```

Exposes port 9300 with `authentik_main_request_duration_seconds` histogram
(full RED: rate, errors by code, latency distribution). **1 target `up`.**

---

## P2 — Gap 6: Harbor metrics disabled + deployment risks

### Three-part problem

**Part A — Metrics disabled by default:**
```yaml
# helm-values/harbor-values.yaml
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
```
Enables a harbor-exporter sidecar (port 8001) on core, registry, jobservice,
and exporter pods. Chart creates 4 ServiceMonitors automatically.

**Part B — Pods don't reload after ConfigMap change:**
Harbor stores `METRIC_ENABLE=true` in the `harbor-core` ConfigMap, loaded
via `envFrom`. The pods don't pick up ConfigMap changes without a restart.
Harbor is not annotated with `reloader.stakater.com/auto: "true"`.

After enabling metrics, restart manually:
```bash
kubectl rollout restart deployment/harbor-core deployment/harbor-jobservice -n harbor
```

**Part C — harbor-jobservice Longhorn RWO Multi-Attach:**
`harbor-jobservice` uses a ReadWriteOnce Longhorn PVC. A rolling update
schedules the new pod on a different node before the old pod's PVC is released
→ `Multi-Attach error: volume is already exclusively attached to node X`.
Rolling update stalls indefinitely.

Fix: roll back and let the pod that is already on the correct node serve metrics:
```bash
kubectl rollout undo deployment/harbor-jobservice -n harbor
# The pod that landed on the PVC's node picks up the ConfigMap via envFrom
# and serves metrics on port 8001 immediately.
```

**4 targets `up`** after restarts.

---

## P2 — Gap 7: Vault no telemetry + ServiceMonitor over-specified

### Two-part problem

**Part A — Telemetry HCL not configured:**
Vault CE does not expose any Prometheus metrics without an explicit `telemetry`
stanza in the HCL config. Added to `helm-values/vault-values.yaml`:

```hcl
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname           = true
}
# inside listener "tcp" block:
telemetry {
  unauthenticated_metrics_access = true
}
```

`unauthenticated_metrics_access = true` inside the `listener "tcp"` block
is what allows Prometheus to scrape `/v1/sys/metrics?format=prometheus`
without a Vault token. Without it, Prometheus receives HTTP 403 and the
target shows as `down`.

**Part B — `component: server` is a pod label, not a Service label:**
The initial ServiceMonitor had:

```yaml
selector:
  matchLabels:
    app.kubernetes.io/name: vault
    app.kubernetes.io/instance: vault
    component: server    # ← THIS IS WRONG
```

`component: server` is set on the StatefulSet **pod** template, not on the
**Service**. The `matchLabels` selector matches against Service labels.
Prometheus finds zero endpoints → the target is completely absent from
`/api/v1/targets` (not `down`, not there at all).

Fix: remove `component: server` from the selector in
`manifests/monitoring/11-vault-servicemonitor.yaml`.

Custom ServiceMonitor targets port `http` (8200), path `/v1/sys/metrics`,
params `format: [prometheus]`. **2 targets `up`** (vault + vault-internal).

Vault StatefulSet also required a restart to load the new telemetry HCL:
```bash
kubectl rollout restart statefulset/vault -n vault
```

---

## P2 — Gap 8: LiteLLM success metrics never emit

### Problem

LiteLLM was already configured with `success_callback: ["prometheus"]` and
`require_auth_for_metrics_endpoint: false`. The ServiceMonitor was pre-existing.
Yet `litellm_proxy_total_requests_metric_total` showed zero even after the
target was confirmed `up`.

The root cause: LiteLLM's Prometheus callback emits counters only on the
**success path**. All Open WebUI RAG embedding requests were failing with HTTP
429 (`insufficient_quota`) because the OpenAI `text-embedding-3-small` API key
was over quota. LiteLLM counted them as errors and never called the success
callback — so the counter was never initialized, and `/metrics` returned 0
series for those metrics (not 0 values — absent entirely).

The metric absence looked identical to a broken ServiceMonitor. Only checking
the LiteLLM API logs revealed the 429s.

### Fix

The underlying cause (quota exhaustion) was fixed by switching to
`nomic-embed-text` (local Ollama, 768-dim). After one successful embedding
request, all RED metrics fired immediately:
- `litellm_proxy_total_requests_metric_total`
- `litellm_input_tokens_metric_total`
- `litellm_request_duration_seconds`

To verify a metric is truly absent vs zero:
```bash
kubectl port-forward svc/litellm -n ai 8080:8080 &
curl -s http://localhost:8080/metrics | grep litellm_proxy_total
# If nothing prints: metric not yet initialized (no successful requests)
# If "0" prints: metric initialized, counter at zero
```

---

## P3 — Gap 9: Matrix Synapse metrics port not in chart Service

### Problem

The `ananace/matrix-synapse` chart generates a `metrics_port: 9090` listener
in `homeserver.yaml` when `enable_metrics: true` is set. But the
chart-managed Service exposes only port 8008. Pointing a ServiceMonitor at
the chart Service returns `{"errcode": "M_UNRECOGNIZED"}` — the Matrix
client-server API, not metrics.

### Fix

Add a standalone Service that exposes port 9090 with a custom label, then
a ServiceMonitor selecting that label:

```yaml
# manifests/monitoring/12-synapse-servicemonitor.yaml
apiVersion: v1
kind: Service
metadata:
  name: matrix-synapse-metrics
  namespace: chat
  labels:
    app.kubernetes.io/name: matrix-synapse
    app.kubernetes.io/component: synapse-metrics   # custom label for the SM selector
spec:
  selector:
    app.kubernetes.io/name: matrix-synapse
    app.kubernetes.io/component: synapse            # selects the actual Synapse pod
  ports:
    - name: metrics
      port: 9090
      targetPort: 9090
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
spec:
  selector:
    matchLabels:
      app.kubernetes.io/component: synapse-metrics  # matches the standalone Service
  endpoints:
    - port: metrics
      path: /_synapse/metrics
```

The pod selector (`component: synapse`) targets the running Synapse pod.
The Service label (`component: synapse-metrics`) is what the ServiceMonitor
selects — it is not present on the pod, only on the Service, so there is
no collision with the chart-managed Service selector.

**1,445 `synapse_*` series, target `up`.**

---

## P3 — Gap 10: Backstage `/metrics` intercepted by plugin-app-backend

### Problem

`@backstage/plugin-app-backend` registers a catch-all SPA handler on
port 7007. Every request that does not match a plugin route — including
`GET /metrics` — returns the SPA HTML with HTTP 200 and
`Content-Type: text/html`. Prometheus's text exposition parser rejects it
and marks the target `down`.

There is no middleware injection point that runs before the SPA catch-all.
Any route registered after `createBackend()` is unreachable.

### Fix

Add a separate `http.createServer` on port 9464, started before
`createBackend()` in `packages/backend/src/index.ts`:

```typescript
import * as http from 'http';
import * as promClient from 'prom-client';

promClient.collectDefaultMetrics();
http
  .createServer(async (req, res) => {
    if (req.url === '/metrics') {
      const body = await promClient.register.metrics();
      res.writeHead(200, { 'Content-Type': promClient.register.contentType });
      res.end(body);
    } else {
      res.writeHead(404);
      res.end();
    }
  })
  .listen(9464);
```

`prom-client` is a transitive dependency already present via
`@backstage/plugin-catalog-backend` — no new package needed.

The Bitnami Backstage chart exposes the port via `extraPorts` (container)
and `service.extraPorts` (Service). The ServiceMonitor in
`manifests/monitoring/14-backstage-servicemonitor.yaml` selects port `metrics`
(9464). **43 Node.js process metric families, target `up`.**

---

## P3 — Gap 11: Open WebUI has no metrics endpoint

### Problem

Open WebUI is a FastAPI application. The upstream image has no Prometheus
instrumentation. Installing `prometheus-fastapi-instrumentator` after the fact
via environment variable or config is not possible — FastAPI's ASGI wiring
happens at `FastAPI.__init__`, and there is no hook that runs before the
application object is created.

### Fix

Exploit Python's `sitecustomize.py` auto-load mechanism. Python imports
`sitecustomize` automatically before any user code runs. This is the only
reliable injection point that executes before `open_webui.main` creates the
FastAPI instance.

`patches/sitecustomize.py` patches `FastAPI.__init__` at the class level:

```python
import fastapi as _f

_orig = _f.FastAPI.__init__

def _new(self, *a, **kw):
    _orig(self, *a, **kw)
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(excluded_handlers=["/metrics"]).instrument(self).expose(
            self, include_in_schema=False
        )
    except Exception:
        pass   # never crash the app if instrumentation fails

_f.FastAPI.__init__ = _new
```

The Dockerfile installs `prometheus-fastapi-instrumentator` and copies the
file to `site.getsitepackages()[0]/sitecustomize.py`. The `/metrics` endpoint
and `http_request_duration_seconds` histogram are served on the existing port
8080 alongside the application — no additional port needed.

The ServiceMonitor in `manifests/monitoring/15-open-webui-servicemonitor.yaml`
targets the existing `http` port (80) on the Open WebUI Service:

```yaml
endpoints:
  - port: http    # the existing Service port 80 → container 8080
    path: /metrics
```

**Full FastAPI `http_request_duration_seconds` histogram, target `up`.**

---

## P3 — Gap 12: No service-level PrometheusRules

After all 17 targets were `up`, a RED signal audit identified which services
still lacked actionable alerting on their own data.

`manifests/monitoring/13-service-alerts.yaml` (gitops PRs #195, #199, #201, #203):

### Harbor

```yaml
- alert: HarborHighErrorRate
  # 5xx rate > 1% of total core requests, sustained 5 minutes
  expr: |
    sum(rate(harbor_core_http_request_total{code=~"5.."}[5m])) /
    sum(rate(harbor_core_http_request_total[5m])) > 0.01
  for: 5m

- alert: HarborJobServiceErrors
  # any errored background task — image scans, GC, replication
  expr: sum(rate(harbor_jobservice_task_total{status="Error"}[10m])) > 0
  for: 10m
```

### NATS

```yaml
- alert: NATSSlowConsumers
  # subscriber can't keep up — NATS will drop messages
  expr: nats_varz_slow_consumers > 0
  for: 2m

- alert: NATSJetStreamAPIErrors
  expr: increase(nats_varz_jetstream_stats_api_errors[5m]) > 0

- alert: NATSStaleConnections
  # nats_varz_stale_connections is CUMULATIVE — use increase(), not > N
  expr: increase(nats_varz_stale_connections[5m]) > 0
```

`nats_varz_stale_connections` counts connections forcibly closed by NATS due
to slow consumer backpressure. It only increments, never decrements. Using a
static threshold (`> 5`) fires permanently once 5 total stale connections have
ever occurred. `increase([5m]) > 0` fires only when new force-closures happen.

### Vault

```yaml
- alert: VaultHighRequestLatency
  # avg latency > 500ms, guarded by minimum traffic rate to avoid
  # false positives from single KMS unseal operations at startup
  expr: |
    (rate(vault_core_handle_request_sum[5m]) / rate(vault_core_handle_request_count[5m]) > 0.5)
    AND
    (rate(vault_core_handle_request_count[5m]) > 0.05)
  for: 5m

- alert: VaultSealedOrUnhealthy
  expr: vault_core_active == 0
  for: 1m
  labels:
    severity: critical
```

The minimum traffic guard (`rate(count[5m]) > 0.05`, approximately 3 req/min)
is required because Vault CE exposes a Summary (`vault_core_handle_request`
`_count` + `_sum`), not a Histogram. A single KMS barrier-initialization call
can take 10–30 seconds — which triggers the 500ms threshold as a false positive
before steady-state traffic accumulates. The guard ignores isolated slow requests.

---

## RED signal audit result

| Service | Rate | Errors | Latency | Notes |
|---------|------|--------|---------|-------|
| platform-demo | ✅ | ✅ | ✅ histogram | `http_requests_total` + `http_request_duration_seconds_bucket` |
| minicloud-plane | ✅ | ✅ | ✅ histogram | Same as platform-demo + `/health` probe seeding |
| NGINX Ingress | ✅ | ✅ | ✅ histogram | `nginx_ingress_controller_request_duration_seconds_bucket`, per-route labels |
| Authentik | ✅ | ✅ | ✅ histogram | `authentik_main_request_duration_seconds` |
| LiteLLM | ✅ | ✅ | ✅ | Native callbacks, seeded after first successful request |
| Harbor | ✅ | ✅ | ⚠️ avg only | `harbor_core_http_request_total{code}` ✅. Latency: Summary upstream |
| NATS | ✅ | ⚠️ backpressure | ❌ | Errors via `slow_consumers` / JetStream. Per-message latency not in exporter |
| Vault | ✅ | ❌ | ⚠️ avg only | No HTTP error codes in CE. Latency: Summary (`vault_core_handle_request`) |
| Matrix Synapse | ✅ | — | — | 1,445 series, specialized `synapse_*` metrics |
| Backstage | ✅ | — | — | Node.js process metrics (GC, event loop lag, heap) |
| Open WebUI | ✅ | ✅ | ✅ histogram | `http_request_duration_seconds` via FastAPI instrumentator |

**Upstream limitations (unfixable without patching source):**

- **Harbor/Vault latency:** Both use `prometheus.Summary` in Go — emits `_count` and `_sum` only. `histogram_quantile` is impossible. Use `rate(sum) / rate(count)` for rolling average.
- **Vault HTTP errors:** Vault CE telemetry has no HTTP 4xx/5xx status code counters.
- **NATS per-message latency:** `prometheus-nats-exporter` polls `/varz` only; delivery timing is not exposed.

---

## Files changed

| File | What |
|------|------|
| `helm-values/authentik-values.yaml` | `server.metrics.enabled: true` + ServiceMonitor |
| `helm-values/harbor-values.yaml` | `metrics.enabled: true` + ServiceMonitor |
| `helm-values/nginx-ingress-values.yaml` | `enable-latency-metrics: "true"`, chart ServiceMonitor |
| `helm-values/vault-values.yaml` | Telemetry HCL stanza |
| `manifests/monitoring/11-vault-servicemonitor.yaml` | New — Vault custom SM, `component: server` removed |
| `manifests/monitoring/12-synapse-servicemonitor.yaml` | New — standalone Service on 9090 + SM |
| `manifests/monitoring/13-service-alerts.yaml` | New — Harbor, NATS, Vault PrometheusRules |
| `manifests/monitoring/14-backstage-servicemonitor.yaml` | New — port 9464 |
| `manifests/monitoring/15-open-webui-servicemonitor.yaml` | New — port `http` / path `/metrics` |
| `manifests/network-policies/monitoring.yaml` | `allow-argo-rollouts` NetworkPolicy added |
| `services/platform-demo/base/analysis-template.yaml` | `kps-prometheus` service name fix |
| `minicloud-backstage/packages/backend/src/index.ts` | Separate metrics server on 9464 |
| `minicloud-open-webui/patches/sitecustomize.py` | New — `FastAPI.__init__` patch |
| `minicloud-open-webui/Dockerfile` | `prometheus-fastapi-instrumentator` install |
| `platform-demo/` + `minicloud-plane/` | `metrics/` package, `Instrument()` wrapper |

---

## Verification

```bash
# All 17 application targets up
kubectl port-forward svc/kps-prometheus -n monitoring 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import json, sys
ts = json.load(sys.stdin)['data']['activeTargets']
app = [t for t in ts if t['labels'].get('job','') not in
       ('apiserver','kubelet','kube-state-metrics','node-exporter')]
down = [t for t in app if t['health'] != 'up']
print(f'{len(app)} app targets, {len(down)} down')
for t in down: print(' ', t['labels']['job'], t['lastError'])
"

# platform-demo RED metrics present
curl -s 'http://localhost:9090/api/v1/query?query=http_requests_total{job="platform-demo"}' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print(len(r['data']['result']), 'series')"

# Vault telemetry responding
kubectl exec -n vault vault-0 -- \
  wget -qO- 'http://localhost:8200/v1/sys/metrics?format=prometheus' | head -5

# Matrix Synapse metrics (standalone Service required)
kubectl -n monitoring get servicemonitor synapse \
  -o jsonpath='{.spec.endpoints[0].port}' && echo  # should print: metrics

# Open WebUI metrics (sitecustomize.py patch active)
kubectl port-forward svc/open-webui -n ai 8080:80 &
curl -s http://localhost:8080/metrics | grep http_request_duration_seconds | head -3
```
