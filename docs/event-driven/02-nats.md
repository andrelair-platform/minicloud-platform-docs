---
id: nats
title: Phase 18 — NATS
sidebar_position: 2
---

# Phase 18 — NATS — High-Performance Message Broker

NATS is a lightweight, high-performance message broker for async communication between services. It replaces point-to-point HTTP calls with a pub/sub model — services publish events without knowing who consumes them. This decouples your services and makes the system far more resilient.

---

## NATS vs RabbitMQ vs Kafka

| | NATS | RabbitMQ | Kafka |
|---|---|---|---|
| Latency | < 1ms | ~5ms | ~10ms |
| Throughput | Very high | High | Very high |
| Complexity | Simple | Moderate | Complex |
| Persistence | JetStream (built-in) | Yes | Yes |
| Protocol | NATS | AMQP | Kafka protocol |
| Best for | Microservices, IoT, fast pub/sub | Enterprise queues | Log streaming, big data |

**NATS is the right choice for this cluster** — simple, fast, low resource usage, works perfectly with KEDA.

---

## Core Patterns

```text
Pub/Sub:
  Publisher → subject: "events.deploy" → Subscriber A
                                       → Subscriber B
  (fire and forget, any number of consumers)

Request/Reply:
  Client → "rpc.process" → Worker
  Worker → response → Client
  (synchronous request over async transport)

JetStream (persistence):
  Publisher → stream: "JOBS" → persisted
  Consumer pulls at own pace → at-least-once delivery
  (for critical events that must not be lost)
```

---

## Deploy NATS via Helm

```bash
helm repo add nats https://nats-io.github.io/k8s/helm/charts/

helm install nats nats/nats \
  --namespace messaging \
  --create-namespace \
  --set config.cluster.enabled=true \
  --set config.cluster.replicas=3 \
  --set config.jetstream.enabled=true \
  --set config.jetstream.fileStore.pvc.enabled=true \
  --set config.jetstream.fileStore.pvc.storageClassName=longhorn \
  --set config.jetstream.fileStore.pvc.size=10Gi
```

3-replica cluster matches your 3-node setup — one NATS server per node.

---

## Verify

```bash
kubectl get pods -n messaging

# Install NATS CLI
curl -sf https://binaries.nats.dev/nats-io/natscli/nats@latest | sh

# Test
nats pub test.subject "hello" --server nats://10.0.0.x:4222
nats sub test.subject --server nats://10.0.0.x:4222
```

---

## Example — Microservice Events

```python
# service: deployment-tracker (Python)
import asyncio
import nats

async def main():
    nc = await nats.connect("nats://nats.messaging.svc:4222")

    # Publish a deployment event
    await nc.publish(
        "events.deployment.completed",
        b'{"app": "my-api", "version": "v1.2", "env": "production"}'
    )

    # Subscribe to deployment events
    async def handler(msg):
        import json
        data = json.loads(msg.data)
        print(f"Deployed: {data['app']} {data['version']}")

    await nc.subscribe("events.deployment.*", cb=handler)
    await asyncio.sleep(10)
    await nc.close()

asyncio.run(main())
```

---

## Example — JetStream Queue for Job Processing

```python
import asyncio
import nats
from nats.js.api import StreamConfig

async def main():
    nc = await nats.connect("nats://nats.messaging.svc:4222")
    js = nc.jetstream()

    # Create a persistent stream
    await js.add_stream(StreamConfig(
        name="JOBS",
        subjects=["jobs.>"],
        retention="workqueue"    # messages consumed once
    ))

    # Publish a job
    ack = await js.publish("jobs.image-process", b'{"image_id": "abc123"}')
    print(f"Published, seq: {ack.seq}")

    # Worker pulls jobs
    psub = await js.pull_subscribe("jobs.image-process", "workers")
    msgs = await psub.fetch(10)
    for msg in msgs:
        print(f"Processing: {msg.data}")
        await msg.ack()

asyncio.run(main())
```

---

## NATS + KEDA Integration

KEDA can scale workers based on NATS JetStream consumer lag:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: job-worker-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: job-worker
  minReplicaCount: 0
  maxReplicaCount: 10
  triggers:
    - type: nats-jetstream
      metadata:
        natsServerMonitoringEndpoint: "nats.messaging.svc:8222"
        account: "$G"
        stream: JOBS
        consumer: workers
        lagThreshold: "10"    # 1 worker per 10 pending messages
```

---

## Event Architecture for This Platform

```text
Services publish events → NATS subjects

events.deployment.*   → consumed by: n8n (notifications), Temporal (saga)
events.ml.completed   → consumed by: MLflow (register), Slack (notify)
events.node.ready     → consumed by: Ansible trigger, Homer refresh
jobs.training.*       → consumed by: Kubeflow workers (KEDA-scaled)
jobs.image-process.*  → consumed by: image processors (KEDA-scaled)
alerts.cluster.*      → consumed by: n8n (create incident), Grafana
```

This is the backbone of a real event-driven platform — no service calls another directly.

---

## NATS Monitoring UI

```bash
kubectl port-forward -n messaging svc/nats 8222:8222
```

Open: `http://localhost:8222` — shows connections, streams, consumers, message rates.

---

## Done When

```text
✔ NATS cluster Running (3 replicas, one per node)
✔ JetStream enabled with Longhorn persistence
✔ Test pub/sub working via NATS CLI
✔ First service publishing events to a subject
✔ KEDA ScaledObject scaling on NATS consumer lag
```
