---
id: phase-10-security
title: Phase 16 — Security Hardening
sidebar_position: 11
---

# Phase 10 — Security & Hardening

Secure the cluster and its workloads for production use.

---

## TLS — cert-manager

Automated TLS certificate management:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
```

Issue self-signed or Let's Encrypt certificates for all services.

---

## RBAC

Role-Based Access Control — limit what each user/service can do:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: default
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
```

---

## Secrets Management

```text
Option A: Kubernetes Secrets (base64, not encrypted at rest)
Option B: Sealed Secrets (encrypted in Git)
Option C: HashiCorp Vault (enterprise-grade)
```

For this cluster, start with **Sealed Secrets**:

```bash
helm install sealed-secrets \
  --namespace kube-system \
  sealed-secrets/sealed-secrets
```

---

## etcd Backup

Back up the control plane state regularly:

```bash
# On set-hog (control plane)
sudo k3s etcd-snapshot save \
  --name backup-$(date +%Y%m%d)
```

---

## Network Policies

Restrict pod-to-pod communication:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

---

## Checklist

- [ ] TLS on all ingress routes
- [ ] RBAC roles defined
- [ ] Secrets encrypted
- [ ] etcd backups scheduled
- [ ] Network policies applied
- [ ] Node SSH hardened (no password auth)
