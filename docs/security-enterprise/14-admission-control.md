---
id: admission-control
title: Admission Control Hardening — 8/8 Gatekeeper Policies
sidebar_position: 14
---

# Admission Control Hardening — 8/8 Gatekeeper Policies

Built on top of [Phase 27 — OPA/Gatekeeper](./opa-gatekeeper), this phase closes every admission control gap identified in the platform security review. All 9 constraints are GitOps-managed via the `gatekeeper-policies` ArgoCD App (sync-wave: CTs at wave 0, Constraints at wave 1).

---

## Final Policy Matrix

| Policy | Constraint | Action | Violations |
|---|---|---|---|
| No `:latest` image tag | `block-latest-tag` | deny | 0 |
| No privileged containers | `no-privileged-containers` | deny | 0 |
| Resource limits required | `require-resource-limits` | deny | 0 (Harbor ns excluded) |
| No root containers | `require-non-root` | deny | 0 (9 third-party ns excluded) |
| No privilege escalation | `no-privilege-escalation` | warn | 42 (third-party charts) |
| Approved registries only | `allowed-registries` | deny | 0 (11 infra ns excluded) |
| Ingress must use TLS | `require-ingress-tls` | deny | 0 |
| No LoadBalancer in dev | `no-loadbalancer-in-dev` | deny | 0 |
| No hostPath volumes | `no-host-path` | deny | 0 (infra ns excluded) |

`no-privilege-escalation` remains `warn` — third-party Helm charts set `allowPrivilegeEscalation` implicitly and cannot be patched without forking.

---

## Policy 4 — Require Non-Root Containers

Containers running as UID 0 have write access to the full container filesystem and can exploit kernel vulnerabilities more easily.

:::caution Third-party exclusions
Nine namespaces are excluded because their upstream Helm charts run as root and cannot be overridden without forking: `authentik`, `messaging`, `nextcloud`, `ai`, `monitoring`, `nfs-provisioner`, `backstage`, `gitops-demo`, `event-demo`.
:::

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequirenonroot
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  crd:
    spec:
      names:
        kind: K8sRequireNonRoot
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequirenonroot

        containers[c] { c := input.review.object.spec.containers[_] }
        containers[c] { c := input.review.object.spec.initContainers[_] }
        containers[c] { c := input.review.object.spec.template.spec.containers[_] }
        containers[c] { c := input.review.object.spec.template.spec.initContainers[_] }

        violation[{"msg": msg}] {
          c := containers[_]
          not c.securityContext.runAsNonRoot == true
          msg := sprintf("Container '%v' must set securityContext.runAsNonRoot: true", [c.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequireNonRoot
metadata:
  name: require-non-root
  annotations:
    argocd.argoproj.io/sync-wave: "1"
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
            - chaos-mesh
            - falco
            - velero
            - observability
            - authentik
            - messaging
            - nextcloud
            - ai
            - monitoring
            - nfs-provisioner
            - backstage
            - gitops-demo
            - event-demo
```

---

## Policy 5 — Require Ingress TLS

All Ingress objects must configure `spec.tls` — plaintext HTTP is not permitted in the platform.

:::danger Rego gotcha — absent optional fields
`count(ing.spec.tls) == 0` fails silently when `spec.tls` is **absent** from the manifest (not an empty list). OPA treats `count(undefined)` as undefined, so the entire rule body evaluates to undefined — no violation fires.

Always use `object.get` to provide a default:

```rego
tls := object.get(ing.spec, "tls", [])
count(tls) == 0   # now works: object.get returns [] when key is absent
```
:::

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequireingresstls
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  crd:
    spec:
      names:
        kind: K8sRequireIngressTLS
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequireingresstls

        violation[{"msg": msg}] {
          ing := input.review.object
          tls := object.get(ing.spec, "tls", [])
          count(tls) == 0
          msg := sprintf("Ingress '%v/%v' must set spec.tls with at least one entry - plaintext ingress is not allowed", [ing.metadata.namespace, ing.metadata.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequireIngressTLS
metadata:
  name: require-ingress-tls
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["networking.k8s.io"]
        kinds: ["Ingress"]
```

---

## Policy 6 — No LoadBalancer in Dev Namespaces

`LoadBalancer` services in dev namespaces consume MetalLB IPs and are indistinguishable from production traffic. Dev workloads must use `ClusterIP` and be accessed via Ingress.

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8snolbindev
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  crd:
    spec:
      names:
        kind: K8sNoLBInDev
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8snolbindev

        violation[{"msg": msg}] {
          svc := input.review.object
          svc.spec.type == "LoadBalancer"
          msg := sprintf("Service '%v/%v' must not use type LoadBalancer in dev namespaces - use ClusterIP + Ingress instead", [svc.metadata.namespace, svc.metadata.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sNoLBInDev
metadata:
  name: no-loadbalancer-in-dev
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Service"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: In
          values:
            - insurance-dev
            - collab-dev
```

---

## Policy 7 — No hostPath Volumes

`hostPath` mounts expose the node filesystem to the container, bypassing all container isolation. Legitimate infrastructure workloads (Falco, node-exporter, Longhorn) are excluded by namespace.

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8snohostpath
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  crd:
    spec:
      names:
        kind: K8sNoHostPath
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8snohostpath

        volumes[v] { v := input.review.object.spec.volumes[_] }
        volumes[v] { v := input.review.object.spec.template.spec.volumes[_] }

        violation[{"msg": msg}] {
          v := volumes[_]
          v.hostPath
          msg := sprintf("Volume '%v' in '%v/%v' uses hostPath '%v' - use PVC or emptyDir instead", [v.name, input.review.object.metadata.namespace, input.review.object.metadata.name, v.hostPath.path])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sNoHostPath
metadata:
  name: no-host-path
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values:
            - kube-system
            - kube-public
            - kube-node-lease
            - gatekeeper-system
            - chaos-mesh
            - falco
            - longhorn-system
            - metallb-system
            - monitoring
            - observability
            - velero
```

---

## GitOps Layout

All CTs and Constraints live in `minicloud-gitops/manifests/gatekeeper-policies/` and are applied by the `gatekeeper-policies` ArgoCD App:

```
manifests/gatekeeper-policies/
  00-ct-block-latest-tag.yaml          # wave 0
  01-ct-no-privileged.yaml             # wave 0
  02-ct-require-resource-limits.yaml   # wave 0
  03-ct-require-non-root.yaml          # wave 0
  04-ct-no-privilege-escalation.yaml   # wave 0
  05-ct-allowed-registries.yaml        # wave 0
  06-ct-require-ingress-tls.yaml       # wave 0
  07-ct-no-loadbalancer.yaml           # wave 0
  08-ct-no-hostpath.yaml               # wave 0
  10-constraint-block-latest-tag.yaml  # wave 1
  11-constraint-no-privileged.yaml     # wave 1
  12-constraint-require-limits.yaml    # wave 1
  13-constraint-require-non-root.yaml  # wave 1
  ...
```

:::warning ArgoCD selfHeal gotcha
`kubectl patch` or `kubectl apply` on any of these resources is reverted by ArgoCD within minutes (`selfHeal: true`). During debugging — e.g., narrowing a constraint's `match` to isolate a problem — changes must be committed to git. After ArgoCD syncs the correct version from git, `kubectl replace -f` can restore a patched object without fighting selfHeal.
:::

---

## Rego Debugging Checklist

When a constraint appears to admit what it should deny:

1. **Check `kubectl get constraint <name> -o yaml`** — `.status.byPod[].enforced` must be `true` on all pods. If `false`, the CT's CRD isn't registered yet.
2. **Check for silent undefined** — `count(x) == 0` where `x` is absent returns undefined, not true. Use `object.get(obj, "key", [])`.
3. **Check the admission test directly** — create the object with `--dry-run=server` and confirm the webhook fires. If it passes silently, the Rego rule body is undefined.
4. **ArgoCD may have reverted your fix** — verify the CT in-cluster matches git with `kubectl get constrainttemplate <name> -o yaml | grep -A5 rego`.

---

## Verification

```bash
# All constraints enforced, expected violation counts
kubectl get constraints
# NAME                        ENFORCEMENT-ACTION   TOTAL-VIOLATIONS
# allowed-registries          deny                 0
# block-latest-tag            deny                 0
# no-host-path                deny                 0
# no-loadbalancer-in-dev      deny                 0
# no-privileged-containers    deny                 0
# no-privilege-escalation     warn                 42   ← expected
# require-ingress-tls         deny                 0
# require-non-root            deny                 0
# require-resource-limits     deny                 24  ← Harbor charts excluded

# Live admission test — no-TLS Ingress blocked
kubectl apply --dry-run=server -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: test-notls
  namespace: homer
spec:
  rules:
    - host: test.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: homer
                port:
                  number: 8080
EOF
# Error: [require-ingress-tls] Ingress 'homer/test-notls' must set spec.tls...

# Live admission test — LoadBalancer in dev blocked
kubectl apply --dry-run=server -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: test-lb
  namespace: insurance-dev
spec:
  type: LoadBalancer
  selector:
    app: test
  ports:
    - port: 80
EOF
# Error: [no-loadbalancer-in-dev] Service 'insurance-dev/test-lb' must not use type LoadBalancer...
```

---

## Done When

```text
✔ 9 ConstraintTemplates registered in gatekeeper-system
✔ 9 Constraints active — 7 deny, 2 warn
✔ 0 unexpected violations (deny constraints)
✔ Ingress without spec.tls rejected at admission
✔ LoadBalancer Service in insurance-dev/collab-dev rejected
✔ hostPath volume rejected outside infra namespaces
✔ Root container rejected outside excluded namespaces
✔ All gatekeeper-policies ArgoCD App resources Synced/Healthy
```
