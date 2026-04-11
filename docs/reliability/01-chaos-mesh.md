---
id: chaos-mesh
title: Phase 21 — Chaos Mesh
sidebar_position: 1
---

# Chaos Mesh — Chaos Engineering & Resilience Testing

Chaos Mesh lets you deliberately inject failures into your cluster — kill pods, delay network traffic, fill disks, crash nodes — to verify your system actually recovers the way you designed it to.

---

## Why Chaos Engineering

```text
"Our system is resilient" means nothing without proof.

Without chaos testing:
  → You discover failure modes in production
  → Customers experience the downtime

With chaos testing:
  → You discover failure modes in controlled experiments
  → You fix the gaps before they become incidents
```

---

## What You Can Inject

| Experiment Type | Example |
|---|---|
| **PodChaos** | Kill random pods, crash containers |
| **NetworkChaos** | Add 200ms latency, 10% packet loss, partition nodes |
| **StressChaos** | CPU spike, memory pressure on a node |
| **IOChaos** | Disk read/write delays |
| **NodeChaos** | Shutdown a node (requires privileges) |
| **TimeChaos** | Skew the clock on a pod |
| **HTTPChaos** | Inject 500 errors, delay responses |

---

## Install Chaos Mesh

```bash
helm repo add chaos-mesh https://charts.chaos-mesh.org

helm install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --create-namespace \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/k3s/containerd/containerd.sock
```

Wait for pods:

```bash
kubectl get pods -n chaos-mesh
```

---

## Access the Dashboard

```bash
kubectl port-forward -n chaos-mesh svc/chaos-dashboard 2333:2333
```

Open: `http://localhost:2333`

Create an account on first launch.

---

## Experiment 1 — Kill Random Pod

Test that a deployment recovers automatically when a pod dies:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: kill-nginx-pod
  namespace: default
spec:
  action: pod-kill
  mode: one           # kill one pod at a time
  selector:
    namespaces:
      - default
    labelSelectors:
      "app": "nginx"
  scheduler:
    cron: "@every 2m"  # kill a pod every 2 minutes
```

```bash
kubectl apply -f pod-kill.yaml
kubectl get pods -n default --watch
# → Pod killed → k8s creates replacement → Ready
```

**Pass condition:** Pod is replaced within 30 seconds, service never goes down.

---

## Experiment 2 — Network Latency Between Nodes

Simulate a slow network link between fast-skunk and set-hog:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: node-latency
  namespace: default
spec:
  action: delay
  mode: all
  selector:
    nodes:
      - fast-skunk
  delay:
    latency: "200ms"
    jitter: "50ms"
    correlation: "25"
  direction: to
  target:
    selector:
      nodes:
        - set-hog
    mode: all
  duration: "5m"
```

**What to observe:** Does ArgoCD sync slow down? Does Prometheus miss scrapes? Do your apps timeout?

---

## Experiment 3 — Memory Pressure

Simulate a pod consuming too much memory:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: memory-stress
  namespace: default
spec:
  mode: one
  selector:
    namespaces:
      - default
    labelSelectors:
      "app": "my-app"
  stressors:
    memory:
      workers: 2
      size: "4GiB"
  duration: "3m"
```

**What to observe:** Does the OOMKiller kick in? Is the pod restarted? Do resource limits protect other workloads?

---

## Steady State Hypothesis

Before each experiment, define what "healthy" means:

```text
Hypothesis: "When one pod dies, the service stays up"

Probe:
  - HTTP GET http://10.0.0.200/api/health → must return 200
  - Response time < 500ms
  - Check every 5 seconds during experiment

Blast radius:
  - Only pods with label app=nginx
  - Only 1 pod killed at a time
  - Automatic rollback if probe fails
```

This structure (from the Chaos Engineering book) ensures you learn something and don't cause uncontrolled damage.

---

## GameDays

Schedule regular GameDays — planned chaos sessions with the whole team:

```text
Monthly GameDay format:
  1. Choose a failure scenario
  2. Define the steady state
  3. Run the experiment (Chaos Mesh)
  4. Observe metrics in Grafana
  5. Debrief: what broke, what held, what to fix
  6. Create tickets for gaps found
```

---

## Done When

```text
✔ Chaos Mesh pods Running
✔ Dashboard accessible
✔ First pod-kill experiment completed
✔ System recovered within SLO
✔ Grafana shows the anomaly and recovery
```
