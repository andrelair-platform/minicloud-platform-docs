---
id: backstage-helm-kustomize
title: Backstage — Helm vs Kustomize Apps
sidebar_label: Backstage + Helm/Kustomize
---

# Backstage — How It Works With Helm and Kustomize Apps

Backstage is the developer portal that aggregates visibility across the
platform. It connects to the Kubernetes cluster, ArgoCD, and GitHub to
surface a unified view of every service. The integration works
differently depending on whether a component is deployed via Helm
(third-party tool) or Kustomize (own service).

---

## The three Backstage integration points

Regardless of deployment method, Backstage uses the same three mechanisms:

| Mechanism | What it does | Configured via |
|---|---|---|
| **Catalog** | Registers the component (name, description, links, owner) | `catalog-info.yaml` in a repo |
| **Kubernetes plugin** | Shows live pod status, restarts, image tag | `backstage.io/kubernetes-id` label on pods |
| **ArgoCD plugin** | Shows sync status, health, last deployed commit | `argocd/app-name` annotation in catalog entry |

---

## Custom apps deployed via Kustomize

`platform-demo` is the reference example. Backstage has full end-to-end
visibility because the team owns every layer.

### How it is wired

**1. Catalog entry lives in the service repo.**

The `platform-demo` GitHub repo has a `catalog-info.yaml` at its root.
Backstage reads it directly from GitHub:

```yaml
# platform-demo/catalog-info.yaml
metadata:
  name: platform-demo
  annotations:
    backstage.io/kubernetes-id: platform-demo   # matches pod label
    argocd/app-name: platform-demo              # ArgoCD app name
    github.com/project-slug: andrelair-platform/platform-demo
```

**2. The pod label is set in the Kustomize base.**

The `base/deployment.yaml` pod template carries the matching label:

```yaml
# services/platform-demo/base/deployment.yaml
spec:
  template:
    metadata:
      labels:
        backstage.io/kubernetes-id: platform-demo
```

Because the label is in the base, it is inherited by all three overlays
automatically — dev, staging, and prod pods all carry it. Backstage shows
pods from all three namespaces on the same component page.

**3. CI/CD tab is populated automatically.**

The `github.com/project-slug` annotation causes Backstage to query the
GitHub API for recent workflow runs. No extra configuration needed.

### What you see in Backstage

```
Component: platform-demo
├── Overview     ← description, tags, live URL, docs link, ArgoCD link
├── CI/CD        ← recent GitHub Actions runs (build, test, push, bump)
├── Kubernetes   ← pods in platform-demo-dev / platform-demo-staging / gitops-demo
│                   each pod: status, restarts, image SHA, CPU/memory
└── ArgoCD       ← sync status, health, last commit SHA, diff link
```

---

## Helm-deployed tools (open source)

For third-party tools deployed via Helm — Vault, Grafana, ArgoCD,
Open WebUI, Ollama, Langfuse — the catalog entry is written in
`minicloud-gitops/catalog-info.yaml` rather than in the upstream chart
repository (which you don't control).

The pod label must be injected via the Helm values file, using whatever
key the chart exposes for pod-level labels.

### Label key by chart

Different charts use different keys:

| Tool | Chart | Values key |
|---|---|---|
| Open WebUI | open-webui/open-webui | `podLabels:` |
| Ollama | otwld/ollama | `podLabels:` |
| Vault | hashicorp/vault | `server.extraLabels:` |
| Grafana (via kps) | prometheus-community/kube-prometheus-stack | `grafana.podLabels:` |
| ArgoCD server | argoproj/argo-cd | `server.podLabels:` |
| Langfuse | langfuse/langfuse | `langfuse.labels:` |

Example for Vault (`helm-values/vault-values.yaml`):

```yaml
server:
  extraLabels:
    backstage.io/kubernetes-id: vault
```

Example for Open WebUI (`helm-values/open-webui-values.yaml`):

```yaml
podLabels:
  backstage.io/kubernetes-id: open-webui
```

### Catalog entry lives in minicloud-gitops

Because there is no source repo to put a `catalog-info.yaml` in, the
entry goes in `minicloud-gitops/catalog-info.yaml`:

```yaml
# minicloud-gitops/catalog-info.yaml
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: vault
  annotations:
    backstage.io/kubernetes-id: vault      # matches server.extraLabels
    argocd/app-name: vault                 # ArgoCD app name
    github.com/project-slug: andrelair-platform/minicloud-gitops
spec:
  type: service
  lifecycle: production
  owner: andrelair-platform
  system: minicloud-platform
```

### What you see in Backstage

```
Component: vault
├── Overview    ← description, tags, Vault UI link, ArgoCD link
├── Kubernetes  ← vault-0 pod: status, restarts, image tag
└── ArgoCD      ← sync status, health, last commit

Component: grafana
├── Overview    ← description, tags, Grafana UI link
├── Kubernetes  ← grafana pod: status, restarts
└── ArgoCD      ← kube-prometheus-stack sync status

Component: open-webui
├── Overview    ← description, links (internal + public URL)
├── Kubernetes  ← open-webui pod across the ai namespace
└── ArgoCD      ← sync status
```

No CI/CD tab — there are no GitHub Actions workflows in
`minicloud-gitops` for these tools. The tab only appears when
`github.com/project-slug` points to a repo that has workflow runs.

---

## Side-by-side comparison

| | Custom app (Kustomize) | Helm tool |
|---|---|---|
| `catalog-info.yaml` | in the service's own repo | in `minicloud-gitops` |
| Pod label added in | base `deployment.yaml` | Helm values file (`podLabels:` / `extraLabels:` etc.) |
| Label key varies by chart | no — you set it directly | yes — check the chart's values schema |
| CI/CD tab | yes — GitHub Actions in the service repo | no |
| ArgoCD tab | yes | yes |
| Kubernetes tab | yes — all envs (dev + staging + prod) | yes — single namespace |
| Who writes the catalog entry | service team | platform team |

---

## Registered components (current state)

### Custom apps — full integration

| Component | Kubernetes label | ArgoCD app |
|---|---|---|
| `platform-demo` | `backstage.io/kubernetes-id: platform-demo` | `platform-demo` |
| `event-demo` | `backstage.io/kubernetes-id: echo-worker` | `event-demo` |
| `homer` | `backstage.io/kubernetes-id: homer` | `homer` |
| `whoami` | `backstage.io/kubernetes-id: whoami` | `whoami` |

### Helm tools — Kubernetes + ArgoCD integration

| Component | Values file key | ArgoCD app |
|---|---|---|
| `vault` | `server.extraLabels` | `vault` |
| `grafana` | `grafana.podLabels` (in kps values) | `kube-prometheus-stack` |
| `argocd` | `server.podLabels` | `argo-cd` |
| `open-webui` | `podLabels` | `open-webui` |
| `ollama` | `podLabels` | `ollama` |
| `langfuse` | `langfuse.labels` | `langfuse` |

---

## Adding a new component to Backstage

### New custom service (Kustomize)

1. Add `catalog-info.yaml` to the service repo root with
   `backstage.io/kubernetes-id: <name>` annotation.
2. Add `backstage.io/kubernetes-id: <name>` label to the pod template
   in `services/<name>/base/deployment.yaml`.
3. Add the catalog URL to `backstage.appConfig.catalog.locations` in
   `helm-values/backstage-values.yaml`.

### New Helm tool

1. Check the chart's default values for the pod label key:
   `helm show values <repo>/<chart> | grep podLabels`
2. Add the label to `helm-values/<tool>-values.yaml`.
3. Add a catalog entry to `minicloud-gitops/catalog-info.yaml`.
4. Commit and push — ArgoCD syncs the label into the pods; Backstage
   picks up the new catalog entry on its next refresh cycle (~1 min).

---

## Troubleshooting

**Kubernetes tab is empty:**
- Check the pod carries the label: `kubectl get pod <pod> -o jsonpath='{.metadata.labels}'`
- Check the value in `catalog-info.yaml` matches exactly (case-sensitive)
- Check the Backstage service account has `get/list/watch` on pods in that namespace

**ArgoCD tab shows "App not found":**
- Verify `argocd/app-name` annotation matches exactly the ArgoCD Application name
- The ArgoCD plugin uses the credentials in `backstage-phase24-secret` — verify they are still valid

**Catalog entry not appearing:**
- Check the URL in `backstage.appConfig.catalog.locations` returns HTTP 200
- Check Backstage logs: `kubectl logs -n backstage -l app.kubernetes.io/name=backstage`
