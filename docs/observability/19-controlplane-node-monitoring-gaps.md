---
id: controlplane-node-monitoring-gaps
title: Control Plane & Node Health Monitoring — 3 Gaps Closed
sidebar_position: 19
---

# Control Plane & Node Health Monitoring — 3 Gaps Closed

Three gaps were identified during a structured review against the
**Observability & Alerting** rubric. All three have been closed
(gitops PR #516, 2026-08-02).

| # | Gap | Severity | Files changed | Status |
|---|-----|----------|---------------|--------|
| 1 | API server latency never alerted on | **Critical** | `38-controlplane-latency-alerts.yaml` | ✅ |
| 2 | Kine/SQLite write latency invisible | **Critical** | `23-kine-alerts.yaml` (new group) | ✅ |
| 3 | No kernel-level node problem detection | **High** | `apps/platform/node-problem-detector.yaml`, `helm-values/minicloud-1/node-problem-detector-values.yaml` | ✅ |

---

## Gap 1 — API server read / write latency alerts

### Problem

The kube-prometheus-stack `kps-kube-apiserver-histogram.rules` recording
rule group computes API server SLO latency at p50, p90, and p99:

```
cluster_quantile:apiserver_request_sli_duration_seconds:histogram_quantile
  labels: {quantile="0.99", verb="read"|"write"}
```

This recording rule was visible in Grafana dashboards but had no alert
rule consuming it. A sustained API server latency spike (e.g., caused by
SQLite I/O saturation on `set-hog`) would never page anyone.

### Fix

`manifests/monitoring/38-controlplane-latency-alerts.yaml` adds two rules
that consume the existing recording rule:

```yaml
- alert: KubeAPIReadLatencyHigh
  expr: >-
    max(
      cluster_quantile:apiserver_request_sli_duration_seconds:histogram_quantile{
        quantile="0.99",
        verb="read"
      }
    ) > 1
  for: 5m
  labels:
    severity: critical

- alert: KubeAPIWriteLatencyHigh
  expr: >-
    max(
      cluster_quantile:apiserver_request_sli_duration_seconds:histogram_quantile{
        quantile="0.99",
        verb="write"
      }
    ) > 4
  for: 5m
  labels:
    severity: critical
```

### Thresholds

The thresholds follow the Kubernetes API server SLO definitions:

| Verb | p99 budget | Alert threshold | Rationale |
|------|-----------|-----------------|-----------|
| read | 1s | >1s for 5 min | Kubernetes SLI target for LIST/GET/WATCH |
| write | 4s | >4s for 5 min | Kubernetes SLI target for POST/PUT/PATCH/DELETE |

The `max()` aggregation over all API server instances (one on `set-hog`)
avoids false suppression if the recording rule has multiple labelsets.

### Correlation with Gap 2

If `KubeAPIWriteLatencyHigh` fires simultaneously with
`KineSQLWriteLatencyHigh`, the root cause is SQLite I/O — the API server
is slow because its backing store is slow. Start at `set-hog` disk I/O.

### Recovery

```bash
# Check API server metrics directly
ssh controller "kubectl --context minicloud get --raw /metrics/slis | head -20"

# Check set-hog disk I/O
ssh set-hog "iostat -x 2 5"
ssh set-hog "df -h /var/lib/rancher/k3s/"

# Check k3s logs for slow SQL warnings
ssh set-hog "sudo journalctl -u k3s -n 100 --no-pager | grep -i 'slow\|timeout\|latency'"
```

---

## Gap 2 — Kine/SQLite write latency alert

### Problem

`23-kine-alerts.yaml` already had `KineSQLError` (Gap 9 in the previous
alerting pass), which fires on unexpected error codes. But a healthy SQLite
database can still have high commit latency — slowing down API writes
without ever generating an `error_code`. This was completely invisible.

### Metric

```
kine_sql_time_seconds_bucket{name=<operation>, error_code=<code>}
```

Write operations (commit path for kine object mutations):

| `name` | Meaning |
|--------|---------|
| `InsertLastInsertID` | INSERT for new objects (create, apply) |
| `UpdateCompact` | UPDATE for compaction (MVCC version pruning) |
| `PostCompactSQL` | WAL checkpoint after compaction |

The `error_code=""` filter selects only successful operations — high
latency on successful writes is the early warning before errors start.

### Fix

New `kine.latency` rule group in `23-kine-alerts.yaml`:

```yaml
- alert: KineSQLWriteLatencyHigh
  expr: >-
    histogram_quantile(
      0.99,
      sum by (name, le) (
        rate(
          kine_sql_time_seconds_bucket{
            error_code="",
            name=~"InsertLastInsertID|UpdateCompact|PostCompactSQL"
          }[5m]
        )
      )
    ) > 0.5
  for: 5m
  labels:
    severity: critical
```

The 500ms threshold is conservative: SQLite on NVMe completes single-row
commits in under 5ms under normal conditions. 500ms indicates disk
contention or Longhorn iSCSI volume sync traffic saturating the same NVMe
that SQLite uses on `set-hog`.

### Recovery

```bash
# Check SQLite write latency live
ssh controller "kubectl --context minicloud port-forward svc/kps-prometheus -n monitoring 9090:9090 &"
curl -sg 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum+by(name,le)(rate(kine_sql_time_seconds_bucket{error_code="",name=~"InsertLastInsertID|UpdateCompact|PostCompactSQL"}[5m])))' \
  | python3 -m json.tool

# Check disk I/O on set-hog
ssh set-hog "iostat -x 2 5"

# Force WAL checkpoint manually (reduces WAL file size)
ssh set-hog "sudo sqlite3 /var/lib/rancher/k3s/server/db/state.db '.timeout 5000' '.stat' 'PRAGMA wal_checkpoint(TRUNCATE);'"

# Check Longhorn replica sync traffic on set-hog
ssh set-hog "nload -u M eth0"
```

---

## Gap 3 — Node-problem-detector DaemonSet

### Problem

`kured` runs on all 5 nodes and handles automated OS-level reboots when
`/var/run/reboot-required` is set. But kured is reactive — it reboots
after a kernel asks for it. It does not detect:

- Kernel deadlocks (uninterruptible processes, `D` state for >30s)
- OOM kill events in the kernel log
- containerd / docker daemon failures
- Disk I/O errors reported by the kernel (not by the application)
- Hung task warnings (`INFO: task <x> blocked for more than 120s`)

These conditions can make a node functionally broken (pods timeout,
kubelet can't communicate, containers can't start) without the node
reporting `NotReady` or generating a `/var/run/reboot-required` file.

The CI/CD demo (`platform-demo`, `minicloud-plane`) relies on Argo Rollouts
canary progression — a hung node during a canary can stall the rollout
indefinitely with no signal beyond the pod timing out.

### Architecture

node-problem-detector (NPD) is a DaemonSet that:
1. Reads kernel logs (`/dev/kmsg`, `/var/log/kern.log`) and system logs
2. Matches them against configurable pattern rules
3. Sets `NodeCondition` objects on the node (e.g., `KernelDeadlock=True`)
4. Exposes `/metrics` on port 20257 — picked up by `kube-prometheus-stack`
   via a ServiceMonitor

```
kernel log → NPD pattern match → NodeCondition update
                                        │
                                        └─ kubectl get node -o json | jq '.status.conditions'
                                        └─ Prometheus scrapes /metrics:20257
```

### Implementation

`apps/platform/node-problem-detector.yaml` — ArgoCD Application, multi-source
pattern (mirrors kured), chart `node-problem-detector` v2.3.14 from
`https://charts.deliveryhero.io/`.

`helm-values/minicloud-1/node-problem-detector-values.yaml` — key settings:

```yaml
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule

metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    additionalLabels:
      release: kps   # picked up by kps PrometheusOperator selector

hostPID: true   # required for kernel-level detection

settings:
  log_monitors:
    - /config/kernel-monitor.json   # kernel OOM, BTRFS errors, hung tasks
    - /config/docker-monitor.json   # containerd/docker failures
```

The `release: kps` label on the ServiceMonitor is required for the
kube-prometheus-stack PrometheusOperator to pick it up (it selects
ServiceMonitors with `release=kps`).

AppProject changes:
- `sourceRepos`: added `https://charts.deliveryhero.io/`
- `destinations`: added `namespace: node-problem-detector`

### Verification

```bash
# DaemonSet running on all 5 nodes
kubectl --context minicloud get ds -n node-problem-detector
# Expected: DESIRED=5, READY=5

# ServiceMonitor created
kubectl --context minicloud get servicemonitor -n node-problem-detector

# NodeConditions exposed (no problems expected)
kubectl --context minicloud get nodes -o json \
  | python3 -c "
import json, sys
for n in json.load(sys.stdin)['items']:
    name = n['metadata']['name']
    conds = {c['type']: c['status'] for c in n['status']['conditions']}
    problems = {k: v for k, v in conds.items() if k not in ('Ready', 'MemoryPressure', 'DiskPressure', 'PIDPressure', 'NetworkUnavailable') and v == 'True'}
    if problems:
        print(f'{name}: {problems}')
    else:
        print(f'{name}: clean')
"

# Prometheus metrics reachable
kubectl --context minicloud exec -n node-problem-detector ds/node-problem-detector \
  -- curl -s http://localhost:20257/metrics | grep problem_gauge
```

### What NPD detects (built-in monitors)

| Monitor | Conditions set | Source |
|---------|---------------|--------|
| `kernel-monitor.json` | `KernelDeadlock`, `ReadonlyFilesystem` | `/dev/kmsg` |
| `docker-monitor.json` | `ContainerRuntimeIssue` | `/var/log/docker.log` or journald |

Additional `NodeCondition` types visible in `kubectl describe node`:
- `KernelDeadlock` — `True` means uninterruptible process or spinlock held >30s
- `ReadonlyFilesystem` — `True` means kernel remounted rootfs read-only (disk error)
- `ContainerRuntimeIssue` — `True` means containerd/docker not responding

These conditions are visible in Grafana's node panel and in Backstage's
Kubernetes plugin, and can be used as canary analysis gates in Argo Rollouts
`AnalysisTemplate` metrics.

---

## Files changed (gitops PR #516)

| File | What changed |
|------|--------------|
| `manifests/monitoring/38-controlplane-latency-alerts.yaml` | New — `KubeAPIReadLatencyHigh` + `KubeAPIWriteLatencyHigh` |
| `manifests/monitoring/23-kine-alerts.yaml` | Added `kine.latency` rule group with `KineSQLWriteLatencyHigh` |
| `apps/platform/node-problem-detector.yaml` | New — ArgoCD Application (deliveryhero chart v2.3.14) |
| `helm-values/minicloud-1/node-problem-detector-values.yaml` | New — tolerations, ServiceMonitor, hostPID |
| `manifests/argocd-project/00-project.yaml` | Added deliveryhero repo + node-problem-detector namespace |

---

## Updated alert routing tree

After this change, the full set of control plane and node health alerts
routing to `webhook-critical` (email + Slack):

```
Control plane:
  KubeAPIDown              — API server absent for 15 min (Gap 6, prior pass)
  KubeAPIReadLatencyHigh   — p99 read > 1s for 5 min    ← NEW
  KubeAPIWriteLatencyHigh  — p99 write > 4s for 5 min   ← NEW
  KineSQLError             — unexpected SQLite error code (Gap 9, prior pass)
  KineSQLWriteLatencyHigh  — p99 write > 500ms for 5 min ← NEW
  KubeControllerManagerDown
  KubeSchedulerDown

Node health:
  NodeCPUCritical          — >95% CPU for 5 min
  NodeMemoryCritical       — >95% memory for 5 min
  LonghornVolumeFaulted    — volume has no healthy replicas
  LonghornNodeNotReady     — Longhorn reports node not ready
```
