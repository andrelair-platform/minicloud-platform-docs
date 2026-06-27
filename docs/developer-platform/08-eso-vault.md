---
id: eso-vault
title: Phase 59 — External Secrets Operator + Vault KV
sidebar_label: External Secrets (ESO)
---

# Phase 59 — External Secrets Operator + Vault KV

Platform secrets migrated from base64 Kubernetes Secrets to **Vault KV v2** via **External Secrets Operator (ESO)**. ESO watches ExternalSecret CRs and syncs values from Vault into native k8s Secrets — apps consume the same secret names with no code changes.

## Architecture

```
Vault KV v2                    ESO                       Apps
secret/platform/               ClusterSecretStore         (unchanged)
  argocd-oidc       ←─────    vault-backend    ─────►   argocd-oidc (Secret)
  grafana-oidc                                            grafana-oidc (Secret)
  openwebui-oidc                                          openwebui-oidc (Secret)
  backstage                                               backstage-phase24-secret (Secret)
  nextcloud-db                                            nextcloud-db (Secret)
  nextcloud-secrets                                       nextcloud-secrets (Secret)
```

ESO authenticates to Vault using the **Kubernetes auth method** — it exchanges its ServiceAccount JWT for a Vault token with the `external-secrets-reader` policy.

## Prerequisites

- Vault unsealed (KMS auto-unseal since Phase 65 — zero manual steps on restart)
- Vault KV v2 already enabled at `secret/` (confirmed during Phase 58 Vault GitOps migration)
- Vault Kubernetes auth already enabled at `kubernetes/` (confirmed — `kubernetes_host: https://10.0.0.2:6443`)

## Vault Setup (one-time)

### 1. Write secrets to Vault KV v2

```bash
# On controller, exec into vault-0
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$(cat ~/.vault-root-token) \
  vault kv put secret/platform/argocd-oidc clientSecret=<value>

kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$(cat ~/.vault-root-token) \
  vault kv put secret/platform/grafana-oidc \
    GF_AUTH_GENERIC_OAUTH_CLIENT_ID=<value> \
    GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET=<value>

# ... repeat for openwebui-oidc, backstage, nextcloud-db, nextcloud-secrets
```

### 2. Write Vault policy

```bash
kubectl cp /tmp/eso-policy.hcl vault/vault-0:/tmp/eso-policy.hcl
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$(cat ~/.vault-root-token) \
  vault policy write external-secrets-reader /tmp/eso-policy.hcl
```

Policy content:
```hcl
path "secret/data/platform/*" {
  capabilities = ["read"]
}
path "secret/metadata/platform/*" {
  capabilities = ["read", "list"]
}
```

### 3. Create Kubernetes auth role

```bash
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$(cat ~/.vault-root-token) \
  vault write auth/kubernetes/role/external-secrets \
    bound_service_account_names=external-secrets \
    bound_service_account_namespaces=external-secrets \
    policies=external-secrets-reader \
    ttl=1h
```

## GitOps Structure

```
minicloud-gitops/
  apps/
    external-secrets.yaml          # ESO Helm install (0.10.x)
    eso-platform-secrets.yaml      # ClusterSecretStore + ExternalSecrets
  manifests/
    eso-platform-secrets/
      00-cluster-secret-store.yaml
      01-argocd-oidc.yaml
      02-grafana-oidc.yaml
      03-openwebui-oidc.yaml
      04-backstage.yaml            # uses dataFrom: extract (all keys)
      05-nextcloud-db.yaml
      06-nextcloud-secrets.yaml
```

## ClusterSecretStore

Points ESO at Vault via HTTP (Vault pod serves plain HTTP on 8200 internally — TLS only at the Ingress):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://vault.vault.svc.cluster.local:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "external-secrets"
          serviceAccountRef:
            name: "external-secrets"
            namespace: "external-secrets"
```

## ExternalSecret Example

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: argocd-oidc
  namespace: argocd
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: argocd-oidc
    creationPolicy: Owner
  data:
    - secretKey: clientSecret
      remoteRef:
        key: platform/argocd-oidc
        property: clientSecret
```

For secrets with many keys, use `dataFrom: extract` to pull all KV fields at once (used for `backstage`, `nextcloud-db`, `nextcloud-secrets`).

## Verification

```bash
# Check ESO pods (3 deployments: controller, webhook, cert-controller)
kubectl get pods -n external-secrets

# Check ClusterSecretStore health
kubectl get clustersecretstore vault-backend

# Check all ExternalSecrets
kubectl get externalsecret -A

# Verify a synced secret value
kubectl get secret argocd-oidc -n argocd -o jsonpath='{.data.clientSecret}' | base64 -d
```

## Gotchas

**NetworkPolicy blocks ESO → Vault:** The vault namespace has `default-deny-ingress`. Added `allow-external-secrets` NetworkPolicy to permit port 8200 from `external-secrets` namespace. Without it, ClusterSecretStore shows `InvalidProviderConfig: connection refused`.

**Vault serves HTTP internally:** `server: http://vault.vault.svc.cluster.local:8200` — NOT https. Vault TLS is terminated at the NGINX Ingress. Using `https://` internally returns "server gave HTTP response to HTTPS client".

**ESO defaults cause ArgoCD drift:** ESO admission webhook adds `conversionStrategy: Default`, `decodingStrategy: None`, `metadataPolicy: None` to all `remoteRef` entries, and `deletionPolicy: Retain` to `spec.target`. ArgoCD detects these as OutOfSync. Fix: add `ignoreDifferences` with `jqPathExpressions` to the ArgoCD app + `RespectIgnoreDifferences=true` sync option.

**creationPolicy: Owner adoption:** If the k8s Secret already exists when ESO first syncs, ESO adopts it by setting ownerReferences. This is non-destructive — the secret content is updated to match Vault, and existing apps see no disruption.

**Force re-sync trigger:** Annotating the ExternalSecret with any change (`kubectl annotate externalsecret <name> -n <ns> force-sync=$(date +%s) --overwrite`) immediately triggers a Vault read + secret sync, useful when the ClusterSecretStore just became ready.

**Gatekeeper resource limits:** ESO pods (controller, webhook, cert-controller) have no resource limits by default → Gatekeeper `require-resource-limits` blocks all 3 Deployments. Must set `resources.limits` in ESO Helm values.

## Updating a Secret

To rotate a secret:
```bash
# 1. Update in Vault
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$(cat ~/.vault-root-token) \
  vault kv patch secret/platform/argocd-oidc clientSecret=<new-value>

# 2. ESO syncs automatically at next refreshInterval (1h), or trigger immediately:
kubectl annotate externalsecret argocd-oidc -n argocd force-sync=$(date +%s) --overwrite

# 3. App picks up the new secret on next pod restart (most apps don't watch secret changes live)
```

## Adding a New Secret

```bash
# 1. Write to Vault
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=$(cat ~/.vault-root-token) \
  vault kv put secret/platform/<new-secret> key=value

# 2. Create ExternalSecret manifest in manifests/eso-platform-secrets/
# 3. Push to git → ArgoCD auto-syncs
```

## Component Versions

| Component | Version |
|---|---|
| external-secrets Helm chart | 0.10.7 |
| ESO CRD API version | v1beta1 |
| Vault KV version | v2 |
| Vault Kubernetes auth role TTL | 1h |

## Secrets in Vault (secret/platform/)

| Vault Path | k8s Secret | Namespace | Keys |
|---|---|---|---|
| `secret/platform/argocd-oidc` | `argocd-oidc` | argocd | clientSecret |
| `secret/platform/grafana-oidc` | `grafana-oidc` | monitoring | GF_AUTH_GENERIC_OAUTH_CLIENT_ID, GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET |
| `secret/platform/openwebui-oidc` | `openwebui-oidc` | ai | OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET |
| `secret/platform/backstage` | `backstage-phase24-secret` | backstage | argocd-password, argocd-username, auth-oidc-client-id, auth-oidc-client-secret, k8s-ca-data, k8s-sa-token |
| `secret/platform/nextcloud-db` | `nextcloud-db` | nextcloud | db-password, db-username |
| `secret/platform/nextcloud-secrets` | `nextcloud-secrets` | nextcloud | nextcloud-admin-password, nextcloud-admin-username, nextcloud-db-password, oidc-client-id, oidc-client-secret, smtp-password |
