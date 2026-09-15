---
title: End-to-End Delivery Workflow (GAP wrapper-chart)
sidebar_label: Delivery Workflow
---

# End-to-End Delivery Workflow

> **What:** how a commit in an application repo becomes a running pod — the two-repo GitOps
> model, the GAP wrapper-chart deployment artifact, and the Kargo-driven promotion path.
> **Why it's its own page:** this is the **current end-to-end standard** for custom apps (wrapper
> charts + single ArgoCD Helm source), verified on `platform-demo`. [Kargo Promotion](./kargo-promotion)
> goes deep on promotion mechanics; [Third-Party Charts](./third-party-charts) covers upstream Helm
> tools (Grafana/Vault/…), which follow a different (no-promotion) path.
> **Chart internals:** the [Helm golden-path ADR](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/helm-golden-path.md)
> and `.claude/rules/gitops.md` (*Helm golden path — GAP wrapper-chart*).

## Two repositories, two responsibilities

Delivery is split across **application repos** and the single **deployment repo**
(`minicloud-gitops`). This mirrors an enterprise *Application Platform* (wrapper-chart) model.

| | Application repo (e.g. `platform-demo`, `ktayl-policy-service`) | Deployment repo (`minicloud-gitops`) |
|---|---|---|
| Contains | source, `Dockerfile`, tests, CI | ArgoCD `Application`s, per-app **wrapper Helm charts**, the shared library chart, platform manifests |
| Answers | *"what the software is"* | *"how/where it runs"* |
| Produces | a signed, SBOM'd **image** | the declarative **desired state** of the cluster |
| Owner | application developer | platform/DevOps (here: same person; the split is structural, enforced by CODEOWNERS) |
| Holds deploy config? | **no** — zero Helm/k8s config in the app repo | **yes** — all of it |

The application developer never edits infrastructure to ship a version; the deployment repo is the
auditable source of truth for what is running.

## Start here: what change are you making?

Most delivery confusion comes from opening the right repo but the wrong layer. Use this routing table
before editing anything:

| Change | Edit where | Why |
|---|---|---|
| Application code, tests, API behavior, UI behavior | the application repo (`retrieva`, `platform-demo`, `ktayl-policy-service`, …) | this changes what the software is |
| Image version promotion from dev to prod | normally Kargo; review the PR it opens in `minicloud-gitops` | promotion is an auditable Git change, not a local edit |
| Replicas, resources, probes, env vars, ingress hosts, KEDA, Vault/ESO wiring | `minicloud-gitops/services/<svc>/helm/values*.yaml` or wrapper `templates/` | this changes how the app runs |
| ArgoCD app source, namespace, project permissions | `minicloud-gitops/apps/` and `manifests/argocd-project/` | this changes what ArgoCD is allowed to reconcile |
| Third-party platform tool config | `minicloud-gitops/helm-values/` | upstream chart plus local values is the platform-tool contract |
| Cluster-wide policy, quota, RBAC, network rule | `minicloud-gitops/manifests/` | shared platform controls belong outside one service |
| Bootstrap, OS, node prep, MAAS/k3s install | `minicloud-ansible` or `minicloud-opentofu` | these are below the GitOps application layer |

The rule of thumb: **source repos produce artifacts; `minicloud-gitops` decides how artifacts and
platform services run; ArgoCD is the only cluster writer for managed workloads.**

## The pipeline, end to end

```
 APPLICATION REPO                         DEPLOYMENT REPO (minicloud-gitops)
 ────────────────                         ─────────────────────────────────
 git push main
   │
   ▼
 CI: test → build → scan → sign (cosign) → SBOM
   │  (build + PROVE only — no gitops write)
   ▼
 image → Harbor (dev tag) + ghcr (prod SHA)
   │
   ▼
 ┌── KARGO ──────────────────────────────────────────────────────────┐
 │ Warehouse detects the new image  →  Freight (immutable artifact)   │
 │   │                                                                │
 │   ▼  auto-promote (ProjectConfig: stage dev, autoPromotionEnabled) │
 │  Stage dev  → yaml-update  services/<svc>/helm/values-dev.yaml     │
 │                            key minicloud-app-deployment.image.tag  │
 │   │                                                                │
 │   ▼  opens PR (label: automerge)                                   │
 │  kargo-automerge.yml  → merges (dev-only path guard)  ───────────► main
 │   │                                                                │
 │   ▼  Stage dev verification (AnalysisRun <svc>-dev-verify)         │
 │  Freight "Verified in dev"  (the dev→prod gate)                    │
 │   │                                                                │
 │   ▼  promote to Stage prod  (manual / gated)                       │
 │  Stage prod → yaml-update  services/<svc>/helm/values-prod.yaml    │
 │   │                                                                │
 │   ▼  opens PR (NO automerge)                                       │
 │  CODEOWNERS review on services/*/helm/  ────────────────────────► main
 └────────────────────────────────────────────────────────────────────┘
   │
   ▼
 ArgoCD renders the wrapper chart (helm dependency build → library chart from OCI)
   │
   ▼
 cluster: Deployment/Rollout + Service + Ingress + KEDA + Cert + … (dev / prod)
```

**Division of labour:** CI *builds and proves* the artifact; **Kargo promotes** it (the one thing
ArgoCD does not do); **ArgoCD deploys** it. Nothing writes to the cluster except ArgoCD.

## Workflow for GitOps changes in `minicloud-gitops`

For a GitOps-only change, the workflow is shorter than a full application release:

1. Open `minicloud-gitops` and run `git status`.
2. Identify the smallest owned path: `services/<svc>/helm/` for a custom app, `helm-values/` for a
   third-party chart, or `manifests/` for a shared platform concern.
3. Make the declarative change in Git. Do not patch the live cluster to make the desired state true.
4. Render or diff locally when possible:
   ```bash
   cd services/<svc>/helm
   helm dependency update .
   helm template <svc> . -f values-dev.yaml
   ```
5. Open a PR. Dev-only Kargo PRs may auto-merge; prod paths and platform controls require CODEOWNERS
   review.
6. After merge, ArgoCD reconciles the change. Verify the relevant app is `Synced` and `Healthy`.

Direct `kubectl apply`, `helm upgrade`, or manual ArgoCD sync is reserved for bootstrap, recovery, or
documented break-glass work. The normal path is always **Git commit -> PR -> ArgoCD reconciliation**.

## The deployment artifact — a wrapper Helm chart

Each app is its **own thin Helm chart** under `services/<svc>/helm/` that declares a dependency on
the shared `minicloud-app-deployment` library chart and carries its service-specific extras in its
own `templates/`:

```
services/<svc>/helm/
  Chart.yaml        # dependencies: [minicloud-app-deployment @ X.Y.Z, oci://ghcr.io/andrelair-platform]
  Chart.lock        # committed — ArgoCD runs `helm dependency build` to fetch the library
  values.yaml       # common: the "minicloud-app-deployment:" subchart block + wrapper-local keys
  values-dev.yaml   # dev overlay  (image.tag, hosts, replicas)        ← Kargo yaml-updates this
  values-prod.yaml  # prod overlay (image.tag, hosts, replicas, gates) ← Kargo yaml-updates this
  templates/        # service-specific extras (DB, AnalysisTemplate, SSO Ingress, ExternalSecret…)
```

One Helm render, **one ArgoCD source** — no kustomize, no multi-source `$values`, no separate
satellites source. The app's `values.yaml` is the **deployment contract**; the library chart is the
platform **golden path**. See the [ADR](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/helm-golden-path.md)
for the chart's config surface and hardened defaults.

## The three control points

| Control | Where | Guards |
|---|---|---|
| **dev auto-merge** | `.github/workflows/kargo-automerge.yml` | merges only dev-only PRs — paths matching `services/*/minicloud-1/dev/` **or** `services/*/helm/values-dev.yaml`. Everything else is refused. |
| **dev→prod gate** | Kargo Stage prod `sources.stages: [dev]` + `<svc>-dev-verify` AnalysisRun | prod only accepts Freight already **verified in dev** |
| **prod merge gate** | `.github/CODEOWNERS` on `services/*/helm/`, `services/*/base/`, `services/*/kargo/`, `apps/` | prod promotion PR needs `@AndreLair` review |

## Verified end-to-end

Proven on `platform-demo` (two promotion cycles): a Kargo Promotion `yaml-update`d
`services/platform-demo/helm/values-dev.yaml` `image.tag` → opened the dev PR → `kargo-automerge`
merged it → ArgoCD synced the wrapper chart → the Rollout picked up the promoted tag. The same
mechanics drive the CODEOWNERS-gated prod PR.

## Invariants & gotchas (learned the hard way)

| Invariant | Why |
|---|---|
| Commit `Chart.lock`; **don't** list `charts/` in `.helmignore` | ArgoCD needs the lock to `helm dependency build`; listing `charts/` in `.helmignore` makes helm treat the dep as missing. `charts/` is gitignored instead. |
| Set `helm.releaseName: <svc>` on the ArgoCD app | the library uses the release name for `fullname`; without it, the workload takes the app's name. |
| Escape non-Helm `{{ }}` in `templates/` | ESO output-templates and Argo-Rollouts args (and even YAML comments) are parsed by Helm — wrap them in backtick strings. |
| Migrating an existing workload: match the **immutable selector** | set subchart `selectorLabels` to the live Deployment/Rollout selector for a zero-downtime in-place flip. A changed `spec.selector` → `SyncFailed`. |
| Keep a service's own SA-token / Vault needs in mind | `automountServiceAccountToken: false` is the hardened default, but **Vault agent injection requires the token mount** — disabling it denies pod creation (latent behind scale-to-zero). |
| A **canary** Rollout at scale-to-zero can't self-complete | with 0 replicas the canary analysis has no pod/traffic → it sits `Progressing`/`Degraded` until real traffic (or the dev-verify smoke) wakes it via the KEDA interceptor. |
| Images must be **env-agnostic** | the *same* artifact runs dev and prod; read env at runtime. Prod pins an immutable ghcr SHA. |

## Operational runbook

```bash
# Render/validate a service's wrapper chart locally
cd services/<svc>/helm && helm dependency update . && helm template <svc> . -f values-dev.yaml

# Promote a specific Freight to dev (normally automatic) — Kargo CLI or a Promotion CR
kubectl -n <svc> create -f - <<'EOF'
apiVersion: kargo.akuity.io/v1alpha1
kind: Promotion
metadata: { generateName: manual-, namespace: <svc> }
spec: { stage: dev, freight: <freight-name> }
EOF

# Promote dev-verified Freight to prod → opens the CODEOWNERS-gated PR (approve with --squash)

# Roll back: re-promote the previous Freight (or revert the values PR); ArgoCD reconciles.

# Wake a scale-to-zero app (e.g. to let a canary finish) via the KEDA interceptor:
#   curl -H 'Host: <dev-host>' http://keda-add-ons-http-interceptor-proxy.keda.svc:8080/<readyz>
```

## Related

- [Third-Party Charts](./third-party-charts) · [Kargo Promotion](./kargo-promotion) · [Helm vs Kustomize](./helm-vs-kustomize) · [Argo Rollouts](./argo-rollouts) · [KEDA scale-to-zero](./keda-cron-scale-to-zero)
- Deployment repo: [`services/_template-helm/`](https://github.com/andrelair-platform/minicloud-gitops/tree/main/services/_template-helm) (scaffold) · [Helm golden-path ADR](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/helm-golden-path.md)
