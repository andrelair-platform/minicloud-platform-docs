---
id: per-env-isolation
title: Phase 86 — Per-Env Namespace Isolation
sidebar_position: 7
---

# Phase 86 — Per-App-Per-Env Namespace Isolation

Implemented 2026-08-02. Completed the **Option 2 multi-namespace pattern** across four services (`platform-demo`, `minicloud-plane`, `collab`, `insurance`): each service gets three dedicated namespaces (`<app>-dev`, `<app>-staging`, `<app>-prod`) with full isolation controls applied consistently at every tier.

Eight pull requests (PRs #480–#487, #496) shipped the controls in a single batch. All PRs were additive except PR #485 (prod namespace rename) and required no cluster downtime.

---

## The Pattern

```
<app>-dev        ← CI auto-syncs on every push to main
<app>-staging    ← Manual sync; tag promoted via PR after dev validation
<app>-prod       ← Manual sync; tag promoted via PR after staging approval
```

Each namespace is an ArgoCD `Application` pointing to the matching Kustomize overlay in `minicloud-gitops/services/<app>/overlays/{dev,staging,prod}/`. The base layer holds shared manifests with no namespace or image tag; overlays pin both.

---

## Controls Deployed Per Namespace

### 1. NetworkPolicies (PR #480)

Every `<app>-{dev,staging,prod}` namespace gets four policies, applied via `manifests/network-policies/`:

| Policy | Type | Effect |
|--------|------|--------|
| `default-deny-ingress` | `NetworkPolicy` | Drops all inbound traffic by default |
| `allow-same-namespace` | `NetworkPolicy` | Pods in the same namespace can reach each other |
| `allow-ingress-nginx` | `NetworkPolicy` | NGINX ingress controller can forward HTTP |
| `allow-monitoring-scrape` | `NetworkPolicy` | Prometheus/OTel can scrape metrics |
| `allow-node-entities` | `CiliumNetworkPolicy` | kubelet health probes pass through (host + remote-node entities) |

The Cilium policy is required because kubelet probe traffic arrives with `host`/`remote-node` Cilium entity identity, not a pod IP — standard K8s NetworkPolicies cannot match it.

### 2. ResourceQuota + LimitRange (PR #481)

Sized for lightweight Go services. Quotas live in `manifests/quotas/` (platform-demo, minicloud-plane) and `environments/overlays/prod/{collab,insurance}/`:

| Tier | CPU request | Mem request | CPU limit | Mem limit | Max pods |
|------|-------------|-------------|-----------|-----------|----------|
| dev | 200m | 256Mi | 1 | 1Gi | 10 |
| staging | 500m | 512Mi | 2 | 2Gi | 20 |
| prod | 1 | 1Gi | 3 | 4Gi | 20 |

LimitRanges inject `50m/64Mi` defaults so pods without a `resources:` block still count against the quota instead of being unconstrained.

### 3. ConfigMap Per Overlay (PR #482)

Non-secret config is now visible in git. Each `platform-demo` overlay ships a `ConfigMap` mounted via `envFrom`:

| Overlay | `APP_ENV` | `LOG_LEVEL` |
|---------|-----------|-------------|
| dev | `development` | `debug` |
| staging | `staging` | `info` |
| prod | `production` | `warn` |

Vault agent injection for `API_KEY` is unchanged — secret and non-secret config coexist.

### 4. Per-Env Ingress + Certificate (PRs #483, #496)

Each overlay now owns its own `Ingress` and cert-manager `Certificate`, giving each environment a stable, independently routable URL:

| Env | Internal URL | Public URL |
|-----|-------------|-----------|
| dev | `platform-demo-dev.10.0.0.200.nip.io` | `dev.demo.devandre.sbs` |
| staging | `platform-demo-staging.10.0.0.200.nip.io` | `staging.demo.devandre.sbs` |
| prod | `platform-demo.10.0.0.200.nip.io` | `demo.devandre.sbs` |

All three ingresses carry identical Authentik forward-auth annotations (proxy to outpost, error-page 401 → sign-in redirect). Certificates are issued by `minicloud-ca` ClusterIssuer; Cloudflare Tunnel provides the public TLS edge.

### 5. RBAC RoleBindings via OIDC Groups (PR #484)

Two Authentik groups created and bound to Kubernetes RBAC:

| Group | Kubernetes binding | Namespaces |
|-------|-------------------|------------|
| `oidc:Développeurs` | `ClusterRole/edit` | all `*-dev` namespaces |
| `oidc:QA` | `ClusterRole/view` | all `*-staging` namespaces |

Production namespaces have **no human RoleBinding** — ArgoCD service account access is the only path to prod, enforcing the principle of least privilege.

`manifests/rbac/02-env-rolebindings.yaml` covers `platform-demo` and `minicloud-plane`. Per-overlay `03-rolebinding.yaml` files handle `collab` and `insurance` via the `environments/overlays/` ApplicationSet path.

### 6. Prod Namespace Rename (PR #485)

`gitops-demo` → `platform-demo-prod` to align with the per-app-per-env naming convention. Three files changed:

```
services/platform-demo/overlays/prod/kustomization.yaml  namespace field
apps/platform-demo.yaml                                  destination.namespace + ignoreDifferences.namespace
manifests/argocd-project/00-project.yaml                 added platform-demo-prod destination
```

Post-merge steps:
1. Create namespace manually (ArgoCD's `CreateNamespace=true` only works with automated sync, not manual patch-trigger)
2. Trigger ArgoCD sync
3. Update Vault Kubernetes auth role to allow `platform-demo-prod` instead of `gitops-demo`
4. Delete old ingress in `gitops-demo` first (nginx admission webhook blocks duplicate host rules)
5. Delete remaining orphans in `gitops-demo`

### 7. minicloud-plane Staging + Prod ArgoCD Applications (PR #486)

`apps/minicloud-plane-staging.yaml` and `apps/minicloud-plane-prod.yaml` added, both with manual sync and `ignoreDifferences` for Rollout replicas. All three namespaces (`minicloud-plane-{dev,staging,prod}`) were already in the AppProject destinations.

---

## Promotion Flow

```
Push to main
    │
    ▼
CI builds image → tags as <sha>
    │
    ▼
kustomize edit set image in overlays/dev/   ← auto-commit by CI
    │
    ▼
ArgoCD auto-syncs platform-demo-dev         ← live within ~30s
    │
    ▼  (validate in dev)
PR: bump newTag in overlays/staging/kustomization.yaml
    │
    ▼
Merge PR → manual ArgoCD sync click
    │
    ▼
ArgoCD syncs platform-demo-staging          ← live after click
    │
    ▼  (validate in staging, QA sign-off)
PR: bump newTag in overlays/prod/kustomization.yaml
    │
    ▼
Merge PR → manual ArgoCD sync click
    │
    ▼
ArgoCD syncs platform-demo-prod             ← live after click
```

---

## Template — Guardrails Ship With Scaffold (PR #487)

`services/_template/` updated so new services start with all controls pre-wired:

```
_template/
├── base/
│   ├── networkpolicy-deny.yaml      ← default-deny + allow-same-ns + Cilium node policy
│   └── networkpolicy-ingress.yaml   ← allow-ingress-nginx + allow-monitoring
└── overlays/
    ├── dev/
    │   ├── ingress.yaml             ← Authentik forward-auth, SERVICE_NAME-dev host
    │   ├── quota.yaml               ← dev ResourceQuota + LimitRange
    │   └── rolebinding.yaml         ← oidc:Développeurs → edit
    ├── staging/
    │   ├── ingress.yaml
    │   ├── quota.yaml
    │   └── rolebinding.yaml         ← oidc:QA → view
    └── prod/
        ├── ingress.yaml             ← internal + devandre.sbs hosts
        ├── certificate.yaml
        └── quota.yaml
```

To scaffold a new service: copy `services/_template/`, replace every `SERVICE_NAME` occurrence, add the three namespaces to `manifests/argocd-project/00-project.yaml`, create ArgoCD Application files in `apps/`, and update the Vault Kubernetes auth role.

---

## Verification

```bash
# NetworkPolicies — all 4 + Cilium policy present
kubectl get networkpolicy,ciliumnetworkpolicy -n platform-demo-dev

# Quota — usage visible
kubectl describe resourcequota -n platform-demo-prod

# ConfigMap injection
kubectl exec -n platform-demo-dev <pod> -- env | grep APP_ENV

# Per-env URLs responding (302 = Authentik redirect, correct)
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://platform-demo-dev.10.0.0.200.nip.io
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://platform-demo-staging.10.0.0.200.nip.io
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://platform-demo.10.0.0.200.nip.io

# Public URLs (Cloudflare edge)
curl -sI https://dev.demo.devandre.sbs
curl -sI https://staging.demo.devandre.sbs
curl -sI https://demo.devandre.sbs

# RBAC — confirm bindings exist
kubectl get rolebinding -A | grep oidc

# RBAC — test with OIDC context
kubectl --context minicloud-oidc auth can-i create pods -n platform-demo-dev   # yes
kubectl --context minicloud-oidc auth can-i create pods -n platform-demo-prod  # no

# ArgoCD app status
kubectl -n argocd get applications | grep -E 'platform-demo|minicloud-plane'
```

---

## Gotchas Encountered

**Vault auth role scoped to old namespace.** After renaming `gitops-demo` → `platform-demo-prod`, the Vault Kubernetes auth role still listed `gitops-demo` as the authorized namespace. Pods in `platform-demo-prod` got `403 namespace not authorized` from Vault. Fix: update the role via API:

```bash
VAULT_ROOT=$(ssh controller "cat ~/.vault-root-token")
curl -sk --cacert ~/minicloud-ca.crt \
  -H "X-Vault-Token: $VAULT_ROOT" -X POST \
  -d '{"bound_service_account_names":["platform-demo"],
       "bound_service_account_namespaces":["platform-demo-prod","platform-demo-dev","platform-demo-staging"],
       "policies":["platform-demo"],"ttl":"1h"}' \
  https://vault.devandre.sbs/v1/auth/kubernetes/role/platform-demo
```

**nginx admission webhook blocks duplicate host rules.** Trying to create the prod ingress in `platform-demo-prod` while the identical host (`platform-demo.10.0.0.200.nip.io`) still existed in `gitops-demo/platform-demo` caused: `admission webhook denied: host already defined`. Delete the old ingress first, then re-trigger the ArgoCD sync.

**`CreateNamespace=true` does not work with manual patch-trigger syncs.** ArgoCD's `syncOptions: [CreateNamespace=true]` only fires during a proper sync operation initiated through the ArgoCD API with full options. A bare `kubectl patch application … operation.sync` does not pass syncOptions through. Workaround: create namespaces manually with `kubectl create namespace` before triggering the first sync.

**Manual sync apps need a trigger on first deploy.** Apps without `syncPolicy.automated` show `OutOfSync Missing` after creation — ArgoCD detects drift but never acts. The initial bootstrap always requires one explicit sync trigger (UI click or `kubectl patch`).
