---
id: application-monitoring
title: Application Monitoring — RED Metrics & Service Alerts
sidebar_position: 7
---

# Application Monitoring — RED Metrics & Service Alerts

This page covers application-level observability: instrumenting microservices with Prometheus metrics following Google's RED method, enabling native metrics on third-party services, wiring ServiceMonitors, and creating PrometheusRule alerts for the remaining signal gaps.

Work was done in three phases: P1 (own Go services), P2 (native-metrics third-party services), P3 (custom instrumentation for Backstage and Open WebUI), and RED signal gap resolution.

---

## Theory — RED Method

| Signal | Description | Prometheus pattern |
|--------|-------------|--------------------|
| **Rate** | Requests per second | `rate(http_requests_total[2m])` |
| **Errors** | Failed request rate | `rate(http_requests_total{code=~"5.."}[2m])` |
| **Duration** | Latency distribution | `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))` |

Saturation (CPU/memory) is handled at the infrastructure layer via node-exporter + VPA.

---

## P1 — Own Go services

### Instrumentation pattern

Both `platform-demo` and `minicloud-plane` use the same two metrics defined via `promauto`:

```go
httpRequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
    Name: "http_requests_total",
}, []string{"method", "handler", "code"})

httpRequestDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
    Name:    "http_request_duration_seconds",
    Buckets: []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5},
}, []string{"method", "handler", "code"})
```

A `statusWriter` wrapper captures the HTTP response code after the handler returns (the code is only known after `WriteHeader` is called):

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

### minicloud-plane — instrument the health probe

Routes in `cmd/server/main.go`:

```go
// All four routes are wrapped — including /health
mux.Handle("/health", metrics.Instrument("/health", http.HandlerFunc(healthHandler)))
mux.Handle("/webhook", metrics.Instrument("/webhook", webhook.NewHandler(...)))
mux.Handle("/api/", metrics.Instrument("/api/", planeapi.NewHandler(...)))
mux.Handle("/metrics", promhttp.Handler())
```

:::caution Promauto gotcha — metrics absent until first request
`promauto.NewCounterVec` and `NewHistogramVec` register the metric but do **not** emit any output until `.WithLabelValues()` is called at least once. In a distroless Go container with no shell and no initial traffic, `http_requests_total` is completely absent from `/metrics` output — Prometheus shows the target as `up` but returns 0 series for that metric.

**Fix:** wrap the liveness probe endpoint with `Instrument()`. The kubelet hits `/health` every ~15 seconds, seeding both the counter and histogram within one scrape cycle. `/metrics` itself must NOT be wrapped (would add noise to the rate signal).
:::

### ServiceMonitors

Both services get a `ServiceMonitor` in their kustomize `base/`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: platform-demo
  # no namespace here — kustomize namespace transformer sets it per overlay
spec:
  selector:
    matchLabels:
      app: platform-demo
  endpoints:
    - port: http    # must be a named port on the Service
      path: /metrics
      interval: 30s
  # no namespaceSelector — defaults to own namespace (correct for overlay pattern)
```

**Why no `namespaceSelector`:** prometheus-operator defaults to scraping in the ServiceMonitor's own namespace. Since kustomize writes the SM to `platform-demo-dev`, it scrapes the Service in `platform-demo-dev`. Adding a `namespaceSelector` to the base would cause the dev SM to scrape the wrong namespace.

---

## P1 — NGINX Ingress — community ingress-nginx 4.15.1

The cluster was migrated from F5 nginx-ingress to community `ingress-nginx/ingress-nginx` chart 4.15.1 (see NGINX migration runbook for full context). The community chart exposes `nginx_ingress_controller_request_duration_seconds_bucket` — a per-route latency histogram — natively in OSS mode.

**Key helm-values configuration:**

```yaml
# helm-values/nginx-ingress-values.yaml
controller:
  config:
    enable-latency-metrics: "true"   # ConfigMap key — NOT a CLI flag
    allow-snippet-annotations: "true"
    annotations-risk-level: "Critical"
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
      namespace: monitoring
```

The chart creates the ServiceMonitor automatically (`controller.metrics.serviceMonitor.enabled: true`). No manual PodMonitor needed.

**Histogram labels:** `ingress`, `host`, `method`, `status`, `path`, `le` — full per-route breakdown.

:::caution annotations-risk-level is a ConfigMap key, not a CLI flag
`server-snippet` and `configuration-snippet` annotations are risk level `Critical` in community ingress-nginx v1.12+. Setting only `allow-snippet-annotations: "true"` is insufficient — you must also add `annotations-risk-level: "Critical"` to `controller.config`. Adding it under `extraArgs` causes CrashLoopBackOff (`unknown flag: --annotations-risk-level`).
:::

---

## P1 — Canary AnalysisTemplate

With both Go services instrumented, the Phase 73 Argo Rollouts AnalysisTemplate works as intended for `platform-demo`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: http-success-rate
spec:
  metrics:
    - name: success-rate
      count: 5
      interval: 30s
      successCondition: result[0] >= 0.95
      failureLimit: 3
      provider:
        prometheus:
          address: http://kps-prometheus.monitoring.svc:9090
          query: |
            sum(rate(http_requests_total{service="platform-demo",code!~"5.."}[2m]))
            /
            sum(rate(http_requests_total{service="platform-demo"}[2m]))
```

- 5 samples × 30s = 2.5 min of canary analysis
- Gate: ≥95% non-5xx requests
- On failure: rollout aborts, stable RS stays live

:::caution Use the actual Prometheus service name
The kube-prometheus-stack was installed with release name `kps`. All services are prefixed `kps-*`. `kube-prometheus-stack-prometheus.monitoring.svc` does not resolve — always run `kubectl get svc -n monitoring` to find the real name.
:::

---

## P2 — Native-metrics third-party services

These services expose `/metrics` natively and only needed Helm values changes and ServiceMonitors.

### Authentik

```yaml
# helm-values/authentik-values.yaml
server:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
```

Chart exposes port 9300 with `authentik_main_request_duration_seconds` histogram. **1 target `up`.**

### Harbor

```yaml
# helm-values/harbor-values.yaml
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
```

Enables harbor-exporter sidecar (port 8001) on core/registry/jobservice/exporter pods. Chart creates 4 ServiceMonitors. **4 targets `up`.**

:::caution Harbor pods need manual restart after enabling metrics
Harbor stores `METRIC_ENABLE=true` in a ConfigMap loaded via `envFrom`. The pods do not reload automatically without the Reloader annotation. After enabling metrics:
```bash
kubectl rollout restart deployment/harbor-core deployment/harbor-jobservice -n harbor
```
If harbor-jobservice is stuck (Longhorn RWO Multi-Attach on different node): `kubectl rollout undo deployment/harbor-jobservice -n harbor`.
:::

### NATS

Already configured from Phase 55. Chart-native PodMonitor (`promExporter.podMonitor.enabled: true`). **3 targets `up`** on port 7777.

### Vault

Added `telemetry` stanza to Vault HCL config in `helm-values/vault-values.yaml`:

```hcl
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname           = true
}
# inside listener "tcp":
telemetry {
  unauthenticated_metrics_access = true
}
```

Custom `manifests/monitoring/11-vault-servicemonitor.yaml` targets port 8200, path `/v1/sys/metrics?format=prometheus`. **2 targets `up`** (vault + vault-internal jobs).

:::caution vault Service does not have the `component: server` pod label
The Vault StatefulSet pod has label `component: server` but the Service does not. An over-specific `matchLabels: {component: server}` on the ServiceMonitor selector finds zero endpoints → target absent from Prometheus entirely. Remove `component: server` from the selector.
:::

### LiteLLM

Already configured from Phase 57 (`success_callback: ["prometheus"]` + `require_auth_for_metrics_endpoint: false`). **1 target `up`.**

### Matrix Synapse

```yaml
# helm-values/synapse-values.yaml
extraConfig: |
  enable_metrics: true
```

Chart generates a `metrics_port: 9090` listener but does **not** expose it in the chart-managed Service (only port 8008). Added standalone `matrix-synapse-metrics` Service in `manifests/monitoring/12-synapse-servicemonitor.yaml`. **1 target `up`.**

---

## P3 — Custom instrumentation

### Backstage — separate metrics server on port 9464

Backstage's `plugin-app-backend` registers a catch-all SPA handler on port 7007 that intercepts **all** routes — including `/metrics` — and returns the SPA HTML with HTTP 200 but wrong content-type. Prometheus's text parser rejects it and marks the target `down`.

The fix is a separate `http.createServer` using `prom-client`'s default registry, started before `createBackend()` in `packages/backend/src/index.ts`:

```typescript
import * as http from 'http';
import * as promClient from 'prom-client';

// Expose Prometheus metrics on port 9464 — separate from 7007 to avoid
// the plugin-app-backend catch-all intercepting /metrics with SPA HTML.
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

`prom-client` is a transitive dependency already pulled in by `@backstage/plugin-catalog-backend` and `@backstage/plugin-scaffolder-backend` — no new dependency needed.

The Bitnami chart exposes the port via `extraPorts` (container) and `service.extraPorts` (Service), then a ServiceMonitor in `monitoring` namespace picks it up. **1 target `up`** — 43 Node.js process metric families.

:::caution plugin-app-backend catch-all intercepts /metrics on port 7007
`GET /metrics` on port 7007 returns HTTP 200 with SPA HTML content. Prometheus marks the target `down` with a content-type parse error. The only fix is a completely separate HTTP server on a different port — there is no middleware injection point that runs before the SPA catch-all.
:::

### Open WebUI — `prometheus-fastapi-instrumentator` via `sitecustomize.py`

Open WebUI is a FastAPI app with no native Prometheus endpoint. The custom image adds instrumentation without touching upstream code by exploiting Python's `sitecustomize.py` auto-load mechanism.

`patches/sitecustomize.py` patches `FastAPI.__init__` before any user code runs:

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
        pass

_f.FastAPI.__init__ = _new
```

The Dockerfile installs `prometheus-fastapi-instrumentator` and copies the file to `site.getsitepackages()[0]/sitecustomize.py`. Python loads it automatically before `open_webui.main` is imported by uvicorn.

The ServiceMonitor in `manifests/monitoring/15-open-webui-servicemonitor.yaml` targets the existing `http` port (80) on the Open WebUI Service — no additional port needed since uvicorn serves both the app and `/metrics` on port 8080. **1 target `up`** with full FastAPI `http_request_duration_seconds` histogram.

:::note Stalwart and ERPNext accepted as N/A
**Stalwart v0.16.13 CE** — no `/metrics` endpoint in the binary. ERPNext (Frappe/Gunicorn) returns 404 on all Prometheus paths. Both are instrumentation dead-ends without upstream changes; accepted as monitoring gaps.
:::

---

## Final Prometheus target state

| Service | Targets | Notes |
|---------|---------|-------|
| authentik | 1 | port 9300 |
| backstage | 1 | port 9464, prom-client default registry |
| harbor | 4 | core + registry + jobservice + exporter |
| litellm | 1 | port 8080 |
| nats | 3 | one per pod |
| nginx-ingress | 1 | port 10254, chart ServiceMonitor |
| open-webui | 1 | port 8080, prometheus-fastapi-instrumentator |
| platform-demo | 1 | port 9898 |
| minicloud-plane | 1 | port 8080 |
| matrix-synapse | 1 | port 9090 |
| vault | 2 | vault + vault-internal jobs |
| **Total** | **17** | **all `up`, 64/64 total Prometheus targets** |

---

## RED signal gap audit & resolution

After all ServiceMonitors were wired, a gap audit checked which services had all three RED signals available.

### Gap audit results

| Service | Rate | Errors | Latency | Root cause |
|---------|------|--------|---------|------------|
| platform-demo | ✅ | ✅ | ✅ histogram | Custom instrumentation |
| minicloud-plane | ✅ | ✅ | ✅ histogram | Custom instrumentation + `/health` probe fix |
| NGINX Ingress | ✅ | ✅ | ✅ histogram | `nginx_ingress_controller_request_duration_seconds_bucket`, 216 samples, per-route `(ingress, host, method, status)` labels |
| Harbor | ✅ | ✅ | ⚠️ avg only | `harbor_core_http_request_total{code}` has status label ✅. Latency uses `prometheus.Summary` in upstream Go code — only `_count/_sum`, no `_bucket` |
| NATS | ✅ | ⚠️ backpressure | ❌ | `nats_varz_slow_consumers` + JetStream API error counter available. Per-message latency not exposed by prometheus-nats-exporter |
| Vault | ✅ | ❌ | ⚠️ avg only | No HTTP status codes in CE telemetry. Latency is `vault_core_handle_request` Summary (avg only). `vault_core_handle_request_sum / count` shows ~16s avg — AWS KMS round-trips from home lab |
| Authentik | ✅ | ✅ | ✅ histogram | `authentik_main_request_duration_seconds` histogram |
| LiteLLM | ✅ | ✅ | ✅ | Native callbacks |

### Upstream limitations

These cannot be fixed without patching upstream source code:

- **Harbor/Vault latency:** Both use `prometheus.Summary` in their Go code — emits `_count` and `_sum` only, no `_bucket`. `histogram_quantile` is impossible. Best available signal: `rate(sum[5m]) / rate(count[5m])` for rolling average.
- **Vault HTTP errors:** Vault CE telemetry endpoint does not expose HTTP 4xx/5xx status code counters.
- **NATS per-message latency:** The prometheus-nats-exporter polls NATS's `/varz` HTTP monitoring endpoint, which does not include delivery timing.

---

## PrometheusRule — service-level alerts

`manifests/monitoring/13-service-alerts.yaml` covers the remaining alertable signals (gitops PRs #195, #199, #201, #203):

### Harbor alerts

```yaml
- alert: HarborHighErrorRate
  expr: |
    sum(rate(harbor_core_http_request_total{code=~"5.."}[5m])) /
    sum(rate(harbor_core_http_request_total[5m])) > 0.01
  for: 5m
  # fires when 5xx rate > 1% sustained over 5 minutes

- alert: HarborJobServiceErrors
  expr: sum(rate(harbor_jobservice_task_total{status="Error"}[10m])) > 0
  for: 10m
```

### NATS alerts

```yaml
- alert: NATSSlowConsumers
  expr: nats_varz_slow_consumers > 0
  for: 2m
  # slow consumer = subscriber can't keep up, NATS will drop messages

- alert: NATSJetStreamAPIErrors
  expr: increase(nats_varz_jetstream_stats_api_errors[5m]) > 0
  for: 0m

- alert: NATSStaleConnections
  expr: increase(nats_varz_stale_connections[5m]) > 0
  for: 0m
```

:::caution nats_varz_stale_connections is a cumulative counter, not a gauge
`nats_varz_stale_connections` counts connections forcibly closed by NATS due to slow consumer backpressure — it only increments, never decrements. Using `> 5` fires permanently once 5 total stale connections have ever occurred. Use `increase([5m]) > 0` to alert only when new force-closures happen.
:::

### Vault alerts

```yaml
- alert: VaultHighRequestLatency
  expr: |
    (
      rate(vault_core_handle_request_sum[5m]) /
      rate(vault_core_handle_request_count[5m]) > 0.5
    ) and (
      rate(vault_core_handle_request_count[5m]) > 0.05
    )
  for: 5m
  # avg latency > 500ms, with minimum traffic guard of 0.05 req/s

- alert: VaultSealedOrUnhealthy
  expr: vault_core_active == 0
  for: 1m
  labels:
    severity: critical
```

:::caution VaultHighRequestLatency needs a minimum traffic rate guard
`rate(sum[5m]) / rate(count[5m])` on a low-volume counter (e.g., 1 request at startup) returns the latency of that single request. A KMS unseal or barrier initialization can take 10-30 seconds — which triggers the 500ms threshold as a false positive. The `AND rate(count[5m]) > 0.05` guard (≥3 req/min) prevents this.
:::

---

## CI bump-gitops — PR auto-merge pattern

Both Go services push to `harbor.10.0.0.200.nip.io` and bump the kustomize overlay in `minicloud-gitops`. The gitops repo's `main` branch requires PRs — direct push is blocked.

```yaml
- name: Bump image tag and open auto-merged PR
  env:
    GH_TOKEN: ${{ secrets.GITOPS_TOKEN }}
  run: |
    SHA="${{ needs.build-and-push.outputs.image_tag }}"
    BRANCH="ci/platform-demo-${SHA}"
    git checkout -b "${BRANCH}"
    cd services/platform-demo/overlays/dev
    kustomize edit set image harbor.10.0.0.200.nip.io/library/platform-demo:${SHA}
    cd -
    git add services/platform-demo/overlays/dev/kustomization.yaml
    git commit -S -m "ci(platform-demo): bump dev image to ${SHA}"
    git push origin "${BRANCH}"
    gh pr create --repo andrelair-platform/minicloud-gitops \
      --base main --head "${BRANCH}" \
      --title "ci(platform-demo): bump dev image to ${SHA}" \
      --body "Automated image promotion from CI run ${{ github.run_id }}."
    gh pr merge "${BRANCH}" \
      --repo andrelair-platform/minicloud-gitops \
      --admin --merge --delete-branch
```

- `GITOPS_TOKEN` (not `GITHUB_TOKEN`) — needs write access to the gitops repo
- `--admin` bypasses the PR review requirement
- `main` push → `overlays/dev` only; prod requires an explicit human PR

---

## Useful PromQL queries

**platform-demo request rate:**
```promql
sum(rate(http_requests_total{job="platform-demo"}[2m])) by (handler)
```

**platform-demo p99 latency:**
```promql
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{job="platform-demo"}[5m])) by (le, handler)
)
```

**minicloud-plane webhook error rate:**
```promql
sum(rate(http_requests_total{job="minicloud-plane", handler="/webhook", code=~"5.."}[5m]))
/
sum(rate(http_requests_total{job="minicloud-plane", handler="/webhook"}[5m]))
```

**NGINX per-route p99 latency:**
```promql
histogram_quantile(0.99,
  sum(rate(nginx_ingress_controller_request_duration_seconds_bucket[5m])) by (le, ingress, status)
)
```

**NGINX per-route error rate:**
```promql
sum(rate(nginx_ingress_controller_requests{status=~"5.."}[5m])) by (ingress)
/
sum(rate(nginx_ingress_controller_requests[5m])) by (ingress)
```

**Harbor 5xx rate:**
```promql
sum(rate(harbor_core_http_request_total{code=~"5.."}[5m])) by (operation)
```

**Harbor avg latency (Summary — no p99 available):**
```promql
rate(harbor_core_http_request_duration_seconds_sum[5m])
/
rate(harbor_core_http_request_duration_seconds_count[5m])
```

**Vault avg request latency:**
```promql
rate(vault_core_handle_request_sum{job="vault-internal"}[5m])
/
rate(vault_core_handle_request_count{job="vault-internal"}[5m])
```

---

## Gotcha summary

| Gotcha | Symptom | Fix |
|--------|---------|-----|
| promauto metrics absent until first `.WithLabelValues()` call | Target `up` but metric has 0 series in Prometheus | Instrument the liveness probe endpoint — probes seed counters within seconds |
| kube-prometheus-stack release name prefix | AnalysisRun DNS error: `no such host kube-prometheus-stack-prometheus` | `kubectl get svc -n monitoring` — actual name is `kps-prometheus` |
| NetworkPolicy blocks Argo Rollouts → Prometheus | `connection refused` from AnalysisRun | Add `allow-argo-rollouts` NetworkPolicy in `monitoring` namespace (port 9090) |
| `annotations-risk-level` is ConfigMap key not CLI flag | CrashLoopBackOff if set under `extraArgs` | Set in `controller.config` section alongside `allow-snippet-annotations` |
| `nats_varz_stale_connections` is cumulative counter | Alert fires permanently once count > threshold | Use `increase([5m]) > 0` not `> N` |
| Vault latency false positive on low-count counter | Single 16s KMS startup request triggers 500ms alert | Add `AND rate(count[5m]) > 0.05` minimum traffic guard |
| Harbor/Vault: Summary not Histogram | No `_bucket` → `histogram_quantile` fails | Upstream limitation — use `rate(sum)/rate(count)` for average only |
| ServiceMonitor `namespaceSelector` in kustomize base | Dev SM scrapes prod namespace | Omit `namespaceSelector` — prometheus-operator defaults to own namespace |
| Vault ServiceMonitor `component: server` over-specified | Zero endpoints found, target absent from Prometheus | Remove `component: server` — that label exists on pods, not on the Service |
| Backstage: `plugin-app-backend` catch-all on port 7007 intercepts `/metrics` | Target `down` with parse error (content-type: text/html) | Add separate `http.createServer` on port 9464 using `prom-client` — do not add middleware on port 7007 |
| Open WebUI: FastAPI app instrumented via `sitecustomize.py` auto-load | (not a failure — design note) | `sitecustomize.py` in `site-packages/` is loaded by Python before any user code; patches `FastAPI.__init__` to inject `prometheus-fastapi-instrumentator` on every app instance |
