---
id: vault-kms-unseal
title: Phase 65 — Vault Auto-Unseal via AWS KMS
sidebar_position: 6
---

# Phase 65 — Vault Auto-Unseal via AWS KMS

Implemented 2026-06-25. Eliminates manual Shamir unseal after every cluster restart by delegating master key decryption to AWS KMS (eu-west-1).

---

## The Problem This Solves

Before this phase, every cluster restart (power outage, maintenance, k3s upgrade) left Vault sealed. The entire secret-dependent stack stayed hard-down until someone manually typed 3 Shamir keys. On a 3-node ThinkPad cluster that might restart at 3 AM, this is the biggest HA gap on the platform.

---

## Architecture

```
vault-0 startup
  └─ reads seal "awskms" from config
  └─ calls AWS KMS kms:Decrypt in eu-west-1
  └─ decrypts master key
  └─ Vault unseals automatically → 1/1 Ready
```

Vault holds 3 **recovery keys** (the former Shamir unseal keys, renamed after migration). These are only needed for:
- Re-initializing Vault from scratch
- Emergency recovery if AWS KMS becomes permanently unavailable

Normal operation requires zero manual steps.

---

## AWS Resources Created

| Resource | Value |
|---|---|
| KMS key | `arn:aws:kms:eu-west-1:625830750465:key/a562e4a3-3708-4656-b2f9-365a073f6457` |
| KMS alias | `alias/vault-auto-unseal` |
| IAM user | `vault-kms-unseal` |
| IAM policy | `VaultKMSUnseal` — scoped to `kms:Encrypt`, `kms:Decrypt`, `kms:DescribeKey` on that key only |

---

## What Changed

### `minicloud-ansible/helm-values/vault-values.yaml`

Added to `server`:

```yaml
extraEnvironmentVars:
  AWS_REGION: eu-west-1

extraSecretEnvironmentVars:
  - envName: AWS_ACCESS_KEY_ID
    secretName: vault-kms-credentials
    secretKey: AWS_ACCESS_KEY_ID
  - envName: AWS_SECRET_ACCESS_KEY
    secretName: vault-kms-credentials
    secretKey: AWS_SECRET_ACCESS_KEY
```

Added to `server.standalone.config`:

```hcl
seal "awskms" {
  region     = "eu-west-1"
  kms_key_id = "arn:aws:kms:eu-west-1:625830750465:key/a562e4a3-3708-4656-b2f9-365a073f6457"
}
```

### Kubernetes Secret (created via kubectl, not committed)

```bash
kubectl create secret generic vault-kms-credentials \
  --namespace vault \
  --from-literal=AWS_ACCESS_KEY_ID=<key> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<secret>
```

---

## Seal Migration Procedure

This is a one-time operation required when migrating an existing Shamir-sealed Vault to KMS. Future Vault instances start with KMS natively.

### 1. Confirm migration mode in startup logs

```bash
kubectl logs vault-0 -n vault | grep migrat
# Expected:
# entering seal migration mode; from_barrier_type=shamir to_barrier_type=awskms
```

### 2. Apply both Shamir keys with the -migrate flag

```bash
kubectl exec -n vault vault-0 -- vault operator unseal -migrate "$(cat ~/.vault-unseal-key-1)"
kubectl exec -n vault vault-0 -- vault operator unseal -migrate "$(cat ~/.vault-unseal-key-2)"
```

After the second key: `Sealed: false`, `Seal Migration in Progress: true`

### 3. Wait for Ready, then verify

```bash
kubectl get pod vault-0 -n vault    # should be 1/1 Running
kubectl exec -n vault vault-0 -- vault status | grep -E 'Seal Type|Sealed'
# Seal Type   awskms
# Sealed      false
```

---

## Verification — Confirm Auto-Unseal Works

```bash
# Delete the pod — StatefulSet recreates it
kubectl delete pod vault-0 -n vault

# Watch it come back (should reach 1/1 without manual input)
kubectl get pod vault-0 -n vault -w

# Verify seal type after restart
kubectl exec -n vault vault-0 -- vault status | grep -E 'Seal Type|Sealed|HA Mode'
# Seal Type   awskms
# Sealed      false
# HA Mode     active
```

---

## Gotchas

### 1. StatefulSet revision must match

When ArgoCD syncs new Helm values, the StatefulSet spec updates but the pod does NOT automatically restart if the revision is already at the correct state. If `vault status` still shows Shamir migration mode not triggered, check:

```bash
kubectl get statefulset vault -n vault -o jsonpath='{.status.updateRevision} {.status.currentRevision}'
# If they differ → delete vault-0 to force recreation on new revision
```

### 2. Migration requires a full restart on the new spec

The `seal "awskms"` block must be in the Vault config before the process starts. Updating a ConfigMap in-place (without pod restart) does NOT trigger migration — Vault reads the seal config once at startup, not dynamically.

### 3. "no migration seal found" error

This means the pod started before the new config was applied (old revision). Delete the pod and retry after confirming the config file contains the awskms stanza:

```bash
kubectl exec -n vault vault-0 -- sh -c 'cat /vault/config/*.hcl' | grep awskms
```

### 4. Cluster internet access required

The Vault pod calls `https://kms.eu-west-1.amazonaws.com` on every startup. If the cluster nodes can't reach AWS (e.g., NAT rule missing after controller network change), Vault will stay sealed with no clear error. Test outbound connectivity:

```bash
ssh set-hog "curl -sI --max-time 5 https://kms.eu-west-1.amazonaws.com | head -2"
```

If unreachable, check the controller's NAT masquerade rule:
```bash
ssh -t controller "sudo iptables -t nat -L POSTROUTING -n -v | grep MASQUERADE"
# Should see a rule for 10.0.0.0/24 → wlp0s20f3 (or whichever interface has internet)
```

### 5. Recovery keys replace Shamir unseal keys

After migration, the old Shamir unseal keys at `~/.vault-unseal-key-{1,2,3}` become **recovery keys**. They are no longer needed for normal operation but must be kept for emergency recovery. Store them securely — losing all recovery keys with an unavailable KMS key means Vault data is permanently inaccessible.

---

## Operational Commands

```bash
# Check seal type
kubectl exec -n vault vault-0 -- vault status | grep 'Seal Type'

# Verify KMS credentials are mounted
kubectl exec -n vault vault-0 -- env | grep AWS

# Rotate IAM access key (if compromised):
# 1. Create new key in AWS IAM → vault-kms-unseal user
# 2. kubectl delete secret vault-kms-credentials -n vault
# 3. kubectl create secret generic vault-kms-credentials --namespace vault \
#      --from-literal=AWS_ACCESS_KEY_ID=<new> --from-literal=AWS_SECRET_ACCESS_KEY=<new>
# 4. kubectl delete pod vault-0 -n vault  (picks up new secret)

# Check KMS key status in AWS
aws kms describe-key --region eu-west-1 \
  --key-id arn:aws:kms:eu-west-1:625830750465:key/a562e4a3-3708-4656-b2f9-365a073f6457 \
  --query 'KeyMetadata.{State:KeyState,Enabled:Enabled}'
```
