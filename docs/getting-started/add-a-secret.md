---
id: add-a-secret
title: Add a secret (Vault → ESO → pod)
sidebar_label: Add a secret (Vault → ESO)
tags: [how-to]
---

# Add a secret — Vault → ESO → your pod

> **How-to.** Secrets **never** live in Git or in a manifest. They live in **Vault**; the **External
> Secrets Operator (ESO)** copies them into a Kubernetes Secret your pod mounts. Here's the whole path,
> end to end.

## The chain

```
Vault (secret/platform/<app>)  →  ESO ExternalSecret  →  k8s Secret  →  your pod (envFrom)
        the source of truth        the bridge (in Git)    ESO creates it   reads it at runtime
```

## 1. Write the value in Vault *(platform owner / break-glass)*

The raw secret is written once to Vault — this is **not** in Git and is done by the owner (the ops token
is read-only; writes use the break-glass root):

```bash
vault kv put secret/platform/myapp \
  DATABASE_URL="postgres://…" \
  API_KEY="…"
```

> Ask the platform owner to seed `secret/platform/myapp` with the keys your app needs, and tell them the
> **namespace** your app runs in.

## 2. Declare the ExternalSecret *(you, in `minicloud-gitops`)*

This **is** committed (it references Vault, it contains no secret material). One per app namespace:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: myapp-secrets
  namespace: myapp
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend        # the cluster-wide ClusterSecretStore
    kind: ClusterSecretStore
  target:
    name: myapp-secrets        # the k8s Secret ESO will create
  data:
    - secretKey: DATABASE_URL  # key in the k8s Secret
      remoteRef:
        key: secret/platform/myapp
        property: DATABASE_URL  # key in Vault
    - secretKey: API_KEY
      remoteRef:
        key: secret/platform/myapp
        property: API_KEY
```

## 3. Consume it in your pod

```yaml
envFrom:
  - secretRef:
      name: myapp-secrets      # all keys become env vars
```

## 4. The mandatory ArgoCD gotcha (or the app stays `OutOfSync` forever)

ESO's webhook injects four default fields that aren't in Git, so under ServerSideApply the app shows
permanent drift. **Every Application that contains an ExternalSecret needs:**

```yaml
ignoreDifferences:
  - group: external-secrets.io
    kind: ExternalSecret
    jqPathExpressions:
      - .spec.data[].remoteRef.conversionStrategy
      - .spec.data[].remoteRef.decodingStrategy
      - .spec.data[].remoteRef.metadataPolicy
      - .spec.target.deletionPolicy
syncOptions:
  - RespectIgnoreDifferences=true    # required, or ESO re-injects in a loop
```

## Verify it worked

```bash
kubectl -n myapp get externalsecret myapp-secrets    # STATUS should be SecretSynced
kubectl -n myapp get secret myapp-secrets            # the k8s Secret exists
```

If `STATUS` is `SecretSyncedError`, the Vault key/path is wrong or the value isn't written yet — re-check
step 1 with the owner.

## Related

- [ESO + Vault](/platform/developer-platform/eso-vault) · [Vault](/platform/developer-platform/vault)
- [Troubleshooting](/platform/getting-started/troubleshooting) — when a pod can't start
- [Getting Started (A→Z)](/platform/getting-started)
