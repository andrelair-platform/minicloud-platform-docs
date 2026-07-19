---
id: application-monitoring
title: Application Monitoring — RED Metrics & Canary Analysis
sidebar_position: 7
---

# Application Monitoring — RED Metrics & Canary Analysis

After the infrastructure monitoring audit (Phase gap analysis, all 5 gaps closed), the next layer was **application-level observability**: instrumenting microservices with Prometheus metrics following Google's Four Golden Signals, wiring ServiceMonitors, and using those metrics as Argo Rollouts canary gates.

Two services were instrumented: `platform-demo` and `minicloud-plane`. A PodMonitor was added for NGINX Ingress latency. Three blocking issues were found and fixed along the way.

---

## Theory — Four Golden Signals vs RED

Google's Four Golden Signals (from the SRE book) define the minimum viable signal set for any production service:

| Signal | Description |
|--------|-------------|
| **Latency** | Time to serve a request — distinguish success from error latency |
| **Traffic** | Demand on the system (requests/sec) |
| **Errors** | Rate of failed requests — explicit (5xx) and implicit (wrong data) |
| **Saturation** | How full the service is — the resource that's most constrained |

**RED** is the per-microservice subset:

| Signal | Prometheus metric |
|--------|------------------|
| **Rate** | `http_requests_total` — requests per second |
| **Errors** | `http_requests_total{code=~"5.."}` — 5xx rate |
| **Duration** | `http_request_duration_seconds` — latency histogram |

Saturation is handled at the infrastructure layer (CPU/memory via node-exporter + VPA).

---

## Gap analysis before instrumentation

| Service | Rate | Errors | Duration | Notes |
|---------|------|--------|----------|-------|
| platform-demo | ❌ | ❌ | ❌ | No `/metrics`, Rollout AnalysisTemplate was a dead letter |
| minicloud-plane | ❌ | ❌ | ❌ | No `/metrics` |
| NGINX Ingress | ✅ | ✅ | ❌ | Metrics port 9113 active, no latency histogram (disabled by default) |
| LiteLLM | ✅ | ✅ | ✅ | Prometheus callback active from Phase 76 |
| Backstage, Open WebUI, Synapse, Stalwart | ❌ | ❌ | ❌ | No native Prometheus endpoint — P3 (exporters needed) |

Priority P1: platform-demo + minicloud-plane (own Go services — full control). P2: native-metrics services (NATS, Harbor, Authentik, Vault). P3: services requiring exporters.

---

## P1 — Instrumenting platform-demo

`platform-demo` is a minimal Go HTTP service. Two metrics were added using `prometheus/client_golang`:

```go
var (
    httpRequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
        Name: "http_requests_total",
        Help: "Total HTTP requests by method, handler, and status code.",
    }, []string{"method", "handler", "code"})

    httpRequestDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
        Name:    "http_request_duration_seconds",
        Help:    "HTTP request duration in seconds.",
        Buckets: []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5},
    }, []string{"method", "handler", "code"})
)
```

A `statusWriter` wrapper captures the HTTP response code after the handler returns (the code isn't known before `WriteHeader` is called):

```go
type statusWriter struct {
    http.ResponseWriter
    code int
}

func (sw *statusWriter) WriteHeader(code int) {
    sw.code = code
    sw.ResponseWriter.WriteHeader(code)
}

func instrument(pattern string, h http.HandlerFunc) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        sw := &statusWriter{ResponseWriter: w, code: http.StatusOK}
        start := time.Now()
        h(sw, r)
        code := strconv.Itoa(sw.code)
        httpRequestsTotal.WithLabelValues(r.Method, pattern, code).Inc()
        httpRequestDuration.WithLabelValues(r.Method, pattern, code).Observe(time.Since(start).Seconds())
    }
}
```

Routes:

```go
mux.HandleFunc("/", instrument("/", handleRoot))
mux.HandleFunc("/healthz", instrument("/healthz", handleHealthz))
mux.HandleFunc("/readyz", instrument("/readyz", handleReadyz))
mux.Handle("/metrics", promhttp.Handler())  // probe routes are NOT instrumented
```

The `/healthz` and `/readyz` probes are instrumented intentionally — their latency shows kubelet probe overhead. The `/metrics` endpoint itself is not (it would add noise to the rate signal).

---

## P1 — Instrumenting minicloud-plane

`minicloud-plane` uses the same metric definitions, extracted to `internal/metrics/middleware.go` since it serves multiple route families (`/webhook`, `/api/`):

```go
// internal/metrics/middleware.go
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

Routes in `cmd/server/main.go`:

```go
mux.HandleFunc("/health", healthHandler)  // probe — intentionally NOT instrumented
mux.Handle("/webhook", metrics.Instrument("/webhook", webhook.NewHandler(...)))
mux.Handle("/api/", metrics.Instrument("/api/", planeapi.NewHandler(...)))
mux.Handle("/metrics", promhttp.Handler())
```

The `/health` probe is excluded — it runs on every kubelet cycle and would dominate the request rate signal.

---

## ServiceMonitors

Both services get a `ServiceMonitor` in their kustomize `base/`:

```yaml
# services/platform-demo/base/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: platform-demo
spec:
  selector:
    matchLabels:
      app: platform-demo
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

**No `metadata.namespace` and no `spec.namespaceSelector` in the base.** This is intentional:

- kustomize's `namespace:` field in an overlay rewrites `metadata.namespace` on every resource — the ServiceMonitor lands in the correct namespace per overlay automatically.
- Without `namespaceSelector`, prometheus-operator defaults to scraping in the ServiceMonitor's own namespace — which is exactly what you want when using overlays (dev SM scrapes dev Service, prod SM scrapes prod Service).

Adding `namespaceSelector` to the base would cause the dev overlay SM (namespace: `platform-demo-dev`) to scrape the service in the wrong namespace.

The Service also needs a named port for the ServiceMonitor `port:` reference:

```yaml
# services/minicloud-plane/base/service.yaml
ports:
  - name: http     # required — ServiceMonitor references by name, not number
    port: 8080
    targetPort: 8080
```

---

## NGINX Ingress — PodMonitor + latency metrics

F5 NGINX Ingress Controller v5.4.1 exposes a Prometheus metrics port (9113) on each pod, named `prometheus`. There is no dedicated metrics Service — a PodMonitor is used instead of a ServiceMonitor:

```yaml
# manifests/monitoring/10-nginx-ingress-podmonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: nginx-ingress
  namespace: monitoring
spec:
  namespaceSelector:
    matchNames:
      - ingress-nginx
  selector:
    matchLabels:
      app.kubernetes.io/name: nginx-ingress
  podMetricsEndpoints:
    - port: prometheus
      scheme: http
      path: /metrics
      interval: 30s
```

Upstream latency histograms (`nginx_upstream_server_response_latency_ms`) are disabled by default. Enable them:

```yaml
# helm-values/nginx-ingress-values.yaml
controller:
  enableLatencyMetrics: true
```

---

## CI bump-gitops — PR auto-merge pattern

Both services push to `harbor.10.0.0.200.nip.io` and bump the kustomize overlay in `minicloud-gitops`. The gitops repo's `main` branch has a `main-protection` ruleset with no bypass actors — direct push is blocked.

**Pattern used:**

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
    if git diff --cached --quiet; then
      echo "No change — already at ${SHA}"
      exit 0
    fi
    git commit -S -m "ci(platform-demo): bump dev image to ${SHA}"
    git push origin "${BRANCH}"
    gh pr create \
      --repo andrelair-platform/minicloud-gitops \
      --base main --head "${BRANCH}" \
      --title "ci(platform-demo): bump dev image to ${SHA}" \
      --body "Automated image promotion from CI run ${{ github.run_id }}."
    gh pr merge "${BRANCH}" \
      --repo andrelair-platform/minicloud-gitops \
      --admin --merge --delete-branch
```

Key points:
- `GH_TOKEN` must be `GITOPS_TOKEN` (not `GITHUB_TOKEN`) — needs write access to the gitops repo, which is a different repo from the one the workflow runs in.
- `--admin` bypasses the PR review requirement using the token owner's admin role.
- `main` branch push → `overlays/dev` (not `overlays/prod` — prod requires an explicit human PR).
- The image verification step (curl + Harbor Registry API) runs before the bump to prevent writing a dead tag to gitops.

---

## Three blocking issues found during rollout

### Issue 1 — Wrong Prometheus service name in AnalysisTemplate

The Argo Rollouts AnalysisTemplate (from Phase 73) referenced the default kube-prometheus-stack service name:

```yaml
# BROKEN
address: http://kube-prometheus-stack-prometheus.monitoring.svc:9090
```

The Helm release was installed with release name `kps`, so the actual service is `kps-prometheus`:

```yaml
# FIXED
address: http://kps-prometheus.monitoring.svc:9090
```

Every canary deploy since Phase 73 was silently aborting due to this DNS failure. Fix: `gitops PR #167`.

**How to find the correct service name:** `kubectl get svc -n monitoring | grep prometheus` — look for the ClusterIP service on port 9090 (not `prometheus-operated`, which is the headless StatefulSet service).

### Issue 2 — NetworkPolicy blocks Argo Rollouts → Prometheus

The `monitoring` namespace has a `default-deny-ingress` NetworkPolicy. The `allow-observability` allowlist only included `observability`, `kube-system`, `ingress-nginx`, and `falco`. The Argo Rollouts controller (in `argo-rollouts` namespace) was refused:

```
Post "http://kps-prometheus.monitoring.svc:9090/api/v1/query": 
dial tcp 10.43.253.241:9090: connect: connection refused
```

The Prometheus pod was healthy (`prometheus-kps-prometheus-0`, 2/2 Running) — the issue was purely NetworkPolicy. Fix: added `allow-argo-rollouts` policy scoped to port 9090 (`gitops PR #169`):

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-argo-rollouts
  namespace: monitoring
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: argo-rollouts
      ports:
        - port: 9090
          protocol: TCP
```

**General rule:** when adding a `default-deny-ingress` policy to a namespace, enumerate every controller or operator that queries services in that namespace (Prometheus, cert-manager, ArgoCD, Argo Rollouts, ESO, etc.) and add allow rules for each.

### Issue 3 — kubectl-argo-rollouts plugin not installed on controller

After fixing the NetworkPolicy, retrying the aborted Rollout required the plugin:

```bash
# Install on controller (matches app version v1.9.0 deployed in Phase 73)
curl -sL https://github.com/argoproj/argo-rollouts/releases/download/v1.9.0/kubectl-argo-rollouts-linux-amd64 \
  -o ~/.local/bin/kubectl-argo-rollouts
chmod +x ~/.local/bin/kubectl-argo-rollouts

# Retry aborted rollout
kubectl argo rollouts retry rollout platform-demo -n platform-demo-dev
```

The plugin version must match (or be compatible with) the controller version — a mismatch causes API errors.

---

## Canary AnalysisTemplate — success rate gate

With both issues fixed, the Phase 73 AnalysisTemplate works as intended:

```yaml
# services/platform-demo/base/analysis-template.yaml
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

- 5 samples × 30s = 2.5 min of analysis
- Gate: ≥95% non-5xx requests
- On failure: rollout aborts, stable RS stays live, no user impact

The canary deploy flow after instrumentation:

1. CI pushes new image → `gh pr merge --admin` bumps `overlays/dev/kustomization.yaml`
2. ArgoCD syncs → Argo Rollouts detects image change → starts canary
3. Canary RS comes up at 50% traffic
4. AnalysisRun runs 5× Prometheus queries against `http_requests_total` from the canary pod
5. If ≥95% success: promote to 100%, mark new RS as stable
6. If below 95%: abort, revert to previous stable RS

---

## Prometheus targets — final state

After all fixes, three new targets are `up`:

```
up  platform-demo    platform-demo-dev   http://10.42.4.236:9898/metrics
up  minicloud-plane  minicloud-plane-dev http://10.42.1.66:8080/metrics  
up  nginx-ingress    ingress-nginx       http://10.42.0.167:9113/metrics
```

Verify:

```bash
kubectl exec -n monitoring prometheus-kps-prometheus-0 -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/targets?state=active' \
  | python3 -c "
import json,sys
data=json.load(sys.stdin)
for t in data['data']['activeTargets']:
    labels=t['labels']
    if any(x in str(labels) for x in ['platform-demo','minicloud-plane','nginx-ingress']):
        print(t['health'], labels.get('job'), labels.get('namespace'), t['scrapeUrl'])
"
```

---

## Sample PromQL queries

**platform-demo request rate (req/s):**
```promql
sum(rate(http_requests_total{job="platform-demo"}[2m])) by (handler)
```

**platform-demo p99 latency:**
```promql
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="platform-demo"}[5m])) by (le, handler))
```

**minicloud-plane webhook error rate:**
```promql
sum(rate(http_requests_total{job="minicloud-plane", handler="/webhook", code=~"5.."}[5m]))
/
sum(rate(http_requests_total{job="minicloud-plane", handler="/webhook"}[5m]))
```

**NGINX upstream latency p95 (ms):**
```promql
histogram_quantile(0.95, sum(rate(nginx_upstream_server_response_latency_ms_bucket[5m])) by (le, ingress))
```

---

## Gotcha summary

| Gotcha | Symptom | Fix |
|--------|---------|-----|
| kube-prometheus-stack release name prefix | AnalysisRun DNS error: `no such host kube-prometheus-stack-prometheus` | Use actual service name: `kubectl get svc -n monitoring` |
| NetworkPolicy blocks controller→Prometheus | `connection refused` from Argo Rollouts AnalysisRun | Add `allow-argo-rollouts` NetworkPolicy in `monitoring` namespace |
| `kubectl argo rollouts` plugin not installed | `unknown command "argo" for "kubectl"` | Install matching version from GitHub releases |
| ServiceMonitor `namespaceSelector` in base | Dev SM scrapes prod namespace | Omit `namespaceSelector` — prometheus-operator defaults to own namespace |
| Direct push to gitops main blocked | CI: `remote: error: GH006: Protected branch update failed` | Use `gh pr create` + `gh pr merge --admin` pattern |
| `main` branch → `overlays/prod` | Prod never got instrumented image, no dev testing | Map `main` → `overlays/dev`; prod requires explicit human PR |
