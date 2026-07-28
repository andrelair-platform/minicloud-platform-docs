---
slug: high-availability-bare-metal-kubernetes
title: "Designing High Availability on Bare-Metal Kubernetes — Layer by Layer"
authors: [andre]
description: >
  HA on a self-managed k3s cluster is not one setting — it is six independent layers,
  each with a concrete trade-off. This post walks through every layer on minicloud,
  what was validated by a live chaos game day, and how the same concerns map to
  EKS, GKE, and AKS.
tags: [kubernetes, k3s, high-availability, bare-metal, platform-engineering, longhorn, argo-rollouts, nginx, metallb, chaos-engineering, eks, gke, aks]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

"High availability" is one of those terms that everyone agrees matters and almost nobody defines precisely. On a managed Kubernetes provider, you tick a checkbox for multi-AZ and move on. On a self-managed cluster, you make six independent architectural decisions, each with its own failure mode, trade-off, and operational cost.

This post documents every HA layer on **minicloud** — a 5-node k3s cluster on ThinkPad laptops — explains the reasoning behind each trade-off, and maps each layer to how EKS, GKE, and AKS solve the same problem.

{/* truncate */}

## The Cluster

Five machines:

| Node | IP | Role |
|------|----|------|
| `set-hog` | 10.0.0.2 | k3s control plane (ThinkPad X390) |
| `fast-skunk` | 10.0.0.4 | worker |
| `fast-heron` | 10.0.0.7 | worker |
| `star-kitten` | 10.0.0.8 | worker |
| `swift-mac` | 10.0.0.10 | worker + Longhorn storage (MacBook Pro 2012, Ubuntu 22.04) |

Every HA decision below was made for this specific context. The reasoning is transferable; the numbers are not.

---

## Layer 1 — Control Plane: Deliberately Single Node

This is the most important HA decision on the cluster, and the answer is: no HA at this layer.

`set-hog` runs the k3s API server, scheduler, controller-manager, and Kine/SQLite datastore. It is one ThinkPad. If it crashes, the control plane is gone until it reboots — roughly 90 seconds.

**What actually happens when the control plane goes down:**
- Running pods on all four workers **keep running**. kubelet is a local process; it does not need the API server to manage existing pods.
- No new scheduling. No Deployments roll out. No ConfigMaps update. No secrets rotate.
- Recovery is automatic when `set-hog` reboots and k3s starts.

**Why not HA control plane?** k3s HA requires `--cluster-init` on the first server node plus two additional server nodes with `--server`. That switches the datastore from Kine/SQLite to embedded etcd with Raft consensus across three nodes. For a 5-node cluster, three machines in control-plane role is a bad ratio — and the operational overhead of managing a Raft cluster is real. Given that control plane downtime does not take down running workloads and recovery takes 90 seconds, the trade-off is clear.

**What managed providers do instead:**
- **EKS:** API server replicated across multiple AZs. etcd is a multi-AZ cluster AWS manages entirely. Control plane goes down → you never notice.
- **GKE:** Same model. The control plane is so opaque that GKE Standard doesn't even charge for it separately; it's part of the cluster SLA.
- **AKS:** Same model. Azure manages the control plane HA; you pay only for worker VMs.

The managed approach eliminates this failure mode entirely. The cost on EKS is $0.10/hr ($73/month) before any workers — for the control plane alone. On minicloud, `set-hog` runs on hardware already owned.

---

## Layer 2 — Workers: Four Nodes, Cross-Node Distribution

All workload pods run on four workers. The k3s scheduler distributes replicas by default using `PodTopologySpread` semantics — multi-replica Deployments land on different nodes without explicit configuration.

**The swift-mac exception:** `swift-mac` is a MacBook Pro 2012. It has no IPMI, no BMC, no remote power-cycle capability (Apple SMC only responds to physical button presses). If the OS hangs, manual intervention is required. StatefulSets that require guaranteed automated recovery are pinned away from `swift-mac` using node affinity rules:

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: NotIn
              values: [swift-mac]
```

`swift-mac` runs stateless workloads and Longhorn storage replicas (where it adds capacity, not critical path availability).

**What managed providers do instead:** cloud worker nodes are VMs with full hypervisor-level power control. If an AWS EC2 instance hangs, the node group terminates and replaces it automatically. Node auto-repair is available on GKE (default on Autopilot). On bare-metal, hung nodes require human attention.

---

## Layer 3 — Applications: Replicas, PDBs, and Argo Rollouts

This is where most of the HA work lives. The control plane and storage layers define the ceiling; the application layer determines whether workloads actually survive failures within that ceiling.

### Replica Count

Production workloads run a minimum of 3 replicas, spread across workers. The number 3 is deliberate: it tolerates 1 pod failure and still serves traffic while the replacement starts. With 2 replicas, a pod kill plus a slow start leaves you at 1 replica — no redundancy.

### PodDisruptionBudgets

Every production workload has a PDB preventing Kubernetes from evicting more than one replica simultaneously during voluntary disruptions (node drains, cluster upgrades):

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: platform-demo-pdb
spec:
  minAvailable: 2        # at least 2 replicas must be Ready at all times
  selector:
    matchLabels:
      app: platform-demo
```

Without a PDB, the k3s upgrade drain could evict all three replicas from a node simultaneously, causing a brief outage. The PDB prevents this — the drain waits for a replacement to become Ready before evicting the next pod.

### Argo Rollouts: Zero-Downtime Deployments

Plain Kubernetes Deployments use `RollingUpdate` strategy, which provides basic HA during deploys. Production services on minicloud use **Argo Rollouts** for more control:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: platform-demo
spec:
  replicas: 3
  strategy:
    canary:
      stableService: platform-demo-stable
      canaryService: platform-demo-canary
      trafficRouting:
        nginx:
          stableIngress: platform-demo
      steps:
        - setWeight: 20      # send 20% to new version
        - pause: {}          # wait for analysis
        - setWeight: 50
        - pause: {duration: 60s}
        - setWeight: 100
      analysis:
        templates:
          - templateName: success-rate
        startingStep: 1
        args:
          - name: service-name
            value: platform-demo-canary
```

The key HA property: the stable replica set stays fully live throughout the rollout. A new version that fails its success-rate analysis is automatically rolled back — the stable set absorbs all traffic, and the canary is torn down. No human intervention needed, no outage window.

### What Phase 81 Chaos Game Day Proved

In Phase 81, three chaos experiments ran against production workloads:

**Experiment 1 — Pod kill (PodChaos):**
- Killed 1 of 3 `platform-demo` replicas
- NGINX EndpointSlice watch excluded the pod before kill completed
- Replacement pod: `Ready` in 16 seconds
- HTTP availability: **100%** (measured, not estimated)

**Experiment 2 — Database latency (NetworkChaos):**
- 200ms artificial delay on `backstage → postgresql` traffic
- Cold-path DB queries: +200ms latency (expected)
- Cached-path requests: unaffected
- Backstage remained functional throughout

**Experiment 3 — CPU stress (StressChaos):**
- 2 workers at 80% load on `platform-demo-staging` pods
- cgroup CPU limit (200m) throttled the stressor — node-level impact: zero
- HTTP p95 latency: stayed within SLO

These are measured results on real production workloads, not simulations on throwaway test services.

**What managed providers do instead:** cloud providers offer similar Deployment strategies natively (EKS Deployment, GKE Rollout), but Argo Rollouts adds traffic-weight control and metric-gated promotion that managed providers do not include out of the box. Argo Rollouts works identically on EKS/GKE/AKS — this is a workload-level pattern, not a provider-level one.

---

## Layer 4 — Storage: Longhorn Replication

Persistent storage HA is the hardest layer to get right on bare-metal. Cloud providers give you EBS Multi-AZ (EKS), Persistent Disk (GKE), or Azure Disk (AKS) — all with built-in replication handled by the storage backend.

On bare-metal, that replication is your responsibility. The answer is **Longhorn**: a cloud-native distributed block storage system that runs entirely inside Kubernetes.

### How Longhorn Replication Works

Each Longhorn PVC is configured with `numberOfReplicas: 2` (the default). Longhorn maintains two replica copies of the volume data on two separate nodes:

```
PVC (16 Gi)
├── Replica A → fast-heron  /var/lib/longhorn/replicas/...
└── Replica B → star-kitten /var/lib/longhorn/replicas/...
```

If `fast-heron` goes down, the volume degrades to Replica B (healthy). Kubernetes reschedules the pod to a node where Replica B is accessible. The volume comes back online. No data is lost.

If both `fast-heron` and `star-kitten` go down simultaneously, the volume is inaccessible. That is the failure mode `numberOfReplicas: 2` accepts. With 4 workers, simultaneous double-node failure is considered acceptable.

### swift-mac as Storage Node

`swift-mac` has the largest available disk in the cluster. Its Longhorn storage is used for capacity, but always with a replica on a ThinkPad worker — `swift-mac` is never the single point of storage for any volume.

### Longhorn HA During Upgrades

During a k3s node upgrade, the upgrade Plan drains the node. A draining node loses its Longhorn replica. Volumes temporarily degrade to 1 replica (still accessible, but no redundancy during drain). This is why upgrade Plans run with `concurrency: 1` — only one node drains at a time, keeping replica degradation to a minimum window.

**What managed providers do instead:**

| | Longhorn (bare-metal) | EBS (EKS) | Persistent Disk (GKE) | Azure Disk (AKS) |
|---|---|---|---|---|
| Replication | Software-defined across nodes | Hardware-level within AZ | Hardware-level, multi-zone option | Hardware-level within AZ |
| Multi-AZ | No (single site) | EBS Multi-Attach (limited) | Regional PD (available) | Zone-redundant disk (available) |
| Snapshot | Longhorn snapshots to MinIO/S3 | EBS snapshots to S3 | Persistent Disk snapshots | Azure Disk snapshots |
| Restore | Longhorn UI or PVC from snapshot | EBS restore to new volume | GKE volume restore | AKS restore |
| Operational cost | You manage replica health, node affinity, backup schedules | Zero — AWS manages it | Zero — Google manages it | Zero — Azure manages it |

The managed storage story is compelling: cloud provider disks replicate at the hardware layer, beneath Kubernetes entirely. The performance characteristics are guaranteed, the replication is invisible, and snapshots are one API call. The trade-off is cost ($0.10–$0.20/GB/month for managed SSDs) and that you're tied to the provider's storage abstraction.

---

## Layer 5 — Ingress and Network: NGINX DaemonSet + MetalLB

### NGINX as DaemonSet

The NGINX ingress controller runs as a **DaemonSet** — one pod per worker node. All four workers (`fast-skunk`, `fast-heron`, `star-kitten`, `swift-mac`) run an NGINX pod listening for traffic.

```
External traffic → 10.0.0.200 (MetalLB VIP) → any NGINX pod → target pod
```

If one worker goes down, its NGINX pod goes with it — but the remaining three workers' NGINX pods continue serving all routes. The VIP re-advertises within seconds.

### MetalLB Layer 2 Failover

MetalLB in L2 mode assigns `10.0.0.200` as the VIP for the cluster. In L2 mode, one node "owns" the VIP at any time and responds to ARP requests for that IP. The owning node is elected by MetalLB's speaker pods.

If the owning node fails:
1. ARP cache on the router expires (typically 30–60 seconds, configurable)
2. MetalLB speakers elect a new owner from remaining healthy nodes
3. The new owner starts responding to ARP for `10.0.0.200`
4. Traffic resumes

Failover time in practice: under 30 seconds. This is the weakest HA link in the network layer — ARP cache expiry is the bottleneck. BGP mode (MetalLB supports it) would give sub-second failover, but requires a BGP-capable router.

### NGINX EndpointSlice Watches

NGINX watches EndpointSlice objects for every Service. When a pod is killed (during chaos experiments, pod evictions, or upgrades), Kubernetes updates the EndpointSlice before the pod terminates. NGINX removes the pod from its upstream pool before any traffic reaches it.

This is why the Phase 81 pod-kill experiment showed 100% HTTP availability: NGINX had already stopped routing to the killed pod by the time the kill signal landed.

### Cloudflare Tunnel: Public HA

Public services (`backstage.devandre.sbs`, `homer.devandre.sbs`, etc.) go through a Cloudflare Tunnel running as systemd on the controller. Cloudflare's network handles global load balancing and DDoS protection upstream of the cluster. The tunnel itself is a single point of failure at the controller — but:

- `cloudflared` runs with `Restart=always` and `StartLimitIntervalSec=0`
- Controller reboots recover the tunnel automatically
- Cloudflare's edge caches recent responses, absorbing brief tunnel interruptions for static content

**What managed providers do instead:**

- **EKS:** AWS Load Balancer Controller provisions ALBs directly from Ingress objects. Multi-AZ, auto-scaling, native TLS termination at the load balancer layer. MetalLB and NGINX DaemonSet complexity disappears.
- **GKE:** GKE Ingress provisions a Google Cloud Load Balancer. Global HTTP(S) load balancing, Anycast IPs, Cloud Armor WAF integration — all from a single Ingress annotation.
- **AKS:** Azure Load Balancer or Application Gateway via the AGIC controller. Comparable model to GKE.

The managed approach moves load balancing entirely outside Kubernetes — the load balancer itself has provider-grade HA, not pod-grade HA. The trade-off is cost (ALB pricing, GLB pricing) and provider lock-in on the load balancer layer.

---

## Layer 6 — Observability: HA for the HA Stack

An HA architecture you cannot observe is not an HA architecture — it is a guess. The observability stack is what turns the above layers into something measurable.

**What runs:**
- **Prometheus + Grafana:** cluster and application SLOs, node resource dashboards, custom `ChaosGameDayActive` alert
- **Loki:** log aggregation from all 5 nodes via OTel Collector (DaemonSet), with Promtail as the collection agent
- **Tempo:** distributed tracing for instrumented services (platform-demo, backstage)
- **AlertManager:** routes alerts to notification channels with inhibit rules to suppress known-false-positives during chaos testing

**The inhibit rule that makes chaos testing honest:**

```yaml
inhibit_rules:
  - source_matchers: ['alertname = "ChaosGameDayActive"']
    target_matchers: ['alertname =~ "KubePodCrashLooping|KubePodNotReady"']
```

When a chaos experiment is running, `ChaosGameDayActive` fires (chaos controller metrics show `status=Injecting`). This inhibits `KubePodCrashLooping` and `KubePodNotReady` alerts — so intentional pod kills don't flood Slack with false alerts. When the experiment ends, inhibition lifts and the alerting resumes normal operation.

**What managed providers do instead:**
- EKS: CloudWatch Container Insights, EKS add-on metrics, AWS Managed Grafana (paid)
- GKE: Cloud Monitoring with GKE integration, Cloud Logging
- AKS: Azure Monitor for Containers, Log Analytics workspace

Managed observability is faster to start (a few clicks vs. helm charts and ServiceMonitors) but less flexible — you can't add custom Prometheus rules or tune the alert inhibition logic without significant workarounds. On bare-metal, you own the full observability pipeline: more work, full control.

---

## The Complete HA Map

| Layer | minicloud decision | Failure mode accepted | Managed provider equivalent |
|---|---|---|---|
| **Control plane** | Single `set-hog` | 90s scheduling gap on reboot | Multi-AZ, provider-managed, invisible |
| **Datastore** | Kine/SQLite, nightly backup | ~23h RPO | etcd with sub-minute replication |
| **Workers** | 4 nodes, `swift-mac` isolated for StatefulSets | `swift-mac` hang = manual recovery | Auto-repair, VM-level power control |
| **Pods** | 3 replicas, PDB, Argo Rollouts canary | — | Same patterns apply on managed k8s |
| **Storage** | Longhorn 2-replica volumes | Double-node loss = volume inaccessible | Provider disk with hardware replication |
| **Ingress** | NGINX DaemonSet + MetalLB L2 | ARP cache expiry = ~30s VIP failover | Provider ALB/GLB, sub-second failover |
| **Observability** | Prometheus + Loki + Tempo + AlertManager | You operate the stack | Managed CloudWatch / Cloud Monitoring |

---

## What This Teaches That Managed Kubernetes Doesn't

Running HA on bare-metal forces you to understand each layer independently because each one can fail independently.

On EKS, you set `--node-count 3` and get worker redundancy, storage replication, load balancer failover, and control plane HA all at once — from a single API call. The system works, the failure modes are rare, and you never have to think about MetalLB ARP cache expiry or Longhorn replica count during node drains.

What you lose: the mental model of *why* it works. When something does go wrong on a managed cluster — and things do go wrong — engineers who only know the "tick the HA checkbox" path struggle to diagnose whether the failure is at the control plane layer, the storage layer, or the network layer.

On bare-metal, you cannot avoid building that mental model. The six layers above are not abstractions. They are decisions I made, configured, tested with live chaos experiments, and documented. Each one maps directly to a concept that appears in production managed Kubernetes incidents.

The same Argo Rollout that protects production deployments on minicloud works identically on EKS. The same PDB that blocks the k3s upgrade drain from evicting all replicas works identically on GKE. The same Prometheus inhibit rule that suppresses false alerts during chaos testing works identically on AKS.

The difference is that on bare-metal, you cannot skip the understanding to get to the result.
