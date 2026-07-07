---
id: rbac-audit
title: RBAC Audit — SA vs Human Identity Separation
sidebar_label: RBAC Audit
---

# RBAC Audit — SA vs Human Identity Separation

Reviewed 2026-07-07. This document covers the full RBAC architecture, separation between human and workload identities, accepted-risk cluster-admin grants, and the fixes applied.

## Identity Architecture

The platform enforces a strict separation between human and workload identities.

| Identity type | Path | Example |
|---|---|---|
| Human (admin) | Authentik OIDC → OIDC group → ClusterRoleBinding | `oidc:Direction IT → cluster-admin` |
| Human (read-only) | Authentik OIDC → OIDC group → ClusterRoleBinding | `oidc:Cybersécurité → view` |
| Break-glass (human) | Static cert kubeconfig (`minicloud-break-glass`) | Used only when Authentik is down |
| Workload SA | Helm-created SA → ClusterRoleBinding (operator-scoped) | `argocd-application-controller`, `cert-manager` |

Human access never shares identity with workload SAs. OIDC subjects use the `oidc:` prefix (`oidc:kanmegnea`, `oidc:Direction IT`) which is structurally distinct from SA subjects (`system:serviceaccount:namespace:name`).

## Human RBAC (GitOps-managed)

All human RBAC is in `manifests/rbac/00-oidc-clusterrolebindings.yaml`:

| Subject | Type | Role |
|---|---|---|
| `oidc:Direction IT` | OIDC Group | `cluster-admin` |
| `oidc:Cybersécurité` | OIDC Group | `view` |
| `oidc:Audit` | OIDC Group | `view` |
| `oidc:kanmegnea` | OIDC User | `cluster-admin` |

**ArgoCD admin login is disabled** (`admin.enabled: false`). The sole login path is Authentik OIDC. Break-glass access is via static cert kubeconfig (no ArgoCD UI).

## Workload SA RBAC

### Accepted cluster-admin Grants

Two workload SAs hold `cluster-admin`. Both are upstream chart design choices that cannot be scoped without forking the chart. They are formally documented in `manifests/rbac/01-rbac-accepted-risks.yaml` (deployed as a ConfigMap in the cluster for audit trail).

**`longhorn-system/longhorn-support-bundle → cluster-admin`**

| | |
|---|---|
| Chart | `longhorn/longhorn v1.6.0` |
| Why broad | Support bundle collects diagnostics from all namespaces; Longhorn grants `cluster-admin` for completeness |
| Risk | Elevated privilege when a support bundle is actively being generated |
| Compensating controls | Longhorn UI is behind Authentik forward-auth; pods are ephemeral (terminated after collection); cluster is not internet-accessible; no standing pod token exposure |
| Decision | **Accept** — revisit if Longhorn 1.7+ introduces a scoped support bundle role |

**`velero/velero-server → cluster-admin`**

| | |
|---|---|
| Chart | `vmware-tanzu/velero` |
| Why broad | Backup and cross-namespace restore requires read+write on all resource types |
| Risk | Backup controller has full cluster write access |
| Compensating controls | Velero namespace has `default-deny` NetworkPolicy; management is kubectl-only (no Ingress); `BackupStorageLocation` credentials in a dedicated Secret |
| Decision | **Accept** — industry-standard for backup tools |

### Least-privilege Grants (correctly scoped)

| SA | ClusterRole | Why |
|---|---|---|
| `argocd/argocd-application-controller` | Custom (watch all resources) | ArgoCD diff/sync requires watching all resource types |
| `argocd/argocd-server` | Custom (get/list namespaces, etc.) | ArgoCD UI project navigation |
| `vault/vault` | `system:auth-delegator` | Vault Kubernetes auth method token review |
| `backstage/backstage-k8s-viewer` | `view` | Backstage Kubernetes plugin read-only display |
| `cert-manager/cert-manager` | Custom (manage cert CRDs) | cert-manager reconciliation |
| `keda/keda-operator` | Custom (watch ScaledObjects) | KEDA autoscaler |
| `gatekeeper-system/gatekeeper-admin` | Custom (manage constraint CRDs) | OPA Gatekeeper admission |
| `external-secrets/external-secrets` | Custom (manage ExternalSecret CRDs) | ESO reconciliation |

### Namespace-level (RoleBindings)

No broad `admin` or `edit` RoleBindings were found on workload SAs. All namespace-level grants are either chart-generated with appropriate scope, or the SA only needs in-namespace access to its own resources.

## automountServiceAccountToken Audit

### Phase 62 baseline

All `default` service accounts across every platform namespace were patched to `automountServiceAccountToken: false` in Phase 62. This prevents the Kubernetes default of mounting a token into every pod that doesn't explicitly opt out.

### Helm-created SAs

Helm chart SAs inherit the chart's default. Most legitimate operator SAs correctly set `automount: true` because they need cluster API access. The audit confirmed the following gaps and actions:

| SA | Automount | Action |
|---|---|---|
| `ai/ollama`, `ai/ollama-secondary`, `ai/ollama-tertiary` | `true` → **`false`** | **Fixed 2026-07-07** — model serving pods make zero Kubernetes API calls |
| `argocd/*`, `cert-manager/*`, `keda/*` | `true` | Correct — these operators need API access |
| `monitoring/kps-*`, `monitoring/kube-prometheus-stack-*` | `true` | Correct — Prometheus operator and scrape agents need API access |
| `vault/*`, `external-secrets/*` | `true` or `unset` | Correct — Vault + ESO controllers need API access |
| `chaos-mesh/*`, `falco/*`, `gatekeeper-system/*` | `unset` | Chart-default; operators need API access; accepted |

The Ollama fix is implemented via `serviceAccount.automount: false` in the three Helm values files and applied via ArgoCD GitOps.

## Audit Commands

```bash
# List all cluster-admin grants
kubectl get clusterrolebindings -o json | python3 -c '
import json,sys
for crb in json.load(sys.stdin)["items"]:
  if crb["roleRef"]["name"]=="cluster-admin":
    for s in crb.get("subjects",[]):
      print(s["kind"]+":"+s.get("namespace","cluster")+"/"+s["name"])
'

# Check SA automount status across all namespaces
kubectl get serviceaccounts -A -o json | python3 -c '
import json,sys
for sa in json.load(sys.stdin)["items"]:
  am=sa["spec"].get("automountServiceAccountToken")
  if am != False:
    print(sa["metadata"]["namespace"]+"/"+sa["metadata"]["name"]+" automount="+str(am))
'

# View accepted risk register in-cluster
kubectl get configmap rbac-accepted-risks -n default -o yaml
```

## Ongoing Rules

1. All new namespaces must patch `default` SA to `automountServiceAccountToken: false` before first workload deploy
2. Workload SAs that do not call the Kubernetes API must set `automount: false` in Helm values or a post-deploy patch
3. Human access is exclusively via OIDC — no static ServiceAccount tokens for humans
4. Any new `cluster-admin` grant requires an entry in `manifests/rbac/01-rbac-accepted-risks.yaml` with justification and compensating controls
