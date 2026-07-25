---
id: cost-optimization-gaps
title: Cost Optimization — Waste & Right-Sizing
sidebar_label: "💰 Cost Optimization"
---

# Cost Optimization — Waste & Right-Sizing

A cluster that is fully observable but ignores waste is still costing more than it should. This page documents the cost visibility gaps that were closed, the signals that make over-provisioning visible, and the automation that cuts idle spend.

---

## Gap Inventory

| # | Gap | Signal | Fix |
|---|-----|--------|-----|
| 1 | No memory waste metric | Unknown how much RAM is reserved vs used | Recording rule: `namespace:memory_waste_bytes:1h` |
| 2 | No CPU waste metric | Unknown how many cores are committed but idle | Recording rule: `namespace:cpu_waste_cores:5m` |
| 3 | No over-provisioning ratio | Can't rank namespaces by waste density | Recording rules: `namespace:memory_overprovisioning_ratio:1h`, `namespace:cpu_overprovisioning_ratio:5m` |
| 4 | No cost attribution | No idea which namespace costs the most | Recording rule: `namespace:estimated_monthly_cost_eur:gauge` |
| 5 | Idle services running 24/7 | platform-demo and minicloud-plane kept alive outside business hours | KEDA cron ScaledObjects (Mon-Fri 08:00-19:00 Paris) |
| 6 | KEDA targeting wrong kind | Scale-to-zero silently broken after Rollout conversion | Fix `scaleTargetRef` to `argoproj.io/v1alpha1 Rollout` |
| 7 | Containers without memory limits | Unbounded allocation can OOMKill node neighbours | `ContainerWithoutMemoryLimit` alert via `unless` vector matching |

---

## Gap 1 & 2 — Waste Recording Rules

**Problem:** Kubernetes resource requests act as scheduling reservations, not actual consumption caps. A pod can request 512 MiB and use 64 MiB for months. Without a metric that explicitly computes the difference, waste is invisible.

**Fix — `manifests/monitoring/30-cost-recording-rules.yaml`:**

```yaml
- record: namespace:memory_waste_bytes:1h
  expr: |
    sum by(namespace)(
      kube_pod_container_resource_requests{resource="memory", container!=""}
    )
    -
    sum by(namespace)(
      avg_over_time(container_memory_working_set_bytes{container!="", container!="POD"}[1h])
    )

- record: namespace:cpu_waste_cores:5m
  expr: |
    sum by(namespace)(
      kube_pod_container_resource_requests{resource="cpu", container!=""}
    )
    -
    sum by(namespace)(job:container_cpu_usage:rate5m)
```

`avg_over_time([1h])` smooths out short bursts — a 10-second memory spike from a GC pass does not cause fake "waste" to disappear and reappear.

---

## Gap 3 — Over-Provisioning Ratio

**Problem:** Absolute waste in bytes is misleading. A 2 GiB waste in a machine-learning namespace running 4 GiB models is fine. The same waste in a tiny homer namespace (nginx, ~1 KB of HTML) means the request is set to 25× actual need.

**Fix:**

```yaml
- record: namespace:memory_overprovisioning_ratio:1h
  expr: |
    sum by(namespace)(
      kube_pod_container_resource_requests{resource="memory", container!=""}
    )
    /
    clamp_min(
      sum by(namespace)(
        avg_over_time(container_memory_working_set_bytes{container!="", container!="POD"}[1h])
      ),
      1048576
    )
```

`clamp_min(..., 1Mi)` prevents division by zero when a pod is at rest and working set rounds to zero. Ratio of 1.0 = perfectly right-sized. Ratio of 8+ = request drastically oversized (homer nginx, most idle sidecars).

---

## Gap 4 — Electricity Cost Attribution

**Problem:** The cluster is 5 ThinkPads + 1 Mac. Real cloud cost is ~0, but electricity is not free. Having a per-namespace cost number — even a heuristic one — surfaces which namespace is the biggest drain and makes the conversation about right-sizing concrete.

**Model:**

```
150 W (average cluster draw) × 24h × 30d × 0.001 kW/W × 0.25 €/kWh ≈ €27/month
```

Per-namespace attribution by CPU request fraction:

```yaml
- record: namespace:estimated_monthly_cost_eur:gauge
  expr: |
    (
      sum by(namespace)(
        kube_pod_container_resource_requests{resource="cpu", container!=""}
      )
      /
      scalar(sum(kube_node_status_allocatable{resource="cpu"}))
    ) * 27
```

This is a proxy — actual draw varies by workload. But it gives a directionally correct leaderboard. A GPU-heavy namespace doing Ollama inference genuinely draws more watts than the number suggests.

---

## Gap 5 — Idle Services Scale-to-Zero

**Problem:** `platform-demo` and `minicloud-plane` are portfolio demo services. They have no real traffic on weekends or outside business hours. Keeping them at 1 replica 24/7 wastes 1/5 of a node's capacity for no reason.

**Fix — KEDA cron ScaledObjects:**

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: platform-demo-cron-scaler
spec:
  scaleTargetRef:
    apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    name: platform-demo
  minReplicaCount: 0
  maxReplicaCount: 1
  cooldownPeriod: 60
  triggers:
    - type: cron
      metadata:
        timezone: Europe/Paris
        start: "0 8 * * 1-5"
        end: "0 19 * * 1-5"
        desiredReplicas: "1"
```

Same pattern applied to `minicloud-plane/overlays/dev/`. Both services are at 0 replicas outside Mon-Fri 08:00-19:00 CET/CEST.

---

## Gap 6 — KEDA ScaledObject Targeting Wrong Kind (the silent bug)

**Problem:** Phase 73 converted `platform-demo` from `apps/v1 Deployment` to `argoproj.io/v1alpha1 Rollout`. The KEDA ScaledObjects in `overlays/dev/` and `overlays/staging/` were not updated. KEDA showed:

```
READY=False  "deployments.apps 'platform-demo' not found"
```

Scale-to-zero appeared configured but was silently doing nothing. The service ran 24/7 even outside business hours.

**Why it's subtle:** KEDA does not crash when the target resource is missing — it just sets `READY=False` and stops acting. There's no Alertmanager alert, no log noise in the workload, and ArgoCD shows the ScaledObject as synced (it is synced — it's just wrong). It only surfaces if you `kubectl get scaledobject -A` and notice the READY column.

**Fix:**

```yaml
scaleTargetRef:
  apiVersion: argoproj.io/v1alpha1   # was apps/v1
  kind: Rollout                       # was Deployment
  name: platform-demo
```

**Rule:** Whenever you convert a Deployment to a Rollout, immediately update every KEDA ScaledObject, HPA, and VPA object that references it. Check with `grep -r "kind: Deployment" services/*/overlays/` after any Rollout conversion.

---

## Gap 7 — Containers Without Memory Limits

**Problem:** A container with no `resources.limits.memory` can consume all RAM on its node, triggering the Linux OOM killer to evict neighbour pods that ARE within their limits. This is a noisy-neighbour risk even on a lightly loaded cluster.

**Detection via vector matching:**

```yaml
expr: |
  kube_pod_container_info{container!="", namespace!~"kube-system|longhorn-system|gatekeeper-system"}
  unless on(namespace, pod, container)
  kube_pod_container_resource_limits{resource="memory", container!=""}
```

`unless on(...)` returns every row from the left side that has no matching row on the right side with the same `(namespace, pod, container)` triple. This finds containers where no `memory` limit entry exists in `kube_pod_container_resource_limits`.

System namespaces (`kube-system`, `longhorn-system`, `gatekeeper-system`) are excluded because many infrastructure components intentionally run without limits and are managed by their own upstream charts.

---

## Alerts

All alerts use `cost: "true"` so they surface in the dashboard's `ALERTS{cost="true"}` table without hardcoding alert names.

```yaml
# Over-provisioned for 7 days — suggests request was never updated after VPA baseline
- alert: HighMemoryOverProvisioning
  expr: namespace:memory_overprovisioning_ratio:1h > 3
  for: 7d
  labels:
    severity: info
    cost: "true"
  annotations:
    summary: "{{ $labels.namespace }} memory request is {{ $value | humanize }}× actual usage"
    description: "Lower requests.memory or enable VPA Auto to right-size automatically."

# Idle Go services with no incoming traffic for a full day
- alert: IdleServiceRunning
  expr: |
    increase(http_requests_total{namespace=~"platform-demo.*|minicloud-plane.*"}[24h]) == 0
  for: 1h
  labels:
    severity: info
    cost: "true"

# Unlimited container that could OOMKill its neighbours
- alert: ContainerWithoutMemoryLimit
  expr: |
    kube_pod_container_info{container!="", namespace!~"kube-system|longhorn-system|gatekeeper-system"}
    unless on(namespace, pod, container)
    kube_pod_container_resource_limits{resource="memory", container!=""}
  for: 10m
  labels:
    severity: warning
    cost: "true"
```

---

## Dashboard — Cost & Efficiency (UID `minicloud-cost`)

File: `manifests/monitoring/32-cost-efficiency-dashboard.yaml`

| Panel | Type | Query |
|-------|------|-------|
| Total memory wasted | Stat (bytes) | `sum(clamp_min(namespace:memory_waste_bytes:1h, 0))` |
| Total CPU wasted | Stat (cores) | `sum(clamp_min(namespace:cpu_waste_cores:5m, 0))` |
| Estimated monthly cost | Stat (€) | `sum(namespace:estimated_monthly_cost_eur:gauge)` |
| Scale-to-zero active | Stat (count) | replicas == 0 on known workloads |
| Memory waste leaderboard | Bar gauge | `sort_desc(clamp_min(namespace:memory_waste_bytes:1h, 0))` |
| Over-provisioning ratio | Bar gauge | `sort_desc(namespace:memory_overprovisioning_ratio:1h > 1)` |
| Cost by namespace | Pie chart (donut) | `namespace:estimated_monthly_cost_eur:gauge` |
| Cost + waste + ratio | Table | merge of A/B/C instant queries |
| Containers without limits | Table | `kube_pod_container_info unless on(...) kube_pod_container_resource_limits` |
| Active cost alerts | Table | `ALERTS{cost="true"}` |

---

## Files Changed

| File | Repo | What |
|------|------|------|
| `manifests/monitoring/30-cost-recording-rules.yaml` | minicloud-gitops | 5 recording rules |
| `manifests/monitoring/31-cost-optimization-alerts.yaml` | minicloud-gitops | 4 alerts (`cost: "true"`) |
| `manifests/monitoring/32-cost-efficiency-dashboard.yaml` | minicloud-gitops | Grafana dashboard UID `minicloud-cost` |
| `services/platform-demo/overlays/dev/scaledobject.yaml` | minicloud-gitops | Fix: Deployment → Rollout |
| `services/platform-demo/overlays/staging/scaledobject.yaml` | minicloud-gitops | Fix: Deployment → Rollout |
| `services/minicloud-plane/overlays/dev/scaledobject.yaml` | minicloud-gitops | New: cron scale-to-zero |
| `services/minicloud-plane/overlays/dev/kustomization.yaml` | minicloud-gitops | Add scaledobject.yaml to resources |

Gitops PR: **#275** (merged 2026-07-25)

---

## Verification

```bash
# Recording rules are loaded
ssh controller "curl -sf 'http://localhost:9090/api/v1/query?query=namespace:memory_overprovisioning_ratio:1h' | python3 -m json.tool | head -20"

# KEDA ScaledObjects are READY
kubectl --context minicloud get scaledobject -A

# Containers without memory limits
ssh controller "curl -sf 'http://localhost:9090/api/v1/query' --data-urlencode 'query=count(kube_pod_container_info{container!=\"\"} unless on(namespace,pod,container) kube_pod_container_resource_limits{resource=\"memory\",container!=\"\"})' | python3 -m json.tool"

# Cost attribution live
ssh controller "curl -sf 'http://localhost:9090/api/v1/query?query=sort_desc(namespace:estimated_monthly_cost_eur:gauge)' | python3 -c 'import sys,json; r=json.load(sys.stdin)[\"data\"][\"result\"]; print(*[(x[\"metric\"][\"namespace\"], round(float(x[\"value\"][1]),3)) for x in r], sep=\"\\n\")'"
```
