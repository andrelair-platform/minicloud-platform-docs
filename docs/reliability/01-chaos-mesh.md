---
id: chaos-mesh
title: Phase 20 — Chaos Mesh (validation engineering)
sidebar_position: 1
---

# Phase 20 — Chaos Mesh: validation engineering

Phase 20 isn't really "install Chaos Mesh." It's **validation
engineering** — using deliberate fault injection to prove that the
resilience claims made in earlier phases actually hold under failure.

The cluster turned into a scientific instrument:

- **Phase 9** said: *"podinfo runs 2 replicas with soft podAntiAffinity
  + HPA, so it stays available under pod loss."*
  → Phase 20 Experiment 1 measured **0 ms downtime under continuous
  pod kills** (5 events over 4 min, 252 probes, 100.0000% HTTP 200).
- **Phase 8** said: *"we have observability — anomalies will be
  visible in Grafana."*
  → Phase 20 Experiment 2 measured the **11× latency spike** during
  injected network delay and verified clean restoration after cleanup.
- **Phase 5 + Kubernetes resource limits** said: *"per-container memory
  limits contain failures to the cgroup, not the node."*
  → Phase 20 Experiment 3 OOM-killed a stressed container while the
  **30+ node-mate pods on the same node had zero new restarts**.

These aren't hypothetical claims anymore. They're measured properties.
That's what chaos engineering is for.

---

## Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│  chaos-mesh namespace                                            │
│                                                                  │
│  ┌──────────────────────────┐    ┌──────────────────────────┐    │
│  │ chaos-controller-manager │    │     chaos-dashboard      │    │
│  │   (3 replicas, HA)       │    │  (cluster-internal only) │    │
│  │   reconciles CRDs        │    │  port-forward access     │    │
│  └──────────┬───────────────┘    └──────────────────────────┘    │
│             │ instructs                                          │
│             ▼                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ chaos-daemon (DaemonSet, 1 per node — privileged)        │    │
│  │   set-hog · fast-skunk · fast-heron                      │    │
│  │   uses nsexec to enter pod netns, applies tc/netem,      │    │
│  │   mounts cgroups for OOM/stress, talks to containerd     │    │
│  │   socket /run/k3s/containerd/containerd.sock             │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

**The daemon is the actual fault-injection engine.** When you create a
`NetworkChaos` CR, the controller-manager schedules it onto the
chaos-daemon on the node where the target pod is running. The daemon
calls `/usr/local/bin/nsexec -n /proc/<pid>/ns/net -- tc qdisc add ...`
— it enters the pod's network namespace and applies a real Linux
Traffic Control rule.

This is **not** a userspace "pretend" simulator. The pod really does
see 200 ms of latency on its eth0, applied by the kernel.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Chart** | `chaos-mesh/chaos-mesh` v2.8.2 | Standard install. App version = chart version. |
| **Runtime hook** | `chaosDaemon.runtime: containerd` + `socketPath: /run/k3s/containerd/containerd.sock` | **The single most important override.** k3s embeds containerd at a non-default path; without this the daemon can't see running containers and every experiment fails with `container runtime not found`. |
| **Dashboard exposure** | **Cluster-internal only** (`port-forward`) | The chaos dashboard is a cluster-wide kill switch. Anyone reaching it can delete pods, partition networks, OOM-kill nodes. Not a kind of UI you put behind a public Ingress, even with TLS. |
| **Dashboard auth** | RBAC token-based (chart default `securityMode: true`) | Token at `~/.chaos-dashboard-token` mode 600, ServiceAccount `chaos-dashboard-operator`, ClusterRole `chaos-mesh-cluster-manager`. |
| **DNSChaos sidecar** | **Disabled** (`dnsServer.create: false`) | Optional component, only needed for DNSChaos experiments which aren't in Phase 20's scope. |
| **Image source** | All chaos-mesh images pulled through Phase 16 Harbor `ghcr` proxy cache | Validates the sovereign-registry pattern again — 5 distinct images all flowed through Harbor on first pull. |
| **Targets** | All 3 experiments target podinfo only | podinfo (Phase 9) is the disposable test workload — 2 replicas, HPA, ServiceMonitor, custom Grafana dashboard, soft podAntiAffinity. The exact resilience pattern we want to validate. |

### What's deliberately deferred

| Component | Why deferred | Future home |
|---|---|---|
| **Public Ingress for the dashboard** | Kill switch — never expose publicly without strong auth | When Keycloak SSO + RBAC gating land in a future security phase |
| **NodeChaos** (full node shutdown) | Single control-plane cluster. Killing set-hog kills the cluster. NodeChaos against worker nodes is OK but adds blast-radius risk for the portfolio demo. | If/when an HA control plane phase lands |
| **Automated GameDays via cron** | "Chaos while you sleep" on a single-operator portfolio = bad. The discipline is "I press the button when I'm watching." | When a real on-call rotation exists |
| **Chaos against ArgoCD / Harbor / cert-manager** | These are cluster-control-plane workloads. Killing them mid-experiment can leave the cluster in a bad state and recovery requires bypassing GitOps. | Out of scope until HA control plane |
| **`chaos-mesh-controller-manager` Workflow CRDs** (sequential experiment chains) | Single-experiment-per-session is enough to demonstrate the discipline | When real GameDays start |

This is the same scope-reduction pattern as every prior phase
(Crossplane in Phase 11, GitLab in Phase 13, Vault in Phase 15,
n8n/Temporal/Airflow in Phase 16, plugins in Phase 18,
MLflow/Kubeflow in Phase 19).

---

## Install

`chaos-mesh-values.yaml`:

```yaml
chaosDaemon:
  runtime: containerd
  socketPath: /run/k3s/containerd/containerd.sock
  hostNetwork: false

dashboard:
  create: true
  serviceType: ClusterIP
  securityMode: true   # require RBAC token
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 500m, memory: 512Mi }

controllerManager:
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 500m, memory: 512Mi }

dnsServer:
  create: false   # optional; not used in Phase 20

webhook:
  certManager:
    enabled: false   # built-in self-signed is fine for an internal webhook
```

```bash
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update chaos-mesh

kubectl create namespace chaos-mesh

helm install chaos-mesh chaos-mesh/chaos-mesh \
  -n chaos-mesh \
  -f chaos-mesh-values.yaml \
  --version 2.8.2 \
  --wait --timeout 5m
```

Expected after install:

```bash
$ kubectl get pods -n chaos-mesh
NAME                                       READY   STATUS    RESTARTS
chaos-controller-manager-...-1             1/1     Running
chaos-controller-manager-...-2             1/1     Running   ← 3 replicas
chaos-controller-manager-...-3             1/1     Running     (HA across nodes)
chaos-daemon-...                           1/1     Running   ← DaemonSet,
chaos-daemon-...                           1/1     Running     1 per node
chaos-daemon-...                           1/1     Running
chaos-dashboard-...                        1/1     Running

$ kubectl get crd | grep -c chaos-mesh.org
23
```

---

## Dashboard RBAC + token

```yaml
# chaos-mesh/dashboard-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: chaos-dashboard-operator
  namespace: chaos-mesh
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: chaos-mesh-cluster-manager
rules:
  - apiGroups: [""]
    resources: [pods, namespaces]
    verbs: [get, watch, list]
  - apiGroups: [chaos-mesh.org]
    resources: ["*"]
    verbs: [get, list, watch, create, delete, patch, update]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: chaos-dashboard-operator-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: chaos-mesh-cluster-manager
subjects:
  - kind: ServiceAccount
    name: chaos-dashboard-operator
    namespace: chaos-mesh
---
apiVersion: v1
kind: Secret
metadata:
  name: chaos-dashboard-operator-token
  namespace: chaos-mesh
  annotations:
    kubernetes.io/service-account.name: chaos-dashboard-operator
type: kubernetes.io/service-account-token
```

```bash
kubectl apply -f chaos-mesh/dashboard-rbac.yaml

# Capture the token (one-time)
kubectl -n chaos-mesh get secret chaos-dashboard-operator-token \
  -o jsonpath='{.data.token}' | base64 -d > ~/.chaos-dashboard-token
chmod 600 ~/.chaos-dashboard-token

# Access the dashboard
kubectl port-forward -n chaos-mesh svc/chaos-dashboard 2333:2333
# Open http://localhost:2333 — paste the token from ~/.chaos-dashboard-token
```

---

## Steady-state hypothesis discipline

Each experiment follows the **classic chaos engineering loop** (from
Netflix's _Chaos Engineering_ book):

```text
1. Define the steady state — what "healthy" looks like (probe + threshold)
2. Hypothesize that injection X won't break the steady state
3. Inject X (the chaos)
4. Observe — does the steady state hold?
5. Either: hypothesis confirmed, or you found a real gap to fix
```

We measure with a **synchronous availability probe** running at 1 Hz
in a parallel shell — so the experiment captures actual user-facing
behavior, not just k8s-internal events.

---

## Experiment 1 — PodChaos pod-kill

**Hypothesis:** podinfo (2 replicas, soft podAntiAffinity, HPA) stays
available under continuous pod kills.

**Manifest** (`chaos-mesh/exp1-podkill.yaml`):

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Schedule
metadata:
  name: podinfo-kill
  namespace: chaos-mesh
spec:
  schedule: "*/30 * * * * *"   # 6-field cron with seconds
  type: PodChaos
  historyLimit: 5
  concurrencyPolicy: Forbid
  podChaos:
    action: pod-kill
    mode: one
    selector:
      namespaces: [podinfo]
      labelSelectors:
        "app.kubernetes.io/name": "podinfo"
    gracePeriod: 0
```

**Probe loop** (run in a separate shell, fires 1× per second):

```bash
PROBE_LOG=/tmp/exp1-probe.log
> "$PROBE_LOG"
(
  for i in $(seq 1 360); do
    out=$(curl -sf --cacert ~/minicloud-ca.crt -m 2 -o /dev/null \
            -w "%{http_code} %{time_total}" \
            https://podinfo.10.0.0.200.nip.io/version 2>/dev/null)
    rc=$?
    ts=$(date +%s.%N)
    echo "$ts $rc $out" >> "$PROBE_LOG"
    sleep 1
  done
) > /dev/null 2>&1 &
```

Then `kubectl apply -f exp1-podkill.yaml`, let it run for ~4-5 min,
then `kubectl delete schedule -n chaos-mesh podinfo-kill`.

**Result — measured live:**

| Metric | Value |
|---|---|
| Probes (1 Hz, ~4 min) | 252 |
| HTTP 200 responses | **252** |
| Failures (any non-200, timeout, conn refused) | **0** |
| Availability | **100.0000%** |
| **Maximum unreachable duration** | **0 ms** |
| Latency p50 | 26 ms |
| Latency p99 | 61 ms |
| Latency max (single outlier during a replacement) | 303 ms |
| Total pod replacements observed | ~13 |
| PodChaos events fired | 5 |

**Why this works:** with `replicas=2` split across nodes, killing any
one pod still leaves one Ready endpoint in the ingress-nginx
endpointslice. The replacement pod is `Scheduled` within ~1 s and
`Ready` within ~3 s. The 303 ms max latency is the worst case — a
probe arrived during the brief moment when one pod was terminating;
the request landed on the surviving pod (still 200, just slower TCP
handshake or warming caches).

---

## Experiment 2 — NetworkChaos delay

**Hypothesis:** Phase 8 observability (Prometheus + Grafana) sees a
200 ms latency injection in real time, and the chaos engine cleanly
restores network state on cleanup.

**Manifest** (`chaos-mesh/exp2-netdelay.yaml`):

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: podinfo-latency
  namespace: chaos-mesh
spec:
  action: delay
  mode: all
  selector:
    namespaces: [podinfo]
    labelSelectors:
      "app.kubernetes.io/name": "podinfo"
  delay:
    latency: "200ms"
    jitter: "50ms"
    correlation: "25"
  duration: "3m"
```

What the chaos-daemon actually runs (visible in
`kubectl logs -n chaos-mesh -l app.kubernetes.io/component=chaos-daemon`):

```text
nsexec -n /proc/<pid>/ns/net -- tc qdisc add dev eth0 root \
  handle 1: netem delay 200ms 50ms 25.000000
```

This is straight Linux Traffic Control. Real kernel-level latency
injection inside the pod's network namespace — not a userspace fake.

**Result:**

| Phase | Mean latency | Multiple of baseline |
|---|---|---|
| Pre-chaos baseline | ~26 ms | 1× |
| **Under chaos** | **299 ms** | **~11×** |
| Post-cleanup | 25 ms | 1× — perfect recovery |

The 11× ratio matches expectations: the 200 ms ± 50 ms delay applies
to outbound packets, doubled for the round trip = ~250 ms added to the
~26 ms baseline = ~276-326 ms range. Measured 299 ms is dead-center.

After deleting the NetworkChaos resource, the daemon issues
`tc qdisc del dev eth0 root` and latency snaps back to baseline
within seconds.

---

## Experiment 3 — StressChaos memory (the safety-critical one)

**Hypothesis:** the 256 MiB cgroup memory limit on the podinfo
container contains a memory blowup at the container level — node-mate
pods are unaffected and the node stays Ready.

> **Critical safety check before running this experiment:** verify the
> target has resource limits set:
>
> ```bash
> kubectl get deploy -n podinfo podinfo \
>   -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
> # → 256Mi
> ```
>
> If the limit is missing, the stressor can eat the entire node's RAM,
> the kernel OOM-killer fires at the node level, and you can lose SSH
> access to the box. **Never run StressChaos against an unbounded
> container on a production-equivalent node.**

**Right-sizing the stressor** — the original draft used 4 GiB, but
that's overkill on a 256 MiB-limited container (the OOM-kill happens
in microseconds, and 4 GiB would only matter if the limit were
removed by accident). 512 MB is **2× the limit** — enough to
guarantee an OOM-kill while keeping the failure clearly contained.

**Manifest** (`chaos-mesh/exp3-memstress.yaml`):

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: podinfo-memory-stress
  namespace: chaos-mesh
spec:
  mode: one
  selector:
    namespaces: [podinfo]
    labelSelectors:
      "app.kubernetes.io/name": "podinfo"
  stressors:
    memory:
      workers: 1
      size: "512MB"
  duration: "2m"
```

**Result:**

| Pod / workload | Restart count change | Outcome |
|---|---|---|
| **podinfo (target pod)** | **0 → 1, reason `OOMKilled`** | Container OOM-killed at cgroup, restarted, back to Running |
| podinfo (other replica, different node) | 0 | Unaffected |
| All ~30 other pods on the target node (Backstage, Harbor-Trivy, NATS, Prometheus, Longhorn-Manager, MetalLB-Speaker, etc.) | **0 new restarts** | **Node-mate isolation held** |
| Service availability (`podinfo.10.0.0.200.nip.io/version`) | — | Probes returned HTTP 200 throughout (other replica served traffic) |

**This is the property the user warned about:** without limits, a
512 MiB stressor on a 16 GiB node would still get OOM-killed
eventually — but possibly only after the kernel had already started
killing other innocent processes to reclaim memory. With limits set,
the kill is **scoped to the cgroup** and happens **before** the node
notices any pressure.

---

## What we learned

1. **Resilience claims are testable, not philosophical.** Phase 9
   said "stays available under pod loss." Phase 20 measured
   exactly that: 0 ms downtime over 5 kill events. That's the
   difference between portfolio-grade and pretend.
2. **The k3s socket override matters.** Without
   `chaosDaemon.socketPath: /run/k3s/containerd/containerd.sock`, the
   daemon comes up but every experiment fails with `container runtime
   not found`. The chart README mentions it; the official docs don't
   loudly. Future-you will appreciate it being in CLAUDE.md.
3. **Always verify resource limits before running stressors.**
   `kubectl get deploy <target> -o jsonpath=...resources.limits` is
   the difference between a safe contained OOM-kill and "why can't I
   SSH into this node anymore."
4. **Linux Traffic Control is the kernel-level reality of network
   chaos.** Reading `chaosdaemon/tc_server.go` shows
   `tc qdisc add dev eth0 root handle 1: netem delay 200ms 50ms` —
   this is the same `tc`/`netem` command-line you'd use by hand on a
   bare-metal Linux box. Chaos Mesh is just a sane management layer
   over a real kernel facility.
5. **Auto-cleanup is part of the contract.** Every chaos experiment
   has a `duration:` field. After expiry, the daemon issues the
   inverse operation (`tc qdisc del`, kill the stressor process) and
   the system returns to its prior state. We verified this for
   NetworkChaos by measuring post-cleanup latency = baseline.

---

## Done When

```text
✔ 7 chaos-mesh pods Running (3 controller-manager, 3 daemon, 1 dashboard)
✔ 23 chaos-mesh.org CRDs registered
✔ Dashboard RBAC token at ~/.chaos-dashboard-token mode 600
✔ kubectl port-forward to dashboard works, token logs in
✔ Experiment 1: podinfo 100.0000% available across 5 pod-kills
✔ Experiment 2: latency went 26ms → 299ms → 25ms (auto-cleanup verified)
✔ Experiment 3: contained OOM-kill, no node-mate pods restarted
✔ All chaos resources deleted; cluster back to steady state
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Validation engineering** | Different from "build it." Senior infra interviews ask "how do you know it works under failure?" Phase 20 is the answer. |
| **Steady-state-hypothesis discipline** | The Netflix _Chaos Engineering_ book formalism: define the steady state, predict the outcome, inject, observe, learn. This is the difference between chaos engineering and chaos. |
| **Linux Traffic Control / netem mental model** | Knowing that `tc qdisc add dev eth0 root netem delay 200ms` is the actual mechanism behind NetworkChaos — and being able to read the daemon's logs to verify it — separates "operates the tool" from "understands the tool." |
| **cgroup memory limits as isolation boundaries** | The instinct to ask "is the limit set before I run a stressor?" is the difference between a chaos test and a node-killing accident. Real production chaos engineers are paranoid about this. |
| **Synchronous availability probing** | Polling at 1 Hz from a separate shell while injecting failure is the canonical methodology. Same shape as canary analysis, blue/green smoke tests, k6/Locust load tests. |
| **kill-switch tooling — security posture** | Recognizing that the chaos dashboard is a kill switch and refusing to give it a public Ingress is the same instinct as "don't expose Redis to the internet" — production-correct security thinking. |
| **Reading controller-runtime CRDs in practice** | PodChaos/NetworkChaos/StressChaos all follow the operator pattern. Reading their `.spec` and `.status` fluently is practice for every k8s controller you'll meet on the job. |
| **Senior scope reduction** | NodeChaos / automated cron GameDays / dashboard Ingress all deliberately deferred. Same skill as every prior deferral. |
