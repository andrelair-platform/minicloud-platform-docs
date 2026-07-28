---
slug: kubernetes-upgrades-self-managed-vs-managed
title: "Kubernetes Upgrades: What Managed Providers Handle for You and What You Own Yourself"
authors: [andre]
description: >
  A concrete look at upgrading Kubernetes — comparing EKS, GKE, and AKS one-click upgrades
  against the system-upgrade-controller Plans and GitHub Actions automation I built for my
  5-node bare-metal k3s cluster. Every decision documented, every gotcha included.
tags: [kubernetes, k3s, upgrades, platform-engineering, devops, eks, gke, aks, system-upgrade-controller, gitops]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

A Kubernetes upgrade is never just changing a version number. There is a node drain, a binary swap, a control plane migration, a pod eviction sequence, and — if you are running bare-metal — nobody to call when it goes wrong.

Managed Kubernetes providers handle most of that for you. Self-managed clusters make you own all of it. This post documents both sides concretely: what EKS, GKE, and AKS actually do during an upgrade, and what I built to automate the same process on my 5-node k3s cluster running on ThinkPad laptops.

{/* truncate */}

## The Setup

**minicloud** is a 5-node k3s cluster on bare-metal Ubuntu 22.04:

| Node | IP | Role |
|------|----|------|
| `set-hog` | 10.0.0.2 | k3s control plane (ThinkPad X390) |
| `fast-skunk` | 10.0.0.4 | worker |
| `fast-heron` | 10.0.0.7 | worker |
| `star-kitten` | 10.0.0.8 | worker |
| `swift-mac` | 10.0.0.10 | worker (MacBook Pro 2012, Ubuntu 22.04) |

k3s replaces etcd with Kine/SQLite on `set-hog`. No cloud. No managed control plane. When `set-hog` needs to upgrade, I own the sequencing, the drain, and the recovery.

---

## How Managed Kubernetes Handles Upgrades

### EKS (Amazon)

EKS splits the upgrade into two independent steps, and this split is intentional.

**Control plane upgrade** is one API call:
```bash
aws eks update-cluster-version \
  --name my-cluster \
  --kubernetes-version 1.31
```

AWS manages the etcd migration, replaces the API server pods across multiple AZs, and handles the transition from the old version to the new one without downtime on the control plane side. You never see the machines it runs on.

**Node group upgrade** is separate. Managed node groups do a rolling replace: a new EC2 instance comes up with the new AMI, gets registered, the old node is cordoned and drained, then terminated. You can tune max unavailable nodes. Spot instance node groups require more care — the eviction + replacement race can leave you under-capacity briefly.

EKS auto-upgrade exists (`enableAutoUpgrade`) but most production teams disable it and handle upgrades on a maintenance schedule. The reason: add-on compatibility. EKS clusters carry VPC CNI, kube-proxy, and CoreDNS as managed add-ons, each with their own upgrade path that must be sequenced with the control plane version. AWS will warn you about version skew but will not block an upgrade that creates it.

**What you still own on EKS:** add-on upgrades (VPC CNI, CoreDNS, kube-proxy), PodDisruptionBudget design, workload drain tolerance, post-upgrade validation.

### GKE (Google)

GKE's upgrade model is the most automated of the three. **Release channels** (Rapid, Regular, Stable) handle upgrades automatically on a schedule aligned with upstream Kubernetes releases — typically 2–4 weeks after a release hits upstream.

When GKE upgrades a node pool, it uses **surge upgrades** by default: it provisions an extra node before draining the old one, so you maintain full capacity throughout. The surge node count and max unavailable are tunable via `--max-surge` and `--max-unavailable`.

GKE also has **maintenance windows** — you define a time window when automatic upgrades are allowed. For production clusters, this is how teams prevent unexpected node churn during business hours.

The control plane upgrade on GKE is fully opaque. Google handles it, it is covered by their SLA, and you cannot observe the individual steps. For most teams this is a feature, not a gap.

**What you still own on GKE:** maintenance window configuration, PDB definitions, ensuring workloads tolerate eviction, validating add-on behaviour on new minor versions.

### AKS (Azure)

AKS upgrades are the closest to manual of the three managed options. There is no automatic upgrade by default — you schedule it:

```bash
az aks upgrade \
  --resource-group my-rg \
  --name my-cluster \
  --kubernetes-version 1.31.0
```

AKS performs a rolling upgrade: the control plane first, then node pools one surge node at a time. Like GKE, AKS uses a surge node approach — it provisions a new node, moves workloads, then removes the old node.

AKS also supports **node image upgrades** separately from Kubernetes version upgrades. You can update the OS image (kernel patches, containerd versions) without changing the Kubernetes minor version — useful for CVE patching between upgrades.

**What you still own on AKS:** triggering upgrades (or configuring auto-upgrade policies), PDB design, node pool sequencing if you have multiple pools with different taints.

### The Common Pattern

All three providers share the same upgrade sequence under the hood:

1. Upgrade the control plane (invisible to you, handled by provider)
2. For each worker node: cordon → drain → replace binary or AMI → uncordon
3. Verify node readiness before moving to the next

What they remove from your plate: managing the etcd data migration, sequencing the API server version across replicas, handling the control plane downtime window, and recovering from partial failures mid-upgrade.

What they cannot remove from your plate: designing workloads that tolerate eviction.

---

## How I Handle Upgrades on Bare-Metal k3s

### The Tool: system-upgrade-controller

k3s's upgrade mechanism is [system-upgrade-controller](https://github.com/rancher/system-upgrade-controller) — a Kubernetes controller that reads `Plan` CRDs and runs upgrade Jobs on matching nodes.

The Plan CRD is declarative. You commit a target version, ArgoCD syncs it, the controller handles the rest:

```yaml
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-server
  namespace: system-upgrade
spec:
  concurrency: 1
  nodeSelector:
    matchExpressions:
      - key: node-role.kubernetes.io/control-plane
        operator: Exists       # not matchLabels: "true" — the value varies across versions
  cordon: true
  drain:
    force: true
    ignoreDaemonSets: true     # required: Longhorn DaemonSet would block drain otherwise
    deleteEmptydirData: true
    timeout: 120
  version: v1.36.2+k3s1
  upgrade:
    image: rancher/k3s-upgrade
  tolerations:
    - key: CriticalAddonsOnly
      operator: Exists
    - effect: NoExecute
      operator: Exists
    - effect: NoSchedule
      operator: Exists
---
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-agent
  namespace: system-upgrade
spec:
  concurrency: 1
  nodeSelector:
    matchExpressions:
      - key: node-role.kubernetes.io/control-plane
        operator: DoesNotExist
  cordon: true
  drain:
    force: true
    ignoreDaemonSets: true
    deleteEmptydirData: true
    timeout: 120
  prepare:
    image: rancher/k3s-upgrade
    args: [prepare, k3s-server]   # blocks until server Plan completes
  version: v1.36.2+k3s1
  upgrade:
    image: rancher/k3s-upgrade
  tolerations:
    - key: CriticalAddonsOnly
      operator: Exists
    - effect: NoExecute
      operator: Exists
    - effect: NoSchedule
      operator: Exists
```

**Upgrade sequence enforced by these Plans:**

1. `k3s-server` Plan runs on `set-hog` (control plane) — cordon, drain, install new k3s binary, uncordon
2. `k3s-agent` Plan's `prepare` step waits for server Plan to complete
3. Workers upgrade one at a time (`concurrency: 1`) — fast-skunk, fast-heron, star-kitten, swift-mac

This mirrors what EKS, GKE, and AKS all do internally. The difference is that here it is visible, auditable YAML checked into git.

### The Gotchas (Undocumented)

Three issues that are not in the system-upgrade-controller docs and that I hit when initially writing these Plans:

**1 — `matchLabels: "true"` breaks on some k3s versions**

The `node-role.kubernetes.io/control-plane` label exists across all k3s versions, but its value (`""` vs `"true"`) varies. `matchLabels: "true"` silently matches nothing on clusters where the value is empty. The fix is `operator: Exists` — match on the key regardless of value.

**2 — `cordon: true` alone does not evict pods**

`cordon: true` prevents new pods from being scheduled on the node. It does not evict existing pods. Without the `drain:` block, running pods stay on the node during the upgrade, including StatefulSets with PVCs — which can cause data corruption if the k3s binary restarts under them.

**3 — `ignoreDaemonSets: true` is mandatory with Longhorn**

Longhorn runs a DaemonSet (`longhorn-manager`) on every node. A drain without `ignoreDaemonSets: true` will wait for that DaemonSet pod to terminate before proceeding — but DaemonSet pods are immediately rescheduled, so the wait never ends. The drain hangs until `timeout` fires, then fails.

**4 — ArgoCD `selfHeal` conflicts with SUC upgrade Jobs**

system-upgrade-controller creates Job pods on target nodes during the upgrade. ArgoCD, if `selfHeal: true` is active on the sync, sees these Job pods as "out of sync" resources (they are not in git) and may delete them mid-upgrade. The safe practice: pause auto-sync or add an `ignoreDifferences` entry for Job resources before triggering an upgrade.

### The Automation: Weekly GitHub Actions

Committing a new version by hand works, but it requires remembering to check. I built a GitHub Actions workflow that runs every Monday at 08:00 UTC, fetches the latest k3s release from the GitHub API, and opens a PR if it finds a newer version:

```yaml
name: k3s upgrade PR

on:
  schedule:
    - cron: '0 8 * * 1'
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: false

jobs:
  check-and-bump:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITOPS_TOKEN }}

      - name: Get latest k3s release
        id: latest
        run: |
          LATEST=$(curl -sf \
            -H "Authorization: Bearer ${{ secrets.GITHUB_TOKEN }}" \
            "https://api.github.com/repos/k3s-io/k3s/releases/latest" \
            | jq -r '.tag_name')
          echo "latest=$LATEST" >> "$GITHUB_OUTPUT"

      - name: Get current version from Plan YAML
        id: current
        run: |
          # grep '^ *version:' skips comment lines that also contain the word 'version:'
          CURRENT=$(grep -m1 '^ *version:' manifests/system-upgrade/01-k3s-plans.yaml \
            | awk '{print $2}')
          echo "current=$CURRENT" >> "$GITHUB_OUTPUT"

      - name: Compare and bump
        run: |
          if [[ "${{ steps.latest.outputs.latest }}" != "${{ steps.current.outputs.current }}" \
             && "${{ inputs.dry_run }}" != "true" ]]; then
            # bump version in both Plans (server + agent share the same version line)
            sed -i "s/${{ steps.current.outputs.current }}/${{ steps.latest.outputs.latest }}/g" \
              manifests/system-upgrade/01-k3s-plans.yaml
            # ... then open a PR
          fi
```

The PR body includes a pre-merge checklist:

- Read the k3s release notes for API deprecations
- Check the containerd version bump (Chaos Mesh's `socketPath` is coupled to the containerd socket path — a containerd major version bump can break chaos experiments)
- Verify no PodDisruptionBudgets block the drain
- Check Longhorn volume replica count
- Take a kine/SQLite backup **before** the upgrade

The last point is what a managed provider does silently before every upgrade. On bare-metal, the checklist enforces it.

---

## Side-by-Side Comparison

| Dimension | minicloud (k3s bare-metal) | EKS | GKE | AKS |
|-----------|---------------------------|-----|-----|-----|
| **Who triggers the upgrade** | Developer — PR to bump `version:` in git | Developer or auto-upgrade policy | Release channel (automatic) or developer | Developer (or auto-upgrade policy) |
| **Control plane migration** | system-upgrade-controller on `set-hog` — visible | AWS — opaque, zero downtime | Google — opaque, SLA-backed | Azure — rolling, visible progress in portal |
| **Worker sequencing** | `concurrency: 1`, server Plan first, then agent Plan | Managed node group: surge + drain per node | Surge upgrade: new node before draining old | Surge: new node before draining old |
| **Pre-upgrade backup** | Manual kine/SQLite backup via PR checklist | AWS backs up etcd automatically | Google backs up etcd automatically | Azure backs up etcd automatically |
| **Rollback** | Restore kine backup + reinstall old binary on each node | Node group rollback possible; control plane rollback not supported | Not supported (no rollback to previous minor version) | Not supported |
| **Add-on sequencing** | Manual (ArgoCD app versions are independent) | Managed add-ons require separate upgrade step | Managed automatically by GKE | Manual for most add-ons |
| **Version lag** | You choose when; k3s releases follow upstream by ~1–2 weeks | N-2 supported versions; new versions available ~2 months post-upstream | Release channels: Rapid (~2 weeks), Regular (~4 weeks), Stable (~6 weeks) | ~2 months post-upstream for GA support |
| **Observability** | `kubectl get nodes -w`, ArgoCD sync status, Longhorn health | CloudWatch Container Insights, EKS upgrade insights dashboard | Cloud Logging, GKE upgrade notifications | Azure Monitor, AKS upgrade events |
| **What breaks silently** | DaemonSet drain hang, ArgoCD selfHeal deleting SUC Jobs, `swift-mac` needs manual power-cycle after OS hang | Add-on version skew after control plane upgrade | Rare — GKE handles most compatibility internally | Node pool version skew if you have multiple pools |
| **Cost** | Electricity (hardware already owned) | $0.10/hr per cluster ($73/month control plane alone) | Free control plane on Standard tier; Autopilot adds per-workload cost | Free control plane; pay for node VMs |

---

## The Honest Trade-off

Managed providers remove the mechanical parts: binary installation, etcd migration, surge node provisioning, post-upgrade readiness checks. They do not remove the design work: PodDisruptionBudgets, drain tolerance, resource limits that allow eviction, and workload health checks.

Self-managed k3s removes none of the mechanical parts. You write the Plan CRDs. You tune the drain spec. You build the automation. You own the backup. But the upside is that every step is in git, every decision is auditable, and you understand what is actually happening when you run `kubectl get nodes -w` and watch a node disappear and come back.

The GitHub Actions workflow I built opens a PR once a week if k3s releases something new. The PR body is a six-point checklist. Merging it takes two minutes. The upgrade itself takes about twenty minutes across five nodes, unattended.

That is the self-managed bargain: more work upfront to understand the system, less mystery when something goes wrong.

---

## What Gets Automated vs What Stays Manual

**Automated:**
- Weekly detection of new k3s releases (GitHub Actions)
- PR with bumped version in both Plans (server + agent)
- Node drain and upgrade sequence (system-upgrade-controller)
- ArgoCD sync of the updated Plans

**Still manual:**
- Reading the release notes for breaking changes
- kine/SQLite backup before merge
- Post-upgrade validation (`kubectl get nodes`, `kubectl get pods -A`, Longhorn volume health)
- `swift-mac` manual intervention if the upgrade stalls (Apple SMC does not support remote power-cycle)

The manual items are intentionally manual. A fully autonomous upgrade that skips the release notes check and the backup is a fast path to a production incident. The PR is not a gate to slow things down — it is the moment where a human reads the release notes and decides the upgrade is safe to apply.

That is the same decision a platform team makes when they un-pause a GKE maintenance window or approve an EKS node group upgrade. The difference is that on bare-metal, the decision and its consequences are entirely yours.
