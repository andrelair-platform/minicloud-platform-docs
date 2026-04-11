---
id: vault
title: Phase 16 — Vault
sidebar_position: 2
---

# HashiCorp Vault — Production Secrets Management

Kubernetes Secrets are base64-encoded — not encrypted. Anyone with cluster access can read them. Vault is the industry-standard solution: secrets are encrypted at rest, access is audited, and credentials can be dynamically generated and automatically rotated.

---

## What Vault Solves

```text
❌ Without Vault:
   kubectl get secret my-db-password -o yaml
   → password: base64decoded_plaintext   (anyone can read this)

✔ With Vault:
   Secrets encrypted with AES-256
   Access requires a valid token + policy
   Every access is logged
   Credentials auto-expire and rotate
```

---

## Key Features Used

| Feature | What It Does |
|---|---|
| **KV Secrets Engine** | Store and version arbitrary secrets |
| **Dynamic Secrets** | Generate DB credentials on demand (auto-expire) |
| **Kubernetes Auth** | Pods authenticate using their ServiceAccount token |
| **Vault Agent Injector** | Automatically inject secrets into pods as files |
| **Audit Logging** | Every secret access logged with who/when/from where |

---

## Install Vault via Helm

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com

helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --set "server.ha.enabled=false" \
  --set "server.dataStorage.storageClass=longhorn"
```

---

## Initialize and Unseal

```bash
kubectl exec -n vault vault-0 -- vault operator init \
  -key-shares=3 \
  -key-threshold=2

# Save the 3 unseal keys and root token — store them safely offline
```

Unseal (needed after every restart):

```bash
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_1>
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_2>
```

---

## Configure Kubernetes Auth

```bash
kubectl exec -n vault -it vault-0 -- /bin/sh

vault auth enable kubernetes

vault write auth/kubernetes/config \
  kubernetes_host="https://10.0.0.2:6443"

exit
```

---

## Store a Secret

```bash
kubectl exec -n vault -it vault-0 -- /bin/sh

vault secrets enable -path=secret kv-v2

vault kv put secret/myapp/database \
  username="appuser" \
  password="$(openssl rand -base64 32)"

vault kv get secret/myapp/database
```

---

## Inject Secrets into Pods Automatically

Vault Agent Injector reads annotations on pods and injects secrets as files — no code changes needed:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "my-app"
    vault.hashicorp.com/agent-inject-secret-config: "secret/myapp/database"
    vault.hashicorp.com/agent-inject-template-config: |
      {{- with secret "secret/myapp/database" -}}
      DB_USER={{ .Data.data.username }}
      DB_PASS={{ .Data.data.password }}
      {{- end }}
spec:
  containers:
    - name: my-app
      image: my-app:latest
```

The secret is injected at `/vault/secrets/config` inside the container — readable as environment variables or a config file.

---

## Dynamic Database Credentials

Instead of storing a static DB password, Vault generates a unique credential per request that expires automatically:

```bash
vault secrets enable database

vault write database/config/postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles="my-app" \
  connection_url="postgresql://{{username}}:{{password}}@10.0.0.2:5432/mydb" \
  username="vault" \
  password="vaultpassword"

vault write database/roles/my-app \
  db_name=postgres \
  creation_statements="CREATE ROLE '{{name}}' WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';" \
  default_ttl="1h" \
  max_ttl="24h"
```

Every app gets its own temporary DB credential. When it expires, Vault generates a new one. Compromise of one credential is time-limited.

---

## Access Vault UI

```bash
kubectl port-forward -n vault svc/vault 8200:8200
```

Open: `http://localhost:8200`

---

## Done When

```text
✔ Vault initialized and unsealed
✔ Kubernetes auth configured
✔ Secrets stored and retrievable
✔ Pod receiving injected secret via annotation
✔ Audit log capturing all access
```
