---
id: phase-6-gitops
title: Phase 13 — GitOps (ArgoCD)
sidebar_position: 7
---

# Phase 6 — GitOps with ArgoCD

Replace manual `kubectl apply` with automated Git-based deployments.

---

## What is GitOps?

```text
Git repo = single source of truth
ArgoCD = sync engine

Developer pushes to Git → ArgoCD detects change → deploys to cluster
```

No manual kubectl commands in production.

---

## Install ArgoCD

```bash
kubectl create namespace argocd

kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

---

## Verify Installation

```bash
kubectl get pods -n argocd
```

Wait for all pods to be `Running`.

---

## Access ArgoCD UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Open: `https://localhost:8080`

---

## Get Initial Admin Password

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
```

---

## Create Your First App

Point ArgoCD at a Git repo containing Kubernetes manifests:

```text
Repo URL: https://github.com/you/your-k8s-manifests
Path: ./apps/my-app
Destination: https://kubernetes.default.svc
Namespace: default
Sync Policy: Automatic
```

---

## Done When

```text
✔ ArgoCD UI accessible
✔ App synced from Git
✔ Pods deployed automatically on git push
```
