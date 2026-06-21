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

## Next Steps

- Enable KV v2 secrets engine and store platform admin credentials
- Enable Kubernetes auth backend for pod-level authentication
- Deploy Vault Agent Injector demo with `platform-demo`
- Enable audit logging to stdout → Loki
