---
id: gitops-directory-patterns
title: GitOps Directory Structure — Design Decisions
sidebar_label: GitOps Directory Patterns
---

# GitOps Directory Structure — Design Decisions

This page explains the directory layout chosen for service overlays on
this platform, and the architectural reasoning behind it.

---

## The four top-level directories (`minicloud-gitops`)

Everything ArgoCD reconciles falls into one of four directories. The distinction is **what kind of
input it is**, and it maps directly to the ArgoCD **source type**:

| Directory | Holds | ArgoCD source | "When do I use it?" |
|---|---|---|---|
| **`helm-values/`** | `values.yaml` **overrides for third-party charts** (not k8s objects) | Helm (upstream chart + `valueFiles`) | Configuring a vendor chart you didn't write (Grafana, Vault, Harbor, cert-manager, ERPNext…) |
| **`manifests/`** | **raw Kubernetes YAML / CRs** applied verbatim | directory (plain) | A raw object with no chart — NetworkPolicies, ResourceQuotas, RBAC, ExternalSecrets, Gatekeeper policies, ClusterIssuers, Kargo CRs, PriorityClasses, or a tiny standalone tool |
| **`services/`** | **your own custom apps** as GAP wrapper Helm charts | Helm (local chart) | An application you build (image from your source) |
| **`apps/`** | the **ArgoCD `Application` manifests** that wire the above to a namespace + sync policy | — | The glue: "sync *this* source → *this* namespace" |

### `helm-values/` vs `manifests/` — the key distinction

They answer two different questions:

- **`helm-values/`** = *"how do I **configure** a chart someone else wrote?"* The files are **chart
  input**, not Kubernetes resources (e.g. `mode: daemonset`, `image: &#123;repository, tag&#125;`).
  ArgoCD runs `helm template <chart> -f helm-values/minicloud-1/<app>-values.yaml` and applies the render.
- **`manifests/`** = *"what raw k8s objects do I apply directly?"* These **are** the resources
  (a `NetworkPolicy`, a `ResourceQuota`, an `ExternalSecret`, a CR). No chart is involved.

A single charted app often spans **both**: e.g. ERPNext has its chart knobs in
`helm-values/minicloud-1/erpnext-values.yaml` **and** supporting raw objects (secrets, netpol) in
`manifests/erpnext/`. Values = the chart's knobs; manifests = the extra objects the chart doesn't create.

### Decision rule — where does *X* go?

- Configuring a **vendor chart** → `helm-values/` (+ an `apps/` Application referencing it).
- A **raw k8s object / policy / secret / quota / CR**, or a tiny tool with no chart → `manifests/`.
- One of **your built apps** → `services/<svc>/helm/`.
- The **Application** that ties a source to a namespace → `apps/`.

See also: [Custom-Built Images](./custom-images) for *when a vendor app additionally earns its own
source repo* (the Backstage pattern).

---

## Helm vs raw manifests — when to use which

**Helm earns its place only when you need templating, parameterization, reuse, or a vendor's packaged
chart. When none of those apply, raw manifests are simpler and more honest.**

### What each buys you

| | Helm (vendor chart or your wrapper chart) | Raw manifests |
|---|---|---|
| **Value** | templating, per-env parameterization, DRY, reuse of a shared library, vendor packaging | transparency — what you see is exactly what's applied; no `helm template` indirection |
| **Cost** | indirection, a chart to configure/maintain, version pinning | no parameterization; copy-paste if it varies |
| **Lifecycle** | Helm release mgmt — **but ArgoCD already gives sync/prune/rollback** | ArgoCD gives the same GitOps lifecycle |

**Key insight:** ArgoCD already provides the deploy lifecycle (sync, prune, git-rollback), so Helm's
*release-management* value is largely redundant here. **Helm is really about templating + packaging, not
lifecycle.**

### Worked example — why OnlyOffice is raw manifests

`manifests/nextcloud/` (`10-onlyoffice`, `11-ingress`, `12-rbac`, `13-config-job`) is raw because
**every reason to use Helm is absent**:

1. **No good upstream chart worth adopting.** OnlyOffice's community chart is heavy/opinionated; for
   ~4 objects (Deployment + Service + Ingress + RBAC + a config Job) it's less work to write them
   plainly than to adopt + configure a bloated chart.
2. **Small, static, single-instance.** No templating value — one instance, fixed config, effectively
   one environment. Helm templating parameterizes *variation*; there's none to parameterize.
3. **It's an adjunct, not a standalone product.** OnlyOffice lives under `nextcloud/` because it's
   Nextcloud's document editor — deployed as part of that bundle, not as an independent app.
4. **Transparency wins for a fixed workload.** Raw YAML = exactly what runs; no `helm template` render
   step to reason about.

### The rule of thumb (this platform's actual pattern)

- **Vendor ships a real chart** (Grafana, Vault, Harbor, cert-manager, ERPNext) → **Helm**
  (`helm-values/`). You'd never hand-write Grafana's hundreds of objects.
- **Your own app that varies across dev/prod or reuses the shared library** (probes, netpol, rollout,
  KEDA) → **your GAP wrapper chart** (`services/`). Templating + the library are the payoff.
- **A small, static, single-instance workload, an adjunct to another app, or a supporting resource**
  (netpol, quotas, RBAC, ESO, CRs, a tiny tool like `whoami`/`homer`) → **raw manifests**
  (`manifests/`). Helm would add indirection for zero gain.

**One-line test:** *"Is there real templating / reuse / packaging value?"* Yes → Helm. No → raw
manifests, and let ArgoCD handle the lifecycle.

### Honest nuance

It's pragmatic, not dogmatic — a few things in `manifests/` *could* be charts and vice-versa; the
platform optimizes for "least indirection that still does the job." The trap to avoid is
**cargo-culting Helm onto a 3-object static app** just because "everything should be a chart" — that's
complexity with no payoff. OnlyOffice is the correct call as raw manifests *today*; if it ever needed
dev+prod variants or multiple instances, that would be the trigger to move it to a wrapper chart.

---

## The two common patterns

### Pattern A — flat overlay per environment

```
services/<service>/
├── base/
└── overlays/
    ├── dev/
    ├── staging/
    └── prod/
```

The overlay path encodes **one dimension**: the environment. One cluster
is implied — the overlay targets a namespace, and namespaces are isolated
within the single cluster.

### Pattern B — environment × cluster nesting

```
services/<service>/
├── dev/
│   ├── cluster-1/
│   └── cluster-2/
├── staging/
│   └── cluster-1/
└── prod/
    ├── cluster-1/        ← primary
    └── cluster-2/        ← DR / secondary region
```

The path encodes **two dimensions**: environment and target cluster. The
directory path is the full deployment address — it answers both "which
environment?" and "which cluster?".

---

## Why this platform uses Pattern A

This platform runs a single k3s cluster. Pattern B's cluster dimension
would add a directory level (`cluster-1/`) that never branches — it would
always be one entry and exist purely as scaffolding. A structure that can
never vary in practice carries no information and only adds path length.

Pattern A maps cleanly to the existing isolation model:

| Overlay | Namespace | Cluster |
|---|---|---|
| `overlays/dev/` | `platform-demo-dev` | k3s (only one) |
| `overlays/staging/` | `platform-demo-staging` | k3s (only one) |
| `overlays/prod/` | `gitops-demo` | k3s (only one) |

The ArgoCD Application `source.path` field reads the overlay directory
directly. The deployment address is fully expressed by the combination of
`path` (environment) + `destination.namespace`.

---

## When Pattern B becomes the right choice

Pattern B pays off when at least one of these is true:

**Multiple physical clusters exist.** If you add an Azure AKS cluster as
a cloud burst or DR target alongside the on-prem cluster, two clusters
serve the same environment. The overlay path needs to distinguish them:

```
overlays/prod/on-prem/    ← k3s, fast-heron/fast-skunk
overlays/prod/cloud/      ← AKS, westeurope
```

A `diff overlays/prod/on-prem/ overlays/prod/cloud/` immediately shows
any config drift between primary and DR. Without the cluster dimension,
this diff is impossible to express in the directory structure.

**CI/CD routes to different API servers based on path.** In a
multi-cluster setup, the deployment pipeline must know which kubeconfig
to use. The simplest routing key is the directory path segment — the
pipeline reads `prod/cloud/` and selects the AKS credential, reads
`prod/on-prem/` and selects the k3s kubeconfig. The path becomes the
routing table, not a config file.

**Drift between clusters is a compliance concern.** Regulated environments
(financial services, healthcare) often require proof that production
workloads are identical across regions. A directory-per-cluster structure
makes cross-region diffs auditable in every pull request.

---

## The design principle

> The directory path should be the minimum unique identifier for a
> deployment unit — no more, no less.

On a single cluster, environment + service name is sufficient. Adding
cluster is over-specification. On a multi-cluster platform, environment +
cluster + service name is the minimum identifier — omitting the cluster
dimension makes the path ambiguous.

Apply the same logic to any new dimension before adding it. A region
segment (`eu/`, `us/`) only belongs in the path if you actually deploy
the same service to multiple regions independently and need to track them
separately. If every service always deploys to both regions together, a
region segment adds noise without enabling any useful diff or routing.

---

## Promotion flow (current, single cluster)

```
CI push to main
  └── kustomize edit set image → overlays/dev/

PR to bump tag → overlays/staging/
  └── manual ArgoCD sync → platform-demo-staging namespace

PR to bump tag → overlays/prod/
  └── manual ArgoCD sync → gitops-demo namespace
```

If a second cluster were added, the staging and prod PRs would target
`overlays/staging/on-prem/` and `overlays/staging/cloud/` independently,
and each would trigger a sync against the corresponding cluster's
ArgoCD instance or kubeconfig.

---

## Summary

| Concern | Single cluster | Multi-cluster |
|---|---|---|
| Structure | `overlays/dev/staging/prod/` | `overlays/<env>/<cluster>/` |
| Path encodes | environment | environment + target cluster |
| Drift detection | namespace isolation | cross-cluster directory diff |
| CI routing | fixed kubeconfig | path-based credential selection |
| When to migrate | When second cluster is added | N/A |

The current flat structure is the correct choice and requires no changes
until a second Kubernetes cluster joins the platform.
