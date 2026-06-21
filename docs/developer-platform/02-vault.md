---
id: vault
title: Phase 26 — Vault (Secrets Management)
sidebar_position: 2
---

# Phase 26 — HashiCorp Vault — Secrets Management

Vault replaces the `~/.xxx-admin` credential-file pattern on the controller with a proper secrets management layer: encrypted at rest, access audited, credentials injectable directly into pods via the Vault Agent Injector.

---

## What Vault Solves

```text
❌ Without Vault:
   ~/.argocd-admin, ~/.grafana-admin, ~/.harbor-admin ...
   (mode 600 files on the controller — secure but unaudited, not rotatable)

   kubectl get secret -o yaml
   → data: base64(plaintext)   ← anyone with cluster access can read

✔ With Vault:
   Secrets encrypted at rest (AES-256-GCM via Raft)
   Every read/write logged with who/when/from where
   Pods receive secrets as injected files — no Kubernetes Secret needed
   Credentials rotatable without redeploying apps
```

---

## Architecture

```text
vault-0 (StatefulSet, 1 replica)
  │  storage: Raft integrated (no external etcd)
  │  PVC: data-vault-0 (5Gi, Longhorn)
  │  TLS: disabled internally (handled by NGINX Ingress + minicloud CA)
  │
  ├── vault-agent-injector (Deployment)
  │     Mutating webhook — patches pods with Vault Agent sidecar when
  │     vault.hashicorp.com/agent-inject: "true" annotation present
  │
  └── NGINX Ingress
        vault.10.0.0.200.nip.io  → port 8200
        vault.devandre.sbs        → port 8200 (via Cloudflare Tunnel)
```

---

## Install

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update hashicorp

helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/vault-values.yaml \
  --wait --timeout 5m
```

`vault-values.yaml`:

```yaml
server:
  ha:
    enabled: false

  standalone:
    enabled: true
    config: |
      ui = true

      listener "tcp" {
        tls_disable = 1
        address = "[::]:8200"
        cluster_address = "[::]:8201"
      }

      storage "raft" {
        path    = "/vault/data"
        node_id = "vault-0"
      }

      service_registration "kubernetes" {}

  dataStorage:
    enabled: true
    size: 5Gi
    storageClass: longhorn
    accessMode: ReadWriteOnce

  resources:
    requests:
      memory: 256Mi
      cpu: 250m
    limits:
      memory: 512Mi
      cpu: 500m

injector:
  enabled: true
  resources:
    requests:
      memory: 64Mi
      cpu: 50m
    limits:
      memory: 128Mi
      cpu: 250m

ui:
  enabled: true
  serviceType: ClusterIP
```

---

## Initialize and Unseal

Run once after first install. The pod will show `0/1` until initialized and unsealed — the readiness probe queries `/v1/sys/health`.

```bash
kubectl exec -n vault vault-0 -- vault operator init \
  -key-shares=3 \
  -key-threshold=2 \
  -format=json
```

Save all output immediately:

```bash
# On controller — mode 600, never committed
cat > ~/.vault-unseal-key-1 << 'EOF'
<unseal_keys_hex[0]>
EOF
cat > ~/.vault-unseal-key-2 << 'EOF'
<unseal_keys_hex[1]>
EOF
cat > ~/.vault-unseal-key-3 << 'EOF'
<unseal_keys_hex[2]>
EOF
cat > ~/.vault-root-token << 'EOF'
<root_token>
EOF
chmod 600 ~/.vault-unseal-key-* ~/.vault-root-token
```

Unseal (needs 2 of 3 keys):

```bash
KEY1=$(cat ~/.vault-unseal-key-1 | tr -d '\n')
KEY2=$(cat ~/.vault-unseal-key-2 | tr -d '\n')
kubectl exec -n vault vault-0 -- vault operator unseal "$KEY1"
kubectl exec -n vault vault-0 -- vault operator unseal "$KEY2"

# Verify: Sealed = false, HA Mode = active
kubectl exec -n vault vault-0 -- vault status
```

**Unseal is required after every pod restart.** Vault starts sealed — it cannot serve requests until unsealed with the threshold number of keys. This is by design: an attacker with access to the pod cannot read encrypted data without the keys.

---

## Ingress + TLS

```bash
# TLS cert from minicloud-ca
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: vault-tls
  namespace: vault
spec:
  secretName: vault-tls
  dnsNames:
    - vault.10.0.0.200.nip.io
  duration: 2160h
  renewBefore: 720h
  privateKey:
    algorithm: ECDSA
    size: 256
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
    group: cert-manager.io
EOF

# NGINX Ingress
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: vault
  namespace: vault
spec:
  ingressClassName: nginx
  rules:
    - host: vault.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: vault
                port:
                  number: 8200
    - host: vault.devandre.sbs
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: vault
                port:
                  number: 8200
  tls:
    - hosts:
        - vault.10.0.0.200.nip.io
      secretName: vault-tls
    - hosts:
        - vault.devandre.sbs
      secretName: vault-tls
EOF
```

Cloudflare Tunnel (`~/.cloudflared/config.yml`) — add before the catch-all rule:

```yaml
- hostname: vault.devandre.sbs
  service: https://10.0.0.200
  originRequest:
    noTLSVerify: true
    originServerName: vault.10.0.0.200.nip.io
```

```bash
~/.local/bin/cloudflared tunnel route dns minicloud vault.devandre.sbs
```

---

## Verification (regression)

```bash
# Both pods Running
kubectl get pods -n vault
# vault-0                       1/1 Running
# vault-agent-injector-...      1/1 Running

# PVC bound on Longhorn
kubectl get pvc -n vault

# Vault health
kubectl exec -n vault vault-0 -- vault status
# Initialized: true  Sealed: false  HA Mode: active

# Public endpoint
curl -s https://vault.devandre.sbs/v1/sys/health | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print("initialized:", d["initialized"], "sealed:", d["sealed"])'
```

---

## Unseal After Restart

Every time `vault-0` pod restarts (node reboot, OOM kill, rolling update), Vault starts sealed. Unseal manually:

```bash
KEY1=$(ssh controller "cat ~/.vault-unseal-key-1 | tr -d '\n'")
KEY2=$(ssh controller "cat ~/.vault-unseal-key-2 | tr -d '\n'")
ssh controller "kubectl exec -n vault vault-0 -- vault operator unseal '$KEY1'"
ssh controller "kubectl exec -n vault vault-0 -- vault operator unseal '$KEY2'"
```

Or run entirely on the controller:

```bash
KEY1=$(cat ~/.vault-unseal-key-1 | tr -d '\n')
KEY2=$(cat ~/.vault-unseal-key-2 | tr -d '\n')
kubectl exec -n vault vault-0 -- vault operator unseal "$KEY1"
kubectl exec -n vault vault-0 -- vault operator unseal "$KEY2"
```

---

## Done When

```text
✔ vault-0 and vault-agent-injector both 1/1 Running
✔ PVC data-vault-0 Bound on Longhorn (5Gi)
✔ vault status: Initialized=true, Sealed=false, HA Mode=active
✔ https://vault.10.0.0.200.nip.io/ui reachable (Tailscale)
✔ https://vault.devandre.sbs/v1/sys/health returns initialized=true
✔ Unseal keys saved at ~/.vault-unseal-key-{1,2,3} mode 600 on controller
✔ Root token saved at ~/.vault-root-token mode 600 on controller
```

---

## KV v2 Secrets Engine

```bash
TOKEN=$(cat ~/.vault-root-token | tr -d '\n')
kubectl exec -n vault vault-0 -- sh -c "
  export VAULT_TOKEN=$TOKEN
  export VAULT_ADDR=http://127.0.0.1:8200
  vault secrets enable -path=secret kv-v2
"
```

Platform admin credentials stored under `secret/platform/`:

```bash
vault kv put secret/platform/argocd        password='...'
vault kv put secret/platform/grafana        password='...'
vault kv put secret/platform/harbor         password='...'
vault kv put secret/platform/minio          password='...'
vault kv put secret/platform/authentik      api_token='...' bootstrap_password='...'
```

Demo workload secret under `secret/platform-demo/`:

```bash
vault kv put secret/platform-demo/config \
  api_key=demo-api-key-a3f8b2c1 \
  environment=production \
  log_level=info
```

---

## Kubernetes Auth Backend

```bash
TOKEN=$(cat ~/.vault-root-token | tr -d '\n')
kubectl exec -n vault vault-0 -- sh -c "
  export VAULT_TOKEN=$TOKEN
  export VAULT_ADDR=http://127.0.0.1:8200
  vault auth enable kubernetes
  vault write auth/kubernetes/config kubernetes_host=https://10.0.0.2:6443
"
```

**Policy** (`/tmp/platform-demo-policy.hcl`):

```hcl
path "secret/data/platform-demo/*" {
  capabilities = ["read"]
}
```

```bash
kubectl cp /tmp/platform-demo-policy.hcl vault/vault-0:/tmp/platform-demo-policy.hcl
kubectl exec -n vault vault-0 -- sh -c "
  export VAULT_TOKEN=$TOKEN
  export VAULT_ADDR=http://127.0.0.1:8200
  vault policy write platform-demo /tmp/platform-demo-policy.hcl
  vault write auth/kubernetes/role/platform-demo \
    bound_service_account_names=platform-demo \
    bound_service_account_namespaces=gitops-demo \
    policies=platform-demo \
    ttl=1h
"
```

---

## Vault Agent Injector — platform-demo Demo

The Vault Agent Injector runs as a mutating webhook. When a pod has `vault.hashicorp.com/agent-inject: "true"`, a `vault-agent` sidecar is automatically injected at admission time. The sidecar authenticates using the pod's ServiceAccount token, fetches the secret, and writes it to `/vault/secrets/`.

`manifests/platform-demo/00-deployment.yaml` (in `minicloud-gitops`):

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: platform-demo
  namespace: gitops-demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: platform-demo
  namespace: gitops-demo
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "platform-demo"
        vault.hashicorp.com/agent-inject-secret-config: "secret/data/platform-demo/config"
        vault.hashicorp.com/agent-inject-template-config: |
          {{- with secret "secret/data/platform-demo/config" -}}
          API_KEY={{ .Data.data.api_key }}
          ENVIRONMENT={{ .Data.data.environment }}
          LOG_LEVEL={{ .Data.data.log_level }}
          {{- end }}
    spec:
      serviceAccountName: platform-demo
      # ... rest of spec
```

Verify injection:

```bash
# Pods show 2/2 (app container + vault-agent sidecar)
kubectl get pods -n gitops-demo -l app=platform-demo

# Read the injected secret from the sidecar container
# (platform-demo is a scratch image — no shell in the app container)
kubectl exec -n gitops-demo <pod> -c vault-agent -- cat /vault/secrets/config
# API_KEY=demo-api-key-a3f8b2c1
# ENVIRONMENT=production
# LOG_LEVEL=info
```

---

## ArgoCD Proxy Fix

Cluster nodes route outbound HTTPS through the MAAS Squid proxy at `10.0.0.1:8000`. ArgoCD's repo-server needs this to reach GitHub:

Add to `argocd-values.yaml`:

```yaml
repoServer:
  env:
    - name: HTTPS_PROXY
      value: http://10.0.0.1:8000
    - name: HTTP_PROXY
      value: http://10.0.0.1:8000
    - name: NO_PROXY
      value: 10.0.0.0/8,127.0.0.1,localhost,.svc,.cluster.local
```

Then upgrade: `helm upgrade argo-cd argo/argo-cd -n argocd --values argocd-values.yaml --wait`

---

## Done When

```text
✔ vault-0 and vault-agent-injector both 1/1 Running
✔ PVC data-vault-0 Bound on Longhorn (5Gi)
✔ vault status: Initialized=true, Sealed=false, HA Mode=active
✔ KV v2 engine at secret/: 5 platform credentials + platform-demo config stored
✔ Kubernetes auth enabled, role platform-demo configured
✔ platform-demo pods show 2/2 (vault-agent sidecar injected)
✔ /vault/secrets/config readable inside platform-demo pods
✔ ArgoCD sync working (Synced Healthy Succeeded) via Squid proxy
✔ https://vault.devandre.sbs/v1/sys/health returns initialized=true
```
