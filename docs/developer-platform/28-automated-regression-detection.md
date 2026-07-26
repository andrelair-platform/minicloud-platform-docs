---
id: automated-regression-detection
title: Automated Regression Detection
sidebar_label: Automated Regression Detection ✅
---

# Automated Regression Detection

Automated regression detection closes the loop between a deployment and its production impact. Instead of manually checking dashboards after each push, the pipeline generates real traffic during the canary or blue-green analysis window, evaluates Prometheus gates, and automatically rolls back if latency or error rate exceeds defined thresholds.

```
Push to main
    │
    ▼
Build + scan + sign image
    │
    ▼
bump-gitops → ArgoCD syncs → Rollout starts
    │
    ├── canary-load (k6, 5 min, parallel) ─────────────────────────┐
    │                                                               │
    └── rollout-gate (waits for Healthy) ───────────────────────────┤
              │                                                      │
              ▼                                                      ▼
       AnalysisRun checks Prometheus gates           k6 p95 < 500ms
       (success-rate ≥ 95%, p95 ≤ 500ms)            error rate < 1%
              │                                                      │
    ┌─────────┴──────────────────────────────────────────────────────┘
    │
    ├── Both pass → promote-staging (GPG-signed PR)
    │
    └── Gate fails → Rollout phase = Degraded → auto-rollback
                          │
                          └── RolloutAutoRollback alert → email
```

---

## What Was Already in Place

The regression detection infrastructure was built incrementally across earlier phases:

| Component | Source | Purpose |
|-----------|--------|---------|
| `24-regression-recording-rules.yaml` | monitoring ns | Pre-compute p95 latency, error fraction, throughput, CPU, memory at 30s intervals |
| `25-regression-alerts.yaml` | monitoring ns | 5 alerts comparing current vs `offset 1h` baseline |
| `26-regression-dashboard.yaml` | Grafana | Before/after view of p95 latency, error rate, throughput per service |
| `services/*/base/analysis-template.yaml` | gitops | AnalysisTemplates: success-rate ≥ 95% + p95 ≤ 500ms gates |
| platform-demo Rollout | gitops | Canary strategy: setWeight 50 → pause 30s → analysis → setWeight 100 |
| minicloud-plane Rollout | gitops | BlueGreen: prePromotionAnalysis (health) + postPromotionAnalysis (Prometheus) |

### Recording rules

```promql
# p95 latency per service
histogram_quantile(0.95,
  sum by (le, service, namespace)
    (rate(http_request_duration_seconds_bucket[5m]))
)

# Error fraction (used by both regression alerts and AnalysisTemplates)
sum by (service, namespace) (rate(http_requests_total{code=~"5.."}[5m]))
/ sum by (service, namespace) (rate(http_requests_total[5m]))
```

### Regression alerts (offset 1h baseline)

| Alert | Expression | Threshold |
|-------|-----------|-----------|
| `LatencyRegressionDetected` | `p95_now / p95_1h_ago` | > 2× |
| `ErrorRateRegressionDetected` | `error_rate_now − error_rate_1h_ago` | > 5% |
| `ThroughputRegressionDetected` | `rps_now / rps_1h_ago` | \< 30% |
| `CPURegressionDetected` | `cpu_now / cpu_1h_ago` | > 3× |
| `MemoryRegressionDetected` | `mem_now / mem_1h_ago` | > 2× |

All fire on `regression: "true"` label → Alertmanager routes to Stalwart SMTP → `kanmegnea@devandre.sbs`.

---

## Three Gaps Closed (2026-07-26)

### Gap 1 — k6 never covered the AnalysisRun window

**Root cause:** The CI job order was sequential:

```
bump-gitops → smoke-test (waits Healthy) → load-test (k6) → promote-staging
```

The AnalysisRun executes *during* the canary step, before the Rollout reaches Healthy. By the time k6 ran, the analysis was already complete. With no traffic in the analysis window, `or vector(1)` returned 1.0 (100% success rate) and `or vector(0)` returned 0s latency — both gates always passed trivially.

**Fix:** Parallel job execution after `bump-gitops`:

```yaml
# .github/workflows/ci.yml (platform-demo + minicloud-plane)
canary-load:
  needs: bump-gitops         # starts immediately after gitops bump
  # waits 30s for ArgoCD sync, then opens port-forward and runs k6 for 5 min

rollout-gate:
  needs: bump-gitops         # also starts immediately
  # polls Rollout phase (Healthy/Degraded), then HTTP smoke probe

promote-staging:
  needs: [rollout-gate, canary-load]   # BOTH must pass
```

k6 now runs for 5 minutes starting ~30 seconds after `bump-gitops` merges — covering the entire analysis window.

### Gap 2 — Analysis fired before Prometheus had traffic data

**Root cause:** The AnalysisRun started its first metric check at `t=0` of the analysis step. Even with the parallel k6 job, the recording rule (30s evaluation interval) may not have had enough data points yet.

**Fix:** `initialDelay: 60s` on both metrics in both AnalysisTemplates:

```yaml
# services/platform-demo/base/analysis-template.yaml
spec:
  metrics:
    - name: success-rate
      count: 5
      interval: 30s
      initialDelay: 60s      # ← wait 60s before first check
      successCondition: result[0] >= 0.95
      ...
    - name: p95-latency
      count: 5
      interval: 30s
      initialDelay: 60s      # ← same delay
      successCondition: result[0] <= 0.5
      ...
```

**Timeline with both fixes:**

| Time (after push) | Event |
|-------------------|-------|
| t=0 | CI starts |
| t~90 | `bump-gitops` merges |
| t~120 | `canary-load` starts; 30s sleep for ArgoCD sync |
| t~125 | k6 begins generating traffic |
| t~150 | Canary pods up, AnalysisRun created |
| t~210 | First gate check fires (`initialDelay: 60s`) — k6 has ~85s of data |
| t~360 | Analysis complete (5 checks × 30s + 60s delay) |
| t~390 | Rollout Healthy; `rollout-gate` smoke probe passes |
| t~420 | `promote-staging` opens GPG-signed PR to staging |

### Gap 3 — Argo Rollouts metrics not scraped

**Root cause:** The Argo Rollouts controller exposes metrics on port 8090 (`argo_rollout_info`, `argo_rollouts_analysis_runs_phase`, etc.) but no ClusterIP Service or ServiceMonitor existed. Prometheus had no way to scrape it, so there was no way to alert on a Degraded rollout.

**Fix:** `manifests/monitoring/36-argo-rollouts-monitoring.yaml` adds three resources:

```yaml
# ClusterIP Service — exposes controller port 8090
apiVersion: v1
kind: Service
metadata:
  name: argo-rollouts-metrics
  namespace: argo-rollouts
spec:
  selector:
    app.kubernetes.io/name: argo-rollouts
  ports:
    - name: metrics
      port: 8090
---
# ServiceMonitor — Prometheus discovers it via label release: kps
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: argo-rollouts
  namespace: argo-rollouts
  labels:
    release: kps
...
---
# PrometheusRule — fires when a rollback happens
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: rollout-degraded-alert
  namespace: monitoring
spec:
  groups:
    - name: rollout.regression
      rules:
        - alert: RolloutAutoRollback
          expr: argo_rollout_info{phase="Degraded"} == 1
          for: 1m
          labels:
            severity: warning
            regression: "true"
          annotations:
            summary: "Rollout {{ $labels.name }} auto-rolled back ({{ $labels.namespace }})"
            description: |
              Argo Rollouts detected a regression and automatically rolled back
              {{ $labels.name }}. Strategy: {{ $labels.strategy }}.
              Check ArgoCD → Rollout → AnalysisRuns for the failing metric.
```

---

## k6 Canary Load Script

Both services have `k6/smoke.js` with a `CANARY_DURATION` env var that switches between short smoke mode (CI smoke check after Healthy) and sustained canary mode (5 min, covers analysis window):

```js
const CANARY_DURATION = __ENV.CANARY_DURATION;

export const options = CANARY_DURATION
  ? {
      // Sustained load for analysis window coverage
      stages: [
        { duration: '10s',           target: 3 },
        { duration: CANARY_DURATION, target: 3 },  // e.g. 5m
        { duration: '10s',           target: 0 },
      ],
    }
  : {
      // Short smoke run for local / post-Healthy checks
      stages: [
        { duration: '10s', target: 5 },
        { duration: '20s', target: 5 },
        { duration: '5s',  target: 0 },
      ],
    };
```

CI invocation in `canary-load` job:

```bash
# platform-demo — hits / healthz readyz
k6 run -e CANARY_DURATION=5m k6/smoke.js

# minicloud-plane — hits /health /metrics
k6 run -e CANARY_DURATION=5m k6/smoke.js
```

---

## What Happens on Regression

If any metric exceeds its threshold during the AnalysisRun:

1. **Argo Rollouts** sets the AnalysisRun phase to `Failed`
2. **Rollout phase** transitions to `Degraded`
3. **Traffic** reverts to the stable ReplicaSet automatically — zero downtime
4. **`RolloutAutoRollback` alert** fires after 1 minute → Alertmanager → SMTP → `kanmegnea@devandre.sbs`
5. **CI `rollout-gate` job** detects `Degraded`, exits 1 → `promote-staging` is blocked
6. **ArgoCD** shows the Rollout as `Degraded` with a link to the failed AnalysisRun

To investigate:

```bash
# Which metric failed?
kubectl get analysisrun -n platform-demo-dev --sort-by=.metadata.creationTimestamp
kubectl describe analysisrun <name> -n platform-demo-dev

# What did Prometheus return at that time?
ssh controller "kubectl argo rollouts logs platform-demo -n platform-demo-dev"

# Check the regression dashboard
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://grafana.10.0.0.200.nip.io
# UID: minicloud-regression-detection (or via Grafana → Dashboards → Regression Detection)
```

---

## Key Files

| File | Repo | Purpose |
|------|------|---------|
| `manifests/monitoring/24-regression-recording-rules.yaml` | minicloud-gitops | Pre-compute p95, error fraction, throughput, CPU, memory |
| `manifests/monitoring/25-regression-alerts.yaml` | minicloud-gitops | 5 offset-1h regression alerts |
| `manifests/monitoring/26-regression-dashboard.yaml` | minicloud-gitops | Grafana before/after view |
| `manifests/monitoring/36-argo-rollouts-monitoring.yaml` | minicloud-gitops | Service + ServiceMonitor + `RolloutAutoRollback` alert |
| `services/platform-demo/base/analysis-template.yaml` | minicloud-gitops | Canary gates: success-rate + p95 (initialDelay: 60s) |
| `services/minicloud-plane/base/analysis-template.yaml` | minicloud-gitops | BlueGreen postPromotion gates (same) |
| `services/minicloud-plane/base/analysis-template-preview.yaml` | minicloud-gitops | BlueGreen prePromotion: HTTP health check on preview service |
| `.github/workflows/ci.yml` | platform-demo | Parallel `canary-load` + `rollout-gate`; `promote-staging: needs: [rollout-gate, canary-load]` |
| `.github/workflows/ci.yml` | minicloud-plane | Same parallel structure |
| `k6/smoke.js` | platform-demo | k6 script with CANARY_DURATION env var |
| `k6/smoke.js` | minicloud-plane | k6 script for /health + /metrics |

---

## Gotchas

**`or vector(1)` / `or vector(0)` are not bugs — they are intentional fallbacks.**
When KEDA scales a service to 0 replicas (idle dev environment), Prometheus has no traffic data. Division by zero in the success-rate query returns NaN → AnalysisRun error. `or vector(1)` returns 1.0 (100% success) as a safe default. The real regression signal comes from `initialDelay` + `canary-load` ensuring there is actual traffic before checks fire.

**`initialDelay` is relative to AnalysisRun creation, not Rollout start.**
The canary pause step (`pause: {duration: 30s}`) runs *before* the analysis step. So the total wait before the first check is: 30s pause + 60s initialDelay = 90s after the canary pods start. k6 needs to be running before t=90s from canary pod start.

**Port-forward hits both stable and canary pods during `setWeight: 50`.**
The Kubernetes Service load-balances 50/50 between old and new pods during the canary step. k6 traffic goes to both. If the canary pods are crashing, roughly half of k6 requests return 5xx → success-rate drops below 95% → gate fails → rollback. This is exactly the intended behavior.

**Argo Rollouts metrics port 8090 needed a manual Service.**
The controller has `containerPort: 8090` (name: metrics) in its PodSpec but the chart does not create a ClusterIP Service for it — only the dashboard Service (port 3100) is chart-managed. Without an explicit Service, Prometheus ServiceMonitor selector finds zero endpoints. Added `argo-rollouts-metrics` Service manually in `36-argo-rollouts-monitoring.yaml`.

**`promote-staging` must depend on BOTH `rollout-gate` AND `canary-load`.**
If only `rollout-gate` is required, a Rollout that passes with zero k6 traffic (via `or vector(1)`) still triggers staging promotion. Requiring both ensures: Argo gates had real traffic AND k6 itself saw no errors above threshold.
