---
id: security-overview
title: Security Layer Overview
sidebar_position: 1
---

# Enterprise Security Layer — Defense in Depth

Security is not a single tool — it is layered. This platform implements defense in depth: each layer assumes the previous one can be bypassed, so multiple independent controls must all fail before an attacker reaches a critical asset.

---

## Defense in Depth Model

```text
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 7 — GOVERNANCE & COMPLIANCE                                  │
│  kube-bench (CIS)  │  API Audit Logs  │  OpenMetadata PII tags      │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 6 — SUPPLY CHAIN                                             │
│  Cosign image signing  │  SBOM generation  │  Trivy CVE scan        │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 5 — RUNTIME SECURITY                                         │
│  Falco (anomaly detection)  │  Seccomp  │  AppArmor profiles        │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 4 — POLICY ENFORCEMENT                                       │
│  OPA / Gatekeeper (admission control)  │  NetworkPolicy (Cilium)    │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 3 — SECRETS MANAGEMENT                                       │
│  Vault (dynamic credentials)  │  External Secrets Operator          │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 2 — AUTHORIZATION                                            │
│  Kubernetes RBAC  │  OPA policies  │  Authentik roles                │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 1 — AUTHENTICATION                                           │
│  Authentik SSO / OIDC  │  Service accounts  │  mTLS (Cilium)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Security Components Map

| Component | Layer | What It Does |
|---|---|---|
| **Authentik** | Identity | Single sign-on for all platform UIs; OIDC/OAuth2 + forward-auth provider (Phase 23 ✅) |
| **OPA / Gatekeeper** | Policy | Admission controller — blocks non-compliant workloads at deploy time |
| **Falco** | Runtime | Detects anomalous container behavior (e.g., shell in container, file read) |
| **Cosign + SBOM** | Supply chain | Signs images; generates bill of materials; blocks unsigned images |
| **kube-bench** | Compliance | Runs CIS Kubernetes benchmark; scores cluster hardening |
| **Vault** | Secrets | Already in Phase 15 — dynamic DB passwords, PKI, secret injection |
| **Cilium** | Network | Already in Phase 22 — eBPF NetworkPolicy + mTLS between pods |

---

## What Each Layer Stops

```text
ATTACK                          STOPPED BY
──────────────────────────────────────────────────────────────
Compromised admin credentials   Authentik MFA + short-lived tokens
Privilege escalation in pod     OPA: no privileged containers
Image with known CVEs           Trivy scan in CI (Phase 13)
Unsigned / tampered image       Cosign policy in Gatekeeper
Shell spawned in running pod    Falco alert + auto-kill
Data exfiltration via DNS       Cilium NetworkPolicy (egress deny)
Lateral movement between pods   Cilium NetworkPolicy (namespace isolation)
Leaked DB password in config    Vault: dynamic credentials, no static secrets
CIS benchmark failures          kube-bench + remediation runbook
PII data accessed by wrong team OPA row-level + OpenMetadata PII tags
```

---

## Platform Security Contacts

Each team owns the security of their namespace. Platform security team owns:

| Area | Contact / Runbook |
|---|---|
| SSO / identity incidents | Platform team → Authentik admin (https://auth.10.0.0.200.nip.io) |
| Active intrusion (Falco alert) | On-call → incident runbook |
| CVE in production image | Dev team → patch + redeploy within SLA |
| Compliance audit | Platform team → kube-bench report |

---

## Security Scanning Pipeline (CI/CD Integration)

```text
git push
  ↓
GitLab CI build stage
  ↓
Trivy scan (CRITICAL exit-code 1)
  ↓
Cosign sign image (if scan passes)
  ↓
Syft SBOM attach to image
  ↓
Harbor stores image + SBOM + signature
  ↓
Gatekeeper admission check (signature required)
  ↓
Deploy to cluster
```

---

## Quick Security Health Check

```bash
# Check Falco alerts in last hour
kubectl logs -n falco daemonset/falco --since=1h | grep -E "WARNING|CRITICAL"

# Check Gatekeeper constraint violations
kubectl get constraintviolations -A

# Check kube-bench score
kubectl logs -n kube-bench job/kube-bench | tail -20

# Check for privileged pods (should be 0)
kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[].securityContext.privileged == true) | .metadata.name'

# Check for pods with no resource limits
kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[].resources.limits == null) | .metadata.name'
```

---

## Done When

```text
✔ Authentik SSO active — 11/13 apps on SSO (Phase 23 ✅); Backstage + MAAS deferred
✔ OPA Gatekeeper blocking privileged / no-resource-limit pods
✔ Falco alerting on shell-in-container and unexpected file access
✔ All production images signed with Cosign + SBOM attached
✔ kube-bench score ≥ 80% on all CIS checks
✔ Zero static DB passwords in Kubernetes secrets (all via Vault)
✔ NetworkPolicy isolating namespaces (Cilium)
```
