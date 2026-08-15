---
slug: vault-pki-ca-migration
title: "Moving Your Kubernetes CA Private Key Into Vault PKI — Without Changing a Single Certificate"
authors: [andrelair]
tags: [kubernetes, security, vault, cert-manager, pki, tls, gitops, k3s, argocd, secrets-management]
date: 2026-08-16
description: "How we migrated the minicloud root CA private key from a plaintext Kubernetes secret into HashiCorp Vault's PKI engine — importing the same CA so no certificate had to be re-issued, no trust store had to be updated, and no service saw any disruption."
---

Every Kubernetes cluster that uses cert-manager for TLS has the same quiet risk buried in it: the CA private key that signs all your internal certificates is sitting in a Kubernetes secret, stored in plaintext in your cluster's datastore.

On managed clusters with etcd encryption at rest, this is adequately mitigated. On k3s with kine and SQLite — which is how many bare-metal clusters run — the secrets table is plaintext. Anyone who can read `state.db` from the control plane node can extract your CA private key and forge certificates your entire cluster trusts.

This post covers how we migrated the minicloud root CA private key into HashiCorp Vault's PKI secrets engine, with the same CA cert so nothing else needed to change — no re-trust, no downtime, no changes to any of our 43 Certificate resources.

{/* truncate */}

## The Problem

When cert-manager bootstraps a CA-based ClusterIssuer, it expects the CA certificate and private key as a Kubernetes secret:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  ca:
    secretName: minicloud-root-ca   # ← CA private key lives here
```

The secret in `cert-manager/minicloud-root-ca` contained three fields: `ca.crt`, `tls.crt` (same as the CA cert), and `tls.key` — the 227-byte EC P-256 private key that signs every TLS certificate on the cluster.

On k3s, that secret lives in a SQLite database on the control plane node:

```
/var/lib/rancher/k3s/server/db/state.db
```

SQLite databases are not encrypted. The kine layer that k3s uses to emulate etcd stores Kubernetes objects as rows in a `kine` table. The secret value is base64-encoded, not encrypted. Anyone with read access to that file — even just a `cat` from a privileged process — can extract the CA key:

```bash
# What an attacker with disk access can do:
sqlite3 state.db "SELECT value FROM kine WHERE name LIKE '%minicloud-root-ca%'"
# → base64-encoded Kubernetes Secret JSON, including tls.key
```

With the CA private key, they can issue a certificate for any hostname that your cluster trusts, sign it with the minicloud root CA, and your browser, curl, and every service-to-service connection will accept it without complaint.

The CA certificate itself is public — it is distributed everywhere, trusted in the macOS Keychain, baked into container images. That is fine. The private key is not.

---

## Why Not Just Enable k3s Encryption At Rest?

k3s supports Kubernetes `EncryptionConfiguration` to encrypt secrets in the SQLite datastore. This is a valid mitigation. But it moves the problem rather than solving it: the encryption key (a KMS key or a local keyfile) is now the sensitive material, and it still has to live somewhere.

Vault PKI solves a different and harder problem. The CA private key **never leaves Vault**. cert-manager does not receive the key. It submits a Certificate Signing Request, Vault signs it and returns only the certificate. The key material is accessed by the signing operation, not transferred.

The exposure surface becomes: anyone who can authenticate to Vault with a valid token and the `cert-manager` policy. That is a much smaller and more auditable set than "anyone who can read the SQLite file."

---

## Architecture After Migration

```
cert-manager controller
        │
        │ 1. creates CSR
        ▼
Vault Kubernetes auth
        │
        │ 2. SA token → 1h Vault token
        ▼
Vault PKI engine (pki/)
        │
        │ 3. signs CSR with CA key (key never leaves Vault)
        │ 4. returns signed certificate
        ▼
cert-manager controller
        │
        │ 5. stores cert in k8s Secret
        ▼
Ingress (Traefik) → TLS terminated with that cert
```

The cert-manager pod authenticates to Vault using its own Kubernetes service account token. Vault's Kubernetes auth backend validates the token against the cluster API server, then issues a short-lived (1h) Vault token scoped to the `cert-manager` policy. That policy allows only `pki/sign/cert-manager` and `pki/issue/cert-manager` — nothing else.

---

## The Migration Strategy: Import, Don't Replace

The critical design choice: **import the existing CA into Vault PKI rather than generating a new one**.

Generating a new CA would mean:
- Distributing the new CA certificate to every device and system that trusts the old one (macOS Keychain, container images, Ansible roles, k3s registry config, dozens of services that embed the CA bundle)
- Re-issuing all 43 existing certificates so they chain to the new CA
- A window where old certs (still trusted by the old CA) and new certs (only trusted by the new CA) coexist

Importing the existing CA means:
- Same CA certificate, same fingerprint
- All existing certs remain valid — they were signed by this CA and continue to be
- No trust store changes anywhere
- The transition is invisible to every TLS client

Vault supports CA import via `POST /v1/pki/config/ca` with a PEM bundle containing both the certificate and the private key. The key is stored internally; the cert becomes the issuing certificate for all subsequent sign operations.

---

## The Migration Steps

### 1. Enable and Configure the PKI Engine

```bash
# Enable PKI at the default path
curl -X POST https://vault.internal/v1/sys/mounts/pki \
  -H "X-Vault-Token: $TOKEN" \
  -d '{"type": "pki"}'

# Tune max lease TTL to match CA validity (10 years)
curl -X POST https://vault.internal/v1/sys/mounts/pki/tune \
  -H "X-Vault-Token: $TOKEN" \
  -d '{"max_lease_ttl": "87600h"}'

# Configure CRL and issuing certificate URLs
curl -X POST https://vault.internal/v1/pki/config/urls \
  -H "X-Vault-Token: $TOKEN" \
  -d '{
    "issuing_certificates": "https://vault.internal/v1/pki/ca",
    "crl_distribution_points": "https://vault.internal/v1/pki/crl"
  }'
```

### 2. Extract the Existing CA and Import It

The CA cert and key live in the `cert-manager/minicloud-root-ca` secret:

```bash
# Extract from k8s secret
CRT=$(kubectl get secret minicloud-root-ca -n cert-manager \
  -o jsonpath='{.data.tls\.crt}' | base64 -d)
KEY=$(kubectl get secret minicloud-root-ca -n cert-manager \
  -o jsonpath='{.data.tls\.key}' | base64 -d)

# Import the bundle — cert first, then key
BUNDLE="${CRT}${KEY}"
curl -X POST https://vault.internal/v1/pki/config/ca \
  -H "X-Vault-Token: $TOKEN" \
  -d "{\"pem_bundle\": \"$BUNDLE\"}"
```

Before proceeding, verify the fingerprint of the imported CA matches what is in the Vault PKI endpoint:

```bash
# Fingerprint of the CA cert in Vault
curl -sk https://vault.internal/v1/pki/ca/pem \
  | openssl x509 -noout -fingerprint -sha256

# Must match the fingerprint of the CA cert trusted everywhere
openssl x509 -in minicloud-ca.crt -noout -fingerprint -sha256
```

If these do not match exactly, stop. Something went wrong with the import.

### 3. Create the PKI Role

The role controls what cert-manager is allowed to request. We restrict it to only the domains we actually use:

```bash
curl -X POST https://vault.internal/v1/pki/roles/cert-manager \
  -H "X-Vault-Token: $TOKEN" \
  -d '{
    "allowed_domains": ["10.0.0.200.nip.io", "devandre.sbs"],
    "allow_subdomains": true,
    "allow_bare_domains": false,
    "allow_wildcard_certificates": false,
    "max_ttl": "8760h",
    "ttl": "2160h",
    "key_type": "ec",
    "key_bits": 256,
    "generate_lease": false
  }'
```

`allow_wildcard_certificates: false` is deliberate. cert-manager always requests specific SANs, not wildcards. Disabling wildcards reduces the blast radius if the Vault token were ever compromised.

### 4. Create the Vault Policy and Kubernetes Auth Role

```bash
# Policy: cert-manager can only sign/issue certs via the cert-manager role
vault policy write cert-manager - <<EOF
path "pki/sign/cert-manager"  { capabilities = ["create", "update"] }
path "pki/issue/cert-manager" { capabilities = ["create", "update"] }
EOF

# Kubernetes auth role: cert-manager SA → cert-manager policy
curl -X POST https://vault.internal/v1/auth/kubernetes/role/cert-manager \
  -H "X-Vault-Token: $TOKEN" \
  -d '{
    "bound_service_account_names": ["cert-manager"],
    "bound_service_account_namespaces": ["cert-manager"],
    "policies": ["cert-manager"],
    "ttl": "1h"
  }'
```

### 5. Update the ClusterIssuer In-Place

This is the key to a zero-disruption migration: we replace the `minicloud-ca` ClusterIssuer spec **in-place**, keeping the same name. All 43 Certificate resources reference `issuerRef.name: minicloud-ca` — none of them need to change.

```yaml
# Before
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  ca:
    secretName: minicloud-root-ca

---
# After
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  vault:
    server: https://vault.10.0.0.200.nip.io   # internal URL — bypasses Cloudflare Access
    path: pki/sign/cert-manager
    caBundle: <base64-encoded minicloud-ca.crt>
    auth:
      kubernetes:
        mountPath: /v1/auth/kubernetes
        role: cert-manager
        serviceAccountRef:
          name: cert-manager
```

The `caBundle` field tells cert-manager how to verify Vault's own TLS certificate. Since Vault's cert was itself issued by `minicloud-ca`, we provide the same CA cert. This avoids a chicken-and-egg situation: cert-manager can verify Vault's cert using the CA bundle embedded in the ClusterIssuer, without needing to call any other issuer first.

### 6. GitOps: A Dedicated ArgoCD App for ClusterIssuers

Before this migration, the ClusterIssuers were applied via `kubectl` and not tracked in GitOps. We moved them into a dedicated ArgoCD application:

```
minicloud-gitops/
  manifests/cert-manager-config/
    00-clusterissuer-selfsigned.yaml   # selfsigned-bootstrap
    01-clusterissuer-vault.yaml        # minicloud-ca (Vault-backed)
  apps/platform/
    cert-manager-config.yaml           # ArgoCD Application, sync wave -1
```

The sync wave `-1` matters. cert-manager itself runs at wave `-2`. The ClusterIssuers at wave `-1` are created after cert-manager is ready but before any other application tries to request a certificate (wave `0` and above). Without this ordering, the first sync of a new cluster would fail because Certificate resources would be submitted before their issuer exists.

One more change required: `ClusterIssuer` is a cluster-scoped resource and must be explicitly listed in the AppProject's `clusterResourceWhitelist`:

```yaml
clusterResourceWhitelist:
  - group: "cert-manager.io"
    kind: ClusterIssuer
```

This is easy to miss. Without it, ArgoCD reports "resource cert-manager.io:ClusterIssuer is not permitted in project" and the sync fails.

---

## Gotchas We Hit

### Cloudflare Blocks API Calls to Vault's Public URL

Our Vault instance is accessible publicly at `vault.devandre.sbs` via Cloudflare Tunnel. Cloudflare Access protects it with browser-based authentication. When our Python setup script tried to call the Vault API at that URL, it received HTTP 403 with `error code: 1010` — Cloudflare blocking a non-browser client.

The fix is to always use the internal URL (`vault.10.0.0.200.nip.io`) for API calls originating from the controller or from within the cluster. cert-manager pods run inside the cluster and reach Vault over the internal network, which is why the ClusterIssuer uses `server: https://vault.10.0.0.200.nip.io`.

**Rule:** If you are scripting Vault API calls from anywhere except a browser, use the internal URL.

### Deleting the Secret Triggers Immediate Regeneration

After the migration was complete, we deleted `cert-manager/minicloud-root-ca` to remove the plaintext key from the cluster. cert-manager immediately regenerated it.

The reason: there was still a `Certificate` object in the `cert-manager` namespace named `minicloud-root-ca`, referencing the `selfsigned-bootstrap` ClusterIssuer. This was the bootstrap certificate that originally created the CA secret. With the Certificate object present, cert-manager treats the secret as managed — when it is deleted, cert-manager re-issues it (with a freshly generated key, not the original one).

The correct sequence is:
1. Delete the `Certificate` object first
2. Then delete the secret

```bash
kubectl delete certificate minicloud-root-ca -n cert-manager
kubectl delete secret minicloud-root-ca -n cert-manager
```

After step 1, cert-manager no longer manages the secret. After step 2, it is gone and nothing recreates it.

### AppProject Whitelist Must Be in Git Before the App Syncs

We patched the AppProject directly with `kubectl patch` to add `ClusterIssuer` to the whitelist, then created the `cert-manager-config` ArgoCD app. The app started syncing — and hit "resource not permitted" errors.

The reason: the `argocd-project` ArgoCD app manages the AppProject from git (`main` branch). On its next reconciliation cycle (every few minutes), it overwrote our `kubectl patch` with the git version, which did not yet include `ClusterIssuer` in the whitelist. Our cert-manager-config app was stuck in a retry loop.

The fix: merge the AppProject change to `main` first, let `argocd-project` sync, then create or re-create the `cert-manager-config` app. In a GitOps system, the git state always wins — direct API changes get reconciled away.

---

## Verification

After the ClusterIssuer switched to Vault, we force-renewed one certificate to confirm the end-to-end flow:

```bash
# Force renewal by deleting the TLS secret
kubectl delete secret homer-tls -n homer

# cert-manager immediately requests a new cert from Vault
kubectl wait --for=condition=Ready certificate/homer-tls -n homer --timeout=30s

# Verify the new cert chains to the same root CA
kubectl get secret homer-tls -n homer \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl verify -CAfile minicloud-ca.crt /dev/stdin
# → /dev/stdin: OK

# Check issuer and expiry
kubectl get secret homer-tls -n homer \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl x509 -noout -issuer -enddate
# issuer=CN=minicloud Internal Root CA
# notAfter=Nov 13 21:54:14 2026 GMT
```

The new certificate was issued in under 2 seconds. The issuer is unchanged. The chain verifies against the same minicloud root CA that was already trusted in the macOS Keychain.

We then ran the same `openssl verify` check across all 43 TLS secrets in the cluster. Every one returned `OK`.

---

## The Security Posture Before and After

| | Before | After |
|---|---|---|
| CA private key location | `cert-manager/minicloud-root-ca` k8s secret | Vault PKI engine internal storage |
| Datastore encryption | None (kine/SQLite plaintext) | Vault's own storage backend |
| Key exposure method | Any process with SQLite read access | Vault audit log only — key never exported |
| cert-manager authentication | None (direct secret read via RBAC) | Kubernetes SA JWT → 1h scoped Vault token |
| Who can forge a cert | Anyone who reads `state.db` | Anyone with a valid `cert-manager` policy token |
| Blast radius of RBAC escalation | Full CA key compromise | Token issue only (no key exposure) |

The difference between "anyone who reads the SQLite file" and "anyone with a Vault token scoped to sign only" is the entire distance between unmanaged secret sprawl and secrets management.

---

## What Stays the Same

The public CA certificate (`minicloud-ca.crt`) is unchanged. It is still trusted in the macOS Keychain. It is still distributed to container images via the Ansible role. It is still embedded in k3s registry configuration. None of that needs to move.

Every existing TLS certificate — the 43 secrets currently in the cluster — remains valid. They were issued by the CA key that Vault now holds. On their next renewal cycle (cert-manager renews at 30 days before expiry by default), they will be re-issued by Vault seamlessly. Services never see a gap in certificate validity.

The only thing that changed is where the private key lives and who can touch it.

---

## One More Thing: Vault Is Also Protected by Its Own Cert

There is a subtle circular dependency here worth naming. Vault's own TLS certificate (`vault/vault-tls`) was issued by cert-manager using the `minicloud-ca` ClusterIssuer. After the migration, cert-manager issues Vault's cert by calling Vault. Vault signs a cert for itself via cert-manager.

This is not a problem in practice. The existing cert is valid for 90 days with a 30-day renew window. Renewal happens long before expiry. cert-manager connects to Vault using the current cert (which is still valid) to request the next cert. The transition is smooth.

But it does mean: if Vault's cert expires before cert-manager can renew it, cert-manager can no longer reach Vault, and the whole issuer is broken. The solution is to keep Vault's cert duration generous (90 days) and monitor cert expiry with alerting — which the existing PrometheusRule for cert-manager already handles.

---

## Summary

Moving a CA private key from a Kubernetes secret into Vault PKI is a non-disruptive operation if you import the existing CA rather than generating a new one. The fingerprint stays the same. The certificates stay valid. The trust stores stay untouched. The only change visible to anything outside Vault is that cert-manager now requests certificates differently — and that the private key is no longer readable by anyone who can access the cluster datastore.

The migration took one session. The cluster ran continuously throughout. Forty-three certificates verified clean after the switch. The CA private key no longer exists anywhere a file read can find it.
