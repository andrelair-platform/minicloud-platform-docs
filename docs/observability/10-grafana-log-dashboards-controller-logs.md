---
title: Grafana Log Dashboards & Controller Log Ingestion
sidebar_label: Log Dashboards & Controller Logs
---

# Grafana Log Dashboards & Controller Log Ingestion

This page covers Gaps 4–7 of the minicloud observability stack, completing the end-to-end logging pipeline built across Phases 21–22.

## What Was Built

| Gap | Description | Status |
|-----|-------------|--------|
| 4 | 3 Grafana dashboards for log exploration and error/crash visibility | ✅ Closed |
| 5 | Metrics↔logs correlation dataLinks on the Workload Health dashboard | ✅ Closed |
| 6 | Controller host log ingestion (Docker + journald) into Loki | ✅ Closed |
| 7 | Loki retention extended from 7 days to 30 days | ✅ Closed |

---

## Gap 4 — Grafana Log Dashboards

Three new dashboards were added as ConfigMaps in `minicloud-gitops/manifests/monitoring/`:

### Application Logs Explorer (`minicloud-app-logs`)

**File:** `16-app-logs-dashboard.yaml`

The primary log search interface. Features:
- Namespace and pod Loki label-value template variables (driven by `label_values({namespace=~".+"},"namespace")`)
- Error rate timeseries over time
- Log volume by level (pie/bar gauge)
- Raw log panel with free-text search (`$search` variable filters the LogQL stream)

**LogQL pattern:**
```logql
{namespace=~"$namespace", pod=~"$pod"} |= "$search"
```

### Error Rate by Service (`minicloud-error-rate`)

**File:** `17-error-rate-dashboard.yaml`

Surfaces error signal across all namespaces. Features:
- 3 stat panels: total errors 1h, FATAL events 1h, affected namespaces count
- Error rate per namespace timeseries (5m window)
- Top namespaces and top pods bar gauges
- Recent error log table

**Error LogQL pattern (excludes infrastructure noise):**
```logql
sum by (namespace) (
  count_over_time(
    {namespace=~".+", namespace!~"kube-system|longhorn-system|observability|monitoring|velero|system-upgrade|reloader|vpa-system"}
    |~ "(?i)(error|ERROR)"
    [5m]
  )
)
```

### Pod Crash & Restart Events (`minicloud-crash-events`)

**File:** `18-crash-events-dashboard.yaml`

Focused on crash analysis. Features:
- 4 stats: crash events 24h, OOM kills, FATAL/panic count, affected namespaces
- Crash timeline by container
- Top crashing pods table
- Crash type breakdown (panic / FATAL / OOM / runtime error)
- Raw crash log panel for root-cause inspection

**Crash LogQL pattern:**
```logql
count_over_time(
  {namespace=~"$namespace"}
  |~ "(?i)(panic|fatal|oom|killed|core dumped|runtime error)"
  [5m]
)
```

### How Grafana Picks Up New Dashboard ConfigMaps

The Grafana sidecar uses the **Kubernetes Watch API** (`METHOD=WATCH` environment variable), not polling. When a new ConfigMap with label `grafana_dashboard: "1"` is created or updated in the `monitoring` namespace, the sidecar receives the Watch event immediately and calls `POST /api/admin/provisioning/dashboards/reload`. Dashboards appear in Grafana within a few seconds — no restart needed.

---

## Gap 5 — Metrics↔Logs Correlation dataLinks

The Workload Health dashboard (`manifests/monitoring/05-workload-health-dashboard.yaml`, version 2) now carries **"View logs"** dataLinks on 5 panels that open Grafana Explore pre-filtered to the relevant pod or namespace.

### Panel Coverage

| Panel | Link variable | LogQL target |
|-------|--------------|--------------|
| CrashLoopBackOff Containers (table) | `${__data.fields.pod}` | `{namespace="...", pod="..."}` |
| Top Restarting Pods (table) | `${__data.fields.pod}` | `{namespace="...", pod="..."}` |
| Deployment Health — Missing Replicas (table) | `${__data.fields.namespace}` | `{namespace="..."}` |
| OOMKilled Containers (table) | `${__data.fields.pod}` | `{namespace="...", pod="..."}` |
| Container Restart Rate (timeseries) | `${__field.labels.namespace}` | `{namespace="..."}` |

### Explore URL Format

The dataLink URL embeds JSON in the query string. Table panels use `${__data.fields.*}` and timeseries panels use `${__field.labels.*}`. The Loki datasource is referenced by its fixed UID `P8E80F9AEF21F6940`.

```
/explore?orgId=1&left={"datasource":"P8E80F9AEF21F6940","queries":[{"refId":"A","datasource":{"type":"loki","uid":"P8E80F9AEF21F6940"},"expr":"{namespace=\"${__data.fields.namespace}\",pod=\"${__data.fields.pod}\"}"}],"range":{"from":"${__from}","to":"${__to}"}}
```

**JSON escaping inside the URL:** quotes within the `expr` string must be escaped as `\\\"` in the YAML value (single backslash-escaped in the JSON string, then escaped again for YAML).

---

## Gap 6 — Controller Host Log Ingestion

The MAAS controller (`ktayl-ThinkPad-X390`, `10.0.0.1`) runs Docker containers and systemd services. These logs were previously invisible in Loki — the cloudflared crash in July 2026 (1.5 days downtime) was diagnosed manually from `docker logs` because those logs were lost after restart.

### Architecture

```
controller
├── Docker containers (MinIO, cloudflared, node-exporter, promtail...)
│   └── /var/lib/docker/containers/*/json-log
├── systemd journal (/var/log/journal)
│
└── Promtail container (grafana/promtail:3.3.2, --net=host)
        ├── docker_sd_configs → discovers containers via Docker socket
        └── journal scrape → systemd unit logs
                ↓
         https://loki.10.0.0.200.nip.io/loki/api/v1/push
                ↓
         Loki (observability namespace) via NGINX Ingress + minicloud-ca TLS
```

### Loki Ingress for External Push

Three resources were added to `manifests/loki/`:

**`01-loki-ingress.yaml`** — NGINX Ingress for `loki.10.0.0.200.nip.io`:
```yaml
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - loki.10.0.0.200.nip.io
      secretName: loki-tls
  rules:
    - host: loki.10.0.0.200.nip.io
      ...
        backend:
          service:
            name: loki
            port:
              number: 3100
```

**`03-loki-certificate.yaml`** — cert-manager Certificate using `minicloud-ca` ClusterIssuer:
```yaml
spec:
  dnsNames:
    - loki.10.0.0.200.nip.io
  issuerRef:
    kind: ClusterIssuer
    name: minicloud-ca
  secretName: loki-tls
```

**`02-loki-networkpolicy.yaml`** — allows NGINX ingress pods → Loki port 3100 (required by `default-deny-ingress` in `observability` namespace):
```yaml
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: loki
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
          podSelector:
            matchLabels:
              app.kubernetes.io/name: ingress-nginx
      ports:
        - port: 3100
```

### Promtail Configuration

Config file at `/home/ktayl/.promtail/config.yaml` on the controller:

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0
positions:
  filename: /home/ktayl/.promtail/positions.yaml
clients:
  - url: https://loki.10.0.0.200.nip.io/loki/api/v1/push
    tls_config:
      ca_file: /home/ktayl/.promtail/minicloud-ca.crt
scrape_configs:
  - job_name: controller-docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: [__meta_docker_container_name]
        regex: '/(.*)'
        target_label: container
      - source_labels: [__meta_docker_container_log_stream]
        target_label: stream
      - replacement: controller
        target_label: host
      - replacement: controller-docker
        target_label: job
    pipeline_stages:
      - docker: {}
  - job_name: controller-journald
    journal:
      max_age: 12h
      path: /var/log/journal
      labels:
        host: controller
        job: controller-journald
    relabel_configs:
      - source_labels: [__journal__systemd_unit]
        target_label: unit
      - source_labels: [__journal_priority_keyword]
        target_label: level
```

### Docker Run Command

```bash
docker run -d --name promtail --restart=always \
  --net=host \
  -v /home/ktayl/.promtail:/etc/promtail:ro \
  -v /home/ktayl/.promtail:/home/ktayl/.promtail \
  -v /var/lib/docker/containers:/var/lib/docker/containers:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/log/journal:/var/log/journal:ro \
  -v /run/log/journal:/run/log/journal:ro \
  -v /etc/machine-id:/etc/machine-id:ro \
  grafana/promtail:3.3.2 \
  -config.file=/etc/promtail/config.yaml
```

The `--restart=always` flag ensures Promtail restarts after controller reboots. The `--net=host` flag is required (see Gotchas below).

### Verification

```bash
# From controller host:
/usr/bin/curl -sk --cacert ~/minicloud-ca.crt \
  'https://loki.10.0.0.200.nip.io/loki/api/v1/label/host/values'
# Expected: {"status":"success","data":["controller"]}

# Check recent controller-docker logs:
/usr/bin/curl -sk --cacert ~/minicloud-ca.crt \
  'https://loki.10.0.0.200.nip.io/loki/api/v1/query?query={job="controller-docker"}&limit=3'
```

In Grafana Explore, query `{host="controller", job="controller-docker"}` or `{host="controller", unit="cloudflared.service"}` for systemd logs.

---

## Gap 7 — Retention Extended to 30 Days

Changed in `helm-values/loki-values.yaml`:

```yaml
loki:
  limits_config:
    retention_period: 720h   # was 168h (7 days)
  compactor:
    retention_enabled: true
    delete_request_store: filesystem
    retention_delete_delay: 2h
```

Loki compactor runs automatically and enforces the retention window. Old chunks are deleted after `retention_period` + `retention_delete_delay`. The 30Gi Longhorn PVC provides ~6 months of typical cluster log volume at the current ingestion rate.

---

## Gotchas

### Docker bridge networking cannot reach MetalLB IP

Docker containers started without `--net=host` use the Docker bridge network (`172.17.0.0/16`). The MetalLB virtual IP `10.0.0.200` is on the controller's physical network interface, which is not routable from inside the bridge. Symptom: `context deadline exceeded` on every push attempt, even though `curl` from the host succeeds.

**Fix:** Always use `--net=host` for Docker containers on the controller that need to reach cluster services (MetalLB IPs or the Kubernetes API). Same pattern as MinIO on the controller.

### Gatekeeper `require-ingress-tls` rejects plain HTTP Ingresses

Every Ingress in the cluster must have a `spec.tls` block. Creating an Ingress without TLS gets denied immediately by the Gatekeeper `require-ingress-tls` constraint:
```
[require-ingress-tls] Ingress 'observability/loki-push' must set spec.tls with at least one entry
```

**Fix:** Create a `cert-manager.io/v1 Certificate` resource alongside any new Ingress. Reference the resulting Secret in `spec.tls.secretName`. The Certificate must be in the same namespace as the Ingress.

### ArgoCD SSA field manager conflict when mixing kubectl apply

The loki ArgoCD app uses `ServerSideApply=true`. If resources in its source path are first applied via `kubectl apply` (e.g. to bypass a loop), ArgoCD reconciles them on the next auto-sync using its own field manager. The result is two field managers (`kubectl` + `argocd`) both owning fields, which can cause drift errors on subsequent updates. In practice, ArgoCD resolved this transparently for the Ingress and Certificate — both showed `Synced` after the next auto-sync without manual intervention.
