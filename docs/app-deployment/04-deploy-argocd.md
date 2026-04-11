---
id: deploy-argocd
title: Deploy via ArgoCD (GitOps)
sidebar_position: 4
---

# Deploy via ArgoCD — GitOps Path (Primary)

This is the **standard production deployment path**. Developers do not run `helm upgrade` in production. Instead, they push changes to Git — ArgoCD detects the change and drives the Helm deployment. The cluster always matches what is in Git.

---

## GitOps Repository Structure

A dedicated repository stores all deployment configuration. It is separate from application code repos:

```text
gitops-repo/
├── apps/
│   ├── myapp/
│   │   ├── application.yaml          ← ArgoCD Application CRD
│   │   ├── values-staging.yaml       ← staging overrides
│   │   └── values-prod.yaml          ← production overrides
│   └── payments-api/
│       ├── application.yaml
│       ├── values-staging.yaml
│       └── values-prod.yaml
└── platform/
    ├── namespaces.yaml               ← Terraform / Crossplane resources
    └── quotas.yaml
```

ArgoCD watches this repo. Any commit triggers a sync check.

---

## ArgoCD Application — Staging

```yaml
# apps/myapp/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-staging
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io    # delete resources when app is removed
spec:
  project: myteam

  source:
    repoURL: oci://harbor.local/charts
    chart: myapp
    targetRevision: "1.3.0"                     # pinned chart version
    helm:
      valueFiles:
        - values-staging.yaml                   # loaded from the gitops repo

  destination:
    server: https://kubernetes.default.svc
    namespace: myteam-staging

  syncPolicy:
    automated:
      prune: true       # remove resources no longer in chart
      selfHeal: true    # re-apply if someone manually changes cluster state
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

---

## ArgoCD Application — Production

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-prod
  namespace: argocd
spec:
  project: myteam

  source:
    repoURL: oci://harbor.local/charts
    chart: myapp
    targetRevision: "1.3.0"
    helm:
      valueFiles:
        - values-prod.yaml

  destination:
    server: https://kubernetes.default.svc
    namespace: myteam-prod

  syncPolicy:
    automated: null       # NO auto-sync in production
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Production requires a **manual sync** in the ArgoCD UI — a human approves every production deploy.

---

## ArgoCD Project — Team Isolation

Each team gets an ArgoCD Project that restricts what they can deploy and where:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: myteam
  namespace: argocd
spec:
  description: "Payments team applications"

  sourceRepos:
    - oci://harbor.local/charts      # only from our Harbor

  destinations:
    - namespace: myteam-staging
      server: https://kubernetes.default.svc
    - namespace: myteam-prod
      server: https://kubernetes.default.svc

  clusterResourceWhitelist: []       # no cluster-level resources
  namespaceResourceWhitelist:
    - group: "apps"
      kind: "Deployment"
    - group: ""
      kind: "Service"
    - group: "networking.k8s.io"
      kind: "Ingress"
    - group: "autoscaling"
      kind: "HorizontalPodAutoscaler"
```

Teams cannot deploy to namespaces they don't own or use cluster-admin resources.

---

## Multi-Source Application (chart + values in separate repos)

Separate the Helm chart (app repo) from the values (gitops repo):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-staging
  namespace: argocd
spec:
  sources:
    # Source 1: Helm chart from Harbor OCI
    - repoURL: oci://harbor.local/charts
      chart: myapp
      targetRevision: "1.3.0"
      helm:
        valueFiles:
          - $values/apps/myapp/values-staging.yaml

    # Source 2: Values files from GitOps repo
    - repoURL: https://gitlab.local/platform/gitops-repo.git
      targetRevision: main
      ref: values

  destination:
    server: https://kubernetes.default.svc
    namespace: myteam-staging
```

This is the cleanest pattern — chart and values evolve independently.

---

## Promotion Flow: Staging → Production

```text
1. Developer merges PR to main
2. CI bumps chart version to 1.3.0 in gitops-repo/apps/myapp/values-staging.yaml
3. ArgoCD auto-syncs → staging deploys 1.3.0
4. QA validates staging
5. Platform team (or developer with permission) updates values-prod.yaml:
     targetRevision: "1.3.0"
6. Commits to gitops-repo
7. ArgoCD detects change → waits (no auto-sync in prod)
8. Developer/release manager clicks Sync in ArgoCD UI
9. Production deploys 1.3.0
```

---

## Sync in ArgoCD UI

```text
ArgoCD UI → Applications → myapp-prod
→ Status: OutOfSync (new version available)
→ Click SYNC
→ Review changes
→ Click SYNCHRONIZE
→ Watch rollout in real time
```

---

## Monitor Rollout

After sync:

```bash
# Watch pods
kubectl rollout status deployment/myapp -n myteam-prod

# Check ArgoCD health
argocd app get myapp-prod

# Rollback if needed
argocd app rollback myapp-prod
```

---

## Done When

```text
✔ gitops-repo created with apps/ structure
✔ ArgoCD Application CRDs applied for staging and prod
✔ ArgoCD Project created for team isolation
✔ Staging auto-syncs on chart version bump
✔ Production requires manual sync in UI
✔ Rollback tested via argocd app rollback
```
