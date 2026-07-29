---
slug: minicloud-vs-openshift-self-hosted
title: "Self-Hosted Kubernetes: What I Built vs What OpenShift Ships"
authors: [andre]
description: >
  A layer-by-layer comparison between minicloud — a 5-node k3s cluster assembled from CNCF components —
  and OpenShift Container Platform (OCP) self-hosted. Same problems, different approaches: immutable nodes,
  control plane management, security posture, upgrades, and what each model teaches you.
tags: [kubernetes, k3s, openshift, okd, platform-engineering, devops, cncf, security, gitops, bare-metal]
date: 2026-07-29
image: /img/docusaurus-social-card.jpg
---

OpenShift Container Platform is an opinionated enterprise Kubernetes distribution. My minicloud cluster is a 5-node k3s stack assembled component by component from CNCF projects. After going through the full build — GitOps, observability, secrets, registry, OIDC, ingress, storage replication, chaos testing, security patching, upgrades — I can say with some precision what the difference actually is.

It is not that OpenShift does more. It is that OpenShift has already made every choice you would have to make yourself, packaged those choices as a versioned, tested, supported unit, and enforced them at the architecture level. Whether that is a benefit or a constraint depends entirely on what you are trying to do.

{/* truncate */}

## The Setup

**minicloud** is a 5-node k3s v1.36.2 cluster on bare-metal Ubuntu 22.04:

| Node | IP | Role |
|------|----|------|
| `set-hog` | 10.0.0.2 | k3s control plane (ThinkPad X390) |
| `fast-skunk` | 10.0.0.4 | worker |
| `fast-heron` | 10.0.0.7 | worker |
| `star-kitten` | 10.0.0.8 | worker |
| `swift-mac` | 10.0.0.10 | worker (MacBook Pro 2012, Ubuntu 22.04, Longhorn storage) |

Every component was chosen, configured, and deployed by hand: ArgoCD for GitOps, Harbor for images, Authentik for OIDC, Longhorn for block storage, NGINX + MetalLB for ingress, Vault + ESO for secrets, Gatekeeper for policy, Falco for runtime security, kube-prometheus-stack for observability.

**OpenShift OCP** self-hosted runs on bare metal or VMs. Minimum production footprint: three masters (16 GB RAM, 120 GB disk each) plus two workers. The control plane OS is RHEL CoreOS (RHCOS), an immutable image managed by the cluster itself. Workers can be RHCOS or RHEL 9.

---

## The Hardware Reality

Before comparing features, the minimum footprint gap is real:

| | minicloud (k3s) | OpenShift OCP |
|---|---|---|
| Control plane nodes | 1 (ThinkPad X390) | 3 masters minimum |
| RAM per control plane node | ~8 GB | 16 GB minimum |
| Total minimum cluster RAM | ~20 GB across 5 nodes | ~64 GB across 5 nodes |
| Install time | k3s binary: 5 minutes | OpenShift IPI installer: 45–90 minutes |
| Minimum disk per control plane | ~256 GB NVMe | 120 GB minimum (etcd is I/O sensitive) |
| License cost | Open source (MIT) | Red Hat subscription (~$10k+/year per cluster) |

k3s runs on a ThinkPad. OpenShift cannot. This is not a knock on OpenShift — it bundles a full enterprise platform, and that platform has real resource requirements. But it means the two tools solve different problems at different scales.

The community alternative is **OKD**, OpenShift's free upstream using Fedora CoreOS instead of RHCOS. Same architecture, same operators, no Red Hat subscription. OKD is what to use if you want to evaluate OpenShift's model without the licensing cost.

---

## Layer 1: The Node OS — Ubuntu vs RHCOS

Your nodes run Ubuntu 22.04. You manage OS patches via `unattended-upgrades`, kernel reboots via kured, and node configuration via Ansible. Configuration can drift silently. A hand-edited file on `fast-heron` can differ from `star-kitten` with no record anywhere.

OpenShift control-plane and worker nodes run **RHEL CoreOS** — an immutable OS. There is no package manager you can call. Configuration is entirely managed by the **Machine Config Operator (MCO)**:

```yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 99-worker-sysctl-inotify
spec:
  config:
    storage:
      files:
        - path: /etc/sysctl.d/99-inotify.conf
          contents:
            source: "data:,fs.inotify.max_user_watches%3D524288"
```

Apply that MachineConfig, and MCO drains the target nodes, applies the change via `rpm-ostree`, reboots, and uncordons. No Ansible playbooks. No SSH. No drift. The node cannot have a configuration that differs from its MachineConfig — that is the constraint the architecture enforces.

**What this means concretely:** my Ansible + kured + kube-bench stack covers the same ground as MCO (node configuration, CIS posture, reboot sequencing after patches). The difference is that MCO enforces convergence architecturally; my Ansible requires someone to remember to run the playbook.

---

## Layer 2: The Control Plane — Kine/SQLite vs etcd + CVO

minicloud runs a single control plane node (`set-hog`) with k3s's Kine adapter replacing etcd with SQLite. This is a deliberate trade-off: single point of failure for the API server, 90-second recovery window on hardware failure, full administrative control over the datastore. Two independent backup mechanisms (k8s CronJob + controller systemd timer) cover the recovery path.

OpenShift requires three masters with a real three-node etcd cluster. Lose one master, the API server keeps scheduling. The etcd cluster is managed entirely by the **etcd Operator**, which is itself managed by the **Cluster Version Operator (CVO)**.

CVO is the part of OpenShift with no equivalent in the k3s ecosystem. It manages every control plane component — API server, controller manager, scheduler, etcd, ingress router, monitoring stack, image registry — as a set of versioned operators. When you run:

```bash
oc adm upgrade --to-latest=true
```

CVO:
1. Validates the new version payload is safe to apply from the current version
2. Updates control plane operators in a defined dependency order
3. Triggers MCO to update RHCOS on each control plane node (drain → `rpm-ostree` → reboot → uncordon)
4. Updates all bundled operators (monitoring, logging, router) in the correct sequence
5. Validates each step before proceeding to the next
6. Can pause and resume mid-upgrade

My equivalent is system-upgrade-controller (SUC) for the k3s binary + GitHub Actions for release detection + Renovate for Helm chart bumps triggered by the version change. CVO manages the entire platform as a versioned unit. My stack manages the k3s binary and then handles every other component separately. CVO knows that cert-manager version N is compatible with OCP 4.17 because Red Hat tested that combination. My compatibility checks are manual.

---

## Layer 3: Security — Gatekeeper + Falco vs SCCs + SELinux + RHACS

This is where the gap is most meaningful.

### Security Context Constraints vs Pod Security Admission

Kubernetes ships Pod Security Admission (PSA) with three built-in levels: `privileged`, `baseline`, `restricted`. They apply at the namespace level, are all-or-nothing within a level, and cannot be customized.

OpenShift ships **Security Context Constraints (SCCs)** as a more granular replacement that predates PSA and remains the primary enforcement mechanism. SCCs are attached to service accounts:

```yaml
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: restricted-v2
allowPrivilegedContainer: false
allowHostDirVolumePlugin: false
runAsUser:
  type: MustRunAsRange      # enforces non-root with a dynamic UID range per namespace
seLinuxContext:
  type: MustRunAs           # mandatory SELinux labelling on every container
fsGroup:
  type: MustRunAs
seccompProfiles:
  - runtime/default
```

The critical difference from PSA: `MustRunAsRange` assigns a UID from a namespace-specific range. If two namespaces both use the `restricted-v2` SCC, their pods get different UIDs. A compromised process that escapes its container cannot write files owned by another namespace's pods. PSA cannot express this — it either allows non-root (no specific UID) or denies root (any non-zero UID).

My equivalent is Gatekeeper/OPA with custom rego policies. I can get close to SCC behavior, but I wrote every constraint manually. SCCs are built in and enforced by default on every pod in every namespace without any admission webhook configuration.

### SELinux vs AppArmor

Every RHCOS node runs SELinux in enforcing mode. Pod processes receive mandatory SELinux labels. File system access is controlled at the kernel level by these labels — a process cannot read a file unless its label permits it, regardless of Unix permissions. You cannot disable SELinux on a RHCOS node without MCO.

Ubuntu nodes (minicloud) default to AppArmor. AppArmor is profile-based: you define what a process can access, and anything not in the profile is denied. It is effective, but it is opt-in per workload and does not provide the cross-process isolation that SELinux mandatory labels give you.

### RHACS vs Falco + Harbor Trivy + Gatekeeper

Red Hat Advanced Cluster Security (RHACS, originally StackRox) is a full container security platform available via OperatorHub. It covers:

- Vulnerability scanning for container images (similar to Harbor Trivy)
- Runtime threat detection (similar to Falco)
- Network segmentation enforcement with visual network topology
- Compliance reporting against CIS, NIST, PCI-DSS, SOC2 out of the box
- Risk scoring per deployment based on CVEs, runtime behavior, and network exposure

My stack does the same work using four separate tools: Falco (runtime), Harbor Trivy (image scanning), Gatekeeper (policy), kube-bench (compliance). Each is configured and maintained separately. RHACS integrates all of these into a single operator with a unified UI.

---

## Layer 4: Networking — Flannel + MetalLB vs OVN-Kubernetes

minicloud uses **Flannel** (k3s default, VXLAN encapsulation) for the pod network and **MetalLB** for LoadBalancer IP assignment via L2 ARP advertisement. Adding **NGINX Ingress Controller** as a DaemonSet on top gives HTTP/HTTPS routing. Three components, each independently versioned and configured.

OpenShift ships **OVN-Kubernetes** as its default CNI. OVN-Kubernetes is built on Open Virtual Network, which provides:

- Distributed L3 routing (each node handles its own east-west traffic, no centralized gateway)
- Hardware offload support (via SR-IOV or SmartNICs on nodes that have them)
- **AdminNetworkPolicy** — a cluster-scoped network policy that takes precedence over namespace-scoped NetworkPolicy. Platform admins can enforce baseline segmentation that tenant teams cannot override.
- Egress IP assignment (stable outbound IP per namespace or pod selector for firewall allowlisting)

**Routes vs Ingress:** OpenShift has an `Ingress` compatible resource but also ships `Route` — a first-class CRD that predates the Ingress spec and carries more configuration surface:

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: my-service
spec:
  host: my-service.apps.cluster.example.com
  to:
    kind: Service
    name: my-service
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

The HAProxy-based router is a core CVO-managed component, not a Helm chart. Wildcard DNS (`*.apps.cluster.example.com`) points to the router VIP. Every Route gets a hostname under that wildcard automatically. My equivalent is cert-manager (TLS) + NGINX DaemonSet (routing) + MetalLB (VIP) + explicit DNS records per service — four separate components where OCP has one.

---

## Layer 5: The Developer Experience

### Operators vs Helm Charts

minicloud deploys everything via Helm charts managed by ArgoCD. Each chart is an independent versioned dependency. Renovate opens PRs when new chart versions ship.

OpenShift's primary delivery mechanism is **Operators** from **OperatorHub** — a curated marketplace of certified, tested operators. An Operator is a controller that manages a specific application using Kubernetes-native CRDs. Installing Prometheus on OpenShift:

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: prometheus
  namespace: openshift-monitoring
spec:
  channel: stable
  installPlanApproval: Automatic
  name: prometheus
  source: redhat-operators
```

The **Operator Lifecycle Manager (OLM)** handles installation, dependency resolution, and updates. An Operator that declares a dependency on cert-manager will have OLM install cert-manager automatically. Helm has no dependency resolution — you install the dependency manually and hope the version is compatible.

The trade-off: Operators are more powerful but less portable. A Helm chart runs anywhere Helm runs. An OLM subscription only works on a cluster with OLM installed (OpenShift, or OLM installed separately on vanilla Kubernetes).

### The Console

k3s has no built-in web console. My platform surface is ArgoCD (GitOps), Grafana (metrics/logs/traces), Harbor (images), Backstage (IDP/catalog), Homer (dashboard). Each has its own authentication flow, even with Authentik OIDC federating them.

OpenShift ships a full web console with two perspectives:

- **Administrator**: cluster-wide resources, node status, operator management, event streams, quota consumption, network topology
- **Developer**: project-scoped views, topology graphs showing service connections, build pipelines, integrated log tailing per pod

Both use the same OpenShift OAuth session. One login, full visibility across all namespaces the user has access to. The console is a CVO-managed component — it upgrades with the cluster and is always compatible with the version running.

For teams where not everyone is a platform engineer, this matters. On minicloud, debugging a failing pod requires knowing to go to ArgoCD for sync status, Grafana for logs, kubectl for events. On OpenShift, the console surfaces all of that in a single view.

---

## Component Mapping

Assembling minicloud meant independently choosing and wiring together the equivalent of every built-in OpenShift component:

| Component | minicloud | OpenShift OCP |
|---|---|---|
| GitOps | ArgoCD (Helm, self-managed) | OpenShift GitOps = certified ArgoCD |
| CI/CD pipelines | GitHub Actions (external) | OpenShift Pipelines = Tekton |
| Image registry | Harbor (Helm) | Built-in integrated registry |
| Authentication | Authentik OIDC (Helm) | Built-in OAuth server |
| Ingress | NGINX + MetalLB (Helm) | HAProxy Router (CVO-managed) |
| TLS | cert-manager (Helm) | cert-manager (OperatorHub) |
| Storage | Longhorn (Helm) | OpenShift Data Foundation = Rook/Ceph |
| Monitoring | kube-prometheus-stack (Helm) | cluster-monitoring-operator (CVO-managed) |
| Logging | Loki (Helm) | OpenShift Logging = Loki or Elasticsearch |
| Tracing | Tempo (Helm) | OpenShift Distributed Tracing = Tempo/Jaeger |
| Secrets | Vault + ESO (Helm) | Vault (OperatorHub) or Secrets Store CSI |
| Policy enforcement | Gatekeeper/OPA (Helm) | Built-in SCCs + optional Gatekeeper |
| Runtime security | Falco (Helm) | RHACS (Red Hat Advanced Cluster Security) |
| Image scanning | Harbor Trivy | RHACS or built-in registry scanning |
| Node updates | system-upgrade-controller + GH Actions | Cluster Version Operator (CVO) |
| Node configuration | Ansible | Machine Config Operator |
| CIS hardening | kube-bench + Ansible (manual post-upgrade) | Built-in CIS L2, SELinux enforced |
| Service mesh | not deployed | OpenShift Service Mesh = Istio + Kiali |
| Developer console | Backstage + Homer + Grafana | Full OpenShift web console |
| Dependency updates | Renovate (self-hosted) | Renovate — not an OCP feature, same either way |

The notable pattern: the tools in the left column are the same upstream CNCF projects that OpenShift packages in the right column. ArgoCD is ArgoCD. cert-manager is cert-manager. Tempo is Tempo. OpenShift adds testing, compatibility guarantees, support contracts, and delivery via OLM. It does not replace the underlying technology.

---

## What OpenShift Gives You That You Cannot Easily Replicate

**Node immutability:** MCO + RHCOS makes node drift impossible by architecture. My Ansible approach requires discipline — an SSH session on `fast-heron` at 2am can leave the node permanently different from its intended state. RHCOS rejects that.

**Platform-level upgrade coordination:** CVO treats the entire cluster as a versioned artifact. When upgrading from OCP 4.16 to 4.17, CVO knows the correct order for updating every component because Red Hat tested that exact sequence. My SUC + Renovate approach upgrades k3s and then each Helm chart independently — compatibility between versions is my problem.

**Out-of-box CIS Level 2 compliance:** OCP passes CIS L2 on install. My cluster needs kube-bench to verify, and passing it requires post-install Ansible work. After a k3s upgrade, I re-run kube-bench because the binary update can reintroduce findings.

**Enterprise support path:** A failing OCP cluster has a Red Hat support ticket with a service level. A failing k3s cluster has Stack Overflow and the k3s GitHub issues.

**OpenShift Local (CRC):** Red Hat ships a single-VM OCP install for local development. If you need OpenShift-specific features (SCCs, Routes, OperatorHub) in development, CRC gets you there without building a multi-node cluster.

---

## What minicloud Has That OpenShift Cannot Give You

**Hardware flexibility:** OCP cannot run on a ThinkPad. k3s can. The entire minicloud platform runs on hardware you could buy at a laptop repair shop for under €1,000 total.

**Component choice:** OCP's built-in monitoring stack (cluster-monitoring-operator) cannot be replaced. It is how OCP monitors itself. My Prometheus can be swapped for VictoriaMetrics, reconfigured, or extended without CVO fighting me.

**Cost at small scale:** Open source plus electricity costs versus a Red Hat subscription. For a portfolio cluster or a small team, the subscription model has no justification.

**Learning depth:** Building a cluster from CNCF primitives forces understanding at every layer. An OpenShift engineer who has never built a cluster from scratch often does not know why cert-manager exists, what problem MetalLB solves, or how etcd leader election works. The platform hides it. Building minicloud means knowing exactly what each component does because you had to make it work.

**Upstream velocity:** k3s typically tracks upstream Kubernetes within days of a release. OCP ships new Kubernetes versions on a 4-month delay as Red Hat completes integration testing. minicloud ran k3s v1.36.2 while many OCP clusters were still on 1.31.

---

## The Conclusion That Actually Matters

By building minicloud component by component, I assembled the functional equivalent of OpenShift using the same upstream CNCF projects that OpenShift packages. GitOps, observability, secrets management, image registry, OIDC, policy enforcement, runtime security, canary deployments, chaos testing, backup and DR — all present on both platforms.

OpenShift's value proposition is everything around those components:
- Red Hat tested all of them together at a specific version matrix
- CVO automates the upgrade sequencing across the entire platform as a unit
- MCO enforces node immutability so configuration drift is architecturally impossible
- SCCs and SELinux provide a security model stronger than what PSA + AppArmor can deliver
- OperatorHub gives you a curated, certified component marketplace with OLM dependency resolution
- The support contract gives you a call to make when the cluster is down at 3am

What neither platform handles for you: container image CVE patching and application Helm/OLM chart updates. Renovate runs identically on k3s and OCP. That layer is always yours.

The choice is not about which platform is technically superior. It is about what you are optimizing for. A regulated enterprise with a 100-person platform team and a compliance requirement optimizes for the guarantees OpenShift provides. A platform engineer building a portfolio cluster, learning the full stack, or running a cost-constrained production environment optimizes for everything that makes minicloud the right answer.

Both are valid. Knowing which model fits which context — and why — is the actual skill.
