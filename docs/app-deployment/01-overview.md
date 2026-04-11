---
id: deploy-overview
title: Enterprise Deploy Flow
sidebar_position: 1
---

# Application Deployment — Enterprise Deploy Flow

This guide defines **how developers ship applications** to the cluster. The platform team owns the infrastructure — developers own their apps. This page is the contract between both.

---

## The Golden Path (Helm + ArgoCD)

Every application deployed to this platform follows the same flow:

```text
┌─────────────────────────────────────────────────────────┐
│                    Developer Machine                    │
│  git push → GitLab (main branch)                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    GitLab CI Pipeline                   │
│                                                         │
│  Stage 1: build                                         │
│    → docker build                                       │
│    → docker push harbor.local/myteam/myapp:v1.2.0       │
│                                                         │
│  Stage 2: test                                          │
│    → unit tests                                         │
│    → vulnerability scan (Trivy in Harbor)               │
│                                                         │
│  Stage 3: package                                       │
│    → helm package ./chart                               │
│    → helm push harbor.local/charts/myapp:v1.2.0         │
│                                                         │
│  Stage 4: promote                                       │
│    → bump imageTag in gitops-repo/apps/myapp/values.yaml│
│    → git commit + push → triggers ArgoCD               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    GitOps Repo                          │
│  apps/                                                  │
│  ├── myapp/                                             │
│  │   ├── values-staging.yaml  ← staging overrides       │
│  │   └── values-prod.yaml     ← prod overrides          │
│  └── ArgoCD Application CRD                             │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    ArgoCD                               │
│  Detects: values changed                                │
│  Pulls chart from Harbor OCI registry                   │
│  Runs: helm upgrade myapp harbor/charts/myapp:v1.2.0    │
│        --values values-staging.yaml                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                   │
│  Namespace: myteam-staging                              │
│  ├── Deployment: myapp (3 replicas)                     │
│  ├── Service: myapp-svc                                 │
│  ├── Ingress: myapp.staging.yourdomain.com              │
│  ├── HPA: scale 3–10 on CPU/KEDA                        │
│  └── PVC: Longhorn volume (if stateful)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Two Deployment Paths

| Method | When to Use | Managed By |
|---|---|---|
| **Helm + ArgoCD** | All production workloads | GitOps repo + ArgoCD |
| **Raw YAML + kubectl** | Quick debugging, one-off jobs | Developer directly |

Helm is the **default**. Raw YAML is allowed but not the standard path for persistent workloads.

---

## Environment Strategy

| Environment | Namespace | Auto-deploy? | Approval needed? |
|---|---|---|---|
| `staging` | `myteam-staging` | Yes (on merge to main) | No |
| `production` | `myteam-prod` | No | Yes — manual sync in ArgoCD |

---

## Developer Responsibilities

```text
✔ Write and maintain the Helm chart in the app repo
✔ Keep image tags semantic (v1.2.3 — not "latest")
✔ Define resource requests and limits
✔ Add readiness and liveness probes
✔ Write the CI pipeline
```

## Platform Team Responsibilities

```text
✔ Own the cluster and namespaces
✔ Maintain ArgoCD Applications
✔ Manage Harbor projects and access
✔ Define the standard Helm chart template (golden path)
✔ Define resource quotas per team namespace
```

---

## Namespace Convention

```text
<team>-staging      → myteam-staging
<team>-production   → myteam-prod
<team>-dev          → myteam-dev (optional — short-lived)
```

Each team gets isolated namespaces with quotas applied by the platform team via Terraform/Crossplane.

---

## Naming Convention

| Resource | Convention | Example |
|---|---|---|
| Docker image | `harbor.local/<team>/<app>:<semver>` | `harbor.local/payments/api:v2.1.0` |
| Helm chart | `harbor.local/charts/<app>:<semver>` | `harbor.local/charts/api:v2.1.0` |
| Helm release | `<app>-<env>` | `api-staging` |
| Ingress host | `<app>.<env>.yourdomain.com` | `api.staging.yourdomain.com` |
