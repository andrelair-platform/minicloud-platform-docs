---
slug: self-managed-vs-managed-kubernetes-control-plane
title: "Self-Managed vs Managed Kubernetes: What Running Your Own Control Plane Actually Looks Like"
authors: [andre]
description: >
  A concrete comparison of running a k3s control plane on a ThinkPad versus EKS/GKE/AKS —
  grounded in a real bare-metal cluster, not theory. What you own, what breaks, and what you learn.
tags: [kubernetes, k3s, bare-metal, platform-engineering, devops, control-plane, eks, gke]
date: 2026-07-26
image: /img/docusaurus-social-card.jpg
---

Most Kubernetes comparisons are written by people who have only used managed services. This one is written by someone who has a ThinkPad named `set-hog` sitting on a desk running the API server right now.

Here is what self-managing a Kubernetes control plane actually looks like — compared line by line against EKS, GKE, and AKS.

{/* truncate */}

## The Setup

The cluster is **minicloud**: five machines, all bare-metal, running k3s v1.36.2+k3s1 on Ubuntu 22.04.

| Node | IP | Role |
|------|----|------|
| set-hog | 10.0.0.2 | **k3s control plane** |
| fast-skunk | 10.0.0.4 | k3s worker |
| fast-heron | 10.0.0.7 | k3s worker |
| star-kitten | 10.0.0.8 | k3s worker |
| swift-mac | 10.0.0.10 | k3s worker (MacBook Pro 2012) |

`set-hog` is where the API server, scheduler, and controller-manager run. It is a ThinkPad. It is on a desk. When it goes down, no new pods get scheduled — exactly what the managed cloud documentation warns you about when you read the architecture diagrams they publish but do not have to operate themselves.

## The Comparison

| Aspect | minicloud (self-managed) | Managed (EKS / GKE / AKS) |
|--------|--------------------------|---------------------------|
| **Where it runs** | Physical ThinkPad on your desk (`set-hog`) | Cloud provider's infrastructure, hidden from you |
| **Who installs it** | You ran `k3s server` via Ansible | Provider handles it — you just `terraform apply` |
| **HA / redundancy** | Single control-plane node — if `set-hog` dies, no new scheduling until it recovers | Multi-AZ etcd + API server replicas, provider SLA 99.9%+ |
| **etcd** | Kine/SQLite (k3s lightweight replacement — no `--cluster-init`) | Real etcd cluster, managed and backed up by provider |
| **API server** | Exposed on `set-hog`, accessed via Tailscale | Exposed on provider endpoint (e.g. `*.eks.amazonaws.com`) |
| **kubectl access** | `minicloud-oidc` context via Tailscale → `set-hog` | IAM/OIDC integration, no VPN needed |
| **Break-glass access** | `minicloud-break-glass` context (static cert, emergency only) | Provider console / IAM emergency roles |
| **Upgrades** | system-upgrade-controller Plans: server Plan runs first (cordon), then agent Plan, you set the target version | Provider one-click or auto-upgrade, they handle etcd migration |
| **Scheduler + ctrl-mgr metrics** | socat DaemonSet on `set-hog` proxying `:10259 → :10269` and `:10257 → :10267` because k3s binds them to `127.0.0.1` only | Provider exposes these natively, or not at all (opaque) |
| **CIS hardening** | kube-bench k3s-CIS-1.7 applied manually via Ansible — **16/16 PASS** on all workers | Provider handles most CIS controls by default |
| **Cost** | Electricity + hardware (already owned) | $70–$150/month per cluster for the control plane alone (EKS: $0.10/hr) |
| **Failure impact** | `set-hog` crash → API server gone → no new pod scheduling (running pods keep running) | Provider restores automatically, usually invisible |

## The Part No One Writes About: Scheduler Metrics

On every managed Kubernetes cluster, you can scrape the scheduler and controller-manager metrics directly from the provider's monitoring integration. On k3s, both components bind to `127.0.0.1` only — loopback, not reachable from Prometheus.

The fix is a socat DaemonSet pinned to `set-hog` with `hostNetwork: true`:

```yaml
# scheduler proxy: 127.0.0.1:10259 → 0.0.0.0:10269
socat TCP-LISTEN:10269,fork TCP:127.0.0.1:10259

# controller-manager proxy: 127.0.0.1:10257 → 0.0.0.0:10267
socat TCP-LISTEN:10267,fork TCP:127.0.0.1:10257
```

Two Kubernetes Services point at the socat pods. Two ServiceMonitors with `scheme: https` and `insecureSkipVerify: true` tell Prometheus to scrape them. Result: 60 scheduler series and 93 controller-manager workqueue series, exactly what you see in the "Kubernetes / Scheduler" Grafana dashboard.

On EKS, you click "enable control plane logging" and CloudWatch does the rest. On k3s bare-metal, you learn what socat is for.

## What You Actually Own vs What the Provider Owns

```
Self-managed (your responsibility)      Managed (provider's responsibility)
────────────────────────────────────    ──────────────────────────────────────
k3s install + initial config            Provisioned automatically
CIS kubelet hardening (Ansible)         Enforced by default
system-upgrade-controller Plans         One-click upgrade in console
socat proxy for control-plane metrics   Metrics exposed natively
Boot order: controller first (30s),     Always available, no order dependency
  then nodes (2 min), then Tailscale
iptables NAT restore after power        Provider networking never breaks on reboot
  failure (manual iptables-restore)
Break-glass static cert management      IAM emergency roles
minicloud root CA + cert-manager PKI    Provider CA, not yours
```

### The Boot Order Problem

Managed Kubernetes does not have a boot order. Your cluster does.

After a full power failure, the correct restart sequence is:

1. **MAAS controller** (ThinkPad X390, the NAT router for `10.0.0.0/24`) — wait 30 seconds
2. **Cluster nodes** — wait 2 minutes for k3s to come up
3. **Tailscale on Mac** — then `kubectl` works again

Miss step 1 and the cluster nodes cannot reach the internet. Nodes come up, k3s starts, ArgoCD tries to sync from GitHub, and every repo-server gets `context deadline exceeded`. The reason: the controller runs NAT (`MASQUERADE` via iptables for `10.0.0.0/24`), and after a reboot, `netfilter-persistent` does not restore the rules because its systemd unit is a broken symlink.

The recovery procedure:

```bash
sudo sh -c 'iptables-restore < /etc/iptables/rules.v4'
sudo iptables -I FORWARD -s 10.0.0.0/24 -j ACCEPT
sudo iptables -I FORWARD -d 10.0.0.0/24 -j ACCEPT
sudo iptables -I FORWARD -s 10.42.0.0/16 -j ACCEPT
sudo iptables -I FORWARD -d 10.42.0.0/16 -j ACCEPT
```

EKS does not have this problem. But EKS engineers do not know what those commands do, either.

## The etcd Difference

Standard Kubernetes uses etcd as its backing store — a distributed key-value store running as a cluster of 3 or 5 nodes, with Raft consensus.

k3s replaces etcd with **Kine** — a translation layer that speaks the etcd API but writes to SQLite under the hood. SQLite is a single file on `set-hog`'s disk. No cluster, no Raft, no quorum. If the disk fails, the cluster state is gone.

The backup story: Velero backs up the Kubernetes objects (but not the etcd/SQLite file directly). For a real production cluster, this is the most significant gap versus managed Kubernetes.

For a homelab and portfolio project, SQLite is fine. But it is worth knowing what you gave up.

## Upgrading the Control Plane

On EKS, upgrading the control plane is a button click or a Terraform resource change. The provider handles the etcd migration, the API server restart, and the compatibility matrix.

On k3s bare-metal, upgrades run through **system-upgrade-controller** using Plans:

```yaml
# server Plan (runs first, concurrency 1, cordons the node)
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-server
spec:
  version: v1.36.2+k3s1
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/control-plane: "true"
  concurrency: 1
  cordon: true
  upgrade:
    image: rancher/k3s-upgrade

---
# agent Plan (waits for server Plan to finish)
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-agent
spec:
  version: v1.36.2+k3s1
  prepare:
    image: rancher/k3s-upgrade
    args: ["prepare", "k3s-server"]
  nodeSelector:
    matchLabels:
      kubernetes.io/os: linux
```

The cluster upgraded from v1.30 to v1.36.2 this way — all 5 nodes, zero downtime on the workloads, one commit to the gitops repo.

## The CIS Benchmark

Managed providers handle most of the CIS Kubernetes Benchmark by default. They configure the API server flags, lock down the kubelet, and enforce secure defaults.

On k3s bare-metal, you do it yourself. The kubelet configuration for each node is deployed via Ansible:

```yaml
# /var/lib/kubelet/config.yaml (deployed by cis-kubelet-hardening.yml)
protectKernelDefaults: true
eventRecordQPS: 0
rotateCertificates: true
serverTLSBootstrap: true
tlsCipherSuites:
  - TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
  - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
```

Running `kube-bench` against the k3s-CIS-1.7 profile after applying the playbook:

```
== Summary node ==
16 checks PASS
0 checks FAIL
0 checks WARN
```

On a managed cluster, you never see this output. The provider ran it for you before you provisioned the first node.

## The Real Trade-off

**What you gain with self-managed:**
- Full operational ownership — you understand every component because you installed it
- Zero control-plane cost (EKS charges $0.10/hr ≈ $73/month for the control plane alone)
- Air-gap capability — the cluster functions with no internet if needed
- Your own PKI — minicloud root CA trusted in the OS, the browser, and every service
- The ability to explain the difference between the API server and the scheduler in a job interview, because you have debugged both

**What you give up:**
- HA control plane — one `set-hog` disk failure ends the cluster
- Managed etcd backups
- The ~2 hours you spend after a power failure restoring iptables rules and waiting for `set-hog` to come back up before `kubectl` works again

## Why It Matters for Platform Engineering Roles

When you sit in front of a managed Kubernetes cluster at work — and you will, because EKS is the default everywhere — you will understand what the provider is doing for you instead of treating it as magic.

You will know:
- What Kine/SQLite is, and why real production uses etcd
- Why the scheduler metrics endpoint is on `127.0.0.1` and how to expose it
- What `iptables-restore` does and why NAT matters for pod networking
- What CIS hardening actually configures, not just that it should be enabled
- What break-glass access means and why you need it separate from OIDC

Being able to say "I ran the control plane myself" is not about the homelab. It is about the depth of understanding that comes from having broken it, fixed it, and understood why.

---

*minicloud is an ongoing bare-metal Kubernetes platform project. The full architecture, runbooks, and phase-by-phase documentation are at [andrelair-platform.github.io/minicloud-platform-docs](https://andrelair-platform.github.io/minicloud-platform-docs).*
