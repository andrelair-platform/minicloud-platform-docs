---
slug: ansible-bare-metal-node-bootstrap
title: "The Layer Below GitOps: How ~200 Lines of Ansible Keep a Bare-Metal Cluster Reproducible"
authors: [andrelair]
tags: [ansible, bare-metal, kubernetes, k3s, gitops, longhorn, harbor, cis, automation, platform-engineering, idempotency]
date: 2026-09-19
description: "GitOps reconciles everything inside the cluster — but not the operating system beneath it. This is how minicloud-ansible codifies the node-level prerequisites (iSCSI, multipath, registry mirrors, default routes, CIS hardening) so any node can be reimaged or added with a single idempotent playbook run."
---

ArgoCD reconciles everything *inside* my cluster: 95 applications, from Vault to the AI gateway, all declared in Git and continuously synced. But ArgoCD cannot format a disk, install `open-iscsi`, or fix a default route. There is a layer **below** GitOps — the operating system on each bare-metal node — and if that layer isn't codified, "reproducible infrastructure" is a half-truth.

For the ktayl-solution information system, that layer is owned by one small repo: **[`minicloud-ansible`](https://github.com/andrelair-platform/minicloud-ansible)**. It's about 200 lines of task code across four roles, and it does exactly one job well: make the node OS prerequisites for a 6-node k3s cluster **reproducible and auditable**. This post is how I use it to operate the organisation's platform.

{/* truncate */}

## The scope boundary: what Ansible owns, and what it deliberately doesn't

The platform runs on refurbished ThinkPads (plus one 2012 MacBook Pro) provisioned by MAAS. The delivery model is trunk-based GitOps: CI builds artifacts, Kargo promotes them, ArgoCD deploys them. So where does Ansible fit? Precisely in the gap the other tools can't reach:

| Layer | Owner | Example |
|---|---|---|
| Bare metal / machine lifecycle | MAAS + OpenTofu | enrol & commission a ThinkPad as a node |
| **Node OS prerequisites** | **Ansible (this repo)** | **`open-iscsi`, multipath blacklist, registry mirror, default route, CIS kubelet config** |
| k3s cluster & workloads | GitOps (ArgoCD + Kargo) | 95 Applications, Helm values, promotion |

The single most important design decision in this repo is a **non-goal**: it does **not** install k3s. The cluster is live and stateful — Longhorn replicas, Harbor registry data, the monitoring TSDB, the kine/SQLite control-plane store. Re-running a `curl | sh` k3s installer against a healthy node has no upside and a real risk of corrupting cluster state if anything in the installer drifts. So the repo covers **only the OS-level prerequisites that must be re-applied if a node is reimaged** — and the k3s install stays a documented, deliberate, manual step. Knowing what *not* to automate is part of operating safely.

## The four roles that keep a node correct

The bootstrap playbook, `site.yml`, is four lines — it composes four roles against the `cluster` inventory group:

```yaml
- name: Bootstrap minicloud cluster nodes (post-MAAS, pre-k3s)
  hosts: cluster
  roles:
    - common
    - longhorn-prereq
    - k3s-registries
    - network
```

Each role encodes a lesson.

### `common` — base utilities, and one that isn't obvious

`htop`, `vim`, `curl`, `jq`, `rsync`… and `sqlite3`. That last one isn't for comfort: the control-plane node runs an online backup of the k3s state database with `sqlite3 .backup`, which is WAL-safe on a live DB. It's harmless on the workers, so it ships to every node rather than being a special case. Small, but it's the difference between "I have a backup" and "I have a backup that doesn't corrupt under load."

### `longhorn-prereq` — the role that earned its multipath blacklist

This is the role with a war story. Longhorn exports each volume as an iSCSI target (vendor `IET`, product `VIRTUAL-DISK`). If `multipathd` is running, it *claims* those `/dev/sdX` devices as `mpathN` and holds them at the device-mapper layer — so kubelet's mount fails with `already mounted or mount point busy`, and pods hang forever in `ContainerCreating`.

The older nodes carried a hand-added blacklist. Then I added `loving-gannet`, the newest node — and it hit the bug immediately, because it *never had the blacklist the others had*. That's the exact failure mode Ansible exists to prevent: undocumented, per-node manual fixes that a new node silently lacks. So the fix went into the role:

```yaml
- name: Blacklist Longhorn iSCSI devices from multipath
  ansible.builtin.copy:
    dest: /etc/multipath.conf
    content: |
      blacklist {
          device {
              vendor "IET"
              product "VIRTUAL-DISK"
          }
      }
  when: multipathd_unit.stat.exists
  notify: Flush and restart multipathd
```

Now the blacklist is a property of *being a node in this cluster*, not a thing I remembered to do. Any future node gets it on its first `site.yml` run. (The role also installs `open-iscsi` and enables `iscsid`, Longhorn's other hard requirement.)

### `k3s-registries` — Harbor as a mirror, with a fallback that prevents self-inflicted outages

Every image pull on the cluster routes through the in-cluster Harbor as a proxy-cache mirror — `docker.io`, `ghcr.io`, `quay.io`, `registry.k8s.io`. This role drops `/etc/rancher/k3s/registries.yaml` (plus the internal root-CA cert, so pulls are HTTPS-verified) onto each node.

The subtlety is in the fallback. Each mirror lists Harbor **first** and the public upstream **second**:

```yaml
mirrors:
  "docker.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/docker-hub"
      - "https://registry-1.docker.io"
```

That ordering is the whole point: if Harbor is down — a pod restart, an upgrade — k3s falls through to the public registry instead of the entire cluster losing the ability to pull images. It avoids the classic "the registry restart broke the cluster" trap. A registry mirror is only a good idea if it fails open.

### `network` — a one-file role for the boring problem that takes a cluster down

A single netplan file pins the default route via `10.0.0.1`. It's trivial — until a node reboots without a default gateway and drops off the network. The role also carries a real gotcha in its metadata: since Ubuntu 24.04, netplan **refuses world-readable files**, so the file must be `0600`. The handler runs `netplan generate` (to validate syntax) *before* `netplan apply` — because the one thing worse than a bad route is applying a bad route to a node you then can't reach.

## Day-2: rolling upgrades without downtime

Bootstrap is once-per-node. The repo's other job is ongoing maintenance, and `upgrade.yml` is where the organisation gets zero-downtime patching. It runs `serial: 1` — strictly one node at a time — and for each node:

1. `kubectl drain` (delegated to the controller) — cordon + evict, respecting PodDisruptionBudgets
2. `apt update` + `apt upgrade` (**safe** upgrade — never removes packages)
3. reboot **only if** `/var/run/reboot-required` exists (i.e. a kernel landed)
4. wait for the node to report `Ready`
5. `kubectl uncordon`

The pre-flight is codified in the playbook's own comments as an operating contract: every workload should have ≥2 replicas with anti-affinity across workers, and every Longhorn volume ≥2 healthy replicas — so the drain can *fail safe* if it can't relocate a volume rather than risk data. This is how a solo-operated platform patches its OS across a live cluster without taking the organisation's services offline.

## Beyond bootstrap: hardening and migrations as playbooks

The same idempotent model extends to bigger changes, kept as separate, reviewable playbooks:

- **`cis-kubelet-hardening.yml`** writes a CIS-benchmarked `/var/lib/kubelet/config.yaml` (read-only port `0`, cert rotation, strong TLS cipher suites only, pod PID limits) and wires k3s to load it — then deploys `kube-bench` to prove it. Result: **16/16 PASS** on the k3s-cis-1.7 kubelet controls, on every worker. Security posture as code, with its own evidence.
- **`cilium-migration.yml`** performed the rolling Flannel→Cilium eBPF CNI swap on a live cluster.
- **`fix-grub-timeout.yml`** is the kind of small, real fix that becomes a repeatable playbook instead of a forgotten SSH session.

## The discipline that makes it trustworthy: `changed=0`

None of this matters if the code doesn't match reality. The workflow that keeps them honest is a **drift audit** — a check-mode run that changes nothing and reports what *would* change:

```bash
ansible-playbook playbooks/site.yml --check --diff
```

Read the `PLAY RECAP`. If every host reports `changed=0`, the codified state **is** reality. If a host reports `changed > 0`, that's drift — either a role that no longer matches the node, or a node that someone touched by hand. Either way you investigate the diff *before* applying. And every role must report `changed=0` on a second consecutive run — the definition of idempotency, and the bar for a role being "done."

For a regulated context (the ktayl-solution IS simulates a French insurer, with DORA in scope), that property is worth as much as the automation itself: at any moment I can *prove*, non-destructively, that the fleet's OS layer matches version-controlled, reviewed intent — and reconstruct any node from it.

## Why this small repo matters to the organisation

It's tempting to see 200 lines of Ansible next to 95 GitOps applications and call it an afterthought. It isn't. It's the **floor** the whole platform stands on:

- **Reproducibility.** A reimaged or brand-new node becomes a correct cluster member with one `site.yml` run — no tribal knowledge, no per-node snowflakes (the `loving-gannet` lesson, made permanent).
- **Safety.** The Harbor-with-fallback mirror and the drain-first upgrade both fail *open*, so routine operations can't cascade into outages.
- **Auditability.** `--check --diff` turns "the servers are configured correctly" from a claim into a verifiable, repeatable fact.
- **A clean scope boundary.** MAAS provisions metal, Ansible makes the OS correct, GitOps runs the cluster. Each tool does the job it's best at, and the seams are explicit.

GitOps gets the spotlight because it runs the applications the business sees. But the applications only run because, underneath them, every node is boringly, provably correct — and that's the job this little repo does for the organisation, every single time a node comes or goes.

*The repo is public: [`andrelair-platform/minicloud-ansible`](https://github.com/andrelair-platform/minicloud-ansible).*
