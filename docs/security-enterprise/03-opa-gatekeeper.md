---
id: opa-gatekeeper
title: OPA / Gatekeeper (Policy as Code)
sidebar_position: 3
---

:::caution Not deployed on this cluster
OPA / Gatekeeper has **not been deployed**. The Security Layer (OPA, Falco, Cosign) is planned but deferred — no namespace, no pods, no admission policies are active. See [`security-enterprise/security-overview`](./security-overview) for current status.
:::


# OPA / Gatekeeper — Policy as Code (Admission Control)

OPA Gatekeeper is a Kubernetes admission controller that enforces policies before any workload is deployed. It intercepts every `kubectl apply` and rejects manifests that violate platform standards — privileged containers, missing resource limits, non-Harbor images, etc.

---

## How Gatekeeper Works

```text
Developer runs: kubectl apply -f deployment.yaml
                         │
                         ▼
               Kubernetes API Server
                         │
                         ▼ (webhook)
              OPA Gatekeeper Webhook
                         │
                         ▼
            Evaluate all ConstraintTemplates
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          ALLOWED                DENIED
      (deploy proceeds)    (error returned to user)
```

---

## Install Gatekeeper

```bash
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update

helm upgrade --install gatekeeper gatekeeper/gatekeeper \
  --namespace gatekeeper-system \
  --create-namespace \
  --set replicas=2 \
  --set auditInterval=60 \
  --set constraintViolationsLimit=100
```

---

## Policy 1 — Require Resource Limits

Every container must declare CPU and memory limits. Unlimited containers can starve other workloads.

```yaml
# constraint-template-require-limits.yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiresresourcelimits
spec:
  crd:
    spec:
      names:
        kind: K8sRequireResourceLimits
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiresresourcelimits

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.cpu
          msg := sprintf("Container '%v' must set resources.limits.cpu", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
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
    excludedNamespaces:
      - kube-system
      - gatekeeper-system
      - cert-manager
```

---

## Policy 2 — Deny Privileged Containers

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
          msg := sprintf("Privileged containers are not allowed: '%v'", [container.name])
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
    excludedNamespaces:
      - kube-system
```

---

## Policy 3 — Images Must Come from Harbor

Block images from Docker Hub or other unapproved registries:

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sallowedrepos
spec:
  crd:
    spec:
      names:
        kind: K8sAllowedRepos
      validation:
        openAPIV3Schema:
          type: object
          properties:
            repos:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sallowedrepos

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not startswith(container.image, input.parameters.repos[_])
          msg := sprintf("Container '%v' uses image '%v' from an unapproved registry", [container.name, container.image])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sAllowedRepos
metadata:
  name: allowed-repos
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
    excludedNamespaces:
      - kube-system
      - gatekeeper-system
  parameters:
    repos:
      - "harbor.local/"
      - "harbor.yourdomain.com/"
```

---

## Policy 4 — Require Non-Root User

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequirenonrootuser
spec:
  crd:
    spec:
      names:
        kind: K8sRequireNonRootUser
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequirenonrootuser

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          container.securityContext.runAsUser == 0
          msg := sprintf("Container '%v' must not run as root (uid=0)", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.securityContext.runAsNonRoot
          not container.securityContext.runAsUser
          msg := sprintf("Container '%v' must set runAsNonRoot: true", [container.name])
        }
```

---

## Policy 5 — Require Signed Images (Cosign)

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiresignedimages
spec:
  crd:
    spec:
      names:
        kind: K8sRequireSignedImages
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiresignedimages

        # This policy checks the Harbor annotation injected by the Cosign verify sidecar
        # or by using Sigstore Policy Controller
        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not startswith(container.image, "harbor.local/")
          msg := sprintf("Image '%v' is not from the trusted registry", [container.image])
        }
```

For full Cosign enforcement, use **Sigstore Policy Controller** (see Cosign + SBOM page).

---

## Apply All Policies

```bash
kubectl apply -f constraint-template-require-limits.yaml
kubectl apply -f constraint-no-privileged.yaml
kubectl apply -f constraint-allowed-repos.yaml
kubectl apply -f constraint-nonroot.yaml

# Verify constraints are active
kubectl get constraints -A

# View violations (audit mode shows existing non-compliant resources)
kubectl get constraintviolations -A
```

---

## Audit Mode vs Deny Mode

```yaml
spec:
  enforcementAction: dryrun   # log violations but don't block
  # OR
  enforcementAction: warn     # return warning but allow
  # OR
  enforcementAction: deny     # block the request
```

Start with `dryrun` to find existing violations, then switch to `deny` after remediation.

---

## Check What Would Be Blocked

```bash
# Test a privileged pod (should be denied)
kubectl apply -f - << 'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: test-privileged
  namespace: default
spec:
  containers:
    - name: test
      image: harbor.local/myteam/myapp:latest
      securityContext:
        privileged: true
EOF
# Expected: Error from server: admission webhook "validation.gatekeeper.sh" denied the request
```

---

## Policy Library

The OPA Gatekeeper policy library has 50+ pre-built policies:

```bash
# Clone policy library
git clone https://github.com/open-policy-agent/gatekeeper-library.git

# Browse available policies
ls gatekeeper-library/library/general/
# allowedrepos  bannedimagetagssuffix  blockloadbalancer  containerlimits
# containerrequests  disallowanonymous  httpsonly  imagedigests ...
```

---

## Done When

```text
✔ Gatekeeper running with 2 replicas in gatekeeper-system
✔ Policies enforced: resource limits, no-privileged, allowed-repos, non-root
✔ kubectl apply of a privileged pod returns admission error
✔ Existing violations visible via kubectl get constraintviolations
✔ All platform namespaces compliant (0 violations in audit)
```
