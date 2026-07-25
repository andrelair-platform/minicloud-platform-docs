---
id: capacity-planning-gaps
title: Capacity Planning — Gap Analysis & Fixes
sidebar_position: 16
---

# Capacity Planning — Gap Analysis & Fixes

Capacity planning answers the question every operations team ignores until it
is too late: **when will we run out?** Not "are we over threshold today" — that
is monitoring. Capacity planning is about reading the trend and acting before
the trend wins.

The cluster had good reactive alerts (NodeCPUWarning, NodeMemoryCritical,
LonghornNodeDiskPressure) but zero forward-looking tooling. `swift-mac` was at
71% CPU and 71% memory on the day of this audit with no signal for when it
would saturate.

---

## Cluster state at audit (2026-07-25)

| Node | CPU (actual) | CPU % | Memory (actual) | Memory % |
|------|-------------|-------|----------------|---------|
| swift-mac | 2840m / 4000m | **71%** | 5645 Mi / 7844 Mi | **71%** |
| star-kitten | 2048m / 8000m | 25% | 8851 Mi / 15648 Mi | 56% |
| set-hog (CP) | 1166m / 8000m | 14% | 10612 Mi / 15656 Mi | 67% |
| fast-skunk | 1003m / 8000m | 12% | 7502 Mi / 15648 Mi | 47% |
| fast-heron | 725m / 8000m | 9% | 8404 Mi / 15648 Mi | 53% |

`swift-mac` (MacBook Pro 2012, 4 CPU / 8 GB) is the capacity ceiling for the
cluster. It runs Longhorn storage (most write-heavy workloads prefer local
replicas) and is the natural landing zone for stateful pods. Without forecasting,
there is no warning before it becomes unschedulable.

---

## Gap inventory

| # | Gap | Root cause | Impact |
|---|-----|-----------|--------|
| C1 | No memory/CPU exhaustion forecast | No `predict_linear()` rules | Silent saturation of swift-mac |
| C2 | No controller disk forecast | Only reactive disk alert at 85/90% | MinIO crashed in July with no advance warning |
| C3 | No scheduler pressure tracking | Actual usage ≠ committed requests | Node can be "underloaded" but unschedulable |
| C4 | No Longhorn PVC fill forecast | Only reactive disk pressure alert | ClickHouse (40 GB quota) grows ~100 MB/day |
| C5 | No quota saturation alerts | 14 ResourceQuotas, zero alerts | New pods silently blocked when quota hits 100% |
| C6 | VPA covers 5 of 35+ Deployments | No right-sizing feedback for most services | Wasted requests or OOMKill risk |
| C7 | No capacity planning dashboard | No cluster-wide resource view | Capacity decisions made by intuition |

---

## Gap C1 — No node memory and CPU exhaustion forecast

### Problem

The existing `NodeMemoryWarning` (>85%) and `NodeCPUWarning` (>80%) fire when
the problem already exists. For `swift-mac` at 71%, you get one warning period
before the critical alert, which may be only hours.

### Fix

`manifests/monitoring/27-capacity-forecasting-rules.yaml` — `predict_linear()`
alerts with a 7-day horizon:

```promql
# NodeMemoryExhaustionForecast
predict_linear(
  node_memory_MemAvailable_bytes[24h],
  7 * 24 * 3600         -- project 7 days forward
) < 0
```

`predict_linear(v[d], t)` fits a linear regression over the last `d` of data
and returns the projected value at `t` seconds in the future. If the projected
available memory is below zero, the alert fires — giving 7 days of lead time
to act.

The `[24h]` lookback window averages out daily cycles (e.g., nightly Velero
backup causes a memory spike that would distort a shorter window). The alert
requires `for: 1h` so a single anomalous hour doesn't trigger a week-long
response.

```promql
# NodeCPUExhaustionForecast
predict_linear(
  (sum without(mode) (avg without(cpu) (rate(node_cpu_seconds_total{mode!~"idle|iowait"}[2m]))))[24h:5m],
  7 * 24 * 3600
) * 100 > 90
```

The `[24h:5m]` is a **subquery**: compute the 2-minute CPU rate at 5-minute
intervals over the last 24 hours, then apply `predict_linear` to that series.
Without the subquery, `predict_linear` would see a single instantaneous value
instead of a time series.

:::caution `predict_linear` requires historical data
`predict_linear(metric[24h], ...)` returns no data until Prometheus has 24
hours of samples for that metric. The alert will be absent (not firing, not
pending) on a fresh install until the lookback window fills.
:::

---

## Gap C2 — No controller disk forecast

### Problem

The MinIO service on the controller crashed in July 2026 when the disk hit ~94%
utilization. The `ControllerDiskWarning` alert at 85% existed but fired only
hours before the actual outage. MinIO caches the disk-full state in memory, so
even after disk was freed it required a manual `docker restart minio`.

### Fix

```promql
# ControllerDiskExhaustionForecast
predict_linear(
  node_filesystem_free_bytes{
    instance="10.0.0.1:9100",
    mountpoint="/"
  }[24h],
  7 * 24 * 3600
) < 1073741824    -- < 1 GiB remaining projected in 7 days
```

The controller disk is scraped by the `node-exporter` Docker container running
at `10.0.0.1:9100`. The threshold is 1 GiB (not zero) because MinIO needs
headroom to create temp files during uploads. Running out below 1 GiB is
operationally equivalent to running out completely.

---

## Gap C3 — Scheduler pressure vs actual usage

### Problem

The distinction that most teams miss:

```
Node actual CPU usage:    10%   ← seems fine
Node CPU requests total:  95%   ← new pods CANNOT schedule here
```

Actual usage measures how many CPU cycles are burning right now. Requests are
the **committed reservation** — the scheduler uses requests, not actual usage,
to decide where to place pods. A node can be nearly idle but unable to accept
new pods if all its allocatable CPU is claimed.

On this cluster, `swift-mac` with 71% actual CPU may have a much higher
committed request fraction — especially from stateful pods that over-request
CPU as a safety margin.

### Fix

```promql
# NodeCPUSchedulerPressure
(
  kube_node_status_allocatable{resource="cpu"}
  - on(node) group_left()
  sum by (node) (kube_pod_container_resource_requests{resource="cpu", node!=""})
) < 0.5    -- less than 500m uncommitted
```

This subtracts total pod CPU requests from allocatable CPU. The result is the
**scheduling headroom**: how much new work can land on this node before the
scheduler rejects new pods with `Insufficient cpu`.

The `on(node) group_left()` is required because `kube_node_status_allocatable`
carries a `node` label while `kube_pod_container_resource_requests` also labels
by `node` — the vector matching must be explicit to avoid a cross-product.

Same pattern for memory with a 512Mi threshold.

---

## Gap C4 — No Longhorn PVC fill forecast

### Problem

The langfuse ClickHouse PVC has a 40 GB Longhorn allocation and grows at roughly
100 MB/day from LLM trace data. No alert would fire until it hit 85% (~34 GB
used), at which point there would be approximately 60 days of runway — but
that 60-day window was invisible.

### Fix

```promql
# LonghornVolumeFillForecast
predict_linear(
  longhorn_volume_usage_bytes[24h],
  7 * 24 * 3600
) > longhorn_volume_capacity_bytes
```

The right side (`longhorn_volume_capacity_bytes`) varies per volume — this
comparison is element-wise (same volume/pvc/namespace labels on both sides),
so each volume's forecast is compared to its own capacity. The alert fires
for any volume individually approaching full within 7 days.

---

## Gap C5 — No quota saturation alerts

### Problem

All 14 namespaces with ResourceQuotas had no alerting when they approached their
hard limits. When a namespace hits 100% of `requests.memory`, every new pod
creation in that namespace is blocked with:

```
Error creating: pods "X" is forbidden:
exceeded quota: requests.memory
```

Deployments, DaemonSets, Argo Rollouts canary pods, and ArgoCD Jobs all fail
silently from the end-user perspective — ArgoCD shows `OutOfSync`, the CI job
times out, but nothing in the alert feed explains why.

### Fix

`manifests/monitoring/28-quota-saturation-alerts.yaml` — four rules, all using
the `kube_resourcequota` metric from kube-state-metrics:

```promql
# Memory requests > 80% of hard limit
kube_resourcequota{resource="requests.memory", type="used"}
/
kube_resourcequota{resource="requests.memory", type="hard"}
> 0.80
```

The ratio query works because `kube_resourcequota` exposes both `type="used"`
and `type="hard"` as separate time series with identical `namespace` and
`resourcequota` label sets. Element-wise division gives the utilization fraction
for every namespace that has a quota — no per-namespace hardcoding needed.

| Alert | Threshold | Severity |
|-------|-----------|----------|
| `NamespaceMemoryRequestsQuotaNearing` | > 80% for 10m | warning |
| `NamespaceCPURequestsQuotaNearing` | > 80% for 10m | warning |
| `NamespacePodCountQuotaNearing` | > 85% for 10m | warning |
| `NamespaceQuotaExhausted` | ≥ 100% for 1m | **critical** |

The pod count threshold is 85% (not 80%) because Argo Rollouts and ArgoCD Jobs
can create burst of short-lived pods that briefly push the count up during a
deploy but settle back down. The 10-minute `for` window filters those transient
bursts.

---

## Gap C6 — VPA covers only 5 of 35+ Deployments

### Problem

VPA recommendations are the cheapest form of right-sizing evidence —
passive, continuous, and based on actual usage. Without them, requests and
limits are set once at deploy time and never revisited. Services gradually drift:
some waste allocations (over-requested), some accumulate OOMKill risk
(under-limited).

At audit: 5 VPA objects existed (litellm, backstage, langfuse-web,
langfuse-clickhouse, prometheus). All other services ran with no right-sizing
feedback.

### Fix

Added 5 Off-mode VPA objects to `manifests/vpa/00-vpa-objects.yaml`:

| Workload | Namespace | Kind | Note |
|----------|-----------|------|------|
| open-webui | ai | StatefulSet | Memory grows with concurrent sessions |
| matrix-synapse | chat | StatefulSet | RWO PVC — Off only (eviction unsafe) |
| vault | vault | StatefulSet | AWS KMS unseal during eviction is slow |
| minicloud-plane | minicloud-plane-dev | Rollout | Off to collect baseline first |
| platform-demo | platform-demo-dev | Rollout | Off to collect baseline first |

VPA can target Argo Rollouts (`kind: Rollout`, group `argoproj.io/v1alpha1`)
natively — the VPA admission webhook patches the pod template regardless of the
controller kind.

**Off vs Auto decision matrix:**

| Condition | Mode |
|-----------|------|
| < 7 days of data | Off |
| StatefulSet with RWO PVC | Off (forced eviction may cause Multi-Attach) |
| External auth dependency at startup (Vault, KMS) | Off |
| Stateless Deployment with 7+ days data | Auto |

**Reading a recommendation:**
```bash
kubectl get vpa platform-demo -n platform-demo-dev -o json \
  | python3 -c "
import json, sys
vpa = json.load(sys.stdin)
for c in vpa['status']['recommendation']['containerRecommendations']:
    print(c['containerName'])
    print('  target:', c['target'])
    print('  upperBound:', c['upperBound'])
    print('  lowerBound:', c['lowerBound'])
"
```

`target` is the recommended setting. `upperBound` is the 95th-percentile
maximum — setting limits to `upperBound` gives a safety margin without over-
provisioning.

---

## Gap C7 — No cluster capacity dashboard

`manifests/monitoring/29-capacity-planning-dashboard.yaml` — Grafana ConfigMap,
UID `minicloud-capacity`, title "Capacity Planning". 7-day default time range.

### Panel layout

| Panel | What it shows |
|-------|--------------|
| Cluster CPU allocatable / requested / actual | Three bargauge bars per node — distinguishes scheduling pressure from load |
| Node CPU scheduler pressure | Gauge: `requested / allocatable` — red at >90% |
| Node memory scheduler pressure | Same as above for memory |
| Node memory 7d trend + forecast | Timeseries with current (solid) + `predict_linear` (dashed); if dashed hits 0 → forecast alert fires |
| Namespace quota saturation — memory | Horizontal bargauge per namespace; yellow >80%, red >95% |
| Namespace quota saturation — CPU | Same for CPU requests |
| Longhorn PVC usage — top 15 | Horizontal bargauge by % full |
| Longhorn PVC growth rate (7d) | Table with `deriv(usage[7d]) * 86400` = bytes/day fill rate + current % |
| VPA recommendations vs limits | Table of `kube_verticalpodautoscaler_status_recommendation_containerrecommendations_target` for Off-mode services |
| Active capacity alerts | `ALERTS{capacity="true"}` — any firing forecast or quota alert |

The **PVC growth rate table** uses:
```promql
deriv(longhorn_volume_usage_bytes[7d]) * 86400
```

`deriv()` returns the per-second rate of change. Multiplied by 86400 it gives
bytes added per day. A negative value means the volume is shrinking (data being
deleted). The table is sorted descending by growth rate so the fastest-filling
volumes appear first.

---

## Sizing runway at audit

Based on `predict_linear` with current 7-day trends (approximate — trend varies
with workload):

| Resource | Node/Volume | Estimated runway |
|----------|-------------|-----------------|
| Memory | swift-mac | Stable (low growth rate) |
| CPU | swift-mac | Stable (Ollama inference spikes but avg low) |
| Disk | controller / | ~60+ days at current MinIO + k3s snapshot rate |
| Longhorn | langfuse-clickhouse | ~120 days at ~100 MB/day fill rate |

No immediate exhaustion risk, but `swift-mac` has no buffer — a single new
memory-hungry workload (e.g., a second large Ollama model) would push it past
the reactive alert threshold within hours, not days.

---

## Files changed (gitops PR #273)

| File | What |
|------|------|
| `manifests/monitoring/27-capacity-forecasting-rules.yaml` | New — 6 PrometheusRules: memory/CPU/disk forecast + scheduler pressure (CPU + memory) + Longhorn PVC forecast |
| `manifests/monitoring/28-quota-saturation-alerts.yaml` | New — 4 quota alerts covering all 14 namespaces |
| `manifests/monitoring/29-capacity-planning-dashboard.yaml` | New — Grafana ConfigMap UID `minicloud-capacity`, 10 panels |
| `manifests/vpa/00-vpa-objects.yaml` | +5 Off-mode VPA objects; coverage 5 → 10 workloads |

---

## Verification

```bash
# Capacity forecasting rules loaded
kubectl port-forward svc/kps-prometheus -n monitoring 9090:9090 &
curl -s 'http://localhost:9090/api/v1/rules' \
  | python3 -c "
import json, sys
for g in json.load(sys.stdin)['data']['groups']:
    for r in g['rules']:
        if r.get('labels', {}).get('capacity') == 'true':
            print(r['name'], r['health'])
"

# No quota alerts firing (cluster should be healthy)
curl -s 'http://localhost:9090/api/v1/query?query=ALERTS{capacity="true"}' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print(len(r['data']['result']), 'active capacity alerts')"

# Scheduler pressure — check remaining headroom
curl -s 'http://localhost:9090/api/v1/query?query=kube_node_status_allocatable{resource="cpu"}-on(node)group_left()sum+by(node)(kube_pod_container_resource_requests{resource="cpu",node!=""})' \
  | python3 -c "
import json, sys
for r in json.load(sys.stdin)['data']['result']:
    node = r['metric'].get('node', '?')
    remaining = float(r['value'][1])
    print(f'{node}: {remaining:.2f} CPU cores uncommitted')
"

# VPA coverage
kubectl get vpa -A --no-headers | awk '{print $1, $2, $3}'

# Grafana dashboard visible
/usr/bin/curl --cacert ~/minicloud-ca.crt -sf \
  https://grafana.10.0.0.200.nip.io/api/dashboards/uid/minicloud-capacity \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['dashboard']['title'], '—', len(d['dashboard']['panels']), 'panels')"
```
