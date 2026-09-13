---
id: deploy-overview
title: Application Delivery Overview
sidebar_position: 1
---

# Application Delivery Overview

This guide explains how custom applications move from source code to a running workload on the
minicloud platform. The current standard is the **two-repo GitOps model**:

- the application repo builds and proves the artifact
- `minicloud-gitops` declares how and where that artifact runs
- Kargo promotes verified artifacts from `dev` to `prod`
- ArgoCD reconciles Git to the Kubernetes cluster

For the detailed runbook, start with
[End-to-End Delivery Workflow](../developer-platform/delivery-workflow).

## Current Golden Path

```text
feature branch -> PR -> main
        |
        v
GitHub Actions: test -> build -> scan -> cosign sign -> SBOM
        |
        v
Image pushed: Harbor for dev, ghcr SHA for prod
        |
        v
Kargo Warehouse detects artifact -> Freight
        |
        +--> dev Stage: yaml-update values-dev.yaml -> auto-merged PR
        |        |
        |        v
        |   ArgoCD syncs dev -> Kargo smoke verification
        |
        +--> prod Stage: only dev-verified Freight -> CODEOWNERS PR
                 |
                 v
            ArgoCD syncs prod
```

## Where Configuration Lives

| Concern | Repository/path | Notes |
|---|---|---|
| Source code, tests, Dockerfile, application CI | service repo | Example: `platform-demo/`, `ktayl-policy-service/`, `retrieva/` |
| Custom app runtime config | `minicloud-gitops/services/<svc>/helm/` | GAP wrapper chart plus `values-dev.yaml` and `values-prod.yaml` |
| ArgoCD Applications | `minicloud-gitops/apps/` | Workloads and platform apps watched by the root app |
| Kargo promotion config | `minicloud-gitops/services/<svc>/kargo/` | Warehouse, Stages, ProjectConfig, verification |
| Third-party chart values | `minicloud-gitops/helm-values/` | Vault, Grafana, Harbor, Nextcloud, Authentik, and other platform tools |
| Shared platform controls | `minicloud-gitops/manifests/` | Quotas, NetworkPolicies, RBAC, ArgoCD projects, backup jobs |

The application repo should not carry Kubernetes manifests or environment-specific runtime values.
That separation keeps the source artifact reusable and the cluster state auditable.

## Environments

The platform standard is **two environments**:

| Environment | Source of change | Gate |
|---|---|---|
| `dev` | Kargo auto-promotes a new `main` artifact and opens a dev values PR | dev-only path guard and smoke verification |
| `prod` | Kargo promotes only Freight verified in dev | CODEOWNERS review before merge |

Git branches are not environments. `main` is the deploy trigger; optional `dev` branches are only
for human collaboration and do not deploy.

## Developer Responsibilities

Developers own:

- application code, tests, and domain behavior
- Dockerfile and build-only CI
- runtime compatibility across `dev` and `prod`
- health endpoints used by Kargo verification
- documentation for app-specific APIs and operations

## Platform Team Responsibilities

The platform owns:

- `minicloud-gitops` desired state
- wrapper-chart standards and shared library chart
- ArgoCD Applications, Kargo promotion, and CODEOWNERS gates
- namespaces, quotas, NetworkPolicies, Vault/ESO, ingress, and certificates
- operational runbooks and production verification

## Normal Change Flow

1. Change the app in its source repo and merge to `main`.
2. CI produces a signed, scanned, SBOM-backed image.
3. Kargo detects the new artifact and updates `values-dev.yaml` in `minicloud-gitops`.
4. ArgoCD deploys dev and Kargo runs smoke verification.
5. Promote the verified Freight to prod.
6. Review and merge the CODEOWNERS-gated prod PR.
7. ArgoCD reconciles prod; verify `Synced` and `Healthy`.

For config-only changes, start directly in `minicloud-gitops`, edit the owned path, open a PR, and
let ArgoCD reconcile after merge.

## What Not To Do

- Do not run `kubectl apply` or `helm upgrade` for managed workloads during normal delivery.
- Do not hand-edit image tags that Kargo owns.
- Do not put deploy config in application repos.
- Do not use mutable prod tags such as `latest`.
- Do not commit secrets; use Vault and External Secrets Operator.

Break-glass cluster commands belong in explicit recovery runbooks. The default operating model is
always: **Git change -> PR -> ArgoCD reconciliation**.
