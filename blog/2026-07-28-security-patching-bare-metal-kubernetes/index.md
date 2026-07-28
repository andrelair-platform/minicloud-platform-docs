---
slug: security-patching-bare-metal-kubernetes
title: "Security Patching a Self-Managed Kubernetes Cluster — Five Layers, Zero Magic"
authors: [andre]
description: >
  On a managed Kubernetes provider, security patching is largely invisible. On a self-managed
  k3s cluster, you own every layer: OS kernel patches, k3s binary CVEs, container base images,
  Helm chart versions, and CIS posture drift. This post documents the full patching stack on
  minicloud — what runs automatically, what requires a PR, and how each layer compares to
  EKS, GKE, and AKS.
tags: [kubernetes, k3s, security, patching, cve, renovate, kured, cis, bare-metal, platform-engineering, eks, gke, aks, devops]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

Managed Kubernetes providers make security patching look simple. You enable auto-upgrade on GKE, you click "update node group" on EKS, and the CVE goes away. What actually happens is that the provider patches the OS image, replaces the node, validates the binary, and restores your workloads — all in the time it takes to refresh the AWS console.

On a self-managed cluster, none of that is automatic. You own the OS. You own the runtime. You own the base images. You own the Helm chart versions. And when a CVE drops, you own the decision about which layer it lives in and which mechanism will close it.

This post documents all five patching layers on **minicloud** — a 5-node k3s cluster on bare-metal ThinkPads — what's automated, what requires a PR, and where the gaps were and how they were closed.

{/* truncate */}

## The Patching Surface

Security patches on a Kubernetes cluster don't form a single queue. They live across five independent layers, each with a different toolchain, different cadence, and different failure mode if ignored.

| Layer | What it covers | Worst-case if ignored |
|---|---|---|
| OS packages | glibc, OpenSSL, kernel CVEs | Node-level compromise via unpatched kernel |
| k3s binary | k3s, containerd, runc, CNI plugins | Container escape, privilege escalation |
| Container base images | `FROM golang:1.25`, `FROM node:22-alpine`, etc. | Vulnerable runtime inside every pod |
| Helm chart versions | Application chart updates with CVE fixes | Workload-level vulnerabilities (e.g. Grafana auth bypass) |
| CIS posture | kubelet config, RBAC, audit policy | Cluster misconfiguration drifts after upgrades |

Each layer requires its own tool and its own trigger. There is no single "patch everything" button on bare-metal.

---

## Layer 1 — OS Packages: `unattended-upgrades` + kured

All five nodes run **Ubuntu 22.04**. OS-level security patches (glibc, OpenSSL, curl, kernel CVEs) arrive through `apt` from the Ubuntu security pocket.

### Automatic patch download

`unattended-upgrades` is configured on every node to apply security pocket updates automatically:

```ini
# /etc/apt/apt.conf.d/50unattended-upgrades
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::Automatic-Reboot "false";   // kured handles reboots
Unattended-Upgrade::Remove-Unused-Dependencies "true";
```

`Automatic-Reboot "false"` is intentional — rebooting a Kubernetes node during a working day without draining it first would evict pods non-gracefully. Instead, `unattended-upgrades` writes `/var/run/reboot-required` when a kernel or libc patch requires a reboot. That file is the handoff signal to kured.

### Automated kernel reboot sequencing: kured

**kured** (Kubernetes Reboot Daemon) runs as a DaemonSet — one pod per node. It watches for `/var/run/reboot-required` on each node's host filesystem and, when it finds one, issues a Kubernetes-native drain followed by a reboot:

```
kured pod sees /var/run/reboot-required on fast-heron
→ acquires reboot lock (only one node reboots at a time)
→ kubectl cordon fast-heron
→ kubectl drain fast-heron (respects PDBs — waits for Longhorn rebalance)
→ nsenter → systemctl reboot
→ node comes back → kubelet re-registers → kured uncordons
→ releases lock → next node can proceed
```

The cluster has been running kured for over three weeks. Current status:

```bash
kubectl get ds -n kured
# NAME    DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE
# kured   5         5         5       5            5
```

One pod per node, including `set-hog` (control plane). The drain respects all PodDisruptionBudgets — Longhorn's DaemonSet is `ignoreDaemonSets: true`, and application PDBs enforce minimum replica counts. A kernel patch that lands on `fast-heron` at 03:00 will have the node back in service before morning.

**The swift-mac caveat:** `swift-mac` is a MacBook Pro 2012. kured can drain and reboot it via normal Kubernetes mechanisms. If the MacBook hangs during the boot process (Apple SMC behaviour), kured cannot power-cycle it — physical intervention is required. This is a known gap accepted for this hardware.

**What managed providers do instead:** cloud worker nodes are VMs. OS patching means replacing the VM with a new one built from a patched AMI (EKS) or a new node image (GKE, AKS). There is no in-place kernel patch and no reboot — the node is terminated and a fresh one joins. The "dirty node" problem disappears. kured is unnecessary.

---

## Layer 2 — k3s Binary: system-upgrade-controller + Weekly GitHub Actions

k3s bundles containerd, runc, and CNI plugins into a single binary. A CVE in any of these components (including the k3s API server itself) is fixed by upgrading k3s. The binary version also carries the Kubernetes minor version — `v1.36.2+k3s1` means k3s 1 on top of Kubernetes 1.36.2.

### Detection: weekly GitHub Actions workflow

A workflow runs every Monday at 08:00 UTC, fetches the latest k3s release from the GitHub API, and compares it to the version in the system-upgrade Plans:

```yaml
- name: Get latest k3s release
  run: |
    LATEST=$(curl -sf \
      -H "Authorization: Bearer ${{ secrets.GITHUB_TOKEN }}" \
      "https://api.github.com/repos/k3s-io/k3s/releases/latest" \
      | jq -r '.tag_name')

- name: Get current version
  run: |
    CURRENT=$(grep -m1 '^ *version:' \
      manifests/system-upgrade/01-k3s-plans.yaml | awk '{print $2}')
```

If versions differ, the workflow bumps `version:` in both system-upgrade Plans and opens a PR with a six-point pre-merge checklist: release notes, containerd version check, PDB review, Longhorn replica health, kine/SQLite backup.

### Application: system-upgrade-controller Plans

Merging the PR triggers ArgoCD sync → system-upgrade-controller reads the new Plan → upgrades run:

1. `k3s-server` Plan: cordon `set-hog`, drain (with `ignoreDaemonSets: true`, 120s timeout), swap binary, uncordon
2. `k3s-agent` Plan's `prepare` step waits for server completion
3. Workers upgrade one at a time (`concurrency: 1`) — drain, swap, uncordon

The whole sequence runs unattended. Monitor with:

```bash
ssh controller "kubectl get nodes -w && kubectl get jobs -n system-upgrade -w"
```

**What managed providers do instead:** the k3s binary equivalent on EKS is the node AMI + Kubernetes control plane version. AWS patches the control plane silently. Node AMIs are updated via managed node group rolling replace — new AMI, new node, no in-place binary upgrade. GKE does the same via node pool auto-upgrade on release channels. You never touch a binary.

---

## Layer 3 — Container Base Images: Renovate + Harbor/Trivy

This is the most frequently overlooked patching layer and the one that affects the most CVEs in practice. Every custom image built from `FROM ubuntu:22.04`, `FROM golang:1.25-alpine`, or `FROM node:22-alpine` inherits the CVE surface of that base image at build time. When `ubuntu:22.04` patches a critical OpenSSL vulnerability, every image built on top of it needs a rebuild.

### What was missing

The six image repos (minicloud-backstage, minicloud-open-webui, minicloud-onlyoffice, minicloud-plane, platform-demo, ktayl-solution-web) had no automated mechanism to detect when their base images had new security releases. A CVE in `golang:1.25-alpine` would sit unpatched until someone noticed.

### The fix: self-hosted Renovate across all repos

**Renovate** is a dependency update tool that watches package manifests — Dockerfiles, `go.mod`, `package.json`, Helm chart `targetRevision`, ArgoCD Application `targetRevision` — and opens PRs when newer versions are available.

A single GitHub Actions workflow in `minicloud-gitops` runs Renovate every Monday 06:00 UTC across all seven platform repos:

```yaml
# .github/workflows/renovate.yml
name: Renovate
on:
  schedule:
    - cron: '0 6 * * 1'   # Monday 06:00 UTC
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: false
jobs:
  renovate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: renovatebot/github-action@v46.1.21
        with:
          configurationFile: .github/renovate-global.json
          token: ${{ secrets.GITOPS_TOKEN }}
        env:
          LOG_LEVEL: info
          RENOVATE_DRY_RUN: ${{ inputs.dry_run == true && 'full' || 'null' }}
```

The global config lists all seven repos:

```json
{
  "repositories": [
    "andrelair-platform/minicloud-gitops",
    "andrelair-platform/minicloud-backstage",
    "andrelair-platform/minicloud-open-webui",
    "andrelair-platform/minicloud-onlyoffice",
    "andrelair-platform/minicloud-plane",
    "andrelair-platform/platform-demo",
    "andrelair-platform/ktayl-solution-web"
  ],
  "onboarding": false,
  "requireConfig": "optional"
}
```

Each repo has its own `renovate.json` that enables the relevant managers and groups updates:

| Repo | Managers | Grouping strategy |
|---|---|---|
| `minicloud-gitops` | `argocd`, `helm-values` | Minor/patch grouped weekly; major requires dashboard approval |
| `minicloud-backstage` | `dockerfile`, `npm` | npm packages grouped; Backstage major version = manual review |
| `minicloud-open-webui` | `dockerfile` | Label `check-default-changes` — Open WebUI changes env defaults between versions |
| `minicloud-onlyoffice` | `dockerfile` | Label `check-ca-cert` — CA injection path changes with Node.js version inside image |
| `platform-demo` | `dockerfile`, `gomod` | Go modules grouped; golang major = manual review |
| `minicloud-plane` | `dockerfile`, `gomod` | Same — NATS client compatibility check on major |
| `ktayl-solution-web` | `dockerfile`, `npm` | Astro + Tailwind grouped; Astro major = manual review |

Private Harbor images (`harbor.10.0.0.200.nip.io/library/*`) are explicitly excluded — Renovate cannot reach the internal registry from GitHub Actions runners.

### Harbor Trivy scanning

Harbor runs Trivy on every pushed image. The scan runs at push time and results are visible in the Harbor UI under each image tag. Images with CRITICAL CVEs can be flagged (and optionally blocked from pull) via Harbor's project policy.

```bash
# Check current scan status for an image
/usr/bin/curl --cacert ~/minicloud-ca.crt \
  "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/library/repositories/platform-demo/artifacts" \
  -u "admin:$(cat ~/.harbor-admin)" | python3 -m json.tool | grep -A3 '"scan"'
```

### The patching loop

When Renovate detects `golang:1.25-alpine` has a new patch version:
1. It opens a PR in `platform-demo` bumping the Containerfile
2. CI builds and pushes the new image to Harbor
3. Trivy scans it at push time
4. If clean, the PR is reviewed and merged
5. ArgoCD detects the new image tag in gitops and rolls out

End-to-end: a base image CVE gets a PR opened within a week of the upstream release. Without Renovate, it waits until someone manually checks.

**What managed providers do instead:** cloud providers patch base images at the hypervisor layer (new AMI = new OS, new containerd, new kernel). But your application's `FROM golang:1.25-alpine` in a Dockerfile is still your responsibility — ECR image scanning, GCR Artifact Registry scanning, and ACR scanning work exactly like Harbor Trivy. No managed provider auto-rebuilds your application containers when their base images update. Renovate fills the same gap on any Kubernetes platform.

---

## Layer 4 — Helm Chart Versions: Renovate + ArgoCD

Helm charts carry their own CVE surface. `kube-prometheus-stack 65.x` might ship a Grafana version with a known authentication bypass. `cert-manager v1.14` might have a webhook vulnerability. These are application-level CVEs that live inside the chart, not in the OS or the runtime.

### What Renovate scans in minicloud-gitops

The `argocd` manager reads every `apps/*.yaml` file and extracts `targetRevision`:

```yaml
# apps/cert-manager.yaml
spec:
  sources:
    - repoURL: https://charts.jetstack.io
      chart: cert-manager
      targetRevision: "v1.20.2"   # ← Renovate watches this
```

When cert-manager releases `v1.20.3` with a CVE fix, Renovate opens a PR bumping `targetRevision`. The PR triggers ArgoCD sync after merge. The chart upgrade rolls out with the cert-manager controller restarting on the new version.

### Special cases requiring manual review

Some charts get explicit `dependencyDashboardApproval: true` regardless of update type:

- **ArgoCD** — ArgoCD upgrading itself has unusual risk: a failed upgrade can prevent further syncs
- **Vault** — secret backend changes require testing ESO + application connectivity before rollout
- **Authentik** — SSO upgrades affect all authentication paths; a bad rollout logs out all users

Minor patches to these are still surfaced by Renovate, but they sit on the Dependency Dashboard issue until explicitly approved.

**What managed providers do instead:** managed add-ons (EKS VPC CNI, GKE Cloud DNS, AKS Azure CNI) are patched by the provider with their own release schedule. Your application Helm charts — the ones you own — require the same Renovate + ArgoCD pattern on EKS/GKE/AKS as on bare-metal. This layer is not simplified by choosing a managed provider.

---

## Layer 5 — CIS Hardening: kube-bench + Ansible

The CIS Kubernetes Benchmark defines hardening requirements for kubelet configuration, RBAC, audit policies, and node-level settings. The minicloud cluster passes **CIS k3s-1.7 at 16/16** on all worker nodes, applied via Ansible playbooks.

The problem with point-in-time hardening: it drifts. A k3s upgrade changes kubelet flags. An Ansible run that modifies containerd config can reset hardening settings. After any infrastructure change, the CIS posture needs re-verification.

### Re-running kube-bench after upgrades

```bash
# Run kube-bench as a Job on each node
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-node.yaml

# Wait and collect results
kubectl wait --for=condition=complete job/kube-bench --timeout=120s
kubectl logs -l app=kube-bench
```

Expected output after a clean k3s upgrade: all 16 checks PASS. Any FAIL or WARN is an Ansible remediation run.

### What CIS hardening actually covers

- kubelet `--protect-kernel-defaults`, `--read-only-port 0`, `--anonymous-auth false`
- containerd runtime configuration (no `--allow-privileged` without explicit annotation)
- RBAC: no `cluster-admin` bindings for service accounts
- Audit policy: API server audit log enabled with minimum verbosity
- NetworkPolicies: default-deny-all in production namespaces

**What managed providers do instead:** EKS, GKE, and AKS enforce CIS Level 1 defaults by default. Managed node groups launch from hardened AMIs/images with most kubelet flags pre-configured. You can request CIS Level 2 hardening on GKE via node pool config. The operational cost of CIS hardening — verifying it after every upgrade — disappears on managed clusters because the base image is always the provider's known-good state.

---

## The Secrets and TLS Layer

Not strictly a "patch" layer, but secret rotation and TLS cert renewal are security maintenance operations that follow the same discipline.

**cert-manager** handles TLS certificate renewal automatically. Certificates from Let's Encrypt (via ACME) and from the internal minicloud CA are renewed before expiry with no human interaction. The minicloud root CA cert is 10 years validity — manual renewal is on the calendar for 2034.

**Vault + ESO** handles application secrets. Secret rotation is currently manual: update the secret in Vault, ESO picks up the new value via `ExternalSecret` sync interval, pods pick up the new env var on next restart (or via Reloader if annotated). Automated rotation is a future work item.

**Authentik OIDC tokens** are short-lived (access tokens: 5 minutes, refresh tokens: 30 days). No manual rotation needed — OIDC clients handle token refresh automatically.

---

## The Full Patching Automation Map

```
Every night (02:30 UTC)
└── kine-backup.sh (controller systemd timer)
    └── WAL-safe SQLite backup to MinIO (pre-patch safety net)

Every night (unattended-upgrades)
└── apt security pocket → downloads patches to all nodes
    └── if kernel/libc → writes /var/run/reboot-required
        └── kured detects → drain → reboot → uncordon (one node at a time)

Every Monday 06:00 UTC (Renovate workflow)
└── Scans 7 repos for:
    ├── Dockerfile/Containerfile base image versions
    ├── go.mod module versions
    ├── package.json npm versions
    ├── ArgoCD app targetRevision (Helm chart versions)
    └── helm-values image tags
    → Opens grouped PRs for minor/patch updates
    → Flags major updates for manual review

Every Monday 08:00 UTC (k3s upgrade workflow)
└── Queries GitHub API for latest k3s release
    → If newer than Plans: opens PR bumping version in both Plans
    → After merge: ArgoCD syncs → system-upgrade-controller upgrades nodes

After every k3s upgrade (manual, ~5 minutes)
└── kubectl apply kube-bench Job
    └── Verify 16/16 CIS checks PASS
    └── Run Ansible remediation if any FAIL
```

---

## Side-by-Side: Bare-Metal vs Managed Providers

| Patching layer | minicloud (bare-metal k3s) | EKS | GKE | AKS |
|---|---|---|---|---|
| **OS security patches** | `unattended-upgrades` downloads; kured drains + reboots | New AMI per node group update; no in-place patching | New node image per pool update | Node image upgrade (separate command) |
| **Kernel reboot sequencing** | kured DaemonSet — drain → reboot → uncordon | Node replacement; no reboot | Node replacement; no reboot | Node replacement; no reboot |
| **k3s / runtime binary** | system-upgrade-controller + weekly PR automation | EKS control plane patched silently; node AMI includes containerd | GKE nodes updated via release channel | AKS node pool update |
| **Container base images** | Renovate (weekly) opens PR per repo | ECR scan + manual rebuild trigger | Artifact Registry scan + manual rebuild | ACR scan + manual rebuild |
| **Helm chart CVEs** | Renovate opens PR; ArgoCD syncs after merge | Same — you own your app charts | Same | Same |
| **CIS posture** | kube-bench after each upgrade; Ansible remediation | Provider enforces CIS L1 defaults; fresh AMI = known state | CIS L1 default; hardened node images available | CIS L1 default |
| **TLS cert renewal** | cert-manager (automatic, zero ops) | ACM + cert-manager or provider TLS termination | Managed certs or cert-manager | Azure-managed certs or cert-manager |
| **Secret rotation** | Vault + ESO (manual rotation trigger) | AWS Secrets Manager auto-rotation | Secret Manager rotation | Azure Key Vault rotation |
| **What you own** | All five layers + their toolchains | Container images, app charts, secrets | Container images, app charts, secrets | Container images, app charts, secrets |

---

## What Managed Providers Cannot Remove From Your Plate

It's worth being precise about what "managed" actually means here.

Cloud providers remove OS patching, runtime binary patching, and CIS posture maintenance from your responsibility. These are real, significant reductions in operational burden — especially the OS and runtime layers, which require kured, system-upgrade-controller, Ansible, and kube-bench on bare-metal.

What they do not remove:
- Container base image CVEs. `FROM golang:1.25-alpine` in your Dockerfile is your responsibility on every Kubernetes platform. Renovate is not an EKS feature or a GKE feature — it's a universal tool.
- Application Helm chart versions. The charts you own need version bumps when CVEs are patched. ArgoCD + Renovate works identically on EKS, GKE, and AKS.
- Secret rotation. AWS Secrets Manager and GCP Secret Manager have auto-rotation APIs, but configuring rotation policies and updating applications is still your work.
- CIS posture for your workloads. The provider hardens the node. Your pods can still run with `privileged: true`, excessive RBAC permissions, or host path mounts. Gatekeeper/OPA and Polaris enforce these — and they run the same on managed and self-managed clusters.

The distinction matters because engineers who move from bare-metal to EKS sometimes assume the entire security patching problem is solved. Layers 3 and 4 — container images and Helm charts — remain exactly as manual as they were before. The two tools that address them, Renovate and Harbor/Trivy, are cluster-agnostic.

---

## The Honest Cost of Each Layer

| Layer | Time to set up | Ongoing cost (per month) | Saved by managed provider |
|---|---|---|---|
| OS patch download | Zero (`unattended-upgrades` default) | Zero | Yes |
| Kernel reboot (kured) | 30 minutes | Zero (DaemonSet, 50m CPU request) | Yes |
| k3s upgrade automation | 2 hours (SUC Plans + GH Actions) | Zero | Yes (absorbed into k8s version) |
| Container image CVEs (Renovate) | 2 hours (global config + 6 per-repo configs) | Zero | **No** |
| Helm chart CVEs (Renovate) | Included above | Zero | **No** |
| CIS hardening (kube-bench + Ansible) | 4 hours initial; 5 minutes post-upgrade | Zero | Yes |

The layers that require real setup time on bare-metal are the ones managed providers solve. The layers that remain your responsibility — container images and Helm charts — cost the same two hours of Renovate configuration on any platform.

Knowing this makes the managed provider value proposition precise rather than vague. You pay $73/month for an EKS control plane to eliminate the OS/runtime/CIS layers. The container image and chart patching story is identical on both sides of that purchase.

---

## The Conclusion That Actually Matters

Managed providers — EKS, GKE, AKS — eliminate **layers 1, 2, and 5**: OS patching, the Kubernetes runtime binary, and CIS posture maintenance. These are real savings. kured, system-upgrade-controller, and kube-bench exist on bare-metal precisely because there is no provider absorbing that work.

They do not touch **layers 3 and 4**: container base image CVEs and application Helm chart CVEs. A critical vulnerability in `golang:1.25-alpine` is your problem whether you run on a ThinkPad or on a $500/month EKS cluster. `FROM ubuntu:22.04` in your Dockerfile inherits CVEs on any platform. Renovate addresses both, and it runs identically on bare-metal and on EKS.

This is the part that gets missed in "just use a managed provider" advice. The layers that feel the most painful on bare-metal — the ones that involve rebooting nodes, swapping binaries, and re-running CIS benchmarks — are exactly the ones managed providers handle. The layer that is quietly the most dangerous — an application container built on a six-month-old base image with 40 unpatched CVEs — is equally your responsibility everywhere.
