---
id: opa-gatekeeper
title: Phase 27 — OPA / Gatekeeper (Policy as Code)
sidebar_position: 3
---

# Phase 27 — OPA / Gatekeeper — Policy as Code

Gatekeeper is a Kubernetes admission controller powered by OPA (Open Policy Agent). Every `kubectl apply` passes through the Gatekeeper webhook before hitting the API server. If the manifest violates a policy, the webhook denies it with an explicit error — no pod ever starts.

---

## How It Works

```text
kubectl apply -f deployment.yaml
        │
        ▼
  Kubernetes API Server
        │
        ▼ (MutatingAdmissionWebhook / ValidatingAdmissionWebhook)
  OPA Gatekeeper Webhook
        │
        ▼
  Evaluate all active Constraints
        │
     ┌──┴──┐
     ▼     ▼
  ALLOW  DENY → "admission webhook denied the request: [policy-name] ..."
```

**Two-object model:**
- **ConstraintTemplate** — defines the policy in Rego. Creates a new CRD.
- **Constraint** — an instance of that CRD. Declares scope (namespaces, resource kinds) and `enforcementAction`.

**enforcementAction values:**
- `warn` — allow but emit a warning (safe for auditing first)
- `deny` — block the request (enforcement)
- `dryrun` — audit only, no webhook response

**Audit loop** — Gatekeeper periodically re-evaluates all existing resources against all constraints and writes violations to constraint `.status`. Catches resources that were created before a policy was added.

---

## Architecture

```text
gatekeeper-system
  ├── gatekeeper-controller-manager  (webhook, constraint reconcile)
  └── gatekeeper-audit               (audit loop, writes .status violations)
```

---

## Install

```bash
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update gatekeeper

~/.local/bin/helm install gatekeeper gatekeeper/gatekeeper \
  --namespace gatekeeper-system \
  --create-namespace \
  --version 3.22.2 \
  --set replicas=1 \
  --set auditInterval=60 \
  --set constraintViolationsLimit=100 \
  --wait --timeout 5m
```

Verify:

```bash
kubectl get pods -n gatekeeper-system
# gatekeeper-audit-...               1/1 Running
# gatekeeper-controller-manager-...  1/1 Running
```

---

## Policy 1 — Block `:latest` Image Tag

Pinning to explicit tags is required for reproducible deployments. `:latest` is mutable and untraceable.

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sblocklatesttag
spec:
  crd:
    spec:
      names:
        kind: K8sBlockLatestTag
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sblocklatesttag

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          endswith(container.image, ":latest")
          msg := sprintf("Container '%v' uses ':latest' tag — pin to an explicit version (image: %v)", [container.name, container.image])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.initContainers[_]
          endswith(container.image, ":latest")
          msg := sprintf("initContainer '%v' uses ':latest' tag — pin to an explicit version (image: %v)", [container.name, container.image])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not contains(container.image, ":")
          msg := sprintf("Container '%v' has no image tag — pin to an explicit version (image: %v)", [container.name, container.image])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sBlockLatestTag
metadata:
  name: block-latest-tag
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values:
            - kube-system
            - kube-public
            - kube-node-lease
            - gatekeeper-system
            - metallb-system
            - longhorn-system
            - nfs-provisioner
            - cert-manager
            - ingress-nginx
            - chaos-mesh
            - velero
```

---

## Policy 2 — No Privileged Containers

`privileged: true` gives the container nearly full host access. No platform workload should need it.

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8snoprivilegedcontainers
spec:
  crd:
    spec:
      names:
        kind: K8sNoPrivilegedContainers
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8snoprivilegedcontainers

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          container.securityContext.privileged == true
          msg := sprintf("Container '%v' must not run as privileged", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.initContainers[_]
          container.securityContext.privileged == true
          msg := sprintf("initContainer '%v' must not run as privileged", [container.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sNoPrivilegedContainers
metadata:
  name: no-privileged-containers
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values:
            - kube-system
            - kube-public
            - kube-node-lease
            - gatekeeper-system
            - metallb-system
            - longhorn-system
            - nfs-provisioner
            - cert-manager
            - ingress-nginx
            - chaos-mesh
            - velero
```

---

## Policy 3 — Require Resource Limits

Containers without CPU/memory limits can starve other workloads on the same node.

:::caution Rego path gotcha — Deployment vs Pod
For **Pod** objects, containers are at `input.review.object.spec.containers`.
For **Deployment / StatefulSet / DaemonSet**, containers are at `input.review.object.spec.template.spec.containers`.

A Rego rule that only references `spec.containers` will silently pass all Deployments — the iterator never binds and the violation never fires. The helper set below handles both paths.
:::

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequireresourcelimits
spec:
  crd:
    spec:
      names:
        kind: K8sRequireResourceLimits
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequireresourcelimits

        # Pod objects
        containers[c] {
          c := input.review.object.spec.containers[_]
        }

        # Deployment/StatefulSet/DaemonSet — nested under spec.template.spec
        containers[c] {
          c := input.review.object.spec.template.spec.containers[_]
        }

        violation[{"msg": msg}] {
          container := containers[_]
          not container.resources.limits.cpu
          msg := sprintf("Container '%v' must set resources.limits.cpu", [container.name])
        }

        violation[{"msg": msg}] {
          container := containers[_]
          not container.resources.limits.memory
          msg := sprintf("Container '%v' must set resources.limits.memory", [container.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequireResourceLimits
metadata:
  name: require-resource-limits
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: In
          values:
            - gitops-demo
            - podinfo
            - homer
            - monitoring
            - observability
            - argocd
            - harbor
            - backstage
            - vault
            - authentik
            - keda
            - messaging
            - event-demo
            - ai
            - ktayl-web
```

---

## Rollout Procedure

Always start in `warn` mode, audit for one cycle, then flip to `deny`:

```bash
# 1. Apply templates + constraints with enforcementAction: warn
kubectl apply -f ct-block-latest-tag.yaml
kubectl apply -f ct-no-privileged.yaml
kubectl apply -f ct-require-resource-limits.yaml

# 2. Wait for one audit cycle (auditInterval: 60s)
sleep 75
kubectl get constraints
# TOTAL-VIOLATIONS should be 0 before flipping to deny

# 3. Flip to deny
kubectl patch k8sblocklatesttag block-latest-tag \
  -p '{"spec":{"enforcementAction":"deny"}}' --type merge
kubectl patch k8snoprivilegedcontainers no-privileged-containers \
  -p '{"spec":{"enforcementAction":"deny"}}' --type merge
kubectl patch k8srequireresourcelimits require-resource-limits \
  -p '{"spec":{"enforcementAction":"deny"}}' --type merge
```

---

## Rejection Demo — Verified

All three policies reject invalid workloads immediately at admission:

```bash
# Demo 1: :latest tag blocked
kubectl run test-latest --image=nginx:latest -n gitops-demo --restart=Never
# Error from server (Forbidden): admission webhook "validation.gatekeeper.sh" denied the request:
# [block-latest-tag] Container 'test-latest' uses ':latest' tag — pin to an explicit version (image: nginx:latest)

# Demo 2: privileged container blocked
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: test-priv
  namespace: gitops-demo
spec:
  containers:
    - name: test-priv
      image: nginx:1.27
      securityContext:
        privileged: true
EOF
# Error from server (Forbidden): ... [no-privileged-containers] Container 'test-priv' must not run as privileged

# Demo 3: missing resource limits blocked
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-nolimits
  namespace: gitops-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-nolimits
  template:
    metadata:
      labels:
        app: test-nolimits
    spec:
      containers:
        - name: test-nolimits
          image: nginx:1.27
EOF
# Error from server (Forbidden): ... [require-resource-limits] Container 'test-nolimits' must set resources.limits.cpu
# [require-resource-limits] Container 'test-nolimits' must set resources.limits.memory
```

---

## Verification (regression)

```bash
# Both pods Running
kubectl get pods -n gatekeeper-system
# gatekeeper-audit-...               1/1 Running
# gatekeeper-controller-manager-...  1/1 Running

# All 3 constraints enforced, 0 violations
kubectl get constraints
# NAME                                ENFORCEMENT-ACTION   TOTAL-VIOLATIONS
# block-latest-tag                    deny                 0
# no-privileged-containers            deny                 0
# require-resource-limits             deny                 0

# Audit log confirms scans are running
kubectl logs -n gatekeeper-system -l control-plane=audit-controller --tail=5 | grep audit_finished
# {"msg":"auditing is complete","duration":"31s"}
```

---

## Done When

```text
✔ gatekeeper-controller-manager and gatekeeper-audit both 1/1 Running
✔ 3 ConstraintTemplates registered (k8sblocklatesttag, k8snoprivilegedcontainers, k8srequireresourcelimits)
✔ 3 Constraints active with enforcementAction: deny
✔ Audit cycle completed — TOTAL-VIOLATIONS = 0 (platform already compliant)
✔ Demo 1: kubectl run nginx:latest rejected by webhook
✔ Demo 2: privileged Pod rejected by webhook
✔ Demo 3: Deployment without resource limits rejected by webhook
✔ All test artifacts cleaned up
```
