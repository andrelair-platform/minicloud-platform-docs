---
id: pod-security
title: Phase 67 — Pod Security Hardening
sidebar_position: 13
---

# Phase 67 — Pod Security Hardening

This phase applies defense-in-depth at the pod level across all platform namespaces. It combines Kubernetes Pod Security Admission (PSA) labels for namespace-level enforcement with Gatekeeper policies for per-workload audit coverage, and fixes securityContext on all platform-owned workloads.

---

## Scope

| Criterion | Standard |
|---|---|
| `runAsNonRoot: true` | Must not run as UID 0 |
| `allowPrivilegeEscalation: false` | Prevents setuid/setgid escalation |
| `readOnlyRootFilesystem: true` | Blocks writes to container root |
| `capabilities.drop: [ALL]` | Removes all Linux capabilities |
| No privileged containers | `securityContext.privileged: true` blocked |
| No hostPath without justification | Node-level filesystem exposure |
| No hostNetwork without justification | Bypass pod network isolation |
| Resource limits required | CPU + memory limits on every container |

---

## Tier 1 — Namespace-Level Controls (No Breakage Risk)

### Pod Security Admission Labels

PSA labels are applied directly to namespaces. `warn` mode surfaces violations in `kubectl apply` output without blocking workloads. `enforce` mode blocks non-compliant pods at admission.

**Warn-restricted applied to all 23 platform namespaces:**

```bash
# Example — apply to all namespaces in bulk
for ns in argocd authentik backstage cert-manager chaos-mesh external-secrets \
  falco gitops-demo harbor homer ingress-nginx keda ktayl-web messaging \
  monitoring nextcloud nfs-provisioner observability podinfo vault \
  event-demo ai collab-dev collab-staging collab-prod \
  insurance-dev insurance-staging insurance-prod; do
  kubectl label ns "$ns" \
    pod-security.kubernetes.io/warn=restricted \
    pod-security.kubernetes.io/warn-version=latest \
    --overwrite
done
```

**Enforce-restricted applied to fully-controlled namespaces** (no third-party Helm charts that run as root):

| Namespace | Rationale |
|---|---|
| `homer` | Single container, UID 1000 (lighttpd) |
| `podinfo` | Designed to be PSA-compliant |
| `ktayl-web` | Migrated to nginx:unprivileged (UID 101, port 8080) |
| `collab-dev`, `collab-staging`, `collab-prod` | Placeholder workloads we control |
| `insurance-dev`, `insurance-staging`, `insurance-prod` | Same |

```bash
for ns in homer podinfo collab-dev collab-staging collab-prod \
  insurance-dev insurance-staging insurance-prod; do
  kubectl label ns "$ns" \
    pod-security.kubernetes.io/enforce=restricted \
    pod-security.kubernetes.io/enforce-version=latest \
    --overwrite
done
```

**NOT applied to:**
- `gitops-demo` — vault-agent init containers are injected by the Vault mutating webhook and may not be PSA-restricted-compliant
- `metallb-system` — MetalLB speaker requires `privileged` mode; enforced as `privileged`

### New Gatekeeper Policies

Two new ConstraintTemplates added in `warn` mode (audit only, no admission denial). These produce violation counts in Gatekeeper audit reports, providing platform-wide coverage independent of PSA.

**`K8sRequireNonRoot`** — `manifests/gatekeeper-policies/04-ct-require-non-root.yaml`

Flags containers that don't set `runAsNonRoot: true` or a non-zero `runAsUser`. Covers both Pod-level and pod template paths (Deployment/StatefulSet/DaemonSet).

Key Rego pattern used:
```rego
container_safe(c) {
  pod_nonroot
  not c.securityContext.runAsNonRoot == false
  not c.securityContext.runAsUser == 0
}
```

The `pod_nonroot` helper checks both `spec.securityContext` (Pod) and `spec.template.spec.securityContext` (Deployment). A pod-level `runAsNonRoot: true` satisfies all containers unless they explicitly override it to false.

**`K8sNoPrivilegeEscalation`** — `manifests/gatekeeper-policies/05-ct-no-privilege-escalation.yaml`

Flags containers that don't explicitly set `allowPrivilegeEscalation: false`.

Critical Rego gotcha — must use `not x == false`, NOT `x != false`:

```rego
# WRONG — OPA undefined comparison evaluates to undefined (falsy), not true:
c.securityContext.allowPrivilegeEscalation != false  # misses absent fields

# CORRECT — negation of equality catches absent fields:
not c.securityContext.allowPrivilegeEscalation == false
```

When the field is absent from the manifest, `c.securityContext.allowPrivilegeEscalation != false` produces `undefined`, which OPA treats as falsy — the violation rule body doesn't fire. `not c.securityContext.allowPrivilegeEscalation == false` correctly treats the absent field as not-false, making the rule fire.

**Constraint exemptions** (known non-compliant system components):

| Namespace | `require-non-root` | `no-privilege-escalation` |
|---|---|---|
| chaos-mesh | exempt | exempt |
| falco | exempt | exempt |
| velero | exempt | exempt |
| observability | exempt | — |

**Current audit violation counts** (as of 2026-06-27):

| Constraint | Mode | Violations |
|---|---|---|
| `allowed-registries` | warn | 134 |
| `block-latest-tag` | deny | 0 ✓ |
| `no-privileged-containers` | deny | 0 ✓ |
| `no-privilege-escalation` | warn | 40 |
| `require-non-root` | warn | 40 |
| `require-resource-limits` | deny | 24 |

The 40 `no-privilege-escalation` violations and 43 `require-non-root` violations are concentrated in third-party Helm charts (Harbor, Authentik, ArgoCD, NATS, kube-prometheus-stack). These are tracked but not blocked — see Known Gaps.

### ArgoCD GitOps for Gatekeeper Policies

All 6 ConstraintTemplates + 6 Constraints are now managed via the `gatekeeper-policies` ArgoCD Application:

```yaml
# apps/gatekeeper-policies.yaml
source:
  path: manifests/gatekeeper-policies
syncPolicy:
  automated:
    prune: true
    selfHeal: true
  syncOptions:
    - ServerSideApply=true
```

**Sync-wave ordering is mandatory** — ConstraintTemplates must be applied before their Constraints, because Gatekeeper registers a new CRD per ConstraintTemplate, and the Constraint references that CRD. ArgoCD must wait for wave 0 (CTs) to complete before wave 1 (Constraints):

```yaml
# ConstraintTemplates — wave 0
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "0"

# Constraints — wave 1
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"
```

**Bootstrap gotcha:** when adding a new ConstraintTemplate for the first time, ArgoCD will show `OutOfSync` for the matching Constraint with error `<Kind>.constraints.gatekeeper.sh "" not found`. This is because the CRD doesn't exist until Gatekeeper processes the CT. Fix: manually apply the CT first, wait ~15 seconds for Gatekeeper to register the CRD, then ArgoCD syncs the Constraint cleanly:

```bash
kubectl apply -f manifests/gatekeeper-policies/04-ct-require-non-root.yaml
kubectl apply -f manifests/gatekeeper-policies/05-ct-no-privilege-escalation.yaml
sleep 15
kubectl annotate application gatekeeper-policies -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite
```

---

## Tier 2 — Fix Own Workloads

All platform-owned workloads received explicit `securityContext` hardening. Third-party Helm charts are tracked as known gaps (see below).

### platform-demo (`gitops-demo` namespace)

Full PSA-restricted-compliant configuration:

```yaml
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-run-as-non-root: "true"
        vault.hashicorp.com/agent-run-as-user: "1000"
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532        # numeric UID required for distroless nonroot
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: platform-demo
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
```

**Distroless nonroot UID gotcha:** The distroless image sets `USER nonroot` (a named user). Kubernetes `runAsNonRoot: true` requires a numeric UID to verify — it cannot look up named users. Setting only `runAsNonRoot: true` fails with:

```
container has runAsNonRoot and image has non-numeric user (nonroot), cannot verify user is non-root
```

Fix: add `runAsUser: 65532` (the numeric UID that distroless maps "nonroot" to).

**Vault agent securityContext:** The `vault-agent` init containers are injected by the Vault mutating webhook. They respect the annotations `vault.hashicorp.com/agent-run-as-non-root: "true"` and `vault.hashicorp.com/agent-run-as-user: "1000"` to run non-root.

### homer (`homer` namespace)

Full PSA-restricted-compliant:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000       # lighttpd non-root UID
    runAsGroup: 65533
    seccompProfile:
      type: RuntimeDefault
  containers:
    - securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
```

Homer's lighttpd runs as UID 1000 natively. PSA `enforce: restricted` confirmed working (pod 1/1 Running).

### whoami (`gitops-demo` namespace)

Partial — `allowPrivilegeEscalation: false` + `capabilities.drop: [ALL]` applied. `runAsNonRoot` not applied because the `traefik/whoami:v1.10.4` image is built `FROM scratch` with no USER directive — it runs as root UID 0.

```yaml
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

### echo-worker (`event-demo` namespace)

Partial — same as whoami: `allowPrivilegeEscalation: false` + `capabilities.drop: [ALL]` applied. The nats-box image runs as root.

### ktayl-solution-web (`ktayl-web` namespace)

Full PSA-restricted-compliant after migrating the base image to `nginxinc/nginx-unprivileged:1.27-alpine`:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 101        # nginx UID in unprivileged image
    runAsGroup: 101
    seccompProfile:
      type: RuntimeDefault
  containers:
    - securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
```

**Why capabilities.drop:ALL previously crashed the standard nginx image:** nginx init scripts call `chown()` to set ownership on temp directories. This requires `CAP_CHOWN`. Dropping ALL capabilities removes it even for UID 0, causing `chown(...) failed (1: Operation not permitted)` on startup.

**`nginx:unprivileged` solves this** by pre-creating those temp directories with the correct ownership (`nginx:nginx` = 101:101) at image build time, so no `chown()` is needed at container start. The server also moves to port 8080 (no `CAP_NET_BIND_SERVICE` required for ports > 1024).

**Changes made:**
- Dockerfile: `FROM nginxinc/nginx-unprivileged:1.27-alpine`, `EXPOSE 8080`
- nginx.conf: `listen 8080`
- Deployment: `containerPort: 8080` (port name `http` unchanged — Service `targetPort: http` resolves correctly)
- No Service or Ingress changes needed (Service port 80 → named targetPort `http` → pod 8080)
- PSA `enforce: restricted` label applied to `ktayl-web` namespace

Verified: `uid=101(nginx) gid=101(nginx)`, HTTP 200, both replicas 1/1 Running.
ktayl-solution-web commit: `bab775e` (source), `f61ff3c` (gitops)

### podinfo (`podinfo` namespace)

Updated via Helm upgrade with values:

```yaml
podAnnotations:
  seccomp.security.alpha.kubernetes.io/pod: runtime/default
securityContext:
  enabled: true
  runAsUser: 1000
  fsGroup: 1000
```

PSA `enforce: restricted` confirmed working (both replicas 1/1 Running).

---

## Known Gaps

| Workload | Namespace | Gap | Remediation |
|---|---|---|---|
| whoami | `gitops-demo` | Built `FROM scratch`, no USER → root UID 0 | Replace with a non-root whoami image or add `USER nonroot` to build |
| echo-worker (nats-box) | `event-demo` | nats-box runs as root | Replace with custom non-root image or nats-box with USER directive |
| Harbor, ArgoCD, Authentik, NATS, Grafana, kube-prometheus-stack | various | Third-party Helm charts run containers as root or need elevated caps | Upstream chart changes; track via Gatekeeper warn violations |
| `readOnlyRootFilesystem: true` | all | Not feasible without per-directory `emptyDir` mounts for every writable path used by each third-party chart | Out of scope for this phase; requires per-chart audit and emptyDir mapping |

The 40 `no-privilege-escalation` and 43 `require-non-root` Gatekeeper violations are expected — they reflect the above third-party chart gaps. The violation counts provide audit visibility without blocking workloads.

---

## Verification

```bash
# Check PSA labels on all namespaces
kubectl get ns --show-labels | grep pod-security

# Check all Gatekeeper constraints and violation counts
kubectl get constraint -A

# Check detail on which pods violate require-non-root
kubectl describe k8srequirenonroot require-non-root | grep -A3 "Message:"

# Verify platform-demo runs as non-root
kubectl exec -n gitops-demo deploy/platform-demo -- id

# Confirm homer is PSA enforce:restricted compliant
kubectl get pods -n homer
```

---

## GitOps Structure

```
minicloud-gitops/
├── apps/
│   └── gatekeeper-policies.yaml          # ArgoCD App (new)
└── manifests/
    └── gatekeeper-policies/
        ├── 00-ct-block-latest-tag.yaml
        ├── 01-ct-no-privileged-containers.yaml
        ├── 02-ct-require-resource-limits.yaml
        ├── 03-ct-allowed-registries.yaml
        ├── 04-ct-require-non-root.yaml   # new
        ├── 05-ct-no-privilege-escalation.yaml  # new
        ├── 10-constraint-block-latest-tag.yaml
        ├── 11-constraint-no-privileged-containers.yaml
        ├── 12-constraint-require-resource-limits.yaml
        ├── 13-constraint-allowed-registries.yaml
        ├── 14-constraint-require-non-root.yaml   # new
        └── 15-constraint-no-privilege-escalation.yaml  # new
```

Commits: `d545d46` (Tier 1+2), `2462f92` (sync-wave), `25b8784` (regression fixes), `c2dac6d` (Rego fix).
