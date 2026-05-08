---
id: phase-8-monitoring
title: Phase 8 — Monitoring (Prometheus + Grafana)
sidebar_position: 5
---

# Phase 8 — Monitoring Stack

Install a production-grade observability foundation: Prometheus scrapes every node, kubelet, cAdvisor, and the API server; Grafana renders the data; Alertmanager handles alert routing. After this phase the cluster has continuous CPU / memory / disk / pod / network visibility, and Grafana is reachable on the existing Ingress at `http://grafana.10.0.0.200.nip.io`.

This phase sits on top of Phase 5 (Longhorn — Prometheus and Alertmanager need persistent storage so metrics survive pod restarts) and Phase 6 (NGINX Ingress — Grafana joins Homer and Harbor under the same `10.0.0.200` entry point).

---

## Stack

| Tool | Purpose | Storage |
|---|---|---|
| **Prometheus** | Metrics scraping & TSDB | 15 GiB on Longhorn, 10-day retention |
| **Alertmanager** | Alert routing & deduplication | 1 GiB on Longhorn |
| **Grafana** | Dashboards & visualization | 5 GiB on Longhorn |
| **node-exporter** | Per-node hardware metrics | DaemonSet, no storage |
| **kube-state-metrics** | Kubernetes object metrics | Deployment, no storage |
| **prometheus-operator** | Manages CRDs (Prometheus, ServiceMonitor, PrometheusRule, etc.) | Deployment, no storage |

---

## Architecture

```text
                     Browser
                        │  http://grafana.10.0.0.200.nip.io
                        ▼
                NGINX Ingress (10.0.0.200, Phase 6)
                        ▼
                    Grafana pod
                        │   queries
                        ▼
            ┌───────────────────────────┐
            │   Prometheus (StatefulSet)│
            │   PVC 15 GiB on Longhorn  │
            └───────────────────────────┘
                ▲           ▲           ▲
   scrape ─────┘  scrape ──┘  scrape ──┘
   /metrics       /metrics       /metrics, /metrics/cadvisor, /metrics/probes
   ▲              ▲              ▲
   │              │              │
   node-exporter  kube-state-    kubelet (3 nodes)  ──►  api-server
   (3 nodes)      metrics                              (1 control plane)
```

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Install method | `prometheus-community/kube-prometheus-stack` Helm chart (v84.5.0, operator v0.90.1) | Bundles Prometheus + Alertmanager + Grafana + node-exporter + kube-state-metrics + ~26 dashboards + sensible ServiceMonitors. The bare `prometheus-operator/bundle.yaml` only installs the operator — you still wire CRDs by hand. |
| Replicas | 1 each (Prometheus, Alertmanager, Grafana) | Single control-plane k3s cluster — HA replicas just compete for the same disk. |
| Prometheus storage | 15 GiB on Longhorn, retention 10d | Default 50 GiB is overkill for 3 nodes; 10 days covers a typical incident-investigation window. |
| Grafana ingress | HTTP via existing Ingress on `10.0.0.200` | Matches Homer / Harbor pattern. TLS deferred to Phase 15 (cert-manager + Let's Encrypt). |
| Grafana auth | Admin password from out-of-band Secret (`grafana-admin-credentials`) | Keeps the password out of `values.yaml` so the file can be committed. |
| **k3s scrape adjustment** | **Disable** `kubeEtcd`, `kubeControllerManager`, `kubeScheduler` ServiceMonitors | k3s embeds etcd, controller-manager, and scheduler inside the apiserver process — they don't expose `:2381` / `:10257` / `:10259`. Leaving them enabled produces continuous "context deadline exceeded" scrape errors that drown out real signal. |

---

## Pre-flight

```bash
# Helm is already installed at ~/.local/bin/helm
helm version --short        # v3.20.2 or later

# Add the upstream chart repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Generate the Grafana admin password (mode 600, never commit)
openssl rand -base64 24 > ~/.grafana-admin
chmod 600 ~/.grafana-admin

# Create the namespace and the admin Secret out of band
kubectl create namespace monitoring
kubectl create secret generic grafana-admin-credentials \
  -n monitoring \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(cat ~/.grafana-admin)"
```

---

## values.yaml

`kube-prometheus-stack-values.yaml`:

```yaml
fullnameOverride: kps

prometheusOperator:
  resources:
    requests: { cpu: 50m,  memory: 100Mi }
    limits:   { cpu: 200m, memory: 256Mi }

prometheus:
  prometheusSpec:
    retention: 10d
    resources:
      requests: { cpu: 500m,  memory: 2Gi }
      limits:   { cpu: 1000m, memory: 4Gi }
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: longhorn
          accessModes: [ReadWriteOnce]
          resources:
            requests:
              storage: 15Gi
    # Pick up ServiceMonitors / PodMonitors / Rules from any namespace by default
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false
    ruleSelectorNilUsesHelmValues: false

alertmanager:
  alertmanagerSpec:
    resources:
      requests: { cpu: 50m,  memory: 64Mi }
      limits:   { cpu: 100m, memory: 128Mi }
    storage:
      volumeClaimTemplate:
        spec:
          storageClassName: longhorn
          accessModes: [ReadWriteOnce]
          resources:
            requests:
              storage: 1Gi

grafana:
  admin:
    existingSecret: grafana-admin-credentials
    userKey: admin-user
    passwordKey: admin-password
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 200m, memory: 512Mi }
  persistence:
    enabled: true
    type: pvc
    storageClassName: longhorn
    accessModes: [ReadWriteOnce]
    size: 5Gi
  ingress:
    enabled: true
    ingressClassName: nginx
    hosts:
      - grafana.10.0.0.200.nip.io
    path: /
    pathType: Prefix

# k3s embeds these inside apiserver — disable to avoid scrape spam
kubeEtcd:
  enabled: false
kubeControllerManager:
  enabled: false
kubeScheduler:
  enabled: false

kube-state-metrics:
  resources:
    requests: { cpu: 10m,  memory: 32Mi }
    limits:   { cpu: 100m, memory: 128Mi }

prometheus-node-exporter:
  resources:
    requests: { cpu: 10m,  memory: 32Mi }
    limits:   { cpu: 100m, memory: 128Mi }
```

---

## Install

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f kube-prometheus-stack-values.yaml \
  --wait --timeout 10m
```

Expected pods (8 total):

```bash
$ kubectl get pods -n monitoring
NAME                                                        READY   STATUS    AGE
alertmanager-kps-alertmanager-0                             2/2     Running   2m
kps-operator-…                                              1/1     Running   2m
kube-prometheus-stack-grafana-…                             3/3     Running   2m
kube-prometheus-stack-kube-state-metrics-…                  1/1     Running   2m
kube-prometheus-stack-prometheus-node-exporter-…            1/1     Running   2m   # × 3 (one per node)
prometheus-kps-prometheus-0                                 2/2     Running   2m
```

PVCs (3 total, all on Longhorn):

```bash
$ kubectl get pvc -n monitoring
NAME                                                                STATUS   CAPACITY   STORAGECLASS
alertmanager-kps-alertmanager-db-alertmanager-kps-alertmanager-0    Bound    1Gi        longhorn
kube-prometheus-stack-grafana                                       Bound    5Gi        longhorn
prometheus-kps-prometheus-db-prometheus-kps-prometheus-0            Bound    15Gi       longhorn
```

---

## Verify Prometheus targets

```bash
kubectl port-forward -n monitoring svc/kps-prometheus 9090:9090
```

Open `http://localhost:9090` → **Status → Targets**. Expected:

| Job | Expected | Why |
|---|---|---|
| `node-exporter` | 3/3 UP | one per node |
| `kubelet` (`/metrics`) | 3/3 UP | per-node kubelet |
| `kubelet` (`/metrics/cadvisor`) | 3/3 UP | container CPU/memory |
| `kubelet` (`/metrics/probes`) | 3/3 UP | liveness/readiness probe stats |
| `apiserver` | 1/1 UP | single control plane |
| `coredns` | 1/1 UP | k3s DNS |
| `kube-state-metrics` | 1/1 UP | Kubernetes object state |

You should **not** see scrape jobs for `kubeEtcd`, `kubeControllerManager`, or `kubeScheduler` — those are disabled in `values.yaml`.

Quick metric sanity checks via `curl`:

```bash
# 3 instances each (one per node)
curl -s -G --data-urlencode 'query=count(count by (instance)(node_memory_MemAvailable_bytes))' \
  http://localhost:9090/api/v1/query | jq '.data.result[0].value[1]'   # → "3"
curl -s -G --data-urlencode 'query=count(count by (instance)(container_cpu_usage_seconds_total))' \
  http://localhost:9090/api/v1/query | jq '.data.result[0].value[1]'   # → "3"
```

---

## Verify Grafana

```bash
# Reachability via Ingress — expect 302 (redirect to /login)
curl -sI http://grafana.10.0.0.200.nip.io/

# Login as admin / contents of ~/.grafana-admin
```

The chart auto-provisions two datasources — `Prometheus` (default, uid `prometheus`, pointing at the in-cluster Prometheus) and `Alertmanager` — plus ~26 built-in dashboards (Kubernetes / Compute Resources, Node Exporter / Nodes, etc.).

---

## Import community dashboards

| Dashboard | grafana.com ID | Notes |
|---|---|---|
| Kubernetes Cluster | 7249 | High-level cluster overview |
| Node Exporter Full | 1860 | Deep per-node metrics |
| 1 Kubernetes All-in-one Cluster Monitoring KR | 13770 | k3s-friendly all-in-one |

Import via the API (replace `$PW` with `~/.grafana-admin`):

```bash
G="http://admin:$PW@grafana.10.0.0.200.nip.io"

import_dash() {
  local id=$1
  local rev=$(curl -s "https://grafana.com/api/dashboards/$id" | jq -r '.revision')
  curl -s "https://grafana.com/api/dashboards/$id/revisions/$rev/download" > /tmp/dash.json
  jq '{
    dashboard: .,
    overwrite: true,
    inputs: ([(.__inputs // [])[] | select(.type=="datasource" and .pluginId=="prometheus")
             | {name: .name, type: "datasource", pluginId: "prometheus", value: "Prometheus"}]),
    folderId: 0
  }' /tmp/dash.json > /tmp/payload.json
  curl -s -X POST -H "Content-Type: application/json" --data @/tmp/payload.json "$G/api/dashboards/import"
}

import_dash 7249
import_dash 1860
import_dash 13770
```

Note the file-based payload: dashboard 1860 is ~470 KB and trips the shell argument limit if passed inline.

### Dashboard 1860 datasource gotcha

Unlike most dashboards, **1860 declares its Prometheus datasource via a template variable (`ds_prometheus`) instead of `__inputs`**. After import, the variable's `current` value is empty — meaning Grafana will pick a Prometheus datasource on first open, but no value is saved. Patch it explicitly so the dashboard always opens with data populated:

```bash
G="http://admin:$PW@grafana.10.0.0.200.nip.io"
curl -s "$G/api/dashboards/uid/rYdddlPWk" > /tmp/dash.json
jq '.dashboard.templating.list = ([.dashboard.templating.list[]
       | if (.type=="datasource" and .name=="ds_prometheus")
         then .current = {"selected": true, "text": "Prometheus", "value": "Prometheus"}
         else . end])
    | {dashboard: .dashboard, folderId: 0, overwrite: true, message: "Set ds_prometheus default"}' \
  /tmp/dash.json > /tmp/patched.json
curl -s -X POST -H "Content-Type: application/json" --data @/tmp/patched.json "$G/api/dashboards/db"
```

---

## Add Grafana to Homer

Update the `Observability` section of `homer-config.yml`:

```yaml
- name: "Grafana"
  icon: "fas fa-chart-bar"
  subtitle: "Dashboards & metrics visualization"
  tag: "live"
  url: "http://grafana.10.0.0.200.nip.io"
  target: "_blank"
```

Apply and restart:

```bash
kubectl create configmap homer-config \
  --from-file=config.yml=homer-config.yml \
  -n homer --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/homer -n homer
```

---

## Troubleshooting

### Prometheus pod stuck in `Pending` for more than 2 minutes

Most likely Longhorn is taking time to attach the 15 GiB volume to the scheduled node:

```bash
kubectl describe pod prometheus-kps-prometheus-0 -n monitoring | tail -20
```

Look for events like `MultiAttachError` or `Volume … is being detached`. Confirm the PVC is `Bound`:

```bash
kubectl get pvc -n monitoring
```

If the volume is genuinely stuck, restart the longhorn-manager DaemonSet on the affected node:

```bash
kubectl rollout restart daemonset/longhorn-manager -n longhorn-system
```

### Spurious "context deadline exceeded" scrape errors after install

You forgot to disable `kubeEtcd` / `kubeControllerManager` / `kubeScheduler` in `values.yaml`. k3s embeds those inside the apiserver process and doesn't expose their standard scrape ports. Edit `values.yaml`, set the three `enabled: false` flags, and run `helm upgrade`.

### Dashboard 1860 panels show "No data"

The `ds_prometheus` template variable wasn't set after import. Open the dashboard, click the **Datasource** dropdown at the top and select `Prometheus`, then save. Or apply the `current` patch from the dashboard import section above.

### Dashboard 1860 import fails with `Argument list too long`

Its JSON is ~470 KB — too big to inline as a shell argument. Always download to a file and POST with `curl --data @/tmp/file.json`.

---

## Done When

```text
✔ 8 pods Running in `monitoring` namespace
✔ 3 PVCs Bound on Longhorn (15 + 5 + 1 GiB)
✔ Prometheus targets all UP — node-exporter 3/3, kubelet 3/3, cAdvisor 3/3, apiserver 1/1
✔ No scrape errors for kubeEtcd / kubeControllerManager / kubeScheduler (disabled)
✔ Grafana reachable at http://grafana.10.0.0.200.nip.io, admin login works
✔ Built-in dashboards "Kubernetes / Compute Resources / Cluster" and "Node Exporter / Nodes" render data
✔ Imported 7249, 1860, 13770 — 1860's `ds_prometheus` variable points at our Prometheus
✔ Homer has a live "Grafana" tile
```

---

## Real-world skills demonstrated

| Skill | Where it applies in industry |
|---|---|
| Operating the **kube-prometheus-stack** Helm chart end-to-end | The de facto monitoring install on virtually every production Kubernetes cluster |
| Sizing Prometheus retention vs disk | Capacity-planning every observability rollout — the question "how long do we keep raw metrics?" comes up at every cost review |
| **k3s-aware scrape configuration** | Recognizing that lightweight Kubernetes distros (k3s, k0s, RKE2, MicroK8s) embed control-plane components and break standard ServiceMonitors — saves days of debugging "why is etcd down" |
| Out-of-band Secret + `existingSecret` pattern | Standard practice for keeping passwords out of values files committed to git |
| Persistent volume sizing on RWO storage | Same pattern Longhorn / Ceph RBD / EBS / GCE PD shops use for stateful workloads |
| Dashboard provisioning via Grafana HTTP API | Foundation for GitOps observability — Phase 12 will move dashboards into ArgoCD |
| Single-IP Ingress consolidation | Real production clusters route 10s–100s of services through one or two Ingress IPs |
