---
id: phase-9-workload
title: Phase 9 — First Workload (podinfo)
sidebar_position: 6
---

# Phase 9 — First Workload (podinfo)

The previous eight phases built the platform — provisioning, Kubernetes, kubectl access, Tailscale, MetalLB, Longhorn, Ingress, Harbor, and the kube-prometheus-stack monitoring layer. Phase 9 is the first **integration test**: deploy a real-world application that simultaneously exercises the scheduler (multi-pod placement across both worker nodes), the Ingress (host-based routing), Prometheus auto-discovery (cross-namespace ServiceMonitor pickup), and the Horizontal Pod Autoscaler (metrics-server → HPA controller → scale events).

The original Phase 9 plan was "deploy nginx with NodePort and `curl` it" — that proves containerd is alive but doesn't exercise any of the platform built in Phases 4–8. We replace it with a workload that genuinely flexes the stack.

---

## Why podinfo

[podinfo](https://github.com/stefanprodan/podinfo) is a small Go HTTP service (~30 MB image) that:

| Feature | Why it matters here |
|---|---|
| Exposes Prometheus `/metrics` (port 9797) — `http_request_duration_seconds_*`, Go runtime, etc. | Tests the cross-namespace ServiceMonitor logic configured in Phase 8 |
| Ships a maintained Helm chart with `hpa.enabled`, `ingress.enabled`, `serviceMonitor.enabled` flags | Exercises every Phase 4–8 layer through a single helm install |
| Used as the canonical demo workload by Flux, Linkerd, FluentBit docs | Recognizable on a CV; not a hand-rolled toy |
| Stateless | Phase 9 is "first workload", not "every pattern". Stateful workloads (PostgreSQL etc.) come in later phases. |

---

## Architecture

```text
            Browser  http://podinfo.10.0.0.200.nip.io/
                 │
                 ▼
        NGINX Ingress (10.0.0.200, Phase 6)
                 │
                 ▼
            Service "podinfo" (ClusterIP :9898)
                 │       │
            ┌────┘       └────┐
            ▼                 ▼
       Pod (fast-skunk)  Pod (fast-heron)        ← anti-affinity splits the 2 baseline replicas
            │                 │
            │  /metrics:9797 (per-pod)
            ▼
     Prometheus (Phase 8) — picks up the ServiceMonitor
                                  in any namespace
            ▼
       Grafana — custom dashboard "/d/podinfo-app/"

            ┌─── HPA loop ────────────────┐
            ▼                             │
     metrics-server → HPA controller → Deployment scale (2..5)
```

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| App | **podinfo** (Helm chart, public image) | See "Why podinfo" |
| Image source | `ghcr.io/stefanprodan/podinfo:6.11.2` (public) | Harbor pull path is still broken (k3s `/v2`-suffix mirror URL mismatch documented in Phase 7); proper end-to-end Harbor pulls land in Phase 15 with TLS |
| Replicas | `replicaCount: 2` with HPA min=2, max=5, target 50% CPU | 2 baseline replicas force scheduler to use both worker nodes; HPA range exercises metrics-server → autoscaler pipeline |
| Anti-affinity | `preferredDuringSchedulingIgnoredDuringExecution` on `kubernetes.io/hostname` | Keeps the baseline 2 pods split across workers, but allows HPA to co-locate replicas 3-5 once we exceed worker count |
| Resource requests | `cpu: 50m, memory: 64Mi` | HPA percentage targets are computed against requests — small request makes the load test easy to trigger; limits set at 200m/256Mi |
| Ingress | `podinfo.10.0.0.200.nip.io`, class `nginx`, HTTP | Same single-IP host-based routing pattern as Homer / Harbor / Grafana |
| ServiceMonitor | `enabled: true, interval: 15s` | Tests Phase 8's `serviceMonitorSelectorNilUsesHelmValues: false` — Prometheus should pick this up with zero extra config |
| Storage | None (PVC=0) | podinfo is stateless. Stateful workloads come in CI/CD (Phase 13) and onward. |
| Grafana dashboard | **Custom**, built via the Grafana API | No community-published podinfo dashboard exists; building one is more portfolio-valuable than importing — same "dashboard-as-code" pattern Phase 12 (ArgoCD) will apply at scale |

---

## Pre-flight

```bash
# metrics-server must be up — HPA depends on it (k3s ships it enabled by default)
kubectl top nodes        # should print CPU/memory rows for all 3 nodes

# Add the chart repo
helm repo add podinfo https://stefanprodan.github.io/podinfo
helm repo update podinfo
```

---

## values.yaml

`podinfo-values.yaml`:

```yaml
replicaCount: 2

image:
  repository: ghcr.io/stefanprodan/podinfo
  tag: 6.11.2
  pullPolicy: IfNotPresent

resources:
  requests: { cpu: 50m,  memory: 64Mi }
  limits:   { cpu: 200m, memory: 256Mi }

hpa:
  enabled: true
  maxReplicas: 5
  cpu: 50            # target 50% of request → ~25m per pod

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: podinfo.10.0.0.200.nip.io
      paths:
        - path: /
          pathType: Prefix

serviceMonitor:
  enabled: true
  interval: 15s

# Soft anti-affinity: prefer one pod per node for the baseline 2 replicas,
# allow co-location once HPA scales past the worker count.
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: podinfo
          topologyKey: kubernetes.io/hostname
```

---

## Install

```bash
kubectl create namespace podinfo
helm install podinfo podinfo/podinfo -n podinfo \
  -f podinfo-values.yaml \
  --wait --timeout 5m
```

---

## Verify

### Scheduler placement

```bash
$ kubectl get pods -n podinfo -o wide
NAME                       READY   STATUS    NODE
podinfo-…-gxsz8            1/1     Running   fast-heron
podinfo-…-xfzfb            1/1     Running   fast-skunk
```

Both replicas land on workers; control plane (`set-hog`) is left alone.

### Ingress

```bash
$ curl -s http://podinfo.10.0.0.200.nip.io/ | jq .
{
  "hostname": "podinfo-…-gxsz8",
  "version": "6.11.2",
  "color": "#34577c",
  "message": "greetings from podinfo v6.11.2",
  "goos": "linux",
  "num_cpu": "8"
}

$ curl -s -o /dev/null -w "%{http_code}\n" http://podinfo.10.0.0.200.nip.io/healthz
200
```

Note: `/healthz` and `/readyz` only accept GET — `curl -I` (HEAD) returns 405.

### Prometheus auto-scrape

```bash
kubectl port-forward -n monitoring svc/kps-prometheus 9090:9090
```

In **Status → Targets**, the `serviceMonitor/podinfo/podinfo/0` job should show 2/2 endpoints `up`. Quick metric check:

```bash
curl -s -G --data-urlencode 'query=sum(http_request_duration_seconds_count{namespace="podinfo"})' \
  http://localhost:9090/api/v1/query | jq -r '.data.result[0].value[1]'
# → some number > 0 (kubelet probes alone bump this)
```

This works **without any extra Prometheus config** because Phase 8's values set `serviceMonitorSelectorNilUsesHelmValues: false` — Prometheus picks up ServiceMonitors from any namespace. That's the "self-service" property of a working monitoring layer.

### Custom Grafana dashboard

The Grafana API accepts a JSON dashboard spec via `POST /api/dashboards/db`. The dashboard for podinfo (built directly in Phase 9) has 7 panels: replicas Running, total requests served, request rate, request rate by path/status, p95 latency by path, CPU per pod, memory per pod. Lives at `http://grafana.10.0.0.200.nip.io/d/podinfo-app/`.

The full JSON-as-code is in the `podinfo-dashboard.json` snippet in this repo's history — same pattern Phase 12 (ArgoCD) will use to put dashboards under git.

### HPA load test

Drive CPU from a controller terminal:

```bash
# 8 parallel curl loops in detached subshells (so they survive the parent shell)
for i in $(seq 1 8); do
  setsid bash -c "while true; do curl -s http://podinfo.10.0.0.200.nip.io/ > /dev/null; done" </dev/null >/dev/null 2>&1 &
done
```

Watch in another terminal:

```bash
kubectl get hpa -n podinfo -w
```

Expected timeline (verified during Phase 9 execution):

| Time | HPA CPU | Replicas | Event |
|---|---|---|---|
| t=0 | 11%/50% | 2 | baseline |
| t=15s | 102%/50% | 2 | load saturating both pods |
| t=33s | 62%/50% | **5** | scaled to max — `SuccessfulRescale` event |
| t=4m | 56%/50% | 5 | converged above 50% target |
| t=6m (after `pkill`) | 11%/50% | 5 | load gone; HPA stabilization window |
| t=10m | 7%/50% | **2** | scaled back to min — `All metrics below target` |

Stop the load:

```bash
pkill -9 -f "curl.*podinfo.10.0.0.200"
```

Final event log:

```bash
$ kubectl describe hpa podinfo -n podinfo | grep -A 10 Events
Events:
  Normal  SuccessfulRescale  …  New size: 5; reason: cpu resource utilization (percentage of request) above target
  Normal  SuccessfulRescale  …  New size: 4; reason: All metrics below target
  Normal  SuccessfulRescale  …  New size: 2; reason: All metrics below target
```

---

## Add podinfo to Homer

Append to `homer-config.yml`:

```yaml
- name: "Apps"
  icon: "fas fa-cubes"
  items:
    - name: "podinfo"
      icon: "fas fa-cube"
      subtitle: "Demo Go web app — first integration workload"
      tag: "live"
      url: "http://podinfo.10.0.0.200.nip.io"
      target: "_blank"
```

Apply and rollout per Phase 8.

---

## Troubleshooting

### HPA shows `cpu: <unknown>/50%` indefinitely

metrics-server isn't scraping the pods. Verify:

```bash
kubectl top pods -n podinfo
```

If this also returns `<unknown>`, restart metrics-server:

```bash
kubectl rollout restart deployment/metrics-server -n kube-system
```

### Prometheus targets list does not include podinfo

The kube-prometheus-stack Prometheus is configured to select all ServiceMonitors only because Phase 8's `values.yaml` sets `serviceMonitorSelectorNilUsesHelmValues: false`. If you skipped that flag, Prometheus only looks for ServiceMonitors with the chart's release label. Either re-install the chart with the flag set, or add the label to your podinfo ServiceMonitor.

### Curl loops keep running after the shell exits

`setsid bash -c "..."` deliberately detaches them. Use `pkill -9 -f "curl.*podinfo"` to clean up. Without `setsid`, the loops die when their parent shell exits.

### Pods land on the same worker despite anti-affinity

The chart uses `preferredDuringSchedulingIgnoredDuringExecution` (soft) — the scheduler will put both pods on the same node if the alternative would be unschedulable. Check capacity with `kubectl describe nodes` and `kubectl top nodes`.

---

## Done When

```text
✔ 2 podinfo pods Running, one on fast-skunk, one on fast-heron
✔ http://podinfo.10.0.0.200.nip.io/ returns JSON with hostname/version
✔ Prometheus targets list shows podinfo ServiceMonitor 2/2 up — without any chart-side config
✔ Custom dashboard /d/podinfo-app/ renders 7 panels with live data
✔ HPA scales 2 → 5 under load and 5 → 2 once load stops, with clean SuccessfulRescale events
✔ Homer has a "podinfo" tile under "Apps"
```

---

## Real-world skills demonstrated

| Skill | Where it applies in industry |
|---|---|
| **Helm chart with values overrides** | The standard pattern for deploying any third-party app on Kubernetes. Every production team's GitOps repo is hundreds of `values.yaml` files. |
| **HorizontalPodAutoscaler tuning** | The first scaling lever on any production workload. Choosing CPU vs memory vs custom-metrics targets is a recurring design decision at every capacity review. |
| **ServiceMonitor / PodMonitor for arbitrary workloads** | The kube-prometheus-stack way of saying "scrape my app's `/metrics`". Foundation of every Kubernetes-native observability rollout. |
| **Cross-namespace metric discovery** | Knowing that `serviceMonitorSelectorNilUsesHelmValues: false` is what makes Prometheus pick up workload ServiceMonitors automatically. Catches a lot of "why isn't my app being scraped" tickets. |
| **Pod anti-affinity (soft)** | Keeps replicas spread across nodes for resilience without making the deployment unschedulable when capacity is tight. Same pattern used for production stateful sets. |
| **HPA verification under load** | Demonstrating a working autoscale loop end-to-end is a recurring interview / on-call drill. The "2 → 5 → 2" sequence with `SuccessfulRescale` events is the receipt. |
| **Dashboard-as-code via Grafana HTTP API** | The bridge to GitOps observability — Phase 12 (ArgoCD) will pick this up. Real teams version-control dashboards. |
