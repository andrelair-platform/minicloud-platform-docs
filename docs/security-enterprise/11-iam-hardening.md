---
id: iam-hardening
title: Phase 62 — IAM Hardening
sidebar_position: 11
---

# Phase 62 — IAM Hardening (OIDC kubectl + RBAC + MFA)

Completed 2026-06-22; OIDC and RBAC model revalidated 2026-10-27. Replaced the shared static kubeconfig with OIDC-based kubectl access via Authentik, enforced MFA for all users, disabled default service account token auto-mounting cluster-wide, and wired human RBAC to dedicated Kubernetes access groups.

---

## What Was Hardened

| Area | Before | After |
|---|---|---|
| kubectl auth | Shared X.509 cert in kubeconfig | OIDC via Authentik (per-user, short-lived) |
| Human RBAC | No RBAC bindings for OIDC | ClusterRoleBindings per Authentik group |
| MFA | Optional | Forced TOTP enrollment on first login |
| Default SA tokens | Auto-mounted in every pod | Disabled cluster-wide (35 namespaces) |

---

## 1. k3s OIDC Flags

Managed in `/etc/rancher/k3s/config.yaml` on set-hog by
`minicloud-ansible/roles/k3s-oidc/` and `playbooks/configure-k3s-oidc.yml`:

```yaml
kube-apiserver-arg:
  - "oidc-issuer-url=https://auth.10.0.0.200.nip.io/application/o/kubernetes/"
  - "oidc-ca-file=/etc/rancher/k3s/minicloud-ca.crt"
  - "oidc-client-id=kubernetes"
  - "oidc-username-claim=preferred_username"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-claim=groups"
  - "oidc-groups-prefix=oidc:"
```

The `oidc:` prefix on username and group claims prevents collisions between OIDC identities and internal Kubernetes service accounts (for example, `oidc:100001` versus an unprefixed local identity).

**Authentik application:** `kubernetes` (OIDC provider, authorization code + device flow).

---

## 2. kubelogin — OIDC Plugin for kubectl

The standard `kubectl` does not support the OIDC Device Authorization Grant flow interactively. `kubectl-oidc_login` (int128/kubelogin) adds this as a credential plugin.

:::warning Wrong package
`brew install kubelogin` installs **Azure's** kubelogin (for AKS) — a completely different tool. Install the int128 version directly:
:::

```bash
# Mac
curl -Lo ~/.local/bin/kubectl-oidc_login \
  https://github.com/int128/kubelogin/releases/latest/download/kubelogin_darwin_arm64.zip
# (unzip first, then move the binary)
chmod +x ~/.local/bin/kubectl-oidc_login

# Controller
curl -Lo ~/.local/bin/kubectl-oidc_login \
  https://github.com/int128/kubelogin/releases/latest/download/kubelogin_linux_amd64.zip
chmod +x ~/.local/bin/kubectl-oidc_login
```

kubectl discovers it automatically when a kubeconfig references `exec: command: kubectl-oidc_login`.

---

## 3. kubeconfig Contexts

Two contexts exist in `~/.kube/config`:

| Context | Auth | When to use |
|---|---|---|
| `minicloud-oidc` | OIDC via Authentik + TOTP | Daily use |
| `minicloud-break-glass` | Static X.509 cert | Authentik is down / emergency only |

### `minicloud-oidc` kubeconfig excerpt

```yaml
users:
  - name: oidc-user
    user:
      exec:
        apiVersion: client.authentication.k8s.io/v1beta1
        command: kubectl
        args:
          - oidc-login
          - get-token
          - --oidc-issuer-url=https://auth.10.0.0.200.nip.io/application/o/kubernetes/
          - --oidc-client-id=kubernetes
          - --oidc-extra-scope=groups
          - --oidc-extra-scope=profile
          - --listen-address=localhost:8000
```

The authorization-code flow opens Authentik in the browser and returns to the localhost callback. This
public client configuration does not place an OIDC client secret in kubeconfig.

### Usage

```bash
kubectl --context minicloud-oidc get nodes
# → Opens browser → Authentik login + TOTP → token cached for 60 min

kubectl --context minicloud-break-glass get nodes
# → Uses static cert — no browser, no MFA
```

---

## 4. ClusterRoleBindings (GitOps-managed)

File: `minicloud-gitops/platform/security/rbac/00-oidc-clusterrolebindings.yaml`

```yaml
---
# Dedicated Kubernetes administrators → cluster-admin
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: oidc-cluster-admin
subjects:
  - kind: Group
    name: "oidc:k8s-cluster-admins"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
---
# Dedicated Kubernetes viewers → read-only
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: oidc-cluster-viewer
subjects:
  - kind: Group
    name: "oidc:k8s-cluster-viewers"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: view
  apiGroup: rbac.authorization.k8s.io
```

Argo CD Application `rbac` syncs this automatically. Authentik group membership and provider mappings
are converged by the plan-first `minicloud-ops/scripts/authentik/kubernetes-rbac.sh`. Direct OIDC user
bindings are prohibited; emergency access uses `minicloud-break-glass`.

---

## 5. RBAC Verification

All personas tested via `kubectl auth can-i --as` impersonation — no interactive Authentik login needed:

```bash
# Kubernetes administrators → cluster-admin
kubectl --context minicloud-oidc auth can-i '*' '*' --all-namespaces \
  --as=oidc:validation --as-group='oidc:k8s-cluster-admins'
# → yes

# Kubernetes viewers → view only
kubectl --context minicloud-oidc auth can-i get pods --all-namespaces \
  --as=oidc:validation --as-group='oidc:k8s-cluster-viewers'
# → yes

kubectl --context minicloud-oidc auth can-i delete pods --all-namespaces \
  --as=oidc:validation --as-group='oidc:k8s-cluster-viewers'
# → no

# Dev editors → edit only in approved dev namespaces
kubectl --context minicloud-oidc auth can-i update deployments -n platform-demo-dev \
  --as=oidc:validation --as-group='oidc:k8s-dev-editors'
# → yes
```

| Access group | Scope | Expected result |
|---|---|---|
| `k8s-cluster-admins` | Cluster-wide | Full administration |
| `k8s-cluster-viewers` | Cluster-wide | Read-only |
| `k8s-dev-editors` | Approved dev namespaces | Edit |

---

## 6. Authentik MFA Enforcement

MFA was optional before Phase 62. All users are now **forced to enroll TOTP on first login**.

In the Authentik admin UI → **Flows → default-authentication-flow** → add a **MFA Validation** stage:

| Field | Value |
|---|---|
| Stage | `default-authentication-mfa-validation` |
| `not_configured_action` | `configure` |
| `configuration_stages` | TOTP setup stage |

`not_configured_action: configure` redirects users who have no MFA device to the TOTP setup flow on their next login. They cannot proceed until they enroll.

---

## 7. Disable Default SA Token Auto-Mount

By default, Kubernetes automatically mounts a service account token into every pod. Most pods don't need it, and mounted tokens have been exploited in container breakout scenarios.

Patched all 35 namespaces:

```bash
for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
  kubectl patch serviceaccount default -n $ns \
    -p '{"automountServiceAccountToken": false}'
done
```

**Rule for future namespaces:** all new namespace manifests must include this patch on the default SA:

```yaml
# In 00-namespace.yaml for any new namespace
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: default
  namespace: <new-namespace>
automountServiceAccountToken: false
```

Pods that genuinely need API server access must create a dedicated ServiceAccount with `automountServiceAccountToken: true` and minimal RBAC — not rely on the default SA.

---

## Operational Notes

```bash
# Test OIDC kubectl (opens browser)
kubectl --context minicloud-oidc get nodes

# Emergency access (no Authentik needed)
kubectl --context minicloud-break-glass get nodes

# Verify RBAC for any user without logging in
kubectl auth can-i <verb> <resource> \
  --as=oidc:<username> --as-group='oidc:<group>'

# Check SA token auto-mount on all namespaces
kubectl get serviceaccount default -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}: {.automountServiceAccountToken}{"\n"}{end}'
# All should show: false

# Verify OIDC flags loaded on apiserver
ssh set-hog "sudo journalctl -u k3s --since '10 minutes ago' --no-pager | grep 'Running kube-apiserver' | grep oidc"
```
