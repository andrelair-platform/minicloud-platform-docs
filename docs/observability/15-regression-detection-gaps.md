---
id: regression-detection-gaps
title: Regression Detection — Gap Analysis & Fixes
sidebar_position: 15
---

# Regression Detection — Gap Analysis & Fixes

Regression detection answers the one question every deployment must answer:
**did this release make things worse?**

```
Before deployment          After deployment
──────────────────         ─────────────────
p95 latency   150 ms  →   p95 latency   450 ms   ← regression
Error rate    0.1%    →   Error rate    3.0%      ← regression
Throughput    120 rps →   Throughput    120 rps   ← OK
CPU           0.05    →   CPU           0.15      ← regression
Memory        32 Mi   →   Memory        33 Mi     ← OK
```

The cluster had all the raw metrics in Prometheus but none of the tooling that
turns those metrics into a structured before/after comparison. Every deployment
was a leap of faith — you had to remember to look at Grafana yourself, recall
what the numbers were before the deploy, and decide manually whether the delta
was acceptable.

---

## Gap inventory

| # | Gap | Root cause | Severity |
|---|-----|-----------|----------|
| R1 | No recording rules | `histogram_quantile` re-computed from raw buckets on every query | Medium |
| R2 | AnalysisTemplate checks success rate only | No p95 gate, no throughput gate | High |
| R3 | minicloud-plane has no Rollout | Plain Deployment — zero regression protection | High |
| R4 | No before/after comparison dashboard | Must manually compare two time windows | High |
| R5 | No regression PrometheusRules | Nothing fires when p95 triples after a deploy | High |
| R6 | Deployment events not visible on dashboards | Can't correlate metric spikes to specific deploys | Medium |
| R7 | CI declares success before metrics stabilize | Gitops bump + exit, no post-deploy verification | Medium |

---

## The `offset` technique

Prometheus's `offset` modifier is the key enabler. It shifts a query window
back in time so the same expression can compare two points:

```promql
# Current p95 latency
histogram_quantile(0.95, job:http_request_duration_seconds_bucket:rate5m{service="platform-demo"})

# Baseline p95 from 1 hour ago — same expression, different time window
histogram_quantile(0.95, job:http_request_duration_seconds_bucket:rate5m{service="platform-demo"} offset 1h)

# Regression ratio — fire when current is > 2× baseline
(current) / (baseline offset 1h) > 2
```

`offset 1h` assumes a 1-hour deployment cycle. If a deployment happened 45
minutes ago and the current window shows degraded metrics, the baseline is the
pre-deployment steady state. No external state store, no baseline snapshots —
it's all in Prometheus's existing TSDB.

**Guard against false positives during idle periods:** a ratio of 100×
fires if the baseline was near zero (e.g., 1ms p95 at 3 AM with no traffic).
Every regression rule in this cluster requires the baseline to exceed a
minimum meaningful threshold before the ratio is evaluated.

---

## Gap R1 — No recording rules

### Problem

Every Grafana panel and every AnalysisRun query called
`rate(http_request_duration_seconds_bucket[5m])` against the raw per-pod metric
stream. At 64 Prometheus targets with histogram metrics, this is an expensive
fan-out computation re-executed on every 30-second scrape cycle.

### Fix

`manifests/monitoring/24-regression-recording-rules.yaml` — a PrometheusRule
with `interval: 30s`:

```yaml
# Pre-aggregate histogram buckets — eliminates per-pod cardinality fan-out
- record: job:http_request_duration_seconds_bucket:rate5m
  expr: sum by (le, service, namespace) (rate(http_request_duration_seconds_bucket[5m]))

# Request rate per service
- record: job:http_requests_total:rate5m
  expr: sum by (service, namespace) (rate(http_requests_total[5m]))

# Error rate fraction 0.0–1.0
- record: job:http_requests_error_fraction:rate5m
  expr: |
    sum by (service, namespace) (rate(http_requests_total{code=~"5.."}[5m]))
    / sum by (service, namespace) (rate(http_requests_total[5m]))

# Container CPU per pod
- record: job:container_cpu_usage:rate5m
  expr: sum by (pod, namespace) (rate(container_cpu_usage_seconds_total{container!="", container!="POD"}[5m]))

# Container memory working set per pod
- record: job:container_memory_working_set:bytes
  expr: sum by (pod, namespace) (container_memory_working_set_bytes{container!="", container!="POD"})

# p95 latency shorthand — applied at recording time
- record: job:http_request_duration_p95:rate5m
  expr: histogram_quantile(0.95, job:http_request_duration_seconds_bucket:rate5m)
```

All AnalysisTemplates and the regression dashboard consume these pre-computed
metrics instead of the raw series. Grafana load time for histogram panels drops
noticeably because `histogram_quantile` runs once per 30-second tick instead of
on every panel render.

---

## Gap R2 — AnalysisTemplate checks only success rate

### Problem

The platform-demo canary had a single gate:

```yaml
- name: success-rate
  successCondition: result[0] >= 0.95
  query: |
    sum(rate(http_requests_total{service="platform-demo",code!~"5.."}[2m]))
    / sum(rate(http_requests_total{service="platform-demo"}[2m]))
```

This would not catch:
- A latency regression from 50ms → 5 seconds (success rate stays 100%)
- A new version that starts but receives no traffic (success rate = NaN → undefined)
- A throughput drop caused by crashing pods being silently replaced

### Fix

`services/platform-demo/base/analysis-template.yaml` — replaced with three gates:

```yaml
# Gate 1: error rate (unchanged)
- name: success-rate
  successCondition: result[0] >= 0.95

# Gate 2: p95 latency ≤ 500ms
- name: p95-latency
  successCondition: result[0] <= 0.5
  query: |
    histogram_quantile(0.95,
      job:http_request_duration_seconds_bucket:rate5m{service="platform-demo"})

# Gate 3: canary is actually receiving traffic
- name: receiving-traffic
  successCondition: result[0] > 0
  query: sum(rate(http_requests_total{service="platform-demo"}[2m]))
```

The traffic gate (Gate 3) catches the silent failure case: a new pod that starts
cleanly but whose readiness probe passes while the kube-proxy rules haven't fully
converged yet. `result[0] > 0` must be true before the analysis passes.

The 500ms p95 threshold is generous — production p95 is ~150ms. The gate fires
on hard regressions (10× latency) while leaving headroom for cold-start JIT effects
during the 30-second canary window.

---

## Gap R3 — minicloud-plane has no Rollout

### Problem

`minicloud-plane` was a plain `apps/v1 Deployment`. It received image updates
via `kustomize edit set image` and ArgoCD auto-sync. If a new image had a bug
that caused 100% errors, the deployment completed successfully, the old pod
terminated, and the service went down — with no automated detection or rollback.

### Fix

`services/minicloud-plane/base/deployment.yaml` converted to
`argoproj.io/v1alpha1 Rollout` with:

```yaml
strategy:
  canary:
    steps:
      - setWeight: 100    # atomic switch — no split (single replica)
      - pause: {duration: 2m}
      - analysis:
          templates:
            - templateName: http-regression-gate
```

With 1 replica, a 50/50 traffic split is not meaningful. `setWeight: 100`
replaces the pod atomically (same as a rolling update), then waits 2 minutes
for metrics to stabilize, then runs the 2-gate AnalysisTemplate. If either gate
fails, Argo Rollouts reverts to the previous ReplicaSet automatically.

The ArgoCD Application (`apps/minicloud-plane.yaml`) was updated with:

```yaml
ignoreDifferences:
  - group: argoproj.io
    kind: Rollout
    jsonPointers:
      - /spec/replicas
      - /spec/template/metadata/annotations
syncPolicy:
  syncOptions:
    - RespectIgnoreDifferences=true
```

Without `ignoreDifferences`, ArgoCD detects that VPA modified `spec.replicas`
and continuously re-syncs — creating a drift loop between VPA and gitops.

:::caution Rollout CRD + SSA incompatibility
Argo Rollouts CRDs do not support Server-Side Apply. Do NOT add
`ServerSideApply=true` to the minicloud-plane app syncOptions — ArgoCD records
`op:Update` instead of `op:Apply` and `ignoreDifferences` stops working.
See Phase 73 notes for the full explanation.
:::

---

## Gap R4 — No regression PrometheusRules

`manifests/monitoring/25-regression-alerts.yaml` adds five regression alerts.
All use `offset 1h` with minimum traffic guards.

### Latency

```promql
# Fire when p95 is > 2× what it was 1h ago AND baseline was > 50ms
(
  job:http_request_duration_p95:rate5m
  / (job:http_request_duration_p95:rate5m offset 1h)
) > 2
AND
(job:http_request_duration_p95:rate5m offset 1h) > 0.05
```

| Scenario | ratio | fires? |
|----------|-------|--------|
| 150ms → 450ms | 3.0 | ✅ yes |
| 150ms → 280ms | 1.87 | no (expected variance) |
| 0ms → 500ms (idle before) | ∞ | no (guard: baseline > 50ms) |

### Error rate

```promql
# Fire when absolute increase > 5 percentage points AND service has traffic
(
  job:http_requests_error_fraction:rate5m
  - (job:http_requests_error_fraction:rate5m offset 1h)
) > 0.05
AND (job:http_requests_total:rate5m) > 0.05
```

Uses absolute delta, not ratio. Ratio is misleading here — going from 0.1% to
0.2% errors is a 2× ratio but completely normal variance. A 5pp increase
(0.1% → 5.1%) always indicates a real problem.

### Throughput

```promql
# Fire when RPS drops to < 30% of baseline (new pods are dropping traffic)
(
  job:http_requests_total:rate5m
  / (job:http_requests_total:rate5m offset 1h)
) < 0.30
AND (job:http_requests_total:rate5m offset 1h) > 0.05
```

### CPU and Memory

```promql
# CPU > 3× baseline (possible infinite loop, tight CPU-bound operation)
avg by (namespace) (job:container_cpu_usage:rate5m{namespace=~"platform-demo.*|minicloud-plane.*"})
/ avg by (namespace) (job:container_cpu_usage:rate5m{namespace=~"platform-demo.*|minicloud-plane.*"} offset 1h)
> 3

# Memory > 2× baseline (possible memory leak in new version)
avg by (namespace) (job:container_memory_working_set:bytes{namespace=~"platform-demo.*|minicloud-plane.*"})
/ avg by (namespace) (job:container_memory_working_set:bytes{namespace=~"platform-demo.*|minicloud-plane.*"} offset 1h)
> 2
```

All five alerts carry `regression: "true"` label, which the regression dashboard
uses to populate the "Active Regression Alerts" table panel.

---

## Gap R5 — No before/after comparison dashboard

`manifests/monitoring/26-regression-dashboard.yaml` — Grafana ConfigMap,
UID `minicloud-regression`, title "Deployment Regression Detection".

### Panel layout

| Panel | Type | Query |
|-------|------|-------|
| p95 Latency — Current vs Baseline | timeseries | current + `offset 1h` as two series |
| p95 Latency Regression Ratio | stat | current / baseline, red at > 2× |
| Error Rate — Current vs Baseline | timeseries | current + `offset 1h` |
| Error Rate Δ | stat | current − baseline, red at > 5pp |
| Throughput — Current vs Baseline | timeseries | current + `offset 1h` |
| Throughput Ratio | stat | current / baseline, red at < 0.3 |
| CPU — Current vs Baseline | timeseries | current + `offset 1h` per pod |
| Memory — Current vs Baseline | timeseries | current + `offset 1h` per pod |
| Active Regression Alerts | table | `ALERTS{regression="true"}` instant query |

Each timeseries panel shows the baseline as a **dashed orange line** so you
can immediately see the delta without needing to remember yesterday's numbers.

### Deployment event annotations

The dashboard configures a Prometheus annotation source:

```json
"expr": "changes(kube_deployment_metadata_generation{namespace=\"$namespace\"}[2m]) > 0"
```

`kube_deployment_metadata_generation` increments on every `kubectl apply`.
`changes()` returns 1 at the moment it increments. Grafana draws a vertical
blue line at each deployment event — correlating metric spikes with specific
deploys without any CI integration.

### Template variables

`$service` drives all panel queries via `label_values(job:http_requests_total:rate5m, service)`.
Switch between `platform-demo` and `minicloud-plane` to compare their individual
regression profiles side by side.

---

## Gap R6 — CI declares success before metrics stabilize

This gap is partially addressed by the Rollout analysis window (gaps R2/R3) —
ArgoCD will not mark the app as `Healthy` until the AnalysisRun completes.

For a full CI loop, add a post-deploy verification step after the gitops bump:

```yaml
# In .github/workflows/deploy.yaml — after bump-gitops job
- name: Wait for Rollout to stabilize
  run: |
    # Give ArgoCD time to pick up the gitops change
    sleep 60
    kubectl --context minicloud rollout status rollout/platform-demo \
      -n platform-demo-dev \
      --timeout=300s

- name: Verify regression metrics
  run: |
    kubectl port-forward svc/kps-prometheus -n monitoring 9090:9090 &
    sleep 5
    P95=$(curl -sf 'http://localhost:9090/api/v1/query' \
      --data-urlencode 'query=job:http_request_duration_p95:rate5m{service="platform-demo"}' \
      | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['data']['result'][0]['value'][1])")
    echo "Post-deploy p95: ${P95}s"
    python3 -c "
    p95 = float('$P95')
    if p95 > 0.5:
        raise SystemExit(f'p95 latency regression: {p95:.3f}s > 500ms threshold')
    "
```

This is documented as a future improvement. The Rollout analysis window
provides automated regression detection within the cluster; the CI step would
add an additional external gate from the GitHub Actions perspective.

---

## Files changed (gitops PR #271)

| File | What |
|------|------|
| `manifests/monitoring/24-regression-recording-rules.yaml` | New — 6 recording rules |
| `manifests/monitoring/25-regression-alerts.yaml` | New — 5 regression PrometheusRules |
| `manifests/monitoring/26-regression-dashboard.yaml` | New — Grafana ConfigMap UID minicloud-regression |
| `services/platform-demo/base/analysis-template.yaml` | Replaced — 3-gate AnalysisTemplate (success rate + p95 + traffic) |
| `services/platform-demo/base/deployment.yaml` | Updated — templateName reference to http-regression-gate |
| `services/minicloud-plane/base/deployment.yaml` | Converted — Deployment → Rollout with 2m analysis window |
| `services/minicloud-plane/base/analysis-template.yaml` | New — 2-gate AnalysisTemplate for minicloud-plane |
| `services/minicloud-plane/base/kustomization.yaml` | Added analysis-template.yaml |
| `apps/minicloud-plane.yaml` | Added ignoreDifferences + RespectIgnoreDifferences=true |

---

## Verification

```bash
# 1. Recording rules materialised
kubectl port-forward svc/kps-prometheus -n monitoring 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=job:http_request_duration_p95:rate5m' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print(len(r['data']['result']), 'series')"

# 2. Regression alerts loaded
curl -s 'http://localhost:9090/api/v1/rules' \
  | python3 -c "
import json, sys
rules = json.load(sys.stdin)['data']['groups']
for g in rules:
    for r in g['rules']:
        if r.get('labels', {}).get('regression') == 'true':
            print(r['name'], r['health'])
"

# 3. minicloud-plane Rollout running
kubectl --context minicloud get rollout minicloud-plane -n minicloud-plane-dev

# 4. platform-demo next AnalysisRun shows 3 metrics
# Trigger a deploy and then:
kubectl --context minicloud get analysisrun -n platform-demo-dev --watch

# 5. Regression dashboard visible in Grafana
/usr/bin/curl --cacert ~/minicloud-ca.crt -sf \
  https://grafana.10.0.0.200.nip.io/api/dashboards/uid/minicloud-regression \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['dashboard']['title'])"
```
