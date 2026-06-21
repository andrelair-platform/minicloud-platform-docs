---
id: multi-env-namespaces
title: Multi-Environment Namespaces (Phase 56)
sidebar_label: Multi-Env Namespaces
---

# Multi-Environment Namespaces

Namespace-based multi-tenancy strategy deployed in Phase 56. A single k3s cluster hosts **dev**, **staging**, and **prod** environments via Kubernetes namespaces, with Kustomize overlays and an ArgoCD ApplicationSet generating all environments automatically.

---

## Design

| Concern | Decision |
|---|---|
| Isolation unit | Kubernetes Namespace |
| Naming convention | `{team}-{env}` (e.g. `insurance-dev`, `collab-staging`) |
| Source of truth | `minicloud-gitops/environments/overlays/{env}/{team}/` |
| Deployment engine | ArgoCD ApplicationSet — matrix generator |
| Resource governance | Namespace-scoped ResourceQuota + LimitRange |

Teams currently: `insurance`, `collab`. Environments: `dev`, `staging`, `prod`.

---

## Namespace Layout

```
environments/
└── overlays/
    ├── dev/
    │   ├── insurance/
    │   │   ├── kustomization.yaml
    │   │   ├── 00-namespace.yaml
    │   │   ├── 01-resourcequota.yaml
    │   │   └── 02-limitrange.yaml
    │   └── collab/
    │       └── … (same structure)
    ├── staging/
    │   ├── insurance/
    │   └── collab/
    └── prod/
        ├── insurance/    # namespace only — no quota
        └── collab/
```

---

## Resource Quotas

| Environment | CPU Request | Memory Request | Storage | Pods | PVCs |
|---|---|---|---|---|---|
| `dev` | 500m | 1 Gi | 20 Gi | 10 | 5 |
| `staging` | 1 | 2 Gi | 50 Gi | 20 | 10 |
| `prod` | — (no quota) | — | — | — | — |

`prod` has no ResourceQuota — resource usage is enforced via Grafana monitoring and alerts, not hard limits.

## LimitRange Defaults

| Environment | Default CPU | Default Mem | Max CPU | Max Mem |
|---|---|---|---|---|
| `dev` | 200m / req 100m | 256Mi / req 128Mi | 1 | 2Gi |
| `staging` | 500m / req 200m | 512Mi / req 256Mi | 2 | 4Gi |
| `prod` | 500m / req 200m | 512Mi / req 256Mi | 4 | 8Gi |

LimitRange defaults ensure every container in the namespace gets CPU/memory limits even when not set explicitly — required by the Gatekeeper `require-resource-limits` policy.

---

## ArgoCD ApplicationSet

`apps/environments.yaml` uses a **matrix generator** (3 envs × 2 teams) to create 6 ArgoCD Applications automatically:

```yaml
generators:
  - matrix:
      generators:
        - list:
            elements:
              - env: dev
              - env: staging
              - env: prod
        - list:
            elements:
              - app: insurance
              - app: collab
template:
  metadata:
    name: "{{ .app }}-{{ .env }}"
  spec:
    source:
      path: "environments/overlays/{{ .env }}/{{ .app }}"
    destination:
      namespace: "{{ .app }}-{{ .env }}"
    syncPolicy:
      automated:
        prune: true
        selfHeal: true
      syncOptions:
        - CreateNamespace=true
        - ServerSideApply=true
```

The 6 resulting apps: `insurance-dev`, `insurance-staging`, `insurance-prod`, `collab-dev`, `collab-staging`, `collab-prod`. All currently **Synced + Healthy**.

---

## Kustomize Overlay Example (insurance-dev)

```yaml
# environments/overlays/dev/insurance/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: insurance-dev
resources:
  - 00-namespace.yaml
  - 01-resourcequota.yaml
  - 02-limitrange.yaml
commonLabels:
  env: dev
  team: insurance
```

`commonLabels` propagates `env` and `team` labels to every resource in the overlay.

---

## Cloudflare Tunnel Routes

15 new routes registered at Phase 56 for app services in each env. Pattern:

| Subdomain | Maps to (originServerName) |
|---|---|
| `dev.erp.devandre.sbs` | `dev.erp.10.0.0.200.nip.io` |
| `staging.erp.devandre.sbs` | `staging.erp.10.0.0.200.nip.io` |
| `erp.devandre.sbs` (prod) | `erp.10.0.0.200.nip.io` |

Apps covered: `erp`, `intranet`, `wiki`, `chat`, `mail`.

Tunnel config (`~/.cloudflared/config.yml` on controller):
```yaml
- hostname: dev.erp.devandre.sbs
  service: https://10.0.0.200
  originRequest:
    originServerName: dev.erp.10.0.0.200.nip.io
    noTLSVerify: true
```

---

## Adding a New Team

1. Create `environments/overlays/dev/{team}/`, `staging/{team}/`, `prod/{team}/` with the 4 files from an existing team as template.
2. Add `- app: {team}` to the ApplicationSet list generator in `apps/environments.yaml`.
3. Commit and push → ArgoCD creates the 3 new namespaces automatically.
4. Register Cloudflare Tunnel DNS CNAMEs for any new public subdomains.

---

## Verification

```bash
# All 6 apps synced
kubectl --context minicloud get applications -n argocd \
  | grep -E 'insurance|collab'

# Namespaces with labels
kubectl --context minicloud get namespaces \
  -l team=insurance

# ResourceQuota in insurance-dev
kubectl --context minicloud get resourcequota -n insurance-dev
```

Expected: 6 namespaces, all Synced+Healthy, quotas showing `0 / <limit>` for each resource.
