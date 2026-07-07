---
id: gitops-directory-patterns
title: GitOps Directory Structure — Design Decisions
sidebar_label: GitOps Directory Patterns
---

# GitOps Directory Structure — Design Decisions

This page explains the directory layout chosen for service overlays on
this platform, and the architectural reasoning behind it.

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
