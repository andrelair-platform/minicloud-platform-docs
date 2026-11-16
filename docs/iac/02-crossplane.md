---
id: crossplane
title: Phase 11 — Crossplane
sidebar_position: 2
---

# Phase 11 — Crossplane

:::tip Status: Delivered (2026-11) — Infrastructure Orchestration (IDP Core Component #2)
Crossplane was originally **deferred** (history below) because there was no real use case on a
bare-metal cluster. **That condition is now met:** Crossplane **v2.4.3** runs as the platform's
**self-service infrastructure control plane**, fronted by **Backstage golden paths** — exactly the
"developer clicks *create*" trigger the deferral predicted. See **As-built** next.
:::

## As-built — the self-service catalog (2026-11)

Crossplane is the **composition engine**: platform-authored **XRDs** (self-service APIs) +
**Compositions** render real resources via `provider-kubernetes`. A developer applies a small claim
(or clicks a Backstage template) and gets the infra — no Helm, no `kubectl`.

| XRD (claim) | What one claim provisions | Pattern |
|---|---|---|
| **`PostgresInstance`** | a **CNPG** cluster (1 inst `small` / 2-inst HA `medium`) + a `NetworkPolicy` locking the DB to its namespace + the `<name>-cnpg-app` connection secret | one function-patch-and-transform Composition → two provider-kubernetes `Object`s |
| **`AppBundle`** | an app's **whole infra baseline** in one claim — it **nests a `PostgresInstance`** (→ CNPG + secret + db-netpol) **and** renders a default-deny baseline `NetworkPolicy` for the app's pods (ingress from ingress-nginx, egress to DNS + its own DB) | **composite-of-composites**: the Composition composes *another XR* directly (not a provider Object) → Crossplane reconciles it via **its own** Composition |

### The composite-of-composites (AppBundle nesting)

```
AppBundle/<app>            (one claim)
├─ PostgresInstance/<app>   ← NESTED XR — composed directly; reconciled by its OWN Composition
│   ├─ Cluster/<app>-cnpg        (CNPG database)
│   └─ NetworkPolicy/<app>-db-netpol
└─ NetworkPolicy/<app>-baseline  (the app's default-deny baseline)
```

Deleting the one `AppBundle` claim **GC-cascades** the entire tree. This is the advanced Crossplane
pattern: a Composition composes managed resources **and other composites**, so a high-level claim
assembles lower-level claims.

### Boundary — infra vs deployment (no overlap)

- **`AppBundle` (Crossplane)** owns the app's **infrastructure** (DB + network baseline).
- **`wrapper-service` (Helm golden path)** owns the app's **deployment** (Deployment/Rollout, Service, Ingress, cert).
- They **compose**: the Deployment mounts the bundle's `<app>-cnpg-app` secret, and its `app=<app>` pods are selected by the baseline netpol.

### Self-service surfaces (how a developer consumes it)

- **Backstage → Create → "Provision a Database"** → opens a gitops PR with a `PostgresInstance` claim.
- **Backstage → Create → "Provision an App Bundle"** → opens a gitops PR with an `AppBundle` claim.
- Claims land under **`platform/foundation/crossplane-claims/`**, synced by the `crossplane-claims`
  ArgoCD app into their namespace. **Gated** — a DB holds persistent data, so the claim PR is
  reviewed before merge (governed self-service), unlike ephemeral preview envs.

```bash
kubectl --context minicloud get xrd                              # the self-service APIs
kubectl --context minicloud -n <ns> get appbundle,postgresinstance,cluster.postgresql.cnpg.io,netpol
```

The install details (the hardened-cluster fix cascade, the pinned-SA scoped RBAC) + the XRD/Composition
sources live in `minicloud-gitops/platform/foundation/crossplane-config/`.

## Why it was deferred (history — superseded)

:::note Superseded
The two reasons below were valid at the time; both are now resolved (a self-service portal + real
claims exist). Kept for the decision trail.
:::

The original 22-phase plan paired **OpenTofu** and **Crossplane** in Phase 11. During execution we
explicitly scoped Crossplane out because the paradigms differ (OpenTofu manages infra from *outside*
the cluster; Crossplane from *inside* as k8s resources) and there was **no compelling external infra
to manage** on bare metal. The deferral predicted Crossplane's home would be **Phase 18 (Backstage /
developer portal)**, where Compositions are the templates a developer clicks "create" on — which is
exactly where it landed.

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
