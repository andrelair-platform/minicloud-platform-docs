---
id: nats
title: Phase 17 — NATS (HA message broker + JetStream)
sidebar_position: 2
---

# Phase 17 — NATS — High-Performance Message Broker

NATS is the message broker half of Phase 17. It's deployed as a
**3-replica HA cluster** (one server per node), with **JetStream**
enabled and persisted on Longhorn. The broker drives the demo
KEDA-scaled worker (see [Phase 17 — KEDA](./keda)) and is wired into
Phase 8's Prometheus for observability.

After this phase the cluster has its first piece of true async
infrastructure: services can publish events without knowing who
consumes them, durable streams survive pod restarts, consumer lag
becomes a first-class autoscaling signal.

---

## Why NATS (vs RabbitMQ, vs Kafka)

| | NATS + JetStream | RabbitMQ | Kafka |
|---|---|---|---|
| Latency | < 1ms | ~5ms | ~10ms |
| Memory baseline | ~100 MiB per replica | ~300 MiB | ~1 GiB+ |
| Persistence | JetStream (built-in, file-store) | classic + streams plugin | core feature, segments |
| Topology | mesh, no zk/etcd dependency | clustered + queue mirroring | requires zookeeper or KRaft |
| Best fit | Microservices pub/sub + durable streams | Enterprise queues | Log streaming, big data |

For our 48 GiB cluster, NATS is the cheapest broker that still gives us
durable streams. Kafka would consume ~3 GiB just to run; RabbitMQ has
heavier memory + clustering overhead. NATS gives 90% of what we need
at 10% of the cost.

---

## Architecture

```text
                              ┌──────────────────────────────────────┐
                              │  messaging namespace                 │
                              │                                      │
                              │   nats-0 (set-hog)    ◀──┐           │
                              │   nats-1 (fast-skunk) ◀──┼─ raft     │
                              │   nats-2 (fast-heron) ◀──┘  cluster  │
                              │   port 4222 (NATS protocol)          │
                              │   port 6222 (cluster routing)        │
                              │   port 8222 (monitoring HTTP)        │
                              │                                      │
                              │   each pod: 5 GiB JetStream PVC      │
                              │             on Longhorn (3× replica) │
                              │                                      │
                              │   nats-box (utility pod, has CLI)    │
                              └──────────────────────────────────────┘
                                                │
                                                │ via Ingress + cert-manager TLS
                                                ▼
                              https://nats.10.0.0.200.nip.io
                              (read-only monitoring UI: streams, consumers, RAFT state)
```

JetStream's `R=3` replication × Longhorn's 3-replica RWO storage =
each message physically stored 9× across the cluster. Acceptable for
demo workloads; in a real production scenario you'd reduce one of those
to avoid replication squared.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Install method | Helm chart `nats/nats` v2.12.6 | Official chart, well-maintained, JetStream-native config |
| Replica count | **3** (one per node) | Matches our 3-node cluster; demonstrates HA broker pattern |
| JetStream persistence | File-store, 5 GiB PVC per replica on Longhorn | 5 GiB is plenty for our demo (10 GiB chart default is overkill) |
| Resources per pod | 50m/128Mi requests, 500m/512Mi limits | Modest; NATS is intentionally lightweight |
| Monitoring port | 8222 (HTTP) — exposed via Ingress for read-only UI | Read-only by design; sensitive operations require admin auth (Phase 18 Vault will rotate) |
| Prometheus integration | `promExporter` sidecar on port 7777 + PodMonitor | Phase 8's serviceMonitorSelectorNilUsesHelmValues=false picks up the PodMonitor automatically |
| Stream config (JOBS) | `R=3`, `workqueue` retention, `discard old` | WorkQueue means acked messages are physically removed — keeps storage bounded and gives KEDA accurate lag metrics |
| Consumer config (echo-workers) | Pull mode, explicit ack, 30s ack-wait, max-deliver=3 | Standard pull pattern; messages redeliver on worker timeout |

---

## Pre-flight

```bash
helm repo add nats https://nats-io.github.io/k8s/helm/charts/
helm repo update nats
helm search repo nats/nats  # confirm v2.12+
```

---

## Install

`nats-values.yaml`:

```yaml
config:
  cluster:
    enabled: true
    replicas: 3
  jetstream:
    enabled: true
    fileStore:
      enabled: true
      pvc:
        enabled: true
        size: 5Gi
        storageClassName: longhorn
  monitor:
    enabled: true
    port: 8222

promExporter:
  enabled: true
  port: 7777
  podMonitor:
    enabled: true
    additionalLabels:
      release: kube-prometheus-stack

container:
  resources:
    requests: { cpu: 50m,  memory: 128Mi }
    limits:   { cpu: 500m, memory: 512Mi }
```

```bash
kubectl create namespace messaging
helm install nats nats/nats -n messaging -f nats-values.yaml --wait --timeout 5m
```

Expected:

```bash
$ kubectl get pods -n messaging
NAME                        READY   STATUS    RESTARTS   AGE
nats-0                      3/3     Running   0          1m
nats-1                      3/3     Running   0          1m
nats-2                      3/3     Running   0          1m
nats-box-...                1/1     Running   0          1m

$ kubectl get pvc -n messaging
nats-js-nats-0    Bound   ...   5Gi   RWO   longhorn
nats-js-nats-1    Bound   ...   5Gi   RWO   longhorn
nats-js-nats-2    Bound   ...   5Gi   RWO   longhorn
```

The `3/3` containers per pod are: nats-server, prom-exporter sidecar,
config-reloader.

---

## NATS UI Ingress (TLS via cert-manager)

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: nats-tls
  namespace: messaging
spec:
  secretName: nats-tls
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
  dnsNames: [nats.10.0.0.200.nip.io]
  duration: 2160h
  renewBefore: 720h
  privateKey: { algorithm: ECDSA, size: 256 }
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nats-monitor
  namespace: messaging
  annotations:
    nginx.org/redirect-to-https: "true"
spec:
  ingressClassName: nginx
  tls:
    - hosts: [nats.10.0.0.200.nip.io]
      secretName: nats-tls
  rules:
    - host: nats.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: nats-monitor      # custom Service we create below
                port: { number: 8222 }
```

The chart's headless Service `nats-headless` exposes 8222 but doesn't
load-balance. We create a **regular ClusterIP Service** for the Ingress:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nats-monitor
  namespace: messaging
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: nats
    app.kubernetes.io/instance: nats
    app.kubernetes.io/component: nats     # CRITICAL: filters out nats-box pods
  ports:
    - { name: monitor, port: 8222, targetPort: 8222 }
```

> **The selector gotcha**: `app.kubernetes.io/name: nats` matches both the
> NATS server pods AND the nats-box utility pod. Adding `component: nats`
> filters to just the server pods (which are the only ones actually
> listening on 8222). Without this, ~25% of monitoring requests
> connection-refuse.

---

## Create the JOBS stream + echo-workers consumer

```bash
NATS_BOX=$(kubectl get pods -n messaging --no-headers | grep nats-box | awk '{print $1}')

# Stream: workqueue retention, R=3, file-storage, 1-day max retention
kubectl exec -n messaging $NATS_BOX -- nats --server nats://nats.messaging:4222 \
  stream add JOBS \
    --subjects 'jobs.>' \
    --retention work \
    --storage file \
    --replicas 3 \
    --discard old \
    --max-msgs=-1 \
    --max-bytes=-1 \
    --max-age=24h \
    --defaults

# Pull consumer with explicit ack
kubectl exec -n messaging $NATS_BOX -- nats --server nats://nats.messaging:4222 \
  consumer add JOBS echo-workers \
    --pull \
    --filter 'jobs.echo' \
    --ack explicit \
    --max-deliver=3 \
    --replay instant \
    --deliver all \
    --wait 30s \
    --defaults
```

---

## End-to-end demo

The same end-to-end timeline as in [Phase 17 — KEDA](./keda):

```bash
T0=$(date +%s%3N)
kubectl exec -n messaging $NATS_BOX -- sh -c '
  for i in $(seq 1 50); do
    nats --server nats://nats.messaging:4222 pub jobs.echo "msg-$i" >/dev/null 2>&1
  done
'

# Watch:
kubectl get scaledobject,pods -n event-demo -w
```

| Phase | Time |
|---|---|
| 50 messages published | ~1.8s |
| First worker Running | t+1.8s (image cache-warm) |
| All 5 workers Running | t+33s |
| Queue drained | t+165s |
| All pods terminated | t+225s |

---

## Verification

```bash
# 3 NATS server pods + nats-box
kubectl get pods -n messaging

# Stream + consumer healthy
kubectl exec -n messaging $NATS_BOX -- nats --server nats://nats.messaging:4222 \
  stream info JOBS | grep -E "Replicas|Cluster|Leader|State"

# UI reachable
curl --cacert ~/minicloud-ca.crt https://nats.10.0.0.200.nip.io/healthz
# {"status":"ok"}
```

---

## Done When

```text
✔ 3 NATS server pods Running, one per node
✔ JetStream cluster healthy (Stream JOBS replicated to all 3 NATS pods)
✔ /healthz returns ok via the TLS Ingress
✔ Consumer echo-workers visible in NATS UI under stream JOBS
✔ Phase 8 Prometheus picks up nats_* metrics (via PodMonitor)
✔ KEDA's nats-jetstream scaler can reach :8222 on each pod via the headless service
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **NATS HA cluster (R=3) with JetStream** | The canonical "lightweight broker" deployment shape. Same recipe at every shop running NATS. |
| **JetStream WorkQueue retention** | Right-sized retention policy for queue-style workloads. WorkQueue auto-deletes acked messages, keeping storage bounded. |
| **Pull consumer with explicit ack** | The right primitive for backend workers — workers control their own pacing, redeliveries handle worker crashes |
| **Service selector specificity** | The `app.kubernetes.io/component=nats` filter to exclude nats-box from the monitoring Service is the kind of detail real Helm-chart consumers learn the hard way |
| **Headless Service for per-pod KEDA queries** | KEDA's nats-jetstream scaler discovers individual pods via DNS — needs a headless Service. Real production knowledge that's not in any tutorial. |
| **Per-pod metrics + cluster-wide Service** | The chart provides both — knowing which is for what (KEDA wants headless; the Ingress wants regular ClusterIP) is the senior shape |
| **Replication-on-replication awareness** | JetStream R=3 × Longhorn R=3 = 9 copies of every message. Documenting this trade-off is more credible than ignoring it. |
