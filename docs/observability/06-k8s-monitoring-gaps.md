---
id: k8s-monitoring-gaps
title: Kubernetes Monitoring — Gap Analysis & Fixes
sidebar_position: 6
---

# Kubernetes Monitoring — Gap Analysis & Fixes

After Phase 21 wired up Alertmanager routing and Phase 8 deployed
kube-prometheus-stack, a targeted gap analysis found 5 holes in the
monitoring coverage. This page documents what was missing, what was
fixed, and one intentional deferral.

---

## Tools — Baseline

| Tool | Status |
|------|--------|
| kube-state-metrics | ✅ Running (`ServiceMonitor kps-kube-state-metrics`) |
| Prometheus | ✅ Running (kube-prometheus-stack) |
| Grafana | ✅ Running (29 dashboards provisioned) |

---

## Data Sources

| Source | ServiceMonitor | Scraping | Note |
|--------|---------------|----------|------|
| kube-apiserver | `kps-apiserver` ✅ | ✅ | — |
| kubelet | `kps-kubelet` ✅ | ✅ | — |
| CoreDNS | `kps-coredns` ✅ | ✅ | — |
| scheduler | ❌ None | ❌ | k3s binds to `127.0.0.1:10259` — see Gap 5 |
| controller-manager | ❌ None | ❌ | k3s binds to `127.0.0.1:10257` — see Gap 5 |
| etcd | ❌ None | ❌ | k3s embedded etcd on `:2381`, TLS client cert required |

---

## Alert Gaps — Before the Fix

kube-prometheus-stack ships many rules out of the box. What it does
**not** ship are these two workload-lifecycle alerts that matter day-to-day:

| Metric | PrometheusRule | Status before fix |
|--------|---------------|-------------------|
| CrashLoopBackOff | `KubePodCrashLooping` (kps) | ✅ already covered |
| Pod not ready | `KubePodNotReady` (kps) | ✅ already covered |
| Deployment replica mismatch | `KubeDeploymentReplicasMismatch` (kps) | ✅ already covered |
| HPA maxed out / mismatch | `KubeHpaMaxedOut`, `KubeHpaReplicasMismatch` (kps) | ✅ already covered |
| PVC filling up / errors | `KubePersistentVolumeFillingUp`, `KubePersistentVolumeErrors` (kps) | ✅ already covered |
| Node NotReady | `NodeFrequentlyNotReady` (infrastructure-alerts) | ✅ already covered |
| Node cordoned | `NodeSchedulingDisabled` (infrastructure-alerts) | ✅ already covered |
| **Pod stuck Pending >5m** | ❌ None | **Gap 1** |
| **OOMKilled** | ❌ None | **Gap 2** |

**Gap 4** was also present: Alertmanager had no receiver — every alert fired
into it and was silently swallowed.

---

## Dashboard Gaps — Before the Fix

| Dashboard | Status before fix |
|-----------|-------------------|
| API server | ✅ `kps-apiserver` |
| Kubelet | ✅ `kps-kubelet` |
| CoreDNS | ✅ `kps-k8s-coredns` |
| Resources (cluster/ns/pod/workload) | ✅ 8 kps dashboards |
| PV usage | ✅ `kps-persistentvolumesusage` |
| Node Exporter Full | ✅ ConfigMap-managed |
| Longhorn | ✅ ConfigMap-managed |
| Controller (MAAS node) | ✅ ConfigMap-managed |
| **Workload Health Overview** | ❌ None | **Gap 3** |
| Scheduler | ❌ Not scrapable (k3s limitation) |
| Controller-manager | ❌ Not scrapable (k3s limitation) |

---

## The 5 Gaps — Effort vs Value

| # | Gap | Effort | Value |
|---|-----|--------|-------|
| 1 | Pod stuck Pending alert | Low (1 PrometheusRule) | High |
| 2 | OOMKilled alert | Low (1 PrometheusRule) | High |
| 3 | Workload Health dashboard | Medium (1 ConfigMap) | High |
| 4 | Alertmanager receiver | Medium | High — alerts were completely silent |
| 5 | Scheduler + controller-manager metrics | High (k3s node config change) | Low at this scale |

---

## What Was Fixed (Gaps 1–4)

### Gap 1 + Gap 2 — PrometheusRules

Added to `minicloud-gitops/manifests/monitoring/04-infrastructure-alerts.yaml`
(gitops commit `a0264c6`):

```yaml
- name: pod-lifecycle
  rules:
    - alert: PodStuckPending
      expr: |
        sum by (namespace, pod) (
          kube_pod_status_phase{phase="Pending"} == 1
        ) > 0
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Pod {{ $labels.namespace }}/{{ $labels.pod }} stuck Pending for >5m"
        description: |
          Common causes: image pull failure, insufficient node resources, PVC not bound.
          Diagnose: kubectl describe pod {{ $labels.pod }} -n {{ $labels.namespace }}

    - alert: ContainerOOMKilled
      expr: |
        kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1
      for: 0m
      labels:
        severity: warning
      annotations:
        summary: "OOMKill: {{ $labels.container }} in {{ $labels.namespace }}/{{ $labels.pod }}"
        description: |
          Check VPA recommendations and raise memory limits:
            kubectl describe pod {{ $labels.pod }} -n {{ $labels.namespace }}
            kubectl get vpa -n {{ $labels.namespace }}
```

`PodStuckPending` fires after 5 minutes to avoid noise from normal pod
startup. `ContainerOOMKilled` fires immediately (`for: 0m`) — an OOMKill is
never noise, and the description points directly to the VPA recommendation
so the fix is one command away.

### Gap 3 — Workload Health Overview Dashboard

Added `minicloud-gitops/manifests/monitoring/05-workload-health-dashboard.yaml`
— a Grafana ConfigMap with label `grafana_dashboard: "1"` so Grafana's
sidecar picks it up automatically.

**9 panels:**

| Panel | Type | What it shows |
|-------|------|---------------|
| Running Pods | Stat (green) | Total pods in Running phase |
| Pending Pods | Stat (yellow threshold) | Turns yellow at ≥ 1 |
| Failed Pods | Stat (red threshold) | Turns red at ≥ 1 |
| CrashLoopBackOff | Stat (red threshold) | Turns red at ≥ 1 |
| CrashLoopBackOff Containers | Table | namespace / pod / container — empty = healthy |
| Top Restarting Pods (1h) | Table | sorted by restart count descending |
| Deployment Missing Replicas | Table | `spec.replicas - status.replicas_available > 0` |
| OOMKilled Containers | Table | `last_terminated_reason == OOMKilled` — empty = no recent kills |
| Restart Rate by Namespace | Timeseries | `rate(restarts_total[5m])` per namespace |

The four stat tiles give a zero-glance cluster health signal. The tables
show exactly which workload needs attention — no PromQL required.

### Gap 4 — Alertmanager Receiver

Fixed as part of Phase 78 (Stalwart mail server). Alertmanager's SMTP
receiver now routes to `stalwart.mail.svc.cluster.local:587` with
STARTTLS. See the [Stalwart phase docs](../developer-platform/amazon-ses)
for the `smtp_require_tls: true` + `insecure_skip_verify: true` gotcha
(Go's `smtp.PlainAuth` refuses PLAIN on non-TLS connections).

---

## Gap 5 — Why Scheduler / Controller-Manager Is Deferred

k3s binds the scheduler (`127.0.0.1:10259`) and controller-manager
(`127.0.0.1:10257`) to **localhost** on `set-hog` (the control plane node).
Prometheus scrapes over the pod network and cannot reach localhost on
another machine.

**Fix would require:**
1. Add `--kube-scheduler-arg=bind-address=0.0.0.0` and
   `--kube-controller-manager-arg=bind-address=0.0.0.0` to the k3s
   systemd unit on `set-hog`
2. `sudo systemctl restart k3s` — brief control-plane disruption
3. Add `ServiceMonitor` objects pointing to `set-hog`'s IP on those ports

**Why it's not worth it at this scale:**

The metrics you'd gain — scheduler queue depth, scheduling latency,
controller reconcile loop errors — matter when thousands of pods are
competing for slots and the scheduler becomes a bottleneck. On a 5-node
cluster with ~100 pods, the scheduler is never the bottleneck.

`kube-state-metrics` already captures the *outcomes*:
- Pod stuck in Pending → `PodStuckPending` fires
- Deployment not converging → `KubeDeploymentReplicasMismatch` fires

You get the same operational value without touching node-level config.

**Revisit threshold:** if the cluster grows beyond ~500 pods or you need
to diagnose intermittent scheduling latency, add the bind-address args
then.
