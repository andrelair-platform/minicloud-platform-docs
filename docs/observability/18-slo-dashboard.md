---
id: slo-dashboard
title: SLO Dashboard — 7 Service-Level Objectives
sidebar_label: SLO Dashboard ✅
---

# SLO Dashboard — 7 Service-Level Objectives

**Live URL:** [grafana.devandre.sbs/d/minicloud-slo](https://grafana.devandre.sbs/d/minicloud-slo)

A purpose-built Grafana dashboard backed by Prometheus recording rules and PrometheusRule alerts covering all seven platform SLOs. When an SLO is violated, an alert fires through Alertmanager → Stalwart SMTP before users notice.

---

## SLO Definitions

| # | Metric | Target | Measurement window | Source |
|---|--------|--------|-------------------|--------|
| 1 | Availability | ≥ 99.9% | 5-minute rolling | NGINX ingress HTTP non-5xx / total |
| 2 | API latency p95 | < 200 ms | 5-minute rolling | NGINX ingress histogram_quantile(0.95) |
| 3 | Error rate | < 1% | 5-minute rolling | NGINX ingress HTTP 5xx / total |
| 4 | Pod restart rate | < 5 / day | Rolling 24h | kube-state-metrics container restarts |
| 5 | CPU utilization | < 70% avg | 5-minute rolling | container CPU working / limits |
| 6 | Memory utilization | < 80% | 5-minute rolling | container working set / limits |
| 7 | Deployment success | > 99% | Instant | available replicas / desired replicas |

All app-namespace metrics exclude infra namespaces (`kube-system`, `longhorn-system`, `monitoring`, `observability`, `velero`, `system-upgrade`, `reloader`, `vpa-system`, `cert-manager`).

---

## Files Shipped

| File | Kind | Purpose |
|------|------|---------|
| `manifests/monitoring/33-slo-recording-rules.yaml` | PrometheusRule | 11 recording rules — pre-aggregates all SLO signals every 60s |
| `manifests/monitoring/34-slo-alerts.yaml` | PrometheusRule | 9 alert rules across 6 groups |
| `manifests/monitoring/35-slo-dashboard.yaml` | ConfigMap (`grafana_dashboard: "1"`) | Grafana JSON — 20 panels, uid `minicloud-slo` |

---

## Recording Rules

Pre-aggregation at 60-second intervals keeps dashboard panel queries instant (no expensive range scans at query time) and makes alert expressions cheap.

```yaml
# groups[0]: slo.recording, interval: 60s
job:slo_availability:ratio5m
job:slo_http_error_rate:ratio5m
job:slo_latency_p95:seconds5m          # seconds — ×1000 in panels for ms
job:slo_pod_restarts:count24h
job:slo_cpu_utilization:avg5m
job:slo_memory_utilization:ratio5m
job:slo_deployment_availability:ratio
job:slo_availability_burn_rate:1h
job:slo_error_rate_burn_rate:1h
job:slo_availability_7d:ratio
job:slo_error_budget_remaining_7d:pct
```

Every rule that can return an empty vector (KEDA scale-to-zero, no traffic) uses `or vector(N)` to prevent NaN from propagating into alerts and panels:

```promql
# Availability: or vector(1) → 100% when no traffic (no requests = no errors)
(
  sum(rate(nginx_ingress_controller_requests{status!~"5.."}[5m]))
  / sum(rate(nginx_ingress_controller_requests[5m]))
) or vector(1)

# Error rate: or vector(0) → 0% errors when no traffic
(
  sum(rate(nginx_ingress_controller_requests{status=~"5.."}[5m]))
  / sum(rate(nginx_ingress_controller_requests[5m]))
) or vector(0)
```

Division-by-zero on the burn rate rules (when total requests = 0) is guarded with `clamp_min(..., 1e-9)` on the denominator rather than `or vector`, because the burn rate formula already has the budget constant in the denominator — `or vector` would give a misleading result.

---

## Burn Rate

Burn rate is the core early-warning mechanism. It answers: *how fast are we consuming our error budget relative to the sustainable rate?*

```
burn_rate = current_error_rate / error_budget_rate
```

| Burn rate | Meaning | Time until 30-day budget exhausts |
|-----------|---------|----------------------------------|
| 0.0 | No errors | Never |
| 1.0 | On track — consuming at exactly sustainable rate | 30 days |
| 14.4 | **Critical threshold** | ~2 hours |
| 72.0 | Catastrophic | ~25 minutes |

**Availability SLO (99.9% target, budget = 0.1%):**

```promql
job:slo_availability_burn_rate:1h =
  (sum(rate(nginx_ingress_controller_requests{status=~"5.."}[1h]))
   / clamp_min(sum(rate(nginx_ingress_controller_requests[1h])), 1e-9))
  / 0.001
```

**Error rate SLO (target < 1%, budget = 1%):**

```promql
job:slo_error_rate_burn_rate:1h =
  (sum(rate(nginx_ingress_controller_requests{status=~"5.."}[1h]))
   / clamp_min(sum(rate(nginx_ingress_controller_requests[1h])), 1e-9))
  / 0.01
```

---

## Alert Rules

All alerts route through the existing Alertmanager → Stalwart SMTP pipeline (`kanmegnea@devandre.sbs`). Each alert includes a `runbook_url` pointing directly to the SLO dashboard.

### Burn rate alerts (two-tier)

```yaml
# Fast burn — page immediately
- alert: SLOAvailabilityBurnRateCritical
  expr: job:slo_availability_burn_rate:1h > 14.4
  for: 2m
  labels: {severity: critical, slo: availability}

# Slow burn — warn if the month is at risk
- alert: SLOAvailabilityBurnRateElevated
  expr: job:slo_availability_burn_rate:1h > 1
  for: 1h
  labels: {severity: warning, slo: availability}
```

The two-tier design is the standard from the *SRE Workbook* (Google, 2018): the fast alert catches large outages early; the slow alert catches slow degradation that would otherwise accumulate silently across a month.

### Per-SLO alerts

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| `SLOLatencyP95Violated` | p95 > 200ms | 10m | warning |
| `SLOErrorRateViolated` | error rate > 1% | 5m | warning |
| `SLOErrorRateCritical` | error rate > 5% | 2m | critical |
| `SLOPodRestartRateHigh` | restarts > 5/day | 15m | warning |
| `SLOCPUUtilizationHigh` | avg CPU > 70% | 15m | warning |
| `SLOMemoryUtilizationHigh` | memory > 80% | 15m | warning |
| `SLODeploymentAvailabilityLow` | available < 99% | 5m | critical |

---

## Dashboard Layout

The dashboard uses a fixed 24-column Grafana grid, 20 panels, default time range 24h.

### Row 1 — SLO Status (y=2, h=5)

Four stat panels at w=6: **Availability**, **API Latency p95**, **Error Rate**, **Pod Restart Rate**.

Three stat panels at w=8: **CPU Utilization**, **Memory Utilization**, **Deployment Success**.

Each panel:
- Shows the current recording rule value
- `colorMode: background` — the entire tile turns green/yellow/red
- Includes a small area sparkline for trend at a glance
- Configured thresholds:

| Panel | Green | Yellow | Red |
|-------|-------|--------|-----|
| Availability | ≥ 99.9% | ≥ 99.5% | < 99.5% |
| API Latency p95 | < 200ms | < 500ms | ≥ 500ms |
| Error Rate | < 1% | < 5% | ≥ 5% |
| Pod Restarts | < 5 | < 20 | ≥ 20 |
| CPU Utilization | < 70% | < 85% | ≥ 85% |
| Memory Utilization | < 80% | < 90% | ≥ 90% |
| Deployment Success | ≥ 99% | ≥ 95% | < 95% |

### Row 2 — Error Budget & Burn Rate (y=14, h=5)

| Panel | Type | What it shows |
|-------|------|---------------|
| Availability Burn Rate (1h) | stat | Current × multiplier. Green \<1, yellow 1–14.4, red ≥14.4 |
| Error Rate Burn Rate (1h) | stat | Same scale against 1% budget |
| 7-Day Availability | stat | Rolling 7d compliance window — proxy for monthly health |
| Error Budget Remaining | gauge | % of 0.1% availability budget unused. 0% = SLO broken |

### Row 3–5 — Trend Timeseries (y=21–45, h=8 each)

Six timeseries panels in three rows of two. Each panel overlays a `vector(TARGET)` series as a dashed reference line (the SLO target) using `thresholdStyle: line`:

| Panel | Color | Reference line |
|-------|-------|---------------|
| Availability Trend | green | 99.9% |
| Error Rate Trend | red | 1% |
| API Latency p95 | blue | 200ms |
| Pod Restart Rate | orange | 5/day |
| CPU Utilization | purple | 70% |
| Memory Utilization | dark-green | 80% |

The reference line approach (`vector(TARGET)`) is more reliable than Grafana panel-level threshold annotations because it shows up in the legend and responds to time-range changes consistently.

---

## Deployment

ArgoCD auto-syncs the `monitoring` app. The Grafana sidecar uses `METHOD=WATCH` against the Kubernetes API — the dashboard ConfigMap is loaded within seconds of ArgoCD applying it, with no Grafana restart.

```bash
# Verify recording rules are loaded
ssh controller "kubectl -n monitoring exec prometheus-kps-prometheus-0 -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/rules' | python3 -m json.tool | grep 'slo'"

# Verify alert rules
ssh controller "kubectl -n monitoring exec prometheus-kps-prometheus-0 -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/rules?type=alert' | \
  python3 -c \"import json,sys; [print(r['name']) for g in json.load(sys.stdin)['data']['groups'] for r in g['rules'] if 'SLO' in r['name']]\""

# Check dashboard was loaded by Grafana
ssh controller "kubectl logs -n monitoring deploy/kube-prometheus-stack-grafana \
  -c grafana-sc-dashboard --tail=20 | grep -i slo"
```

---

## Limitations & Known Gaps

**Deployment Success metric excludes Rollouts.**
`kube_deployment_status_replicas_available` tracks `Deployment` objects only. Services managed by Argo Rollouts (platform-demo, minicloud-plane) use `ReplicaSet` objects directly — their availability is visible in the Workload Health dashboard (`minicloud-workload-health`) but not in this SLO ratio. A future improvement would add `kube_customresource_replicas_available` from kube-state-metrics custom resource state metrics.

**7-day window used instead of 30-day for error budget.**
A 30-day Prometheus range query (`[30d]`) is expensive on a 5-node homelab cluster. The `job:slo_availability_7d:ratio` and `job:slo_error_budget_remaining_7d:pct` recording rules use the current 5m rate as a proxy rather than a true 30d sliding window. This means the error budget gauge reflects recent activity, not cumulative monthly compliance. For a production environment, Prometheus recording rules would pre-compute sliding 30d windows.

**CPU/Memory SLO uses limits, not node capacity.**
`job:slo_cpu_utilization:avg5m` measures CPU used vs CPU *limit* per container, not vs total node CPU. A container running at 65% of its limit on a node at 95% capacity would show green. Node-level saturation is covered by the Node Exporter Full dashboard and `NodeCPUSaturation` / `NodeMemorySaturation` alerts.
