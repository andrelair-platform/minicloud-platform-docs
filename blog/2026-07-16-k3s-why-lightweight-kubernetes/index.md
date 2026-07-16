---
slug: k3s-why-lightweight-kubernetes-bare-metal
title: "Why k3s? Installing Kubernetes on 5 Laptops with a Single curl Command"
authors: [andre]
description: >
  How k3s was installed on a 5-node bare-metal cluster — one curl command per machine —
  and why k3s beat kubeadm, microk8s, RKE2, and k0s for this specific hardware.
tags: [kubernetes, k3s, bare-metal, platform-engineering, devops, homelab]
date: 2026-07-16
image: /img/docusaurus-social-card.jpg
---

The hardware was provisioned. MAAS had PXE-booted four ThinkPads and cloud-init had written the SSH keys and hostnames. The next question was: **how do you actually get Kubernetes running on five laptops?**

There are more ways to install Kubernetes than there are Kubernetes certification paths. I ended up with k3s. Here is why — and exactly what the installation looked like.

{/* truncate */}

## The Constraint That Made the Decision

Choosing a Kubernetes distribution for this cluster was not a philosophical debate. The hardware made the decision for me.

The cluster includes a **MacBook Pro 13" (late 2012)** — an Intel Core i5-3210M (dual-core, 2012 vintage), 8 GB DDR3 RAM. That machine became `swift-mac`, running Ubuntu 22.04 as a Longhorn storage worker. The MacBook cannot be provisioned via PXE (Apple's EFI firmware does not support network boot), so Ubuntu was installed manually from a USB drive. After that, it joins the cluster exactly like any other node.

If the MacBook can run a k3s agent without being starved of RAM, any node in this cluster can. That is the selection criterion.

## The Options and Why They Fell Short

| Distribution | Why not |
|---|---|
| **kubeadm** | The "official" method — but it requires you to install containerd, a CNI plugin, and etcd separately before you can even initialise the control plane. The control plane alone consumes 2 GB+ at idle. Too heavy, too many moving parts, 40 pages of documentation before hello world. |
| **minikube / kind** | Single-node, designed for local development and CI runners. Cannot form a real multi-node bare-metal cluster. |
| **microk8s** | Snap-dependent. Hard-coupled to Ubuntu's package manager, non-trivial overhead from the snap runtime, less portable across distros. |
| **RKE2** | Rancher's hardened distribution — CIS-compliant by default, excellent for regulated enterprise production. More resource-intensive than k3s and over-engineered for a homelab. Worth revisiting if a second cluster is ever built to enterprise spec. |
| **k0s** | Comparable in weight to k3s, but the ecosystem was less mature when this project started — fewer community examples, less tooling, less documentation. |

## Why k3s

k3s wins on four criteria that actually matter for this hardware:

**1. Single binary, everything included.**  
containerd, CoreDNS, flannel (CNI), kube-proxy, and a local path provisioner are all bundled into one ~70 MB binary. There is nothing to install separately, nothing to version-pin across multiple packages, nothing to break in a gap between component versions.

**2. Minimal memory footprint.**  
The k3s control plane starts at around 300 MB of RAM on a quiet cluster. The MacBook Pro's 8 GB is not a ceiling — it is headroom. Under load, the same node runs Longhorn replicas, system daemonsets, and a k3s agent without being starved.

**3. CNCF-certified Kubernetes.**  
This is the argument that matters for a portfolio. k3s exposes exactly the same APIs as GKE, EKS, and AKS. Every concept learned here — Deployments, Services, PersistentVolumes, RBAC, Admission Webhooks — transfers directly to managed cloud Kubernetes. This is not a homelab toy; it is Kubernetes, stripped of the components that are irrelevant at this scale.

**4. Rolling upgrades with zero manual steps.**  
Once [system-upgrade-controller](https://github.com/rancher/system-upgrade-controller) is deployed, upgrading the entire cluster is a single YAML change: update the `version:` field in the Plan manifest and commit. The controller handles cordon → drain → upgrade → uncordon on each node, server before agents. The cluster was upgraded from v1.33 to v1.36.2+k3s1 this way with zero downtime across five nodes.

## The Installation

The four ThinkPad cluster nodes (set-hog, fast-skunk, fast-heron, star-kitten) were already running Ubuntu 22.04 LTS, provisioned by MAAS. `swift-mac` had Ubuntu installed manually. From there, the install is three steps.

**Step 1 — Control plane on `set-hog` (10.0.0.2):**

```bash
ssh ubuntu@10.0.0.2
curl -sfL https://get.k3s.io | sh -
```

The script detects the architecture, downloads the single binary, registers a systemd unit, and starts the k3s server. The full API server, scheduler, controller-manager, and embedded etcd are up within 30 seconds.

**Step 2 — Retrieve the join token:**

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

**Step 3 — Join each worker (fast-skunk, fast-heron, star-kitten, swift-mac):**

```bash
curl -sfL https://get.k3s.io | \
  K3S_URL=https://10.0.0.2:6443 \
  K3S_TOKEN=<token> \
  sh -
```

Four SSH sessions. Four curl commands. The cluster appears in `kubectl get nodes` within seconds of each join.

```
NAME          STATUS   ROLES                  AGE   VERSION
set-hog       Ready    control-plane,master   5m    v1.36.2+k3s1
fast-skunk    Ready    <none>                 4m    v1.36.2+k3s1
fast-heron    Ready    <none>                 3m    v1.36.2+k3s1
star-kitten   Ready    <none>                 2m    v1.36.2+k3s1
swift-mac     Ready    <none>                 1m    v1.36.2+k3s1
```

The `swift-mac` node joined over the Tailscale mesh (the MAAS controller acts as NAT). Apple's SMC does not support Wake-on-AC, so `swift-mac` does not auto-start after a power failure — every other node does. That is the only infrastructure asymmetry introduced by the hardware.

## The Analogy

The relationship between kubeadm and k3s is the same as the relationship between manually installing a Linux server package by package versus using MAAS to provision it. The outcome is identical. The path is radically different. Kubeadm gives you maximum control over every component. k3s gives you a working cluster you can build on immediately.

For a project where the goal is to demonstrate platform engineering skills — not to demonstrate ability to configure etcd from scratch — k3s is the correct choice. The cluster is now in its 75th operational phase. The distribution has never been the bottleneck.

## Automating It with Ansible

Four SSH sessions is fine for a one-time bootstrap. But after the cluster was up and `minicloud-ansible` was established as the automation layer, the natural next step was to write a playbook that can reproduce the full install from scratch — so the next cluster rebuild takes one command, not four.

The playbook lives at `playbooks/install-k3s.yml` in [minicloud-ansible](https://github.com/andrelair-platform/minicloud-ansible). It has three plays:

**Play 1 — Control plane (`set-hog`):**  
Installs the k3s server, waits for port 6443 to be ready, waits for the node to reach `Ready` state, then reads the join token into an Ansible variable.

**Play 2 — Workers (`fast-skunk`, `fast-heron`, `star-kitten`, `swift-mac`):**  
Joins one worker at a time (`serial: 1`) using the token fetched from `hostvars`. Each worker must be `Ready` before the next one starts.

**Play 3 — Kubeconfig:**  
Fetches `/etc/rancher/k3s/k3s.yaml` from the control plane, patches the server address from `127.0.0.1` to the real IP, and renames the context to `minicloud`. Saves the result to `/tmp/minicloud.yaml` on the Ansible controller.

```bash
# Dry run
ansible-playbook playbooks/install-k3s.yml --check

# Full install (pins to current cluster version)
ansible-playbook playbooks/install-k3s.yml

# Pin a different version
ansible-playbook playbooks/install-k3s.yml -e k3s_version=v1.37.0+k3s1

# Workers only (control plane already running)
ansible-playbook playbooks/install-k3s.yml --tags workers

# After the playbook — copy kubeconfig to the controller
scp /tmp/minicloud.yaml controller:~/.kube/minicloud.yaml
```

The playbook is **idempotent** — it checks for `/usr/local/bin/k3s` before installing. Re-running on an existing cluster skips the install tasks and only re-validates the `Ready` state.

### Why the install wasn't automated from day one

Two reasons. First, the k3s install is a Day-0 operation — it runs once per cluster lifetime. The effort of writing and testing a playbook outweighed the cost of four SSH commands. Second, `swift-mac` cannot be PXE-booted, so Ubuntu was installed manually via USB regardless. As long as one step is manual, the whole bootstrap sequence is effectively manual for that node.

What was automated from day one was the part that actually repeats: `system-upgrade-controller` handles every future k3s version bump as a single YAML commit. The Ansible playbook covers the edge case — rebuild from scratch — which is worth automating even if it only happens once or twice in the cluster's lifetime.

## What Comes Next

With five nodes running k3s, the next layer is networking and load balancing: MetalLB for bare-metal `LoadBalancer` services, a wildcard ingress controller, and a private CA so every internal service gets real TLS. That is covered in the next post.

---

*The full runbooks for every phase, including the exact cloud-init templates used for MAAS provisioning, live in the [Documentation](/platform-roadmap/roadmap-overview) section.*
