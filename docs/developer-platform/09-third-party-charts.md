---
id: third-party-charts
title: Third-Party Chart Deployment (ArgoCD + Helm values)
sidebar_label: Third-Party Charts
---

# Third-Party Chart Deployment

> **Scope:** how **upstream/third-party Helm charts** (Grafana, Vault, Harbor, Authentik, …) are
> deployed and configured. For **custom-built apps** (your own source → image) the current standard
> is the **[Delivery Workflow](./delivery-workflow)** (GAP wrapper-chart + Kargo) — not this page.
>
> This is the still-current half of the old "GitOps Workflow — two combos" page. *Combo 1*
> (Kustomize base+overlays for internal apps) was **retired** with the wrapper-chart golden path
> (2026-09) and the two-environment move; only this third-party pattern remains.

Third-party tools self-update by a **Git version bump → ArgoCD sync** — there is nothing to
*promote* (no dev→prod artifact of ours; a single upstream chart + a single values file). This is
exactly why they don't need Kargo (see [Kargo Promotion](./kargo-promotion) *Which deployments need
Kargo?*).

## The pattern — ArgoCD multi-source (chart + values)

Each third-party tool is an ArgoCD Application that pairs the **upstream chart** with a
**version-controlled values file** in `minicloud-gitops/helm-values/`:

```yaml
sources:
  - repoURL: https://helm.releases.hashicorp.com
    chart: vault
    targetRevision: "0.33.0" # chart version pin
    helm:
      valueFiles:
        - $values/helm-values/vault-values.yaml
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    ref: values
```

To change any configuration: **edit the values file in `minicloud-gitops/helm-values/`, commit,
push** — ArgoCD picks it up within ~3 minutes. No `helm upgrade`, no SSH to the controller. Chart
upgrades are a `targetRevision` bump in the ArgoCD Application.

## Repository role separation (the rule)

```
minicloud-ansible   = cluster bootstrap only (MAAS, k3s install, OS config)
minicloud-gitops    = ALL desired application state (manifests, values, wrapper charts)
service repos       = code only (Dockerfile, source, CI workflow)
```

Never edit `minicloud-ansible/helm-values/` for an ArgoCD-managed tool — the live source of truth is
`minicloud-gitops/helm-values/`. The authoritative live set of tools + their values files is whatever
exists in that directory (query it directly rather than trusting a copied list).

## Known gotchas (still current)

### ArgoCD "resource belongs to multiple apps" conflict

**Symptom:** an app stays `OutOfSync` with `Secret/X is part of applications argocd/app-a and app-b`.

**Root cause:** two ArgoCD Applications track the same cluster resource — commonly a Helm chart that
natively renders a Secret **and** an ESO `ExternalSecret` creating a secret with the same name
(`creationPolicy: Owner` adds an ownerReference but the Helm labels remain → ArgoCD sees dual
ownership).

**Fix:** pick the single authoritative owner. If the chart renders it natively, remove the ESO
`ExternalSecret`; if ESO is authoritative, point the chart at the existing secret
(`existingSecret: <name>`) so it stops rendering its own. *(Fixed for `nextcloud-db`, 2026-07-07:
deleted the duplicate `ExternalSecret` → GC removed the Secret via ownerReference → Helm `selfHeal`
recreated it as sole owner → `Synced`.)*

### Namespace created on first sync

A new Application targeting a not-yet-existing namespace shows `OutOfSync + Missing` — expected.
`CreateNamespace=true` in `syncOptions` creates it on the first sync.

### Vault Init:0/1 after a new namespace is added

When you extend a Vault Kubernetes auth role to a new namespace, existing pods don't auto-retry —
the Vault auth cache doesn't refresh. Delete the stuck pod to force a fresh auth attempt:

```bash
kubectl delete pod -n <namespace> -l app=<service> --force --grace-period=0
```

## Operational reference

| Task | Command |
|---|---|
| Force ArgoCD re-poll | `kubectl annotate app -n argocd <app> argocd.argoproj.io/refresh=normal` |
| Check what ArgoCD would change | ArgoCD UI → App Diff |
| Change a tool's config | edit `minicloud-gitops/helm-values/<tool>-values.yaml` → commit → push |
| Upgrade a chart | bump `targetRevision` in the tool's ArgoCD Application |
