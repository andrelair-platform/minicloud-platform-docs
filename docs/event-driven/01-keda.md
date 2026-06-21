---
id: keda
title: Phase 17 — KEDA (event-driven autoscaling)
sidebar_position: 1
---

# Phase 17 — KEDA — Event-Driven Autoscaling

Phase 9 demonstrated **CPU-based** scaling with podinfo (HPA target: 50%
CPU). Phase 17 demonstrates the next step: **event-driven** scaling,
where pods come into existence because a *real signal* fires —
JetStream consumer lag, queue depth, message rate — rather than CPU.

The hero feature is **scale-to-zero**: an idle worker Deployment with
`replicas: 0`, costing zero RAM, becomes 5 pods in seconds when 50
messages arrive, drains the queue, scales back to 0. No manual button-
pushing, no wasteful idle pod, no cron schedule that doesn't match
actual load.

KEDA is paired with **NATS JetStream** in this phase (see
[Phase 17 — NATS](./nats)). The companion deliverable is the
`event-demo` workload deployed via the gitops repo.

---

## What KEDA does

KEDA is a Kubernetes-native operator that watches `ScaledObject` Custom
Resources. Each `ScaledObject` links a Deployment to one or more
**triggers** (NATS, Kafka, RabbitMQ, Prometheus, AWS SQS, cron, etc.).
When a trigger reports activity, KEDA creates a standard
`HorizontalPodAutoscaler` behind the scenes targeting that Deployment —
extending HPA to scale on signals beyond CPU/memory.

The minReplicaCount can be **0** (scale-to-zero), unlike standard HPA
which has a 1-replica floor.

```text
ScaledObject (CR)
    │
    │ KEDA operator watches
    ▼
   HPA (auto-generated)
    │
    │ targets
    ▼
   Deployment (replicas controlled by HPA)
```

---

## Architecture (this cluster)

```text
┌──────────────────────────────────────────────────────────────────┐
│  event-demo namespace (ArgoCD-managed via minicloud-gitops)      │
│                                                                  │
│  ┌────────────────────┐                ┌──────────────────────┐  │
│  │ ScaledObject       │ ──────────────▶│ HPA keda-hpa-...     │  │
│  │   echo-worker      │                │ min:0  max:5         │  │
│  │   trigger:         │                │ (auto-generated)     │  │
│  │   nats-jetstream   │                └──────────┬───────────┘  │
│  │   lagThreshold:10  │                           │              │
│  └─────────┬──────────┘                           ▼              │
│            │                            ┌─────────────────────┐  │
│            │ polls                      │ Deployment          │  │
│            │ every 5s                   │   echo-worker       │  │
│            ▼                            │   replicas: 0..5    │  │
│  ┌────────────────────┐                 └─────────────────────┘  │
│  │  KEDA operator     │                                          │
│  │  (keda namespace)  │                                          │
│  └─────────┬──────────┘                                          │
│            │ HTTP GET                                            │
│            ▼                                                     │
│  http://nats-headless.messaging:8222/jsz?...&consumers=true      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Install method | Helm chart `kedacore/keda` v2.19.0 | Standard install, auto-creates CRDs |
| `minReplicaCount` | **0** (scale-to-zero) | Demonstrates the canonical "no idle pods cost RAM" pattern |
| `maxReplicaCount` | 5 | Within cluster headroom; aligns with the 5-worker burst-test target |
| `pollingInterval` | 5s (default 30s) | Visible scale-up speed for demo; production typically uses 30s |
| `cooldownPeriod` | 60s (default 300s) | Faster scale-down for demo viewing; production keeps 300s to avoid thrashing |
| Trigger type | `nats-jetstream` | Matches Phase 17's NATS install; the canonical KEDA-NATS integration |
| Trigger metadata `natsServerMonitoringEndpoint` | **`nats-headless.messaging:8222`** | Important: KEDA's NATS scaler queries `<pod>.<endpoint>:8222` per pod (e.g., `nats-0.nats-headless.messaging:8222`). Requires a **headless** Service for per-pod DNS. The chart's plain `nats` Service only exposes 4222. |
| `lagThreshold` | 10 | 1 worker per 10 pending messages → queue of 50 → 5 workers (matches `maxReplicaCount`) |
| `activationLagThreshold` | 0 | Any pending message > 0 wakes from zero (vs. waiting for 10 to accumulate) |

---

## Pre-flight

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update kedacore
helm search repo kedacore/keda  # confirm v2.19+
```

---

## Install KEDA

`keda-values.yaml`:

```yaml
resources:
  operator:
    requests: { cpu: 50m, memory: 128Mi }
    limits:   { cpu: 500m, memory: 512Mi }
  metricServer:
    requests: { cpu: 50m, memory: 128Mi }
    limits:   { cpu: 500m, memory: 512Mi }
  webhooks:
    requests: { cpu: 25m, memory: 64Mi }
    limits:   { cpu: 100m, memory: 128Mi }

# Wire all 3 components into kube-prometheus-stack via ServiceMonitors.
# The release label is what kube-prometheus-stack's serviceMonitorSelector
# picks up (set in Phase 8 to be wide-open via serviceMonitorSelectorNilUsesHelmValues=false).
prometheus:
  metricServer:
    enabled: true
    serviceMonitor:
      enabled: true
      additionalLabels:
        release: kube-prometheus-stack
  operator:
    enabled: true
    serviceMonitor:
      enabled: true
      additionalLabels:
        release: kube-prometheus-stack
  webhooks:
    enabled: true
    serviceMonitor:
      enabled: true
      additionalLabels:
        release: kube-prometheus-stack
```

```bash
kubectl create namespace keda
helm install keda kedacore/keda -n keda -f keda-values.yaml --wait --timeout 5m

kubectl get pods -n keda
# 3 pods Running: keda-operator, keda-operator-metrics-apiserver, keda-admission-webhooks
```

---

## ScaledObject for the demo workload

`apps/event-demo.yaml` (ArgoCD Application) points at
`manifests/event-demo/02-scaledobject.yaml` in the gitops repo:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: echo-worker
  namespace: event-demo
spec:
  scaleTargetRef:
    name: echo-worker          # the Deployment to scale
  minReplicaCount: 0
  maxReplicaCount: 5
  pollingInterval: 5
  cooldownPeriod: 60
  triggers:
    - type: nats-jetstream
      metadata:
        natsServerMonitoringEndpoint: "nats-headless.messaging:8222"
        account: "$G"
        stream: JOBS
        consumer: echo-workers
        lagThreshold: "10"
        activationLagThreshold: "0"
```

---

## End-to-end burst test

The headline test: from a clean idle state (replicas=0), publish 50
messages and observe scale up + drain + scale to zero.

```bash
NATS_BOX=$(kubectl get pods -n messaging --no-headers | grep nats-box | awk '{print $1}')

# Idle: 0 pods, queue empty
kubectl get pods -n event-demo
# (no resources)

# Publish 50 messages in a tight loop inside the nats-box pod
T0=$(date +%s%3N)
kubectl exec -n messaging $NATS_BOX -- sh -c '
  for i in $(seq 1 50); do
    nats --server nats://nats.messaging:4222 pub jobs.echo "msg-$i" >/dev/null 2>&1
  done
'

# Watch scale-up
kubectl get scaledobject,pods -n event-demo -w
```

### Observed timeline

| Event | Time relative to T0 |
|---|---|
| 50 messages published | t+1.8s |
| **First worker pod Running** | **t+1.8s** (image cache-warm in containerd) |
| All 5 workers Running | t+33s |
| Queue fully drained | t+165s (~5s per message average × 5 parallel workers) |
| Scale-down begins (cooldown elapsed) | t+212s |
| All pods terminated | t+225s |

The "first pod Running in ~1.8s" number assumes the worker image is
already cached on the target node's containerd. On a true cold start
(image not yet on the node), add ~3-5s for the cache-warm pull through
Harbor's docker-hub proxy (Phase 16).

### What you can verify after the test

```bash
# Stream sequence advanced from 1 to 50 (or wherever previous tests left it)
nats stream info JOBS

# Consumer ack floor matches stream sequence — all messages were acked, no redeliveries
nats consumer info JOBS echo-workers
# num_pending: 0
# num_redelivered: 0
# ack_floor.consumer_seq == delivered.consumer_seq

# Workqueue retention: acked messages are physically removed (state.messages: 0)
```

---

## Other KEDA trigger types worth knowing

The same `ScaledObject` shape works with other triggers — useful when
adding more event-driven workloads later:

```yaml
# Cron-based scaling
- type: cron
  metadata:
    timezone: "Europe/Paris"
    start: "0 8 * * 1-5"
    end:   "0 20 * * 1-5"
    desiredReplicas: "5"

# Prometheus query (scale on any metric in Phase 8's Prometheus)
- type: prometheus
  metadata:
    serverAddress: http://kps-prometheus.monitoring:9090
    metricName: http_requests_per_second
    threshold: "100"
    query: sum(rate(podinfo_http_requests_total[1m]))

# Kafka lag (when we install Kafka in the data-layer phases)
- type: kafka
  metadata:
    bootstrapServers: kafka.data-platform:9092
    consumerGroup: my-app
    topic: events
    lagThreshold: "100"
```

---

## Verification (regression)

```bash
# 3 KEDA pods Running
kubectl get pods -n keda
# Expected: keda-admission-webhooks, keda-operator, keda-operator-metrics-apiserver — all 1/1 Running

# CRDs registered
kubectl get crd | grep keda.sh
# Expected at minimum: scaledobjects.keda.sh, scaledjobs.keda.sh, triggerauthentications.keda.sh

# event-demo ScaledObject Ready
kubectl get scaledobject -n event-demo
# Expected: READY=True, ACTIVE depends on whether messages are pending
```

---

## Done When

```text
✔ 3 KEDA pods Running in keda namespace
✔ ScaledObjects + ScaledJobs CRDs registered
✔ event-demo ScaledObject reports READY=True
✔ Burst test: 50 msg → first pod Running in <5s → 5 pods peak → drain → 0 pods
✔ Workqueue retention verified: acked messages physically removed
✔ Both KEDA and NATS metrics visible in Prometheus Targets
```

---

## Troubleshooting

### keda-operator ImagePullBackOff (imagePullPolicy: Always)

**Symptom:** `keda-operator` pod stuck in `ImagePullBackOff` for an extended period while the other two KEDA pods (`keda-admission-webhooks`, `keda-operator-metrics-apiserver`) run fine.

**Root cause:** The Helm chart sets `imagePullPolicy: Always` on the operator container. With `Always`, Kubernetes must contact the registry on every pod start — even if the image is already cached locally. If the registry is unreachable (Harbor proxy DNS glitch, ghcr.io rate limit, network blip), the pod refuses to start regardless of local cache state.

This is incorrect behaviour for a fixed version tag like `2.19.0`. The image content at a fixed tag never changes, so re-pulling on every start is pointless and creates a hard dependency on registry availability.

```
imagePullPolicy: Always  +  registry unreachable
        │
        ▼
Pod refuses to start — even though image is in containerd cache
        │
        ▼
ImagePullBackOff with exponential back-off (5s → 10s → 20s → 5m → 10m...)
```

**Diagnosis:**

```bash
# Confirm imagePullPolicy
kubectl get deploy -n keda keda-operator \
  -o jsonpath='{.spec.template.spec.containers[0].imagePullPolicy}'
# → Always  (wrong for a versioned tag)

# Find which node the pod is on
kubectl get pod -n keda -l app=keda-operator -o wide

# Check if image is in that node's containerd cache
ssh <node> "sudo -n crictl images | grep keda"
# If the image appears here, the pod COULD run — it's the pull policy blocking it

# Check what the pull failure actually says
kubectl describe pod -n keda keda-operator-<hash> | grep -A5 "Warning  Failed"
```

**Fix — two steps:**

Step 1: Change `imagePullPolicy` to `IfNotPresent` (use cache if available):

```bash
kubectl patch deployment -n keda keda-operator \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"keda-operator","imagePullPolicy":"IfNotPresent"}]}}}}'
```

Step 2: If the new pod lands on a node that doesn't have the image cached, copy it from the node that does:

```bash
# Export from the node that has it
ssh set-hog "sudo -n ctr -n k8s.io images export /tmp/keda-2.19.0.tar ghcr.io/kedacore/keda:2.19.0"

# Stream to all other nodes in parallel
ssh set-hog "cat /tmp/keda-2.19.0.tar" | ssh fast-skunk "sudo -n ctr -n k8s.io images import -" &
ssh set-hog "cat /tmp/keda-2.19.0.tar" | ssh fast-heron "sudo -n ctr -n k8s.io images import -" &
wait

# Delete stuck pods so deployment creates fresh ones against the local cache
kubectl delete pod -n keda -l app=keda-operator
```

Step 3: Verify all three pods are Running:

```bash
kubectl get pods -n keda
# keda-admission-webhooks-...         1/1  Running
# keda-operator-...                   1/1  Running   ← was broken
# keda-operator-metrics-apiserver-... 1/1  Running
```

**Why this is a Helm chart issue, not a cluster issue:**

`imagePullPolicy: Always` is appropriate for `latest` or mutable tags where the image content can change without the tag changing. For immutable versioned tags (`2.19.0`), `IfNotPresent` is correct — if the image is cached, use it. The KEDA chart uses `Always` by default; this can be overridden in `keda-values.yaml`:

```yaml
# Add to keda-values.yaml to prevent this on reinstall
image:
  keda:
    pullPolicy: IfNotPresent
  metricsApiServer:
    pullPolicy: IfNotPresent
  webhooks:
    pullPolicy: IfNotPresent
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Scale-to-zero** | The defining feature of "serverless on Kubernetes" — same pattern Knative, OpenFaaS, AWS Lambda use |
| **Event-driven autoscaling** | The next step after CPU-based HPA; required for any workload whose load doesn't correlate with CPU (queue workers, batch jobs, schedulers) |
| **`ScaledObject` declarative scaling** | KEDA's API surface; same shape on any cluster running KEDA — Bunq, Walmart, Microsoft Azure all use it in production |
| **NATS-headless service for per-pod metrics queries** | Real KEDA-NATS deployment knowledge: a regular ClusterIP doesn't give per-pod DNS; KEDA's scaler discovers individual JetStream cluster members |
| **`activationLagThreshold` for wake-from-zero** | Distinguishes "any work to do" (activation) from "should we add another worker" (scaling). Subtle but critical config. |
| **`pollingInterval` and `cooldownPeriod` tuning** | Demo settings (5s/60s) vs. production (30s/300s). Same trade-off every shop tunes. |
| **ServiceMonitor wiring across components** | KEDA exports metrics from 3 different deployments; each one's labels need to align with kube-prometheus-stack's selector |
