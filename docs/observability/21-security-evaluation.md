---
id: security-evaluation
title: Security Evaluation — Runtime, Admission, Network, Secrets & RBAC
sidebar_position: 21
---

# Security Evaluation — Runtime, Admission, Network, Secrets & RBAC

Evaluated 2026-08-02. Two gaps found and closed in gitops PR #520.

| Criterion | Before | After |
|-----------|--------|-------|
| Runtime detection (Falco) | ✅ 5/5 nodes, routed to Alertmanager | No change needed |
| Admission control (Gatekeeper) | ✅ 11 constraints; 25 violations from stale debug pods | 🔧 Deleted stale pods → 0 violations |
| Network isolation | ⚠️ 8 namespaces with no NetworkPolicy | 🔧 49/49 namespaces now isolated |
| Secrets management | ✅ All ESO-synced from Vault | No change needed |
| RBAC | ✅ OIDC groups, least-privilege | No change needed |

---

## 1 — Runtime detection (Falco)

**Status: ✅ Pass**

Falco DaemonSet runs on all 5 nodes (`falco-*` pods, 5/5 Running).
Falcosidekick forwards events to Alertmanager at `minimumpriority: warning`:

```
Falco (kernel eBPF probe)
    → Falcosidekick (webhook bridge)
    → Alertmanager at kps-alertmanager.monitoring:9093
    → webhook-critical (email + Slack)
```

Events below `warning` (notice, debug, informational) are captured in Falco's
own JSON stdout (scraped by Loki via the node-exporter log path) but do not
page anyone — intentional, to avoid alert noise.

**What Falco detects on this cluster:**

| Rule category | Examples |
|---|---|
| Container escapes | `proc_name` in a privileged container, write to `/proc/sysrq-trigger` |
| Credential access | Read from `/etc/shadow`, access to `/root/.ssh/` |
| Lateral movement | Unexpected outbound connection from a non-network workload |
| Persistence | New binary written to `/usr/bin` inside a running container |
| K8s API abuse | `kubectl exec` into a running pod by a non-admin user |

Default Falco ruleset is active. Custom rules can be added to
`helm-values/minicloud-1/falco-values.yaml` under `customRules:`.

---

## 2 — Admission control (Gatekeeper)

**Status: ✅ Pass** (0 violations on `deny` constraints after cleanup)

OPA Gatekeeper v3 runs in `gatekeeper-system` with 3 replicas (controller,
webhook, audit). 11 constraints are active:

| Constraint | Mode | What it blocks |
|---|---|---|
| `block-latest-tag` | **deny** | `:latest` image tag in Deployments/StatefulSets/DaemonSets/Pods |
| `no-privileged-containers` | **deny** | `securityContext.privileged: true` |
| `require-resource-limits` | **deny** | Containers without CPU+memory limits |
| `allowed-registries` | **deny** | Images not from: harbor.*, docker.io, ghcr.io, quay.io, registry.k8s.io, oci.external-secrets.io, ecr-public.aws.com |
| `require-non-root` | **deny** | Containers without `runAsNonRoot: true` or explicit non-zero UID |
| `no-privilege-escalation` | **deny** | Containers missing `allowPrivilegeEscalation: false` |
| `require-ingress-tls` | **deny** | Ingress without a `tls:` block |
| `no-loadbalancer-in-dev` | **deny** | `type: LoadBalancer` Services in `*-dev` namespaces |
| `no-host-path` | **deny** | `hostPath` volumes (kured and node-problem-detector are excluded) |
| `block-net-raw` | **deny** | `NET_RAW` capability |
| `block-capabilities` | **deny** | Adding any capabilities not in the default set |
| `require-seccomp` | **warn** | Containers without `seccompProfile: RuntimeDefault` |

`require-seccomp` is intentionally in `warn` mode. Switching to `deny` would
block a large number of existing workloads (158 containers currently lack a
seccomp profile, including many upstream Helm charts). The warn mode collects
audit data; enforcement will be graduated namespace by namespace.

### Gap closed — stale debug pods

Gatekeeper's audit controller runs every 1 minute and counts violations on
**existing** resources, not only on admission. Five Completed debug pods in
`default` namespace (`tmp2`, `tmp-ftest`, `tmp-persistent`, `tmp-trace`,
`diag`) were triggering 25 violations across 4 constraints:

```
block-latest-tag       5 violations  (busybox image, no tag)
allowed-registries     5 violations  (busybox without registry prefix)
require-non-root       5 violations  (no runAsNonRoot)
no-privilege-escalation 5 violations (no allowPrivilegeEscalation:false)
```

The pods had been Completed for 3+ days with no purpose. Deleted directly:
```bash
kubectl delete pod tmp2 tmp-ftest tmp-persistent tmp-trace diag -n default
```

**Gatekeeper violations on `deny` constraints after cleanup: 0.**

---

## 3 — Network isolation

**Status: ✅ Pass** (49/49 application namespaces isolated as of PR #520)

### Before (gap)

The `apps/platform/network-policies.yaml` ArgoCD Application deployed
NetworkPolicies from `manifests/network-policies/` to 41 namespaces, but
8 application namespaces had **zero isolation**:

| Namespace | Workload |
|---|---|
| `automation` | n8n workflow automation |
| `chat` | Matrix Synapse + Element Web |
| `collab` | Jitsi Meet (JVB uses hostNetwork — exempt from pod NP) |
| `erp` | ERPNext (MariaDB + workers) |
| `mail` | Stalwart mail server (SMTP/IMAP/webmail) |
| `nextcloud` | Nextcloud + OnlyOffice |
| `productivity` | Plane CE (web + api + worker + beat) |
| `sign` | DocuSeal document signing |

Any pod in any namespace could reach these workloads on any port — including
workloads that should be internal-only (ERPNext admin, MariaDB, Plane worker).

### Fix

Added the standard 5-policy set to each namespace:

```yaml
# 1. Drop all inbound traffic by default
default-deny-ingress     (K8s NetworkPolicy, policyTypes: [Ingress])

# 2. Allow pods in the same namespace to communicate
allow-same-namespace     (ingress from podSelector: {})

# 3. Allow ingress-nginx to forward HTTP/HTTPS traffic in
allow-ingress-nginx      (ingress from namespaceSelector: ingress-nginx)

# 4. Allow Prometheus to scrape metrics
allow-monitoring-scrape  (ingress from namespaceSelector: monitoring + observability)

# 5. Allow kubelet health probes (host/node traffic)
allow-node-entities      (CiliumNetworkPolicy, fromEntities: [host, remote-node])
```

The `CiliumNetworkPolicy/allow-node-entities` is required because Cilium
uses endpoint identity rather than IP CIDRs. Kubelet liveness/readiness
probes originate from the `host` entity — an `ipBlock: cidr: 10.0.0.0/8`
NetworkPolicy would silently drop them.

NodePort and LoadBalancer traffic entering via the node's network stack is
matched by the `host` entity and is therefore permitted for all services
that use those exposure types (mail SMTP/IMAP, Jitsi JVB media).

### Verification

```bash
# All 49 namespaces with default-deny
kubectl --context minicloud get networkpolicy -A | grep default-deny | wc -l

# NetworkPolicies live in chat
kubectl --context minicloud get networkpolicy -n chat
kubectl --context minicloud get ciliumnetworkpolicy -n chat

# Matrix still reachable (allow-ingress-nginx works)
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://matrix.10.0.0.200.nip.io | head -2

# Isolation test: pod in monitoring cannot reach chat on arbitrary port
kubectl --context minicloud run test --rm -it --restart=Never \
  -n monitoring --image=busybox:1.36 -- \
  nc -zv matrix-synapse.chat.svc.cluster.local 8448
# Expected: connection refused or timeout (denied by default-deny-ingress)
```

---

## 4 — Secrets management

**Status: ✅ Pass**

All application secrets follow the same pipeline:

```
Vault (secret/platform/<service>)
    → External Secrets Operator ClusterSecretStore (vault-backend)
    → ExternalSecret CR (per namespace, refreshInterval: 1h)
    → k8s Secret (in-namespace, reconciled every hour)
```

20+ ExternalSecrets across all namespaces, all `SecretSynced`.

**No secrets in git.** Confirmed by:
```bash
git -C ~/Developer/cloudplateform/minicloud-gitops log --all -p -- '**/*.yaml' \
  | grep -iE 'password|secret|token|key' | grep -v '#\|metadata\|selector'
# Returns: only field names (secretKeyRef, tokenKey, etc.) — no values
```

**Secrets that are intentionally NOT in ESO** (cluster-internal, chart-generated):
- `argocd-redis` — Redis password generated at install, not user-configurable
- `matrix-synapse-signingkey` — signing key must persist across pod restarts; ESO rotation would break federation
- `gatekeeper-webhook-server-cert` — managed by cert-manager, not ESO

---

## 5 — RBAC

**Status: ✅ Pass**

### ClusterRoleBindings (cluster-wide)

Defined in `manifests/rbac/00-oidc-clusterrolebindings.yaml`:

| Group | ClusterRole | Scope |
|---|---|---|
| `oidc:Platform Admins` | `cluster-admin` | Full cluster (ArgoCD, cert-manager management) |
| `oidc:Viewers` | `view` | Read-only across all namespaces |

### RoleBindings (namespace-scoped)

Defined in `manifests/rbac/02-env-rolebindings.yaml`:

| Group | Role | Namespaces |
|---|---|---|
| `oidc:Développeurs` | `edit` | `platform-demo-dev`, `minicloud-plane-dev` |
| `oidc:QA` | `view` | `platform-demo-staging`, `minicloud-plane-staging` |

**Production namespaces have no human RoleBinding.** Only the ArgoCD
ServiceAccount (`argocd-application-controller`) has write access to
`*-prod` namespaces. Human access to production requires the ArgoCD UI
or `cluster-admin` escalation (Authentik OIDC MFA gate).

### Accepted risks

`manifests/rbac/01-rbac-accepted-risks.yaml` documents workloads that
require elevated cluster-scoped permissions and the justification:
- Falco (`cluster-admin` equivalent for eBPF probe access)
- Velero (needs to read/write all namespaces for backup/restore)
- VPA admission controller (needs to patch Pod specs at admission)
- Chaos Mesh (needs to create/delete pods and network routes)

---

## Security summary

```
Falco              → Alertmanager → Slack + email at warning priority ✅
Gatekeeper         → 10 deny constraints, 0 violations                ✅
                      1 warn constraint (require-seccomp, 158 items)  ⚠️ warn-only
Network isolation  → 49/49 namespaces have default-deny + Cilium NP   ✅
Secrets            → ESO + Vault, all synced, no secrets in git       ✅
RBAC               → OIDC groups, least-privilege, no human prod access ✅
```

The single remaining item (seccomp profiles) is a standard backlog item
for production Kubernetes deployments. The path to closing it:
1. Identify the 158 containers from `kubectl get K8sRequireSeccomp require-seccomp`
2. Add `seccompProfile: RuntimeDefault` to each workload's `securityContext`
3. Once all are compliant, switch the constraint from `warn` to `deny`
