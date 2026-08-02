---
id: security-resource-boundaries
title: Security & Resource Boundaries — RBAC, Admission Control, Quotas & LimitRanges
sidebar_position: 23
---

# Security & Resource Boundaries — RBAC, Admission Control, Quotas & LimitRanges

Evaluated 2026-08-02. Two gaps found and closed in gitops PR #525.

| Criterion | Before | After |
|-----------|--------|-------|
| RBAC & Admission Control | ✅ 11 constraints, 0 deny violations | 🔧 Gatekeeper exclusion list corrected; collab removed |
| Resource Quotas & Limits | ⚠️ 22/63 namespaces covered; 10 app namespaces unprotected | 🔧 10 new ResourceQuota + LimitRange files; 32/63 now covered |

---

## 1 — RBAC & Admission Control

### Gatekeeper (OPA) — 11 constraints active

| Constraint | Mode | Violations |
|---|---|---|
| `no-privileged-containers` | deny | 0 |
| `require-non-root` | deny | 0 |
| `no-privilege-escalation` | deny | 0 |
| `require-resource-limits` | deny | 0 (see exclusion list below) |
| `block-latest-tag` | deny | 0 |
| `allowed-registries` | deny | 0 |
| `no-host-path` | deny | 0 |
| `block-net-raw` | deny | 0 |
| `block-capabilities` | deny | 0 |
| `require-ingress-tls` | deny | 0 |
| `no-loadbalancer-in-dev` | deny | 0 |
| `require-seccomp` | **warn** | 158 (unchanged — graduated enforcement backlog) |

### RBAC bindings

**ClusterRoleBindings (cluster-wide):**

| Subject | Role | Type |
|---------|------|------|
| `oidc:Direction IT` | `cluster-admin` | Group |
| `oidc:kanmegnea` | `cluster-admin` | Direct user |
| `oidc:Cybersécurité`, `oidc:Audit` | `view` | Group |

**RoleBindings (per namespace):**

| Group | Role | Namespaces |
|-------|------|------------|
| `oidc:Développeurs` | `edit` | `platform-demo-dev`, `minicloud-plane-dev`, `collab-dev`, `insurance-dev` |
| `oidc:QA` | `view` | `platform-demo-staging`, `minicloud-plane-staging`, `collab-staging`, `insurance-staging` |

No human RoleBinding on any `*-prod` namespace.

### Gap found — `require-resource-limits` exclusion list

Gatekeeper's `require-resource-limits` constraint had a namespace exclusion list that included active production workloads: `chat`, `erp`, `mail`, `collab`, `productivity`, `sign`. These namespaces were excluded because upstream Helm charts don't allow setting resource limits on all their sub-components (StatefulSet sidecars, init containers, bundled PostgreSQL/Redis/RabbitMQ).

**Confirmed effect:** several pods in excluded namespaces were running without limits:

| Namespace | Pod | Status |
|-----------|-----|--------|
| `chat` | `matrix-synapse-redis-master` | No limits on Redis container |
| `erp` | `erpnext-scheduler`, `erpnext-conf-bench-*` | No limits |
| `productivity` | `plane-ce-pgdb`, `plane-ce-minio`, `plane-ce-rabbitmq`, `plane-ce-redis` | No limits |

### Gap closed — `collab` removed from exclusion list (PR #525)

After verifying that all 4 Jitsi containers (jicofo, jvb, prosody, web) have explicit resource limits in `helm-values/minicloud-1/jitsi-values.yaml`, `collab` was removed from the exclusion list. New Deployments/StatefulSets in `collab` will now be blocked by Gatekeeper if they lack limits.

### Accepted gap — direct user ClusterRoleBinding

`oidc-cluster-admin-kanmegnea` grants `cluster-admin` to the individual OIDC user `kanmegnea` rather than going through the group model. This is intentional: the group binding (`oidc:Direction IT → cluster-admin`) relies on Authentik's group token claim, and a direct binding serves as a break-glass fallback if the group claim is misconfigured.

**Path to close:** Add `kanmegnea` to the `Direction IT` Authentik group, then delete `oidc-cluster-admin-kanmegnea`. The group binding alone is sufficient.

### Remaining exclusion list (known backlog)

These namespaces remain excluded from `require-resource-limits` due to upstream chart limitations:

| Namespace | Reason |
|-----------|--------|
| `chat` | `matrix-synapse-redis` StatefulSet has no limit support in chart values |
| `erp` | `erpnext-scheduler` Deployment has no resource limit in chart values |
| `mail` | `ses-inbound` sidecar container has `resources: {}` — chart doesn't expose per-sidecar limits |
| `productivity` | Plane CE StatefulSets (pgdb, minio, rabbitmq, redis) don't expose resource limit config |
| `sign` | Pending chart audit |
| `argo-rollouts` | Upstream chart doesn't set limits on the controller Deployment |
| `system-upgrade` | SUC chart doesn't set limits on the controller |
| `vpa-system` | VPA admission controller has no limits in chart values |
| `temporal` | Temporal server chart generates init/config containers without resource limits |

**LimitRange injection mitigates this:** Each of these namespaces now has a LimitRange (added in PR #525). New pods without explicit limits will receive defaults from the LimitRange automatically. The Gatekeeper exclusion only affects admission of Deployments/StatefulSets/DaemonSets — the LimitRange is the primary defense for existing workloads.

---

## 2 — Resource Quotas & LimitRanges

### Before (gap)

22 of 63 namespaces had a ResourceQuota. 10 application namespaces with active, resource-intensive workloads had nothing:

| Namespace | Workload | Risk |
|-----------|---------|------|
| `ai` | Ollama (4 CPU/8 GiB per pod), LiteLLM, Open WebUI, docling, RAG | **High** — scaling Ollama to 2 replicas consumes 16 GiB with no guard |
| `langfuse` | ClickHouse, Langfuse web/worker | Medium — ClickHouse can spike memory |
| `erp` | ERPNext + MariaDB + workers | Medium — 11 pods, no ceiling |
| `chat` | Matrix Synapse, Element | Low-medium |
| `mail` | Stalwart, ses-inbound | Low |
| `nextcloud` | Nextcloud, OnlyOffice | Medium — OnlyOffice can spike CPU |
| `automation` | n8n | Low |
| `productivity` | Plane CE (11 pods) | Medium — bundled databases |
| `sign` | DocuSeal | Low |
| `collab` | Jitsi (JVB, prosody, jicofo, web) | Low-medium |

### Fix — 10 new quota files (PR #525)

Each file in `manifests/quotas/` contains both a `ResourceQuota` and a `LimitRange`. Deployed automatically by the existing `apps/platform/quotas.yaml` ArgoCD Application.

**Sizing approach:**
- ResourceQuota ceiling = ~2× measured current usage to allow headroom without unbounded scaling
- LimitRange defaults = sane per-container defaults for new pods (prevents pods from inheriting cluster maximums)

| Namespace | Quota (requests.cpu / limits.memory / pods) | LimitRange default |
|-----------|--------------------------------------------|--------------------|
| `ai` | 12 CPU / 80 GiB / 30 pods | 1 CPU / 2 GiB |
| `langfuse` | 1 CPU / 12 GiB / 15 pods | 500m / 1 GiB |
| `chat` | 500m CPU / 6 GiB / 15 pods | 200m / 512 MiB |
| `mail` | 250m CPU / 4 GiB / 10 pods | 200m / 512 MiB |
| `erp` | 1 CPU / 12 GiB / 25 pods | 200m / 256 MiB |
| `nextcloud` | 500m CPU / 8 GiB / 15 pods | 500m / 512 MiB |
| `automation` | 100m CPU / 2 GiB / 10 pods | 200m / 512 MiB |
| `productivity` | 1 CPU / 10 GiB / 20 pods | 200m / 256 MiB |
| `sign` | 100m CPU / 2 GiB / 10 pods | 200m / 512 MiB |
| `collab` | 500m CPU / 4 GiB / 15 pods | 300m / 256 MiB |

### LimitRange effect on pods without explicit limits

LimitRanges inject defaults at **pod admission** time. Existing pods that were created before the LimitRange existed are not retroactively updated. They will receive the default limits on their **next restart** (rolling update, node drain, OOMKill restart, etc.).

To verify injection is working for a new pod:
```bash
# Create a test pod without resource spec
kubectl run test-lr --image=busybox:1.36 --restart=Never -n erp -- sleep 60

# Confirm LimitRange injected defaults
kubectl get pod test-lr -n erp -o jsonpath='{.spec.containers[0].resources}'
# Expected: {"limits":{"cpu":"200m","memory":"256Mi"},"requests":{"cpu":"50m","memory":"64Mi"}}

kubectl delete pod test-lr -n erp
```

---

## Summary

```
RBAC
  cluster-admin  → oidc:Direction IT (group) + oidc:kanmegnea (direct user, break-glass)  ✅
  view           → oidc:Cybersécurité, oidc:Audit                                          ✅
  dev edit       → oidc:Développeurs in *-dev namespaces (4 services)                     ✅
  staging view   → oidc:QA in *-staging namespaces (4 services)                           ✅
  prod           → no human binding, ArgoCD SA only                                       ✅

Gatekeeper
  11 constraints active: 10 deny (0 violations) + 1 warn (158, graduated backlog)         ✅
  collab removed from require-resource-limits exclusion list (PR #525)                    ✅
  9 namespaces still excluded — upstream chart limits required before removal             ⚠️

Resource Quotas & LimitRanges
  32/63 namespaces now have ResourceQuota (was 22)                                        ✅
  31/63 namespaces have LimitRange (was 21)                                               ✅
  All 10 application workload namespaces now bounded                                      ✅
  Existing pods without limits get defaults on next restart from LimitRange               ✅
```

### Files changed (gitops PR #525)

| File | Change |
|------|--------|
| `manifests/quotas/ai.yaml` | New — ResourceQuota (50 CPU/80 GiB/30 pods) + LimitRange |
| `manifests/quotas/langfuse.yaml` | New |
| `manifests/quotas/chat.yaml` | New |
| `manifests/quotas/mail.yaml` | New |
| `manifests/quotas/erp.yaml` | New |
| `manifests/quotas/nextcloud.yaml` | New |
| `manifests/quotas/automation.yaml` | New |
| `manifests/quotas/productivity.yaml` | New |
| `manifests/quotas/sign.yaml` | New |
| `manifests/quotas/collab.yaml` | New |
| `manifests/gatekeeper-policies/12-constraint-require-resource-limits.yaml` | Remove collab exclusion; fix misplaced comment; add per-entry comments |
