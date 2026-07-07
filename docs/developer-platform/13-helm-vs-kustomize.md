---
id: helm-vs-kustomize
title: Helm vs Kustomize — When to Use Which
sidebar_label: Helm vs Kustomize
---

# Helm vs Kustomize — When to Use Which

This platform uses both Helm and Kustomize. They are not competing tools —
each is the right fit for a different category of workload. This page
explains the split, the tradeoffs, and the single question that decides
which to reach for.

---

## The split in one sentence

**Helm** for software you consume. **Kustomize** for software you build.

---

## Why Helm for third-party tools

Third-party software (Vault, ArgoCD, Prometheus, NATS, Ollama, Harbor,
cert-manager, …) ships with an official Helm chart maintained by the
upstream team. That chart encodes years of operational knowledge:
lifecycle hooks, upgrade paths, dependency ordering, sane defaults.

You don't write or maintain the templates. You only write a `values.yaml`
that expresses your configuration choices. When the upstream team ships a
new chart version, you bump `targetRevision` in the ArgoCD Application and
get all their fixes and improvements.

```
upstream chart templates  +  your values.yaml  →  ArgoCD deploys it
      (not yours)                (yours)
```

Maintaining those templates yourself would mean re-implementing work that
has already been done and tested by hundreds of production users.

## Why Kustomize for own services

For services you wrote — `platform-demo`, future internal apps — you
already own the Kubernetes manifests. Kustomize lets you maintain one
canonical `base/` definition and layer environment-specific differences
on top without duplicating any YAML.

```
your base manifests  +  overlay patches  →  ArgoCD deploys it
      (yours)              (yours)
```

Image tag promotion fits naturally: CI runs
`kustomize edit set image` in `overlays/dev/` only. Staging and prod
require explicit PRs. This promotion flow would be awkward to express
cleanly in a `values.yaml`.

---

## The deciding question

> Do you own the Kubernetes templates?

| Answer | Tool | Reason |
|---|---|---|
| No — upstream maintains them | Helm | Let the chart maintainer own the upgrade path |
| Yes — you wrote them | Kustomize | Overlays cost nothing extra when you already have the YAML |

---

## You can use either for anything

Nothing technically prevents using Helm for your own app or Kustomize
for third-party software. Both would work. The tradeoffs are:

### Helm for your own app — when it makes sense

Packaging your app as a Helm chart makes sense when it becomes a
**platform product consumed by other teams**. If multiple teams deploy
the same service with different configuration (different replica counts,
different ingress hostnames, different feature flags), a Helm chart lets
each team supply their own `values.yaml` without touching templates.

The enterprise pattern for this is a central **library chart** — one
chart that encodes all organisational standards (probes, security
contexts, resource limits, ingress TLS), with a thin wrapper chart per
application that only provides values. Teams never write Kubernetes YAML
directly; they configure the library chart.

Tradeoffs:

| Pro | Con |
|---|---|
| Reusable across teams | You write and maintain the templates |
| Versioned as a package (chart semver) | Image tag promotion is less clean |
| One chart → many deployments | Overkill for a single-team, single-deployment service |

### Kustomize for third-party software — when it makes sense

Vendoring upstream manifests and managing them with Kustomize makes sense
when the upstream Helm chart is poorly maintained, too opinionated, or
exposes insufficient values for the changes you need. You `kubectl kustomize`
the upstream YAML, add strategic merge patches for the fields the chart
doesn't expose, and own the result.

Tradeoffs:

| Pro | Con |
|---|---|
| Full control over every manifest field | You vendor and maintain all upstream YAML |
| No Helm dependency | Upstream upgrades require manual YAML diffing |
| Simple — just files | No lifecycle hooks, no `helm test`, no dependency graph |

---

## The hybrid model

Using Helm for third-party tools and Kustomize for own services is a
well-established pattern sometimes called the **hybrid GitOps model**.
It is the approach most platform teams converge on in practice because
it applies each tool to the problem it is designed for.

The two tools operate independently and compose cleanly under ArgoCD:

```
minicloud-gitops/
├── apps/                        ← ArgoCD Application definitions
│   ├── vault.yaml               ← Helm multi-source app
│   ├── prometheus.yaml          ← Helm multi-source app
│   ├── platform-demo-dev.yaml   ← Kustomize app
│   └── platform-demo-staging.yaml
│
├── helm-values/                 ← Helm values (third-party tools)
│   ├── vault-values.yaml
│   └── kube-prometheus-stack-values.yaml
│
└── services/                    ← Kustomize base+overlays (own services)
    └── platform-demo/
        ├── base/
        └── overlays/
            ├── dev/
            ├── staging/
            └── prod/
```

ArgoCD handles both patterns identically from an operational standpoint —
Git is the source of truth, changes are detected automatically, drift is
corrected. The difference is invisible to ArgoCD; it only matters to the
engineers maintaining the deployment config.

---

## Summary

| Concern | Helm | Kustomize |
|---|---|---|
| Who maintains the templates | Upstream chart team | You |
| Configuration expressed as | `values.yaml` overrides | Base + overlay patches |
| Image tag promotion | Value bump in values file | `kustomize edit set image` in overlay |
| Multi-team reuse | Natural (package + version) | Requires copying base |
| Upstream upgrade path | `targetRevision` bump | Manual YAML re-vendoring |
| Best fit | Third-party / consumed software | Own / built software |
