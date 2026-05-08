---
id: crossplane
title: Phase 11 — Crossplane (Deferred)
sidebar_position: 2
---

# Phase 11 — Crossplane (Deferred)

:::caution Status: Deferred to a later phase
The original 22-phase plan paired **OpenTofu** and **Crossplane** in
Phase 11. During execution we explicitly scoped Crossplane out, for two
reasons:

1. **Different paradigms.** OpenTofu manages external infrastructure from
   *outside* Kubernetes; Crossplane manages external infrastructure
   *as Kubernetes resources from inside the cluster*. Same problem
   space, fundamentally different mental models. Doing both shallowly
   in one phase is worse than doing one well.
2. **No compelling external infrastructure to manage.** On a 3-node
   bare-metal cluster, there are no AWS RDS instances, GCP GKE clusters,
   or Azure subscriptions to provision. Crossplane's value lights up
   when there's a cloud account or a self-service portal in front of it.
   On this cluster, Phase 11 (OpenTofu against MAAS) is the right fit;
   Crossplane lands later when there's a real use case.

The most likely home for Crossplane is **Phase 18 (Backstage / developer
portal)**, where Crossplane Compositions act as the templates a developer
clicks "create" on. That's where it earns its weight.

This page is kept as conceptual reference. The implementation has not
been done.
:::

---

## What Crossplane is

Crossplane extends Kubernetes with Custom Resource Definitions (CRDs) to manage external infrastructure. Instead of running `tofu apply` from a terminal, you `kubectl apply` a YAML file — and Kubernetes continuously reconciles the desired state, just like it does for pods.

---

## Crossplane vs Terraform

| | Terraform / OpenTofu | Crossplane |
|---|---|---|
| Interface | CLI (`tofu apply`) | `kubectl apply` (YAML) |
| State management | State file / backend | Kubernetes etcd |
| Drift detection | On `plan` only | Continuous reconciliation |
| GitOps compatible | Via CI pipeline | Native (ArgoCD applies YAML) |
| Complexity | Moderate | Higher (more Kubernetes knowledge) |
| Best for | Initial provisioning | Ongoing platform management |

---

## How It Works

```text
Developer writes YAML:
  kind: RDSInstance  (example: AWS RDS)
  → Crossplane provider calls AWS API
  → Creates real RDS instance
  → Continuously reconciles

Same pattern for:
  → k8s namespaces
  → Vault secrets engines
  → Harbor projects
  → Any system with a provider
```

---

## Install Crossplane

```bash
helm repo add crossplane-stable https://charts.crossplane.io/stable

helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace

kubectl get pods -n crossplane-system
```

---

## Install the Kubernetes Provider

Manage Kubernetes resources as Crossplane objects:

```bash
kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-kubernetes:v0.13.0
EOF
```

---

## Install the Helm Provider

Manage Helm releases as Crossplane objects:

```bash
kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-helm
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-helm:v0.18.1
EOF
```

---

## Example — Manage a Namespace via Crossplane

```yaml
apiVersion: kubernetes.crossplane.io/v1alpha2
kind: Object
metadata:
  name: production-namespace
spec:
  forProvider:
    manifest:
      apiVersion: v1
      kind: Namespace
      metadata:
        name: production
        labels:
          environment: production
          managed-by: crossplane
  providerConfigRef:
    name: kubernetes-provider
```

```bash
kubectl apply -f namespace.yaml

# Crossplane creates + reconciles the namespace
# If someone deletes it manually, Crossplane recreates it automatically
```

---

## Example — Manage a Helm Release via Crossplane

```yaml
apiVersion: helm.crossplane.io/v1beta1
kind: Release
metadata:
  name: prometheus-stack
spec:
  forProvider:
    chart:
      name: kube-prometheus-stack
      repository: https://prometheus-community.github.io/helm-charts
      version: "57.0.0"
    namespace: monitoring
    values:
      grafana:
        adminPassword: changeme
  providerConfigRef:
    name: helm-provider
```

```bash
kubectl apply -f prometheus-release.yaml
kubectl get release prometheus-stack
```

ArgoCD can now sync this YAML from Git — full GitOps for Helm releases.

---

## Composite Resources (XRDs)

The real power of Crossplane: define your own "platform API" that abstracts complexity from developers.

```yaml
# Platform team defines:
apiVersion: platform.minicloud.io/v1alpha1
kind: Application
metadata:
  name: my-api
spec:
  namespace: production
  image: harbor.local/platform/my-api:v1.2
  replicas: 3
  database: true   # automatically provisions a DB

# Crossplane composes this into:
#   → Deployment
#   → Service
#   → Ingress
#   → PVC
#   → DB credentials in Vault
```

Developers request an "Application" — they never touch the underlying complexity.

---

## Crossplane + ArgoCD

Store all Crossplane YAMLs in Git. ArgoCD applies them:

```text
Git commit → ArgoCD detects → kubectl apply → Crossplane reconciles → infra updated
```

This is full GitOps for infrastructure, not just applications.

---

## Done When

```text
✔ Crossplane installed in crossplane-system namespace
✔ Kubernetes provider and Helm provider installed
✔ At least one namespace managed via Crossplane Object
✔ One Helm release managed via Crossplane Release
✔ ArgoCD syncing Crossplane manifests from Git
```
