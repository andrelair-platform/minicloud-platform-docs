---
id: dora-metrics
title: DORA Metrics Dashboard
sidebar_position: 22
---

# DORA Metrics Dashboard

Implemented 2026-08-02 via gitops PR #522.

| Metric | Source | Coverage |
|--------|--------|---------|
| Deployment Frequency | `rollout_events_total{reason="RolloutCompleted"}` | All Rollout-managed services, all envs |
| Change Failure Rate | failure reasons / total events | platform-demo, minicloud-plane, preview envs |
| Lead Time (proxy) | `rollout_reconcile_bucket` p50/p99 | Deploy phase only (CI time not captured) |
| MTTR (proxy) | `ALERTS_FOR_STATE` duration + active alert count | Cluster-wide |

Dashboard UID: `minicloud-dora` — available in Grafana under **Dashboards → observability → DORA Metrics**.

---

## What was enabled

### ArgoCD metrics (new)

Both the ArgoCD `server` and `controller` components now expose Prometheus metrics via ServiceMonitor (label `release: kps`, picked up by kube-prometheus-stack):

```yaml
# helm-values/minicloud-1/argocd-values.yaml (both server: and controller:)
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    additionalLabels:
      release: kps
```

This exposes:
- `argocd_app_info` — per-app sync status, health, project
- `argocd_app_sync_total` — sync operation count by phase (Succeeded/Failed)
- `argocd_app_reconcile_bucket` — reconciliation duration histogram
- `argocd_cluster_info` — connected cluster metadata

### DORA dashboard ConfigMap (new)

`manifests/monitoring/40-dora-dashboard.yaml` — ConfigMap with label `grafana_dashboard: "1"` in the `monitoring` namespace. Grafana sidecar picks it up automatically.

---

## Dashboard panels

### Row 1 — Deployment Frequency

| Panel | Query | Meaning |
|-------|-------|---------|
| Deployments to Prod (window) | `increase(rollout_events_total{reason="RolloutCompleted", exported_namespace=~".*-$env"}[$window])` | Total successful rollout completions |
| Daily Deployment Rate | sum of above / window in days | Average deploys per day |
| Deployment Events Over Time | 1d increase for completed + failure events | Visual history of deploy cadence |

**DORA thresholds:**

| Rate | Classification |
|------|----------------|
| ≥ 1/day | Elite |
| ≥ 1/week | High |
| ≥ 1/month | Medium |
| < 1/month | Low |

### Row 2 — Change Failure Rate

```
CFR = failed rollouts / (completed + failed) × 100
```

Failure reasons counted: `Error`, `Failed`, `ProgressDeadlineExceeded`.

| CFR | Classification |
|-----|----------------|
| < 5% | Elite |
| < 10% | High |
| < 15% | Medium |
| ≥ 15% | Low |

The panel also shows a 7-day rolling CFR trend per namespace, making it easy to spot whether failures are concentrated in one service.

### Row 3 — Lead Time (proxy)

`rollout_reconcile_bucket` measures the time Argo Rollouts spends reconciling a Rollout object from the first sync to `Healthy` phase. This is a proxy for the **deploy phase** of lead time — it does not include:

- Time from commit to CI trigger
- CI build and push duration
- ArgoCD polling interval (typically 3 minutes)

**Why a proxy is sufficient here:** The cluster has no commit-timestamp metric source integrated with Prometheus. A full lead time measurement would require instrumenting the CI pipeline to emit a gauge at deploy start. The rollout duration gives the most actionable segment — it captures image pull time, health check wait, and canary step delays.

| p99 Duration | Classification |
|--------------|----------------|
| < 1 hour | Elite |
| < 1 day | High |
| < 1 week | Medium |
| ≥ 1 week | Low |

### Row 4 — MTTR (proxy)

Two proxies are used because Prometheus does not record historical alert resolution times natively:

**`ALERTS_FOR_STATE`** — a gauge that tracks how long each currently-firing alert has been active. The average of this across all critical/warning alerts approximates MTTR for ongoing incidents.

**Active alert count over time** — the timeseries panel shows how many critical/warning alerts were firing at each point in time. Sustained high counts indicate unresolved multi-hour incidents.

**Limitation:** Once an alert resolves, `ALERTS_FOR_STATE` disappears. The panel shows current incident duration, not historical MTTR. For historical MTTR, use Alertmanager's silences/inhibitions timeline or a dedicated incident tracking tool.

### Row 5 — ArgoCD Sync Health

Supplements deployment frequency with GitOps pipeline health:
- Apps in `Synced` state (should stay near total app count — currently 75)
- Apps `OutOfSync` (expected: 0 outside active deployments)
- Sync operation rate (success vs failure per hour)

---

## Variables

| Variable | Values | Default | Effect |
|----------|--------|---------|--------|
| `$env` | prod, staging, dev | prod | Filters rollout panels by namespace suffix |
| `$window` | 7d, 30d, 90d | 30d | Range for frequency and CFR stat panels |

---

## Current baseline (2026-08-02)

From `rollout_events_total{reason="RolloutCompleted"}` at time of dashboard creation:

| Namespace | Rollout | Completions |
|-----------|---------|-------------|
| platform-demo-prod | platform-demo | 1 |
| platform-demo-staging | platform-demo | 1 |
| platform-demo-dev | platform-demo | 1 |
| minicloud-plane-prod | minicloud-plane | 1 |
| minicloud-plane-staging | minicloud-plane | 1 |

These counters accumulate — the dashboard will become more meaningful over weeks as more deployments are executed. The 30-day window will show realistic frequency data starting from early September 2026.

---

## Verification

```bash
# ArgoCD server metrics exposed
kubectl --context minicloud get servicemonitor -n argocd | grep argocd

# Dashboard ConfigMap loaded
kubectl --context minicloud get configmap grafana-dashboard-dora -n monitoring

# Rollout completions count
kubectl --context minicloud exec -n monitoring deploy/kps-prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=rollout_events_total%7Breason%3D%22RolloutCompleted%22%7D' \
  | python3 -c "import sys,json; [print(r['metric']['exported_namespace'], r['value'][1]) for r in json.load(sys.stdin)['data']['result']]"

# ArgoCD app sync metrics (after next helm upgrade)
kubectl --context minicloud exec -n monitoring deploy/kps-prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=argocd_app_info' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['data']['result']), 'apps tracked')"
```

---

## Files changed (gitops PR #522)

| File | Change |
|------|--------|
| `helm-values/minicloud-1/argocd-values.yaml` | Add `metrics.enabled: true` + ServiceMonitor to `server:` and `controller:` sections |
| `manifests/monitoring/40-dora-dashboard.yaml` | New — Grafana dashboard ConfigMap with 5 rows, 20 panels |
