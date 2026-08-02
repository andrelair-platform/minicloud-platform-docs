---
id: lifecycle-day2-operations
title: Lifecycle & Day-2 Operations — Evaluation & Gap Closure
sidebar_position: 20
---

# Lifecycle & Day-2 Operations — Evaluation & Gap Closure

Evaluated 2026-08-02 against three Day-2 criteria. Gaps closed via gitops PR #518.

| Criterion | Assessment | Gaps closed |
|-----------|-----------|-------------|
| OS & Kubernetes upgrade strategy | ✅ Automated rolling upgrade via SUC | ArgoCD pause procedure documented |
| Cluster autoscaling / capacity planning | ✅ VPA (vertical) + alerts at 80%/85% | Node expansion runbook added |
| Certificate management | ✅ cert-manager for workloads + k3s auto-rotate | k3s cert expiry alert added |

---

## Criterion 1 — OS & Kubernetes Upgrade Strategy

### What's in place

**k3s upgrades — system-upgrade-controller (SUC) v0.19.2:**

Rancher's system-upgrade-controller runs as a Deployment on `set-hog`
(pinned to control-plane node). It watches `Plan` CRs and creates upgrade
Job pods that drain, upgrade, and uncordon each node in sequence.

```
Plan: k3s-server    → upgrades set-hog (control plane)
                         ↓ prepare step
Plan: k3s-agent     → upgrades fast-skunk, fast-heron, star-kitten,
                       swift-mac (1 at a time, concurrency: 1)
```

Both Plans are in `manifests/system-upgrade/01-k3s-plans.yaml`. To trigger
a k3s upgrade, bump `version:` and commit — ArgoCD auto-syncs the updated
Plan, SUC detects the change and starts upgrade Jobs.

**Drain settings (both Plans):**

```yaml
cordon: true
drain:
  force: true
  ignoreDaemonSets: true   # Longhorn, node-exporter — don't block drain
  deleteEmptydirData: true
  timeout: 120
```

`ignoreDaemonSets: true` is required. Longhorn instance-manager DaemonSets
and node-exporter don't get evicted, so drain proceeds without waiting for
them. Without this flag, drain hangs on Longhorn pods.

**OS security patching — kured:**

`kured` DaemonSet runs on all 5 nodes. Ubuntu's `unattended-upgrades`
applies security patches on a nightly schedule. When a patch requires a
reboot, it creates `/var/run/reboot-required`. kured detects this file,
cordons the node, and reboots it — one node at a time, respecting the same
PDB constraints as kubectl drain.

Current cluster version: `v1.36.2+k3s1` (all 5 nodes, verified 2026-08-02).

### Gap closed — ArgoCD auto-sync conflict during active upgrades

During an active SUC upgrade, Job pods appear in the `system-upgrade`
namespace. ArgoCD's `selfHeal: true` sees these as "extra" resources not in
git and may interfere with them. The mitigation is to pause auto-sync for
the `system-upgrade` Application during the upgrade window.

Documented in `apps/platform/system-upgrade.yaml` as a comment header:

```bash
# Step 1: Pause ArgoCD auto-sync before starting the upgrade
argocd app set system-upgrade --sync-policy none

# Step 2: Commit + push the version bump in 01-k3s-plans.yaml
# ArgoCD detects OutOfSync but does not act

# Step 3: Manually sync once to push the updated Plan
argocd app sync system-upgrade

# Step 4: Monitor upgrade Jobs (typically 2-4 min per node)
kubectl get jobs -n system-upgrade -w

# Step 5: After all nodes upgraded, re-enable auto-sync
argocd app set system-upgrade --sync-policy automated --self-heal --auto-prune
```

### Expected upgrade cadence

k3s typically releases a new patch every 2-4 weeks and a new minor
(e.g., v1.37) every 4-6 months. With Kubernetes SLO releasing 3 minors
per year and k3s tracking upstream closely:

| Release type | Frequency | Action |
|---|---|---|
| k3s patch (e.g., v1.36.2→v1.36.3) | Monthly | Bump version + follow procedure |
| k3s minor (e.g., v1.36→v1.37) | Quarterly | Review changelog for breaking changes first |
| Ubuntu kernel/security | Nightly | kured handles automatically |

---

## Criterion 2 — Cluster Autoscaling / Capacity Planning

### What's in place

**Vertical Pod Autoscaler (VPA) — fairwinds/vpa 4.12.3:**

VPA `recommender`, `updater`, and `admissionController` all run in `vpa-system`.
11 VPA objects cover the main workloads:

| Workload | Namespace | Mode |
|----------|-----------|------|
| langfuse-web | langfuse | **Auto** (evicts and resizes) |
| backstage | backstage | **Auto** |
| litellm | ai | **Auto** |
| langfuse-clickhouse | langfuse | Off (recommendation only) |
| prometheus | monitoring | Off |
| open-webui | ai | Off |
| matrix-synapse | chat | Off |
| vault | vault | Off |
| minicloud-plane | minicloud-plane-dev | Off |
| platform-demo | platform-demo-dev | Off |

`Auto` mode workloads are evicted and restarted with updated resource
requests when the VPA recommendation drifts >10% from current requests.
StatefulSets with RWO Longhorn PVCs stay in `Off` mode — forced eviction
during a storage rebalance risks deadlock.

**ResourceQuotas — per namespace:**

Quotas are defined for 14 namespaces (`manifests/quotas/`), covering the
highest-traffic namespaces: argocd, authentik, backstage, harbor, vault,
ingress-nginx, monitoring, observability, and the per-app per-env
namespaces for platform-demo and minicloud-plane.

**Node capacity alerts:**

NodeCPUWarning/Critical (>80%/>95%) and NodeMemoryWarning/Critical
(>85%/>95%) from `manifests/monitoring/22-node-resource-alerts.yaml` fire
before resources are exhausted — giving 10 minutes of warning time.

**Current node utilization (2026-08-02):**

| Node | CPU | RAM (15.6 GiB total) | Role |
|------|-----|----------------------|------|
| fast-heron | 3% | 30% (~4.7 GiB) | worker |
| fast-skunk | 11% | 64% (~10 GiB) | worker |
| set-hog | 12% | 65% (~10.2 GiB) | control plane |
| star-kitten | 6% | 43% (~6.8 GiB) | worker |
| swift-mac | 31% | 73% (~5.7 GiB / 7.9 GiB) | worker + Longhorn |

**swift-mac** (MacBook Pro 2012, 4 CPU / 8 GiB) is the capacity constraint
node. At 73% RAM it is 12 points below NodeMemoryWarning. It hosts Longhorn
storage and Ollama (GPU inference). Any new memory-intensive workload should
avoid swift-mac by default.

### Why there is no cluster autoscaler

This is a 5-node bare-metal homelab on ThinkPad laptops. There is no cloud
API to provision VMs. A cluster autoscaler is architecturally impossible
for this environment — the VPA + ResourceQuotas + node resource alerts
provide the equivalent signal: "a workload needs more resources."

The action when that signal fires is physical expansion (add a node) or
workload redistribution (increase resource limits, move a workload to a
less-utilized node). Both are captured in the node expansion runbook below.

### Node expansion runbook

**Trigger:** NodeMemoryCritical (>95%) sustained 5 min on any node, OR
VPA recommendation on a workload in `Off` mode exceeds current node
capacity.

**Option A — Add a sixth node (ThinkPad on 10.0.0.x):**

```bash
# 1. Commission via MAAS (enlist → commission → deploy Ubuntu)
ssh controller "maas ktayl machine create ... fqdn=new-node.maas"

# 2. Bootstrap k3s agent
K3S_URL=https://10.0.0.2:6443
K3S_TOKEN=$(ssh set-hog "sudo cat /var/lib/rancher/k3s/server/token")
ssh new-node "curl -sfL https://get.k3s.io | K3S_URL=${K3S_URL} K3S_TOKEN=${K3S_TOKEN} sh -"

# 3. Verify node joins
ssh controller "kubectl --context minicloud get nodes"

# 4. Label for workload scheduling (if dedicated role)
kubectl --context minicloud label node new-node.maas workload=gpu

# 5. Update VPA maxAllowed if new node has more RAM
# Edit manifests/vpa/00-vpa-objects.yaml, commit + push
```

**Option B — Redistribute workload to a less-utilized node:**

```bash
# Force a specific pod to a specific node
kubectl --context minicloud patch deployment <name> -n <ns> \
  -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"fast-heron"}}}}}'

# Or use a NodeAffinity patch in the overlay kustomization
```

**Option C — Switch a VPA from Off to Auto:**

When a workload in `Off` mode shows a VPA recommendation significantly
above its current requests (visible in `kubectl describe vpa <name> -n <ns>`),
switch it to Auto after verifying 7+ days of stable recommendations:

```bash
# Check recommendation
kubectl --context minicloud describe vpa platform-demo -n platform-demo-dev \
  | grep -A 10 "Container Recommendations"

# Switch to Auto (edit manifests/vpa/00-vpa-objects.yaml)
# updateMode: "Auto"
# Commit + push — VPA will evict and resize on next request drift
```

---

## Criterion 3 — Certificate Management

### What's in place

**cert-manager v3 (84d running)** — 3 deployments healthy:
- `cert-manager` (webhook server)
- `cert-manager-cainjector`
- `cert-manager-webhook`

**2 ClusterIssuers:**

| Issuer | Type | Used for |
|--------|------|----------|
| `minicloud-ca` | CA (backed by minicloud root CA PEM) | All workload certs |
| `selfsigned-bootstrap` | Self-signed | Bootstrapping the minicloud CA |

**50+ Certificate objects across all namespaces — all `Ready: True`.**

cert-manager auto-renews every Certificate 90 days before expiry
(`renewBefore` defaults to 1/3 of duration). No manual intervention
is ever needed for workload TLS certs.

**Root CA expiry:** `cert-manager/minicloud-root-ca` expires 2036-05-06
(10-year cert). `renewBefore: 2160h` (90 days). cert-manager will
auto-renew around 2036-02-05 — not a concern this decade.

### k3s internal certificates

k3s manages its own PKI independently of cert-manager. These certs
live on `set-hog` at `/var/lib/rancher/k3s/server/tls/` and as the
`k3s-serving` Secret in `kube-system`.

**Expiry summary (all issued 2026-04-26):**

| Certificate | Path | Expiry | Action required |
|------------|------|--------|-----------------|
| server-ca | `tls/server-ca.crt` | 2036-04-23 | None (10-year CA) |
| client-ca | `tls/client-ca.crt` | 2036-04-23 | None |
| request-header-ca | `tls/request-header-ca.crt` | 2036-04-23 | None |
| etcd server-ca | `tls/etcd/server-ca.crt` | 2036-04-23 | None |
| etcd peer-ca | `tls/etcd/peer-ca.crt` | 2036-04-23 | None |
| **serving-kube-apiserver** | `tls/serving-kube-apiserver.crt` | **2027-04-26** | Rotate before then |
| **client-kube-apiserver** | `tls/client-kube-apiserver.crt` | **2027-04-26** | Auto-rotated on restart |
| **client-admin** | `tls/client-admin.crt` | **2027-04-26** | Auto-rotated on restart |
| **kube-scheduler** | `tls/kube-scheduler/kube-scheduler.crt` | **2027-04-26** | Auto-rotated on restart |
| **kube-controller-manager** | `tls/kube-controller-manager/kube-controller-manager.crt` | **2027-04-26** | Auto-rotated on restart |
| **etcd server-client** | `tls/etcd/server-client.crt` | **2027-04-26** | Auto-rotated on restart |
| **etcd peer-server-client** | `tls/etcd/peer-server-client.crt` | **2027-04-26** | Auto-rotated on restart |

### k3s auto-rotation behavior

k3s automatically rotates leaf certificates during startup **if the cert
has less than 90 days remaining**. The 90-day window opens 2027-01-25.

After auto-rotation, k3s must be restarted a second time to load the
new serving cert into the running API server process.

The explicit rotation command (can be run before the 90-day window):

```bash
# Rotate all k3s certificates immediately
ssh set-hog "sudo k3s certificate rotate"

# Load new certs into the running API server (~30s API unavailability)
ssh set-hog "sudo systemctl restart k3s"

# Verify new expiry (should be ~1 year from today)
ssh set-hog "sudo openssl x509 -noout -dates \
  -in /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt"
```

### Gap closed — k3s cert expiry alert

`manifests/monitoring/39-k3s-cert-expiry.yaml` adds:

1. **Blackbox exporter** (enabled in kps via `prometheus-blackbox-exporter`
   subchart, module `https_skip_verify`) probes
   `https://kubernetes.default.svc:443` and exposes
   `probe_ssl_earliest_cert_expiry` — the Unix timestamp of the earliest
   cert in the TLS chain.

2. **`K3sServingCertExpiringSoon`** (critical, 1h):
   ```
   (probe_ssl_earliest_cert_expiry{job="k3s-apiserver-tls"} - time()) / 86400 < 60
   ```
   Fires when the serving cert has fewer than 60 days remaining, giving
   30 days of lead time before the k3s auto-rotate window opens at 90 days.

   Expected first fire: **~2027-02-25** (60 days before 2027-04-26 expiry).

3. **`K3sServingCertProbeFailing`** (warning, 10m): fires if the probe
   itself cannot reach the API server — distinguishes a probe failure
   from a cert expiry event.

### Certificate management summary

```
Workload certs (50+):
  cert-manager → minicloud-ca ClusterIssuer → auto-renewed 90 days before expiry ✅

k3s internal certs (leaf, expire 2027-04-26):
  monitoring: K3sServingCertExpiringSoon alert fires ~2027-02-25 ✅
  rotation: ssh set-hog "sudo k3s certificate rotate && sudo systemctl restart k3s" ✅

Root CA (expires 2036-05-06):
  cert-manager auto-renews 90 days before (renewBefore: 2160h) ✅
```

---

## Files changed (gitops PR #518)

| File | What changed |
|------|--------------|
| `apps/platform/system-upgrade.yaml` | Upgrade window procedure documented as comment header |
| `helm-values/minicloud-1/kube-prometheus-stack-values.yaml` | Enable `prometheus-blackbox-exporter` subchart with `https_skip_verify` module |
| `manifests/monitoring/39-k3s-cert-expiry.yaml` | Probe CR + K3sServingCertExpiringSoon + K3sServingCertProbeFailing rules |

---

## Verification

```bash
# k3s serving cert expiry (expect 2027-04-26 today, < 60 days triggers alert)
ssh set-hog "sudo openssl x509 -noout -dates \
  -in /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt"

# Blackbox exporter running
kubectl --context minicloud get deploy -n monitoring | grep blackbox

# Probe hitting the API server
kubectl --context minicloud exec -n monitoring \
  deploy/kps-prometheus-blackbox-exporter -- \
  wget -qO- 'http://localhost:9115/probe?target=https://kubernetes.default.svc:443&module=https_skip_verify' \
  | grep probe_ssl_earliest_cert_expiry

# Days until k3s cert expiry (query in Prometheus/Grafana Explore)
# (probe_ssl_earliest_cert_expiry{job="k3s-apiserver-tls"} - time()) / 86400

# VPA recommendations for workloads in Off mode
kubectl --context minicloud get vpa -A
kubectl --context minicloud describe vpa platform-demo -n platform-demo-dev \
  | grep -A 5 "Container Recommendations"

# Node utilization
kubectl --context minicloud top nodes
```
