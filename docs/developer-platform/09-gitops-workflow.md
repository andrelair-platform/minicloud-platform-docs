---
id: gitops-workflow
title: GitOps Workflow — Service Onboarding & Promotion
sidebar_label: GitOps Workflow
---

# GitOps Workflow — Service Onboarding & Promotion

This page describes the enterprise-grade GitOps strategy in use on the minicloud platform. It combines two complementary patterns:

- **Combo 1 — ArgoCD + Kustomize** for internal apps (own source code, per-environment image promotion)
- **Combo 2 — ArgoCD + Helm** for third-party tools (upstream charts, values files in minicloud-ansible)

---

## Why Two Combos?

| Concern | Internal Services | Third-Party Charts |
|---|---|---|
| Source of truth | `minicloud-gitops/services/<name>/` | `minicloud-ansible/helm-values/<name>-values.yaml` |
| Diff tool | Kustomize overlays | Helm values |
| Env promotion | Image tag bump per overlay | Single values file, chart version pin |
| CI integration | `kustomize edit set image` in dev overlay | Manual `helm upgrade` |
| Blast radius | Dev auto-syncs; staging/prod require PR | Helm controls rollout |

---

## Combo 1 — Kustomize base + overlays

### Directory layout

```
minicloud-gitops/services/<service-name>/
├── base/
│   ├── kustomization.yaml   ← lists resources, NO image tag
│   ├── deployment.yaml      ← no namespace field
│   └── service.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml  ← namespace + newTag (CI updates this)
    │   └── patch-resources.yaml
    ├── staging/
    │   ├── kustomization.yaml  ← namespace + newTag (PR to promote)
    │   └── patch-resources.yaml
    └── prod/
        ├── kustomization.yaml  ← namespace + newTag (PR to promote)
        ├── patch-resources.yaml
        ├── ingress.yaml        ← prod-only
        └── certificate.yaml   ← prod-only
```

**Key invariant:** the base has no `images:` block and no `namespace:` field. Each overlay is fully self-contained. Ingress and TLS certificates only exist in the prod overlay — dev and staging have no public exposure.

### How promotion works

```
CI push to main
  │
  ├─ build + push image to ghcr.io + Harbor
  │
  └─ bump overlays/dev/kustomization.yaml  ← kustomize edit set image
         │
         └─ ArgoCD auto-syncs platform-demo-dev (2/2 Running in platform-demo-dev ns)
                │
                ├─ open PR: bump overlays/staging/kustomization.yaml
                │     └─ ArgoCD manual sync → platform-demo-staging
                │
                └─ open PR: bump overlays/prod/kustomization.yaml
                      └─ ArgoCD manual sync → platform-demo (gitops-demo ns)
```

No single CI push ever reaches staging or prod. Both require an explicit pull request and a human clicking Sync in ArgoCD.

### ArgoCD Applications

Three ArgoCD Applications manage the three overlays:

| App | Path | Namespace | Sync |
|---|---|---|---|
| `platform-demo-dev` | `services/platform-demo/overlays/dev` | `platform-demo-dev` | Automated |
| `platform-demo-staging` | `services/platform-demo/overlays/staging` | `platform-demo-staging` | Manual |
| `platform-demo` | `services/platform-demo/overlays/prod` | `gitops-demo` | Manual |

All three are in the `minicloud-platform` AppProject — no wildcard destinations.

---

## Combo 2 — Helm + ArgoCD (third-party charts)

Third-party Helm charts (Vault, ESO, Langfuse, NGINX, etc.) are deployed via ArgoCD multi-source apps:

```yaml
sources:
  - repoURL: https://helm.releases.hashicorp.com
    chart: vault
    targetRevision: "0.*"
    helm:
      valueFiles:
        - $values/ansible/helm-values/vault-values.yaml
  - repoURL: https://github.com/andrelair-platform/minicloud-ansible.git
    targetRevision: main
    ref: values
```

Values files live in `minicloud-ansible/helm-values/` (not a git repo on the controller — always `scp` updated files before `helm upgrade`). Version pinning is done via `targetRevision` in the ArgoCD Application.

---

## Adding a new internal service

Use the template scaffolding in `services/_template/`:

```bash
cd minicloud-gitops
cp -r services/_template services/<your-service>

# Replace all placeholders
find services/<your-service> -type f -exec sed -i 's/SERVICE_NAME/<your-service>/g' {} +

# Set the initial image tag in each overlay
vim services/<your-service>/overlays/dev/kustomization.yaml
vim services/<your-service>/overlays/staging/kustomization.yaml
vim services/<your-service>/overlays/prod/kustomization.yaml
```

Then:

1. **Add the namespace to AppProject** (`manifests/argocd-project/00-project.yaml`) before creating any ArgoCD Application — permission violations happen otherwise.
2. **Add ArgoCD Application files** in `apps/` for dev, staging, and prod.
3. **Update Vault Kubernetes auth role** if the service uses vault-agent injection — add the new namespaces to `bound_service_account_namespaces`.
4. **Add Ingress + Certificate** to `overlays/prod/` if the service needs a public URL.
5. **Wire CI** in the service repo: set `GITOPS_OVERLAY: services/<your-service>/overlays/dev` and use `kustomize edit set image`.

---

## CI workflow (platform-demo as reference)

The `bump-gitops` job in `.github/workflows/ci.yml`:

```yaml
- name: Install kustomize
  run: |
    curl -sSL https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh | bash
    sudo mv kustomize /usr/local/bin/

- name: Bump image tag in dev overlay and push signed commit
  run: |
    cd "${{ env.GITOPS_OVERLAY }}"
    kustomize edit set image \
      harbor.10.0.0.200.nip.io/ghcr/${{ github.repository }}:${{ needs.build-and-push.outputs.image_tag }}
    cd -
    git add "${{ env.GITOPS_OVERLAY }}/kustomization.yaml"
    git commit -S -m "ci(<service>): bump dev image to ${{ needs.build-and-push.outputs.image_tag }}"
    git push
```

`kustomize edit set image` updates the `images[].newTag` in `overlays/dev/kustomization.yaml` atomically. No fragile yq path expressions, no risk of touching unrelated YAML documents.

---

## Vault auth for new service namespaces

When a service uses vault-agent injection, update the Kubernetes auth role to cover all three environment namespaces:

```bash
VTOKEN=$(cat ~/.vault-root-token)
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$VTOKEN vault write auth/kubernetes/role/<service> \
  bound_service_account_names=<service> \
  bound_service_account_namespaces=<service>-dev,<service>-staging,<prod-namespace> \
  policies=<service> \
  ttl=1h
```

If the pod stays in `Init:0/1`, delete it to force a retry — the Vault auth cache doesn't auto-refresh.

---

## Operational reference

| Task | Command |
|---|---|
| Force ArgoCD re-poll | `kubectl annotate app -n argocd <app> argocd.argoproj.io/refresh=normal` |
| Manually sync staging | ArgoCD UI → platform-demo-staging → Sync |
| Verify kustomize output | `kustomize build services/platform-demo/overlays/dev` |
| Check what ArgoCD would change | ArgoCD UI → App Diff |
| Roll back dev | Bump `newTag` in overlays/dev back to prior SHA, push |
