---
id: deploy-argocd
title: Deploy via ArgoCD (GitOps)
sidebar_position: 4
---

# Deploy via ArgoCD — GitOps Path (Primary)

:::warning Stale examples — concept correct, details outdated
The ArgoCD-drives-Git concept on this page is current, but the **examples use a `staging` environment**
(removed — the standard is `dev` + `prod`) and the old per-service chart layout. For the real, current
Application manifests see **[Deploy a new business service → Step 4](./new-business-service)** and
**[Standard Helm Chart](./helm-chart)** (single Helm source + `helm.releaseName`, dev auto-sync +
CODEOWNERS-gated prod, Kargo promotion).
:::

This is the **standard production deployment path**. Developers do not run `helm upgrade` in production. Instead, they push changes to Git — ArgoCD detects the change and drives the Helm deployment. The cluster always matches what is in Git.

---

## How it actually works here — `apps/` + the wrapper chart (current)

:::note Verified, current (2026-11-13)
This section describes the **real** mechanism on this cluster. The generic sections further down are kept
as conceptual background but use a stale `staging`/multi-source layout — prefer this section +
[Deploy a new business service](./new-business-service) + [Standard Helm chart](./helm-chart).
:::

### `apps/` is the app-of-apps registry

Everything ArgoCD runs is declared by **one file per deployment** under `minicloud-gitops/apps/` (~105
files). A single **root `Application`** (`bootstrap/root-app.yaml`) points at `apps/` with
`directory.recurse: true`, so ArgoCD discovers an `Application` **wherever** it sits in the tree — the
sub-folders are **pure taxonomy**, not functional:

```
apps/
├── platform/   shared infrastructure capabilities (foundation, storage, networking, secrets,
│               security, observability, delivery, data, ai, automation, shared-services, _demos)
├── is/         the business/IS apps (insurance, iam, erp, itsm, workplace)
├── retrieva/   the RNCP39583 cert product (its own group)
└── previews/   PR preview environments
```

The folder an `Application` lives in just records **what kind of thing it is** (the Platform ↔ IS
ownership boundary — enforced by the `architecture-guard` CI, which blocks a new `Application` outside
`apps/platform/<layer>/` or `apps/is/<group>/`).

### `apps/` vs `services/` — pointer vs recipe

| | `services/<svc>/helm/` | `apps/.../<svc>-{dev,prod}.yaml` |
|---|---|---|
| Is | the **recipe** (the wrapper Helm chart) | the **pointer** (an ArgoCD `Application`) |
| One per | custom service | **deployment** → a service = **two** pointers (dev + prod) |
| Says | *how* to run it | *what* to run + *where* (namespace) + *which* overlay |

The dev/prod split lives entirely in these two pointers: `<svc>-dev` → namespace `<svc>` +
`values-dev.yaml`; `<svc>-prod` → namespace `<svc>-prod` + `values-prod.yaml`. **One recipe, two
pointers.**

### How an `Application` renders a `services/<svc>/helm` chart (the pipeline)

A single-source Helm `Application` (the golden path — no kustomize, no multi-source `$values`):

```yaml
source:
  repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
  targetRevision: main
  path: services/ktayl-policy-service/helm     # the wrapper chart dir
  helm:
    releaseName: ktayl-policy-service          # MANDATORY (see below)
    valueFiles:
      - values-dev.yaml                        # the env overlay
destination:
  namespace: ktayl                             # the room (dev)
```

What ArgoCD's **repo-server** does with that, step by step:

1. **Checkout** `minicloud-gitops@main` and read the chart at `path:`. It sees `Chart.yaml` → this is a
   Helm source.
2. **Resolve the dependency.** The wrapper `dependencies:` on the shared library chart
   `minicloud-app-deployment` (`repository: oci://ghcr.io/andrelair-platform`, version-pinned). The
   repo-server runs **`helm dependency build`**, which reads the **committed `Chart.lock`** and pulls that
   exact library version from the **ghcr OCI registry**. That registry is authenticated by a registered
   ArgoCD repo credential (`ghcr-oci-repo`, `type: helm`, `enableOCI: true`, delivered by ESO from Vault)
   — which is why `Chart.lock` **must be committed** (no lock → the build can't resolve the dep → the app
   won't render).
3. **Render.** `helm template <releaseName> . -f values-dev.yaml` — the chart's own `values.yaml` is the
   base, `values-dev.yaml` overlays it. The **library subchart** renders the reusable workload
   (Deployment/Rollout + Service + Ingress + NetworkPolicy + ServiceMonitor + PDB…); the wrapper's **own
   `templates/`** render the service-specific extras (TLS Certificate, CNPG database, ExternalSecrets…).
   One Helm render → a flat stream of plain Kubernetes manifests.
4. **Apply.** ArgoCD diffs that rendered output against the live cluster and applies it with
   **ServerSideApply** into the `destination.namespace` (`CreateNamespace=true` makes the namespace if
   missing). `syncPolicy.automated` then keeps it reconciled forever: **selfHeal** re-applies any manual
   drift, **prune** deletes anything removed from git.

```
apps/.../ktayl-policy-service-dev.yaml  (the Application)
        │ source.path → services/ktayl-policy-service/helm
        ▼
ArgoCD repo-server:  helm dependency build (Chart.lock → pull minicloud-app-deployment from ghcr OCI)
        │            helm template <releaseName> . -f values-dev.yaml
        ▼            → library subchart (workload) + wrapper templates/ (cnpg, cert, ES…)
rendered manifests ──ServerSideApply──► namespace "ktayl"   (selfHeal + prune keep it matching git)
```

**Why `releaseName` is mandatory:** the library chart derives every object's name from the Helm
**release name**. Omit `helm.releaseName` and ArgoCD defaults it to the *Application* name — the workload,
Service and Rollout would silently take the wrong name. Always set it to the service slug.

**Promotion (dev→prod)** never changes *where* an app runs — it's the **same immutable image** moved across
the two overlay files by **Kargo** (a dev-overlay PR, then a CODEOWNERS-gated prod-overlay PR). The two
`Application` pointers are stable; only the `image.tag` inside the values files advances. See
[End-to-End Delivery Workflow](/platform/developer-platform/delivery-workflow).

---

## The two deploy paths — custom wrapper vs vendor multi-source (current)

The pipeline above is for apps **you build**. Most apps on the cluster — Grafana, Vault, Harbor, Tempo,
ERPNext, cert-manager… — come from an **upstream open-source Helm chart you did not write**, and are wired
a different way. The split is roughly:

| | **Custom-built** (single-source) | **Vendor / open-source chart** (multi-source) |
|---|---|---|
| ~Count | ~63 Applications | ~42 Applications |
| Chart comes from | `services/<svc>/helm/` (your wrapper chart) | the **vendor's own Helm repo** (pulled at deploy time) |
| You build the image? | yes → **Kargo** promotes dev→prod | no → nothing to build, nothing to promote |
| Updates via | Kargo (image tag) | **Renovate** bumps the pinned chart version |
| Your config lives in | `services/<svc>/helm/values-*.yaml` | `helm-values/minicloud-1/<app>-values.yaml` |

### How a vendor app is provisioned — the multi-source `Application`

Instead of pointing at a chart in your repo, the `Application` lists **2–3 `sources:`** that ArgoCD
stitches together at render time. Real example (Tempo):

```yaml
spec:
  sources:
    # 1️⃣ THE UPSTREAM CHART — pulled straight from the vendor, pinned version
    - repoURL: https://grafana.github.io/helm-charts
      chart: tempo
      targetRevision: "1.24.4"                 # Renovate bumps this
      helm:
        releaseName: tempo
        valueFiles:
          - $values/helm-values/minicloud-1/tempo-values.yaml   # ← OUR config

    # 2️⃣ THE VALUES SOURCE — our gitops repo, exposed as "$values"
    - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
      targetRevision: main
      ref: values                              # makes $values resolve to this checkout

    # 3️⃣ (optional) OUR EXTRA RAW MANIFESTS alongside the chart
    - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
      targetRevision: main
      path: platform/observability/tempo       # e.g. 01-networkpolicy.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: tempo
```

What ArgoCD does with it:

1. **Pulls the upstream chart** directly from the vendor's Helm repo (`grafana.github.io/...`) at the
   pinned `targetRevision` — the real published chart, not a copy kept in your repo.
2. **Overlays *your* values.** The `$values/...` reference resolves into source #2 (the gitops repo), so
   `helm-values/minicloud-1/tempo-values.yaml` is **your** customization of the vendor chart (hostnames,
   storage, CA trust, resources, SSO…). `ref: values` is what makes `$values` a valid prefix.
3. **Adds your extras** (source #3) — raw manifests the vendor chart doesn't ship: a NetworkPolicy, an
   ExternalSecret, an Ingress, CRs. Applied in the same sync.
4. Same tail as any app: ServerSideApply into the namespace, `selfHeal` + `prune` keep it matching git.

### The mental map (where each piece lives)

```
apps/platform/<layer>/<app>.yaml              ← the Application (lists the sources)
helm-values/minicloud-1/<app>-values.yaml     ← YOUR values (the config you own)
platform/<layer>/<app>/                        ← YOUR extra raw manifests (netpol, ES, CRs)
   ⟵ the chart itself is NOT in your repo — pulled from the vendor at deploy time
```

**No wrapper chart, no `Chart.lock`, no library dependency, no Kargo.** A vendor chart fails the Kargo
test (you don't build its image; it's one instance, not a dev→prod pair of an artifact you built), so it
**self-updates by a Git version bump** → ArgoCD sync. **Renovate** watches the `targetRevision` (its
`argocd` manager in `renovate.json`) and opens a PR when the vendor publishes a new chart version; merging
it is the release decision. To change *how* a vendor app runs, you edit **one file**:
`helm-values/minicloud-1/<app>-values.yaml`.

:::tip Which path am I on?
**Did you build the image?** Yes → custom wrapper (single-source, `services/<svc>/helm`, Kargo). No, it's
an upstream chart → vendor multi-source (`helm-values/` + the pinned `targetRevision`, Renovate). The
generic sections below predate this split and use a stale `staging`/manual-sync layout — prefer this
section.
:::

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
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Kargo-managed services use the protected promotion PR as the human release decision. After it merges,
ArgoCD syncs production automatically; do not add a second manual sync gate. Manual sync is reserved
for applications whose owning GitOps pattern explicitly requires it, plus documented recovery work.

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

:::warning Superseded — see [The two deploy paths](#the-two-deploy-paths--custom-wrapper-vs-vendor-multi-source-current) above
This generic example (a `staging` env, a Harbor-hosted chart) predates the current layout. The **real,
current** multi-source pattern — a vendor chart pulled from its upstream Helm repo + `$values` from
`helm-values/` + optional raw extras — is documented in *The two deploy paths* section above. Kept here
only for the conceptual shape.
:::

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
    - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
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
