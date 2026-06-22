---
id: vault-gitops
title: Phase 58 — Vault GitOps Migration
sidebar_position: 5
---

# Phase 58 — Vault GitOps Migration + CoreDNS Completions

Completed 2026-06-22. Migrated Vault from a direct `helm install` on the controller to full ArgoCD GitOps management — zero downtime, existing release adopted in-place. Also completed CoreDNS in-cluster resolution for all public `*.devandre.sbs` hostnames.

---

## Why Migrate Vault to GitOps

Vault was the only platform component still deployed by running `helm install` manually on the controller. This meant:

- The deployed state existed only in the controller's shell history
- No Git history for value changes
- ArgoCD showed it as an unmanaged release

After migration, Vault is managed the same way as every other platform component — values in Git, ArgoCD syncs automatically, rollbacks via `git revert`.

---

## Migration Approach — Adopt Existing Release

The key constraint: **Vault stores secrets data on its PVC**. A fresh install would create a new PVC, losing the existing Raft storage. The solution is to make ArgoCD adopt (not replace) the existing Helm release.

ArgoCD's `--adopt-existing-resources` approach was not needed — ArgoCD's `helm upgrade` path (`syncPolicy.automated`) is equivalent to running `helm upgrade` on an existing release, which preserves the PVC and StatefulSet.

```text
Before: controller $ helm install vault hashicorp/vault ...
After:  ArgoCD ──→ helm upgrade vault hashicorp/vault (same release name + namespace)
                   PVC data-vault-0 (Longhorn) ──→ preserved
                   Vault pod ──→ rolling restart, ~30s downtime
```

---

## GitOps File Structure

```
minicloud-gitops/
  apps/
    vault-base.yaml      # ArgoCD App: namespace + cert-manager Certificate
    vault.yaml           # ArgoCD App: multi-source Helm release

  manifests/
    vault/
      00-namespace.yaml  # vault namespace + default SA token disable
      01-certificate.yaml  # cert-manager Certificate (nip.io + devandre.sbs)

minicloud-ansible/
  helm-values/
    vault-values.yaml    # all Helm values (ingress, storage, TLS, UI)
```

### `apps/vault.yaml` — multi-source Helm app

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: vault
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  sources:
    - repoURL: https://helm.releases.hashicorp.com
      chart: vault
      targetRevision: 0.33.0
      helm:
        valueFiles:
          - $values/helm-values/vault-values.yaml
    - repoURL: https://github.com/andrelair-platform/minicloud-ansible.git
      targetRevision: main
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: vault
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Multi-source lets the Helm chart live in the HashiCorp repo while values live in `minicloud-ansible`. The `ref: values` source is not deployed directly — it's a named reference used in `valueFiles:` via `$values`.

### `manifests/vault/01-certificate.yaml`

cert-manager Certificate covering both ingress hostnames:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: vault-tls
  namespace: vault
spec:
  secretName: vault-tls
  issuerRef:
    name: minicloud-ca-issuer
    kind: ClusterIssuer
  dnsNames:
    - vault.10.0.0.200.nip.io
    - vault.devandre.sbs
```

This certificate is managed by `vault-base` (the base App) separately from the Helm release — so cert rotation is independent of Vault upgrades.

---

## Adoption Procedure

```bash
# 1. Commit the GitOps files to minicloud-gitops + minicloud-ansible

# 2. Apply the base app first (namespace + cert)
kubectl apply -f minicloud-gitops/apps/vault-base.yaml

# 3. Apply the Helm app — ArgoCD runs 'helm upgrade' on the existing release
kubectl apply -f minicloud-gitops/apps/vault.yaml

# 4. Watch ArgoCD sync
argocd app get vault --watch

# 5. Verify Vault is still unsealed and serving
/usr/bin/curl --cacert ~/minicloud-ca.crt -s https://vault.10.0.0.200.nip.io/v1/sys/health | python3 -m json.tool
# → {"initialized":true,"sealed":false,...}
```

No data migration needed. The existing Raft PVC is preserved through the `helm upgrade`.

---

## CoreDNS In-Cluster Resolution

### The problem

Pods inside the cluster that connect to `*.devandre.sbs` hostnames normally resolve via public DNS (Cloudflare → home IP → Cloudflare Tunnel → NGINX). This adds latency and a dependency on the tunnel being up.

k3s ships with a configurable CoreDNS custom ConfigMap (`coredns-custom` in `kube-system`). Adding rewrites here makes cluster-internal traffic to public hostnames go directly to the NGINX ingress IP (`10.0.0.200`) without leaving the cluster.

### ConfigMap

```yaml
# kubectl get cm coredns-custom -n kube-system -o yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns-custom
  namespace: kube-system
data:
  devandre.server: |
    devandre.sbs {
      hosts {
        10.0.0.200 homer.devandre.sbs
        10.0.0.200 demo.devandre.sbs
        10.0.0.200 grafana.devandre.sbs
        10.0.0.200 argocd.devandre.sbs
        10.0.0.200 harbor.devandre.sbs
        10.0.0.200 backstage.devandre.sbs
        10.0.0.200 auth.devandre.sbs
        10.0.0.200 chat.devandre.sbs
        10.0.0.200 nats.devandre.sbs
        10.0.0.200 ktayl.devandre.sbs
        10.0.0.200 vault.devandre.sbs
        10.0.0.200 cloud.devandre.sbs
        fallthrough
      }
    }
```

After editing, CoreDNS picks up the change within ~30s without a restart — it watches the ConfigMap.

### Verify

```bash
kubectl run -it --rm dns-test --image=busybox:1.36 --restart=Never -- \
  nslookup vault.devandre.sbs
# → Server: 10.43.0.10 (CoreDNS)
# → Address: 10.0.0.200
```

All 12 public `*.devandre.sbs` hostnames now resolve to `10.0.0.200` in-cluster without going through Cloudflare.

---

## Why This Matters for Authentik OIDC

Several apps (ArgoCD, Nextcloud, Backstage) use Authentik as their OIDC provider. The Authentik discovery URL must be reachable from inside the cluster. Before CoreDNS rewriting:

- App pod resolves `auth.devandre.sbs` → public DNS → Cloudflare tunnel → NGINX → Authentik ✓ (but slow, external dependency)

After CoreDNS rewriting:
- App pod resolves `auth.devandre.sbs` → CoreDNS → `10.0.0.200` → NGINX → Authentik ✓ (fast, in-cluster)

The Cloudflare Tunnel is still the entry point for **external** traffic (from the internet), but cluster-internal traffic never leaves the home network.

---

## Operational Notes

```bash
# Vault health check (internal)
/usr/bin/curl --cacert ~/minicloud-ca.crt -s https://vault.10.0.0.200.nip.io/v1/sys/health

# Vault health check (public)
curl -s https://vault.devandre.sbs/v1/sys/health

# Unseal status
/usr/bin/curl --cacert ~/minicloud-ca.crt -s https://vault.10.0.0.200.nip.io/v1/sys/seal-status

# ArgoCD sync status
argocd app get vault
argocd app get vault-base

# Verify CoreDNS custom config
kubectl get cm coredns-custom -n kube-system -o yaml

# Test in-cluster DNS resolution
kubectl run -it --rm dns-test --image=busybox:1.36 --restart=Never -- \
  nslookup cloud.devandre.sbs
```

:::caution Vault root token
The Vault root token and unseal keys are stored on the controller at `~/.vault-keys` (mode 600). They are **never committed to Git**. If Vault restarts (e.g. after a node reboot), it must be manually unsealed using these keys.
:::
