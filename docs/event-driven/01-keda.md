---
id: keda
title: Phase 18 — KEDA
sidebar_position: 1
---

# Phase 18 — KEDA — Event-Driven Autoscaling

KEDA (Kubernetes Event-Driven Autoscaling) scales your pods based on real signals — queue depth, message count, HTTP request rate, Prometheus metrics, or a cron schedule. Standard Kubernetes HPA only scales on CPU/RAM — KEDA scales on **what actually matters**.

---

## How KEDA Extends HPA

```text
Standard HPA:
  CPU > 70% → scale up
  CPU < 30% → scale down
  Problem: CPU doesn't always reflect load (batch jobs, queues)

KEDA:
  RabbitMQ queue depth > 100 → scale up workers
  Queue empty → scale down to 0 (zero pods = zero cost)
  Cron: 08:00–18:00 → 5 replicas, nights → 1 replica
  Prometheus metric: requests/s > 500 → scale up
```

---

## Install KEDA

```bash
helm repo add kedacore https://kedacore.github.io/charts

helm install keda kedacore/keda \
  --namespace keda \
  --create-namespace
```

```bash
kubectl get pods -n keda
```

---

## ScaledObject — The Core Resource

A `ScaledObject` links a Deployment to a trigger:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-app-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: my-app            # the Deployment to scale
  minReplicaCount: 0        # can scale to zero!
  maxReplicaCount: 20
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc:9090
        metricName: http_requests_total
        threshold: "100"    # scale up when > 100 req/s
        query: sum(rate(http_requests_total{app="my-app"}[1m]))
```

---

## Example 1 — Scale on RabbitMQ Queue Depth

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: worker-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: job-worker
  minReplicaCount: 0
  maxReplicaCount: 10
  triggers:
    - type: rabbitmq
      metadata:
        host: amqp://rabbitmq.production.svc:5672
        queueName: job-queue
        queueLength: "5"    # 1 worker per 5 messages in queue
```

When the queue is empty → 0 workers (saves all resources).
When 50 messages → 10 workers processing in parallel.

---

## Example 2 — Cron Schedule

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: api-cron-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: api-deployment
  triggers:
    - type: cron
      metadata:
        timezone: "Europe/Paris"
        start: "0 8 * * 1-5"    # 08:00 Mon–Fri
        end:   "0 20 * * 1-5"   # 20:00 Mon–Fri
        desiredReplicas: "5"
    - type: cron
      metadata:
        timezone: "Europe/Paris"
        start: "0 20 * * 1-5"   # nights + weekends
        end:   "0 8 * * 1-5"
        desiredReplicas: "1"
```

---

## Example 3 — Scale ML Workers on Job Queue

Scale Kubeflow training workers based on pending jobs:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: ml-worker-scaler
  namespace: ai
spec:
  scaleTargetRef:
    name: ml-worker
  minReplicaCount: 0
  maxReplicaCount: 3        # max 3 workers (1 per node)
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc:9090
        metricName: ml_jobs_pending
        threshold: "1"
        query: ml_training_jobs_pending_total
```

When no ML jobs → 0 pods, freeing cluster resources for other workloads.

---

## ScaledJob — For Batch Processing

For jobs that should run once per event (not continuously):

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: image-processor
  namespace: production
spec:
  jobTargetRef:
    template:
      spec:
        containers:
          - name: processor
            image: harbor.local/platform/image-processor:latest
        restartPolicy: Never
  triggers:
    - type: rabbitmq
      metadata:
        queueName: images-to-process
        queueLength: "1"    # 1 job pod per message
```

One message = one pod = process and exit. Perfect for image processing, report generation, one-off tasks.

---

## KEDA + This Cluster

```text
Autoscale based on:
  ✔ n8n triggers webhook → scale API workers
  ✔ Airflow DAG enqueues jobs → scale batch processors
  ✔ Prometheus: request rate → scale web services
  ✔ Cron: business hours → full capacity, nights → minimal
  ✔ ML job queue → scale training workers
```

Combined with scale-to-zero, idle workloads consume no CPU/RAM — your 48 GiB is always available where it's needed.

---

## Done When

```text
✔ KEDA pods Running in keda namespace
✔ First ScaledObject created and monitoring triggers
✔ Deployment scales up when trigger fires
✔ Deployment scales to zero when idle
✔ kubectl get scaledobjects shows all scalers
```
