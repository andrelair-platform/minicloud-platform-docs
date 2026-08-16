---
slug: non-human-identity-management-k8s-platform
title: "Every Non-Human Identity on a Self-Hosted k8s Platform: A Complete Taxonomy"
authors: [andrelair]
tags: [security, iam, kubernetes, vault, service-accounts, devops, k3s, self-hosted]
date: 2026-08-16
description: "Service accounts, robot accounts, break-glass tokens, OAuth2 client credentials, API keys — a self-hosted Kubernetes platform uses all of them. Here is how they differ, why each one exists, and what happens when you lose track of one."
---

When you build a production Kubernetes platform from scratch, you accumulate non-human identities faster than you expect. By the time the minicloud platform reached operational maturity — a 5-node bare-metal k3s cluster running 70+ workloads — it had more than 35 distinct non-human identities spanning six different categories. Most of them are invisible during normal operations. You only notice them when one breaks.

This post maps every non-human identity type in use on the platform, explains how they differ, and documents the operational lessons learned from the ones that caused incidents.

{/* truncate */}

## The Six Identity Types

Not all non-human identities are created equal. They differ in who creates them, how they authenticate, how long they live, and what happens when they go wrong.

### 1. Kubernetes Service Accounts

The cleanest identity type in the stack. A `ServiceAccount` object in a namespace gives a pod a JWT token, mounted automatically at `/var/run/secrets/kubernetes.io/serviceaccount/token`. The kubelet rotates this token regularly. When the pod is deleted, the token is gone.

Service accounts are the right choice whenever a workload needs to call the Kubernetes API or any system that supports Kubernetes-native authentication (like Vault with the `kubernetes` auth method).

```yaml
# cert-manager authenticates to Vault PKI using its ServiceAccount JWT
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  vault:
    auth:
      kubernetes:
        role: cert-manager
        serviceAccountRef:
          name: cert-manager
```

The token is short-lived, automatically rotated, and bound to the pod's identity. No credential management required.

**Minicloud service accounts in use:**

| SA | Namespace | Authenticates to |
|---|---|---|
| `cert-manager` | cert-manager | Vault PKI engine |
| `external-secrets` | external-secrets | Vault (reads all `secret/platform/*`) |
| `argocd-application-controller` | argocd | k8s API (cluster-admin) |
| `velero` | velero | k8s API + object storage |
| `backstage` | backstage | k8s API (catalog discovery) |
| `minicloud-agent` | ai | k8s API + LiteLLM |
| `longhorn-pvc-labeler` | longhorn-system | k8s API (patches Longhorn volumes) |
| `node-problem-detector` | node-problem-detector | k8s API (patches node conditions) |

---

### 2. Robot / Technical Accounts

A robot account is a human-shaped identity that belongs to a machine. Harbor's terminology; other systems call it a "service user," "system account," or "bot account." It authenticates exactly like a human user — username and password or API token — but the credential is owned by an automated system.

The defining characteristic: **the credential lives somewhere external to the system that issued it**. After you create a Harbor robot account, you copy the one-time-display token to Vault and to your CI secrets. The token and the account then live independent lives. If the account's database is wiped, the token in Vault is now pointing at nothing.

This is exactly what happened with `robot$ci` in late July 2026. A Longhorn PVC failure forced a Harbor database wipe and rebuild. The old `robot$ci` account was re-created with the same name, but the token was new — and the GitHub org secrets still held the old one. CI image pushes failed silently for weeks before the mismatch was noticed.

**The fix:** store the token in Vault (`secret/platform/harbor` key `robot-ci-secret`) immediately after creation. When rebuilding Harbor, check Vault first, then update GitHub secrets.

**Minicloud robot/technical accounts:**

| Account | System | Token location |
|---|---|---|
| `robot$ci` | Harbor | Vault `secret/platform/harbor` + GitHub org secrets |
| `admin` | MinIO (Docker) | Vault `secret/platform/minio` |
| `ktayl` | MAAS | Controller-local only (low risk — MAAS is controller-only) |

---

### 3. Break-Glass Accounts

A break-glass account is an emergency exit. It should be sealed, documented, and used only when the normal authentication path (OIDC/SSO) is unavailable.

On the minicloud platform, Authentik provides SSO for ArgoCD, Grafana, Harbor, Backstage, Plane, ERPNext, and more. If Authentik goes down — pod crash, database corruption, Longhorn volume fault — every one of those UIs becomes inaccessible to human operators. Break-glass accounts are the offline path.

**Minicloud break-glass accounts:**

| Account | System | Normal login path | Emergency credential |
|---|---|---|---|
| `admin` | ArgoCD | Authentik OIDC → `kanmegnea` | Vault `secret/platform/break-glass` key `argocd` |
| `admin` | Grafana | Authentik OIDC → `kanmegnea` | Vault `secret/platform/break-glass` key `grafana` |
| `admin` | Harbor | Authentik OIDC → `kanmegnea` | Vault `secret/platform/break-glass` key `harbor` |
| `minicloud-break-glass` | k3s API | OIDC kubeconfig `minicloud-oidc` | Static cert kubeconfig context |

The operational discipline for break-glass accounts:
1. **Create them once** and write credentials to Vault immediately
2. **Re-disable after use** (ArgoCD local admin requires `accounts.admin: enabled: false` in `argocd-cm`)
3. **Test them periodically** — a break-glass account that has never been tested may not work when you need it most

Before this session, the break-glass passwords existed only as files on the controller filesystem (`~/.argocd-admin`, `~/.grafana-admin`, `~/.harbor-admin`). If the controller X390 ThinkPad's disk failed, those credentials would be unrecoverable. They now live in Vault at `secret/platform/break-glass`.

---

### 4. OAuth2 Client Credentials (OIDC Providers)

Every application that delegates authentication to Authentik holds an OAuth2 client credential pair: `client_id` + `client_secret`. Authentik issues these when you create an OAuth2/OIDC provider for an application.

These are not "accounts" — they are credentials that identify an application to the identity provider. The application uses them to exchange an authorization code for an access token.

```
Browser → ArgoCD → Authentik (presents client_id, receives code)
                 → exchanges code + client_secret for JWT
                 → user lands on ArgoCD with claims from JWT
```

**Minicloud OIDC providers (one per application):**

| Application | Authentik provider slug | client_secret location |
|---|---|---|
| ArgoCD | `argocd` | k8s secret `argocd-secret` |
| Harbor | `harbor` | k8s secret + Vault `secret/platform/harbor` |
| Grafana | `grafana` | k8s secret `grafana-oidc` |
| Backstage | `backstage` | k8s secret |
| Plane CE | `plane` | k8s secret |
| ERPNext | `frappe` | k8s secret |
| Open WebUI | `open-webui` | k8s secret |
| Vaultwarden | `vaultwarden` | k8s secret (Timshel fork required for SSO) |
| Matrix/Element | `synapse` | Synapse config |

The risk profile of OAuth2 client credentials is lower than robot accounts — they can only initiate authentication flows, not directly access data. If a `client_secret` leaks, an attacker can impersonate the application to Authentik, but still cannot bypass the user's authentication step.

---

### 5. External Service API Keys

Long-lived tokens issued by third-party services that don't support Kubernetes-native auth. These are the credentials for Cloudflare, AWS SES, Tailscale, GitHub, and monitoring services.

All of them live in Vault under `secret/platform/<service>` and are pulled into the cluster via External Secrets Operator at runtime. Pods never see the raw token — they see the k8s Secret that ESO populated.

**Minicloud external API keys:**

| Service | Vault path | Used by |
|---|---|---|
| Cloudflare API (`MINICLOUD` token) | `secret/platform/cloudflare` key `api-token` | cloudflared tunnel + cert-manager DNS01 |
| Cloudflare R2 access key + secret | `secret/platform/cloudflare` keys `r2-*` | Velero off-site backup BSL |
| Tailscale OAuth | GitHub org secrets | CI pipelines (all repos, Tailscale action) |
| GitHub `GITOPS_TOKEN` | GitHub org secrets | CI → kustomize push, Backstage scaffolder |
| AWS SES SMTP | `secret/platform/mail` | Stalwart mail relay |
| Healthchecks.io API key | `secret/platform/healthchecks-io` | minicloud-ops heartbeat + watchdog alerts |

---

### 6. The Vault Root Token

In a different category from everything else. The Vault root token is not an application identity — it is the master key to the secret store itself. Every other credential in the platform is accessible to whoever holds the root token.

On minicloud, the root token lives at `~/.vault-root-token` on the controller filesystem (mode 600). It was generated during `vault operator init` and has never been rotated.

The improvement made in this session: a scoped `platform-ops` token was created with a read-only policy on `secret/platform/*` plus PKI sign permissions. This token lives at `~/.vault-ops-token` and is what automation and day-to-day scripts should use. The root token is reserved for write operations and policy management.

```
platform-ops policy:
  secret/data/platform/*    → read, list
  secret/metadata/platform/* → read, list
  pki/sign/*                → create, update
  pki/issue/*               → create, update
```

The `platform-ops` token is a 10-year periodic token, renewable. The root token rotation procedure (revoke + `vault operator generate-root` with unseal key) is documented but not yet executed — that step requires offline coordination with the unseal key.

---

## The Decision Rule

When you need a new non-human identity on the platform, the choice follows this hierarchy:

| Situation | Identity type |
|---|---|
| Pod needs to call k8s API or Vault | Kubernetes `ServiceAccount` |
| CI pipeline needs to push to a registry | Robot account (stored in Vault immediately) |
| External service with no SA concept | Technical account with credentials in Vault |
| Application delegates login to Authentik | OAuth2 client credential (OIDC provider) |
| Third-party SaaS API (Cloudflare, AWS) | API key in Vault `secret/platform/<service>` |
| Human emergency when SSO is down | Break-glass account, re-disabled after use |

The hierarchy reflects auto-rotation: use the highest-automation option available. Kubernetes SAs rotate automatically. OAuth2 client credentials rotate on Authentik re-issue. API keys and robot accounts are manual — Vault is the mitigation.

---

## What Breaks When You Lose Track

Three incidents from the minicloud operational history that each map to a different identity type:

**Robot account — Harbor `robot$ci` (2026-08-16):**
Harbor database wiped and rebuilt after Longhorn PVC fault. `robot$ci` was re-created with the same name but a new token. GitHub org secrets still held the old token. CI image pushes started failing with 401. Fix: recreate the robot account, update GitHub secrets, store new token in Vault. Time to resolution: found during a routine audit of ArgoCD Degraded apps. **Lesson: always store robot tokens in Vault immediately after creation. Never rely on the CI secret alone.**

**Break-glass account — ArgoCD admin (ongoing until today):**
ArgoCD admin password existed only on the controller filesystem. If the X390's NVMe failed, the only path to ArgoCD during an Authentik outage would be regenerating the bcrypt hash directly in the argocd-cm. That's a 20-minute procedure during what is already an incident. **Lesson: break-glass credentials belong in Vault, not local files.**

**ESO SecretSyncedError — silent for 5 days (2026-08-11 to 2026-08-16):**
`harbor-stable-secrets` ExternalSecret failed after a Vault key was deleted during the Harbor DB wipe. ESO logged `SecretSyncedError` but pods kept running — the k8s Secret already had valid cached data from the last successful sync. The failure was invisible until an audit. **Lesson: ESO health is not visible from pod health. Monitor ExternalSecret `.status.conditions` separately, not just pod status.**

---

## Complete Identity Inventory

For reference, the full minicloud identity count as of 2026-08-16:

| Type | Count | Auto-rotated | All in Vault |
|---|---|---|---|
| Kubernetes Service Accounts | 9 | Yes (kubelet JWT) | N/A |
| Robot / Technical accounts | 3 | No — manual | Yes (as of this session) |
| Break-glass accounts | 4 | No | Yes (as of this session) |
| OAuth2 client credentials | 9 | No | Partially |
| External API keys | 6 | No | Yes |
| Vault root / ops tokens | 2 | No | N/A (root of trust) |
| **Total** | **33** | — | — |

The goal for a platform at this maturity level: every non-human identity that cannot auto-rotate should have its credential in Vault, with ESO pulling it into the cluster at runtime. The only exceptions are the Vault root token itself (it must be stored outside Vault) and the k8s break-glass kubeconfig (it must be stored outside the cluster).
