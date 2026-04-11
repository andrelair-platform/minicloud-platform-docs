---
id: deploy-helm
title: Deploy with Helm
sidebar_position: 3
---

# Deploy with Helm (Direct)

Direct Helm commands are used for local development, debugging, and first-time namespace setup. For persistent production workloads, use [ArgoCD (GitOps)](./deploy-argocd) instead.

---

## Prerequisites

```bash
# Logged in to Harbor
helm registry login harbor.local -u admin -p Admin12345

# kubectl pointing to the right cluster
kubectl config current-context

# Target namespace exists
kubectl get namespace myteam-staging
```

---

## First Install

```bash
helm install myapp-staging \
  oci://harbor.local/charts/myapp \
  --version 1.2.0 \
  --namespace myteam-staging \
  --values values-staging.yaml \
  --create-namespace \
  --wait \
  --timeout 5m
```

| Flag | Purpose |
|---|---|
| `myapp-staging` | Release name — unique per namespace |
| `--version` | Explicit chart version from Harbor |
| `--values` | Environment-specific overrides |
| `--wait` | Block until all pods are Ready |
| `--timeout` | Fail if not ready within 5 minutes |

---

## Upgrade

```bash
helm upgrade myapp-staging \
  oci://harbor.local/charts/myapp \
  --version 1.3.0 \
  --namespace myteam-staging \
  --values values-staging.yaml \
  --atomic \
  --wait
```

`--atomic` automatically rolls back if the upgrade fails — no broken half-states.

---

## Install or Upgrade (idempotent)

Use in CI pipelines where you don't know if the release exists yet:

```bash
helm upgrade --install myapp-staging \
  oci://harbor.local/charts/myapp \
  --version 1.3.0 \
  --namespace myteam-staging \
  --values values-staging.yaml \
  --atomic \
  --wait
```

---

## Override Individual Values at Deploy Time

```bash
helm upgrade --install myapp-staging \
  oci://harbor.local/charts/myapp \
  --version 1.3.0 \
  --namespace myteam-staging \
  --values values-staging.yaml \
  --set image.tag=1.3.1-hotfix \
  --set replicaCount=1
```

`--set` takes priority over `--values`. Use for one-off overrides only — do not use in production deploys.

---

## Inspect a Release

```bash
# Status
helm status myapp-staging -n myteam-staging

# Full rendered manifest
helm get manifest myapp-staging -n myteam-staging

# Current values
helm get values myapp-staging -n myteam-staging

# History of all deploys
helm history myapp-staging -n myteam-staging
```

---

## Rollback

Rollback to the previous release instantly:

```bash
# Rollback to previous version
helm rollback myapp-staging -n myteam-staging

# Rollback to a specific revision
helm rollback myapp-staging 3 -n myteam-staging

# Verify
helm history myapp-staging -n myteam-staging
```

---

## Diff Before Upgrade

Install the helm-diff plugin to preview changes before applying:

```bash
helm plugin install https://github.com/databus23/helm-diff

helm diff upgrade myapp-staging \
  oci://harbor.local/charts/myapp \
  --version 1.3.0 \
  --namespace myteam-staging \
  --values values-staging.yaml
```

Shows a git-diff-style view of what will change in the cluster — very useful before production upgrades.

---

## Uninstall

```bash
helm uninstall myapp-staging -n myteam-staging
```

This removes all resources created by the release. PVCs are **not** deleted by default — add `--cascade=foreground` if you want everything including data removed.

---

## Multi-Environment Deploy Reference

```bash
# Staging
helm upgrade --install myapp-staging \
  oci://harbor.local/charts/myapp --version 1.3.0 \
  -n myteam-staging -f values-staging.yaml --atomic --wait

# Production (requires explicit version — never latest)
helm upgrade --install myapp-prod \
  oci://harbor.local/charts/myapp --version 1.3.0 \
  -n myteam-prod -f values-prod.yaml --atomic --wait
```

---

## Helm Release Naming Convention

| Environment | Release Name | Namespace |
|---|---|---|
| Staging | `myapp-staging` | `myteam-staging` |
| Production | `myapp-prod` | `myteam-prod` |
| Dev (local) | `myapp-dev` | `myteam-dev` |

List all releases across all namespaces:

```bash
helm list -A
```
