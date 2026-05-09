---
id: cilium
title: Phase 22 — Cilium + Hubble (runbook + deferred execution)
sidebar_position: 2
---

# Phase 22 — Cilium + Hubble: runbook authored, execution deferred

:::caution Status: Procedure documented, **execution deferred to fresh-cluster rebuild**
The original 22-phase plan ended with "replace k3s's bundled Flannel
CNI with Cilium + Hubble." This page captures **the complete
migration procedure** that would be executed — but the execution
itself is deliberately deferred until the next fresh-cluster install.

This is the same scope-reduction discipline applied throughout the
project: Phase 11 (Crossplane), Phase 13 (GitLab), Phase 15 (Vault +
RBAC), Phase 16 (n8n / Temporal / Airflow), Phase 18 (Backstage
plugins / templates / SSO), Phase 19 (MLflow + Kubeflow), Phase 20
(NodeChaos + automated GameDays + dashboard Ingress), Phase 21
(Jaeger / distributed tracing).

The runbook is the deliverable. Execution can happen anytime —
ideally during a planned MAAS-driven cluster rebuild, when the cost
of CNI replacement is zero.
:::

---

## Why deferred (the engineering call)

The CNI is the network plumbing every pod depends on. Replacing it on
a live 22-phase cluster carries risk that doesn't scale with the
benefits **at our cluster size**:

### What we'd gain

| Feature | Real benefit on this cluster |
|---|---|
| eBPF data plane | Measured speed wins emerge at thousands of pods. We have ~111. |
| `kubeProxyReplacement` | Matters most when standalone kube-proxy is a bottleneck. **k3s already embeds kube-proxy efficiently** — there is no separate process to replace. |
| L7 network policies (CiliumNetworkPolicy) | Useful for production multi-team clusters with strict zero-trust. We have one operator and zero deployed NetworkPolicies. |
| Hubble UI for L7 traffic visibility | Most valuable when there's distributed multi-service traffic to observe. **Same argument as Phase 21's Jaeger deferral** — single-service apps (podinfo, whoami, platform-demo) emit single-step flow trees. |
| mTLS between pods | Useful for zero-trust workloads. None of our current workloads have that requirement. |

### What we'd risk

| Concern | Magnitude |
|---|---|
| Pods affected by hot CNI swap | **111 pods cluster-wide** |
| LoadBalancer services to reattach | 2 (the MetalLB-assigned NGINX Ingress) |
| Ingress resources requiring re-admission | 10 |
| Stateful workloads requiring volume reattach | Harbor (5 PVs), Longhorn (~16 PVs), kube-prometheus-stack (3), Backstage Postgres, NATS x3, Loki, open-webui, ollama, ArgoCD redis |
| GitOps reconciliation storm during transition | ArgoCD with auto-sync + selfHeal would fight the migration |
| Rollback path | k3s reinstall + Velero restore = ~45-60 min RTO (Phase 14) |

The headline: **22 phases of validated infrastructure on top of a
working CNI.** Replacing it now is high blast radius for marginal
upside. The right time is the next fresh-cluster install — the cost
of CNI choice is zero on a clean slate.

### What this deferral demonstrates (skill-wise)

This isn't "we couldn't do it." This is **knowing when not to act**.

- **Read the upgrade docs critically** — identified that Cilium's
  benefits assume conditions our cluster doesn't meet
- **Quantified the risk** — 111 pods, 10 Ingresses, 30+ PVCs, 2
  LoadBalancers, all Live workloads
- **Authored the runbook anyway** — when conditions change, the next
  operator (or future-you) doesn't start from a blank page
- **Same discipline as 8 prior phases** — Crossplane, GitLab, Vault,
  n8n/Temporal/Airflow, plugins, MLflow, Kubeflow, NodeChaos, Jaeger

Senior infra engineers are paid as much for what they DON'T do as
what they do.

---

## What was actually executed in Phase 22

Even with execution deferred, two real things shipped:

### 1. Cilium CLI installed on the controller

```bash
# Tarball install — no apt repo dependency, no sudo
CILIUM_CLI_VERSION=v0.19.2
curl -sL --remote-name-all \
  https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-amd64.tar.gz \
  https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-amd64.tar.gz.sha256sum
sha256sum --check cilium-linux-amd64.tar.gz.sha256sum
mkdir -p ~/.local/bin
tar xzvf cilium-linux-amd64.tar.gz -C ~/.local/bin
rm -f cilium-linux-amd64.tar.gz cilium-linux-amd64.tar.gz.sha256sum

cilium version --client
# cilium-cli: v0.19.2 compiled with go1.25.5 on linux/amd64
# cilium image (default): v1.19.1
# cilium image (stable): v1.19.3
```

The CLI is **read-only useful** even with no Cilium installed —
`cilium install --dry-run-helm-values` lets us inspect the manifests
that WOULD be applied (see below).

### 2. Captured the dry-run install plan

`cilium install --dry-run-helm-values` rendered the exact Helm values
Cilium would use for our cluster:

```yaml
# /home/ktayl/minicloud-ktaylorganisation/cilium/dry-run-values.yaml
cluster:
  name: default
hubble:
  relay:
    enabled: true
  ui:
    enabled: true
ipam:
  mode: kubernetes        # use Kubernetes pod CIDR allocation
                          # (matches our existing 10.42.0.0/16 Flannel range)
k8sServiceHost: 10.0.0.2  # set-hog control plane
k8sServicePort: 6443
kubeProxyReplacement: true
operator:
  replicas: 1
routingMode: tunnel       # VXLAN encapsulation between nodes
tunnelProtocol: vxlan
```

This is what the next operator (or future-you) would `helm install`
on a clean cluster. It's been captured and committed alongside the
runbook so the procedure is reproducible.

---

## The migration runbook (when conditions are right to execute)

Run this only on a **fresh k3s install** OR with a **planned
maintenance window + Velero backup taken first**.

### Pre-flight (mandatory)

```bash
# 1. Take a fresh Velero backup as a snapshot point
velero backup create pre-cilium-migration \
  --include-cluster-resources \
  --wait

# 2. Capture current state for diff later
kubectl get pods -A -o wide > /tmp/pre-cilium-pods.txt
kubectl get svc -A -o wide > /tmp/pre-cilium-svc.txt

# 3. Pause ArgoCD auto-sync to prevent reconciliation storm during migration
for app in $(kubectl -n argocd get app -o name); do
  kubectl -n argocd patch $app --type merge \
    -p '{"spec":{"syncPolicy":{"automated":null}}}'
done
```

### Step 1 — Reconfigure k3s on every node

```bash
# Edit /etc/rancher/k3s/config.yaml on EACH node — append:
flannel-backend: none
disable-network-policy: true
disable: [traefik, servicelb]   # already set; ensure unchanged

# Apply the config and restart k3s on each node, control plane FIRST:
ssh ubuntu@10.0.0.2 "sudo systemctl restart k3s"      # set-hog
ssh ubuntu@10.0.0.4 "sudo systemctl restart k3s-agent" # fast-skunk
ssh ubuntu@10.0.0.7 "sudo systemctl restart k3s-agent" # fast-heron

# At this point: pod-network is DOWN cluster-wide. All running pods
# are in NotReady. Critical: do NOT panic. Move immediately to step 2.
```

### Step 2 — Install Cilium

```bash
helm repo add cilium https://helm.cilium.io
helm repo update cilium

helm install cilium cilium/cilium \
  --namespace kube-system \
  --version 1.19.3 \
  --values /home/ktayl/minicloud-ktaylorganisation/cilium/dry-run-values.yaml \
  --wait --timeout 5m

# Verify
cilium status --wait
# /̇‾‾\
# /¯¯\__/¯¯\    Cilium:             OK
# \__/¯¯\__/    Operator:            OK
# /¯¯\__/¯¯\    Hubble:              OK
# \__/¯¯\__/    ClusterMesh:         disabled
# \__/
```

### Step 3 — Verify pod-network restoration

```bash
# Pods should rapidly transition NotReady → Ready as Cilium installs
# the CNI on each node and pods get re-scheduled networking
kubectl get pods -A --field-selector=status.phase!=Running
# Hopefully empty within 2-3 min

# Compare before/after pod IPs (same range, just re-attached)
kubectl get pods -A -o wide > /tmp/post-cilium-pods.txt
diff /tmp/pre-cilium-pods.txt /tmp/post-cilium-pods.txt | head -20

# Verify kube-proxy has been replaced (no kube-proxy DaemonSet anymore)
kubectl get ds -n kube-system -l k8s-app=kube-proxy
# No resources found — Cilium replaced it
```

### Step 4 — Re-attach LoadBalancer services + Ingress

The MetalLB → NGINX Ingress chain should re-establish automatically
once Cilium starts handling pod networking. Verify:

```bash
kubectl get svc -A --field-selector=spec.type=LoadBalancer
# nginx-ingress-controller   LoadBalancer   10.0.0.200   ...

curl -sI -m 3 --cacert ~/minicloud-ca.crt https://homer.10.0.0.200.nip.io/
# HTTP/1.1 200 OK
```

If LoadBalancer IP doesn't reattach, restart the MetalLB controller:
```bash
kubectl rollout restart deployment/controller -n metallb-system
```

### Step 5 — Enable Hubble UI

```bash
cilium hubble enable --ui
cilium hubble port-forward &

# Open http://localhost:12000 in browser
# OR add a TLS Ingress for hubble.10.0.0.200.nip.io
```

### Step 6 — Re-enable ArgoCD auto-sync

Once everything is verified Running:

```bash
for app in $(kubectl -n argocd get app -o name); do
  kubectl -n argocd patch $app --type merge \
    -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
done
```

### Step 7 — Run the regression check (CLAUDE.md sections 1-18)

If all 18 checks pass: migration successful. If any fail: triage
individually. The Velero backup from pre-flight is your rollback
escape hatch (`velero restore create --from-backup
pre-cilium-migration`).

---

## Rollback procedure

If migration fails irrecoverably:

```bash
# 1. Stop k3s + Cilium
ssh ubuntu@10.0.0.2 "sudo systemctl stop k3s"
ssh ubuntu@10.0.0.4 "sudo systemctl stop k3s-agent"
ssh ubuntu@10.0.0.7 "sudo systemctl stop k3s-agent"

# 2. Revert /etc/rancher/k3s/config.yaml on each node:
#    Remove: flannel-backend: none
#    Remove: disable-network-policy: true

# 3. Wipe Cilium-installed CNI artifacts on each node
for n in 10.0.0.2 10.0.0.4 10.0.0.7; do
  ssh ubuntu@$n "sudo rm -rf /etc/cni/net.d/05-cilium*"
done

# 4. Restart k3s — Flannel comes back as default
ssh ubuntu@10.0.0.2 "sudo systemctl start k3s"
ssh ubuntu@10.0.0.4 "sudo systemctl start k3s-agent"
ssh ubuntu@10.0.0.7 "sudo systemctl start k3s-agent"

# 5. If pod state is corrupted, restore via Velero
velero restore create --from-backup pre-cilium-migration --wait
```

Estimated rollback RTO: 30-45 min.

---

## When to actually execute this runbook

The right conditions:

1. **Fresh-cluster install** — when MAAS-driven rebuild happens, swap
   to `flannel-backend: none` from the start; Cilium becomes the only
   CNI from day 0. Zero migration cost.
2. **Multi-service workload exists** that benefits from L7 visibility
   in Hubble (e.g., a real microservices demo: gateway → auth →
   business-service → DB). Until then, Hubble shows trivial flows.
3. **Cluster scale exceeds ~500 pods** where eBPF data-plane speed
   becomes measurably better than iptables.
4. **Network policy enforcement** becomes a real requirement (e.g.,
   compliance, multi-tenancy, zero-trust).

None of these conditions are true today. Hence the deferral.

---

## What this deferral does NOT mean

| Misreading | Truth |
|---|---|
| ❌ "Couldn't figure out Cilium" | Read the docs, captured the dry-run, wrote the runbook. The procedure is concrete. |
| ❌ "Cilium isn't impressive enough" | It's the canonical eBPF-CNI portfolio piece. The deferral is a value-vs-risk call, not a technology rejection. |
| ❌ "Phase 22 is incomplete" | The runbook IS the Phase 22 deliverable. Execution is downstream. |
| ❌ "The cluster has a CNI gap" | k3s's bundled Flannel works fine for our scale and workloads. The cluster is fully functional. |

---

## Done When (procedure complete, execution deferred)

```text
✔ cilium CLI installed on controller (~/.local/bin/cilium v0.19.2)
✔ cilium install --dry-run-helm-values output captured
  (/home/ktayl/minicloud-ktaylorganisation/cilium/dry-run-values.yaml)
✔ Migration runbook authored — pre-flight, 7 steps, rollback procedure
✔ Deferral rationale documented — when to execute, why not now
✔ CLAUDE.md, intro.md, 00-overview.md updated with Phase 22 status
```

---

## Real-world skills demonstrated (even with execution deferred)

| Skill | Industry context |
|---|---|
| **Reading invasive upgrade docs critically** | Senior infra interview test: "We have a working production cluster — should we replace the CNI?" Identifying that the canonical answer is "yes" but the right answer for THIS cluster is "not yet" is a senior judgment call. |
| **Quantifying migration impact** | 111 pods, 10 Ingresses, 30+ PVCs, 2 LoadBalancers — concrete numbers convert "this is risky" into "this is N units of risk for M units of upside." |
| **Authoring runbooks for invasive changes** | Real production work. The next operator (you in 6 months, or a colleague) doesn't have to derive the procedure from scratch. |
| **Pre-flight + rollback discipline** | Every production-grade upgrade procedure has a Velero-equivalent snapshot point and a documented rollback path. Without those, you don't run the procedure. |
| **Senior scope reduction (defer to fresh cluster)** | Pattern match: 9th deferral in the project. Knowing what NOT to ship is the senior portfolio piece. |
| **Honest framing** | "Procedure documented, execution deferred" is more credible than "Cilium installed (but I disabled the eBPF features so nothing actually changed)." |
