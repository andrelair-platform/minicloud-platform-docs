---
id: k8s-monitoring-gaps
title: Kubernetes Monitoring — Gap Analysis & Fixes
sidebar_position: 6
---

# Kubernetes Monitoring — Gap Analysis & Fixes

After Phase 21 wired up Alertmanager routing and Phase 8 deployed
kube-prometheus-stack, a targeted gap analysis found 5 holes in the
monitoring coverage. All 5 are now closed.

---

## Tools — Baseline

| Tool | Status |
|------|--------|
| kube-state-metrics | ✅ Running (`ServiceMonitor kps-kube-state-metrics`) |
| Prometheus | ✅ Running (kube-prometheus-stack) |
| Grafana | ✅ Running (29 dashboards provisioned) |

---

## Data Sources

| Source | ServiceMonitor | Scraping | Status |
|--------|---------------|----------|--------|
| kube-apiserver | `kps-apiserver` | ✅ | ✅ |
| kubelet | `kps-kubelet` | ✅ | ✅ |
| CoreDNS | `kps-coredns` | ✅ | ✅ |
| scheduler | `kube-scheduler-proxy` | ✅ | ✅ closed via socat proxy |
| controller-manager | `kube-controller-manager-proxy` | ✅ | ✅ closed via socat proxy |
| etcd | N/A — see below | ✅ | ✅ Kine/SQLite metrics via apiserver scrape |

:::info No etcd — this cluster uses Kine/SQLite
k3s was started without `--cluster-init`, so there is no embedded etcd process.
The datastore is **Kine** (a SQLite-backed etcd-compatible layer). Kine metrics
(`kine_sql_total`, `kine_sql_time_seconds_*`, `kine_compact_total`) are already
flowing in Prometheus via the existing `kps-apiserver` ServiceMonitor — no additional
scrape config needed.
:::

---

## All 5 Gaps — Status

| # | Gap | Fix | Result |
|---|-----|-----|--------|
| 1 | Pod stuck Pending alert | `PodStuckPending` PrometheusRule | ✅ closed — gitops `a0264c6` |
| 2 | OOMKilled alert | `ContainerOOMKilled` PrometheusRule | ✅ closed — gitops `a0264c6` |
| 3 | Workload Health dashboard | 9-panel Grafana ConfigMap | ✅ closed — gitops `a0264c6` |
| 4 | Alertmanager receiver (silent alerts) | SMTP via Stalwart (Phase 78) | ✅ closed |
| 5 | Scheduler + controller-manager metrics | socat DaemonSet proxy on `set-hog` | ✅ closed — gitops PR #157 |

---

## Gap 1 + 2 — PrometheusRules

Added to `minicloud-gitops/manifests/monitoring/04-infrastructure-alerts.yaml`:

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

`PodStuckPending` fires after 5 minutes to avoid startup noise. `ContainerOOMKilled`
fires immediately (`for: 0m`) — an OOMKill is never noise.

---

## Gap 3 — Workload Health Overview Dashboard

`minicloud-gitops/manifests/monitoring/05-workload-health-dashboard.yaml` — Grafana
ConfigMap with label `grafana_dashboard: "1"`, sidecar picks it up automatically.

**9 panels:**

| Panel | Type | What it shows |
|-------|------|---------------|
| Running Pods | Stat (green) | Total pods in Running phase |
| Pending Pods | Stat (yellow at ≥1) | Turns yellow immediately |
| Failed Pods | Stat (red at ≥1) | Turns red immediately |
| CrashLoopBackOff | Stat (red at ≥1) | Zero-glance crash signal |
| CrashLoopBackOff Containers | Table | namespace / pod / container — empty = healthy |
| Top Restarting Pods (1h) | Table | sorted by restart count descending |
| Deployment Missing Replicas | Table | `spec.replicas - status.replicas_available > 0` |
| OOMKilled Containers | Table | `last_terminated_reason == OOMKilled` — empty = no recent kills |
| Restart Rate by Namespace | Timeseries | `rate(restarts_total[5m])` per namespace |

---

## Gap 4 — Alertmanager Receiver

Fixed in Phase 78 (Stalwart mail server). Alertmanager SMTP receiver routes to
`stalwart.mail.svc.cluster.local:587` with STARTTLS.

Gotcha: Go's `smtp.PlainAuth` refuses PLAIN on non-TLS connections —
requires `smtp_require_tls: true` + `smtp_tls_config.insecure_skip_verify: true`
in the Alertmanager config.

---

## Gap 5 — Scheduler / Controller-Manager via Socat Proxy

**gitops PR #157 — merged 2026-07-19**

### Architecture

```
[Prometheus] ──scrape──▶ [ClusterIP Service :10269]
                                   │
                         [Endpoints: 10.0.0.2:10269]
                                   │
                    [DaemonSet pod on set-hog, hostNetwork: true]
                    [socat TCP-LISTEN:10269 → TCP:127.0.0.1:10259]
                                   │
                         [k3s scheduler on 127.0.0.1:10259]
```

Same flow on port 10267 → 10257 for controller-manager.

### Why socat over kube-rbac-proxy

k3s scheduler and controller-manager serve **HTTPS with self-signed certs**.
`kube-rbac-proxy` is HTTP-aware and requires TLS config for the upstream.
`socat` in TCP tunnel mode passes bytes blindly — HTTPS traverses the tunnel
intact, and Prometheus handles TLS with `insecureSkipVerify: true`. No
cert management on the proxy side.

### Files

| File | Purpose |
|------|---------|
| `manifests/monitoring/07-controlplane-proxy.yaml` | DaemonSet — two socat containers |
| `manifests/monitoring/08-controlplane-services.yaml` | Two ClusterIP Services |
| `manifests/monitoring/09-controlplane-servicemonitors.yaml` | Two ServiceMonitors |

### DaemonSet key fields

```yaml
spec:
  nodeSelector:
    kubernetes.io/hostname: set-hog      # control-plane only
  hostNetwork: true                      # reach host's 127.0.0.1
  dnsPolicy: ClusterFirstWithHostNet
  containers:
    - name: scheduler-proxy
      image: harbor.10.0.0.200.nip.io/library/socat:1.8.0.0
      command: [socat, TCP-LISTEN:10269,fork,reuseaddr, TCP:127.0.0.1:10259]
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534        # nobody — ports >1024 don't need root
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        seccompProfile: {type: RuntimeDefault}
        capabilities: {drop: [ALL]}
```

### ServiceMonitor pattern (matches kps-kubelet exactly)

```yaml
endpoints:
  - port: https-metrics
    scheme: https
    bearerTokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
    tlsConfig:
      insecureSkipVerify: true   # k3s self-signed cert
```

### No changes needed to

- **Gatekeeper** — `monitoring` namespace already excluded from all `deny` constraints
- **RBAC** — `kps-prometheus` ClusterRole already has `nonResourceURLs: [/metrics] get`
- **kps values** — `serviceMonitorSelectorNilUsesHelmValues: false` picks up all ServiceMonitors

### Ports

| Component | k3s binds to | Proxy listens on |
|-----------|-------------|-----------------|
| scheduler | `127.0.0.1:10259` | `0.0.0.0:10269` on set-hog |
| controller-manager | `127.0.0.1:10257` | `0.0.0.0:10267` on set-hog |

### Verification

```bash
# DaemonSet pod running on set-hog
kubectl get pod -n monitoring -l app=controlplane-proxy -o wide
# NAME                       READY   STATUS    NODE
# controlplane-proxy-bnggp   2/2     Running   set-hog

# Endpoints point to set-hog's IP (hostNetwork pod IP = node IP)
kubectl get endpoints kube-scheduler-proxy kube-controller-manager-proxy -n monitoring
# kube-scheduler-proxy            10.0.0.2:10269
# kube-controller-manager-proxy   10.0.0.2:10267

# Prometheus targets — both UP
# scheduler_framework_extension_point_duration_seconds_count → 60 series
# workqueue_depth{job="kube-controller-manager-proxy"} → 93 series
```

---

## Important Metrics Coverage

All 9 key operational metrics are actively collected, alerted on, or visible in dashboards.

| Metric | Collected by | Alert | Dashboard |
|--------|-------------|-------|-----------|
| Pending Pods | kube-state-metrics | `PodStuckPending` (fires after 5m) | Workload Health — Pending Pods stat |
| Failed Pods | kube-state-metrics | — | Workload Health — Failed Pods stat (red at ≥1) |
| Pod restarts | kube-state-metrics | — | Workload Health — Top Restarting Pods table |
| CrashLoopBackOff | kube-state-metrics | — | Workload Health — stat + CrashLoop table |
| Node NotReady | kube-state-metrics | `KubeNodeNotReady` (kps built-in) | Kubernetes / Compute Resources |
| PVC usage | kubelet (`volume_manager`) | `KubePersistentVolumeFilesystemUsage` (kps built-in) | Kubernetes / Persistent Volumes |
| Deployment availability | kube-state-metrics | `KubeDeploymentReplicasMismatch` (kps built-in) | Workload Health — Deployment Missing Replicas |
| Replica count | kube-state-metrics | — | Workload Health — Deployment Missing Replicas |
| HPA activity | kube-state-metrics | — | Kubernetes / HPA |

---

## Verdict

:::tip All coverage confirmed ✅

| Category | Result |
|----------|--------|
| **Data sources** (6/6) | kube-apiserver ✅ · kubelet ✅ · CoreDNS ✅ · scheduler ✅ · controller-manager ✅ · etcd → Kine ✅ |
| **Important metrics** (9/9) | Pending ✅ · Failed ✅ · Restarts ✅ · CrashLoop ✅ · NodeNotReady ✅ · PVC ✅ · Deployment ✅ · Replicas ✅ · HPA ✅ |
| **Tools** (3/3) | kube-state-metrics ✅ · Prometheus ✅ · Grafana ✅ |

:::
