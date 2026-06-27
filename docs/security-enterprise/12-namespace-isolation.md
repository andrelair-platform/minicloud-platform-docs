---
id: namespace-isolation
title: Phase 64 — Namespace Isolation
sidebar_position: 12
---

# Phase 64 — Namespace Isolation (NetworkPolicies + ResourceQuotas)

Implemented 2026-06-22, extended 2026-06-27. Locked down lateral movement between Kubernetes namespaces by applying default-deny ingress NetworkPolicies across **all 23 platform namespaces**, and added ResourceQuotas + LimitRanges on 8 namespaces to prevent any single workload from starving the platform.

Extended coverage added 2026-06-27 (commit `1f4fa75`): 15 additional namespaces covered, Backstage PostgreSQL isolated to accept connections only from backstage app pods, and ai namespace restricted from outbound internet access.

---

## What Was Hardened

| Area | Before | After |
|---|---|---|
| Ingress to platform namespaces | Open — any pod can reach any pod | Default-deny with explicit allow rules (23 namespaces) |
| Backstage PostgreSQL | Accessible to all namespace pods | Only backstage app pods on port 5432 |
| ai namespace internet egress | Unrestricted | Default-deny egress + allow cluster-internal (10.0.0.0/8 only) |
| Resource consumption | No limits — one namespace could exhaust all cluster CPU/memory | Per-namespace quota sized at ~10x actual usage |
| Pod resource defaults | Many pods had no `resources:` spec | LimitRange injects defaults so all pods count against quota |

---

## NetworkPolicy Architecture

### Why ingress-only default-deny

Applying default-deny to **egress** as well would require:
- Explicit DNS egress allow (CoreDNS in kube-system, port 53)
- Explicit kube-apiserver egress allow (ArgoCD, Backstage, Kubernetes plugin)
- Explicit allow to every external hostname (GitHub, Helm repos, OIDC providers)

For a platform this interconnected, egress restriction adds significant operational complexity with limited additional security gain. Ingress default-deny already closes the main threat: unauthorized pod-to-pod lateral movement.

### Policy pattern per namespace

Every protected namespace gets four policies:

```
default-deny-ingress      podSelector: {}  →  drops all ingress by default
allow-same-namespace      allow from podSelector: {}  →  intra-namespace traffic (e.g. app → DB)
allow-ingress-nginx       allow from ingress-nginx namespace  →  web traffic via NGINX
allow-monitoring-scrape   allow from monitoring + observability  →  Prometheus scraping
```

Plus namespace-specific extras (see below).

### How k3s enforces NetworkPolicies

k3s ships a built-in network policy controller (based on kube-router code) that translates NetworkPolicy resources into iptables rules. **Flannel alone does NOT enforce NetworkPolicies** — it's the k3s-embedded kube-router controller that does it.

Verification signal:
- `Connection refused` → port not listening, NOT a NetworkPolicy drop
- `No route to host` → iptables DROP rule from the network policy controller ✓

---

## NetworkPolicies per Namespace

### argocd

```yaml
# manifests/network-policies/argocd.yaml
policies:
  - default-deny-ingress
  - allow-same-namespace        # controller ↔ redis ↔ repo-server ↔ dex
  - allow-ingress-nginx         # ArgoCD UI + API
  - allow-monitoring-scrape     # Prometheus scrapes argocd-metrics
  - allow-kube-system           # metrics-server, CoreDNS health probes
```

### vault

```yaml
policies:
  - default-deny-ingress
  - allow-same-namespace        # vault-agent-injector ↔ vault server
  - allow-ingress-nginx         # Vault UI + API
  - allow-monitoring-scrape     # Prometheus vault metrics
  - allow-webhook-from-apiserver  # kube-apiserver → vault-agent-injector:8080
                                  # (MutatingWebhookConfiguration)
```

The kube-apiserver is not a pod — it runs on the node at `10.0.0.2`. The webhook allow uses `ipBlock: 10.0.0.0/24` targeting only the `vault-agent-injector` pod on port 8080.

### authentik

```yaml
policies:
  - default-deny-ingress
  - allow-same-namespace        # server ↔ worker ↔ redis ↔ postgresql
  - allow-ingress-nginx         # login + OIDC flows
  - allow-monitoring-scrape
  - allow-oidc-clients          # all namespaces → authentik:9000/9443
                                # (in-cluster OIDC token validation)
```

`allow-oidc-clients` uses `namespaceSelector: {}` (empty = match all namespaces). This is intentional: every app that validates OIDC sessions needs to reach Authentik's server. The Backstage, ArgoCD, and Vault OIDC clients all use the `devandre.sbs` URL which goes through NGINX, so they're already covered by `allow-ingress-nginx` — but direct in-cluster clients (if any) also need this.

### monitoring

```yaml
policies:
  - default-deny-ingress
  - allow-same-namespace        # Grafana → Prometheus, Alertmanager → Prometheus
  - allow-ingress-nginx         # Grafana UI
  - allow-kube-system           # kube-state-metrics, node-exporter pushes
  - allow-observability         # Grafana reads Loki datasource (port 3100)
```

Note: Prometheus PULLS from other namespaces (egress from monitoring). This policy only restricts what can reach INTO monitoring — Prometheus scraping is unaffected.

### harbor

```yaml
policies:
  - default-deny-ingress
  - allow-same-namespace        # core ↔ registry ↔ database ↔ redis ↔ trivy
  - allow-ingress-nginx         # Harbor web UI + Docker Registry API
  - allow-monitoring-scrape     # Prometheus harbor-core metrics
  - allow-kubelet-image-pull    # ipBlock 10.0.0.0/24
                                # (kubelet on nodes pulls images from harbor)
```

Kubelet image pulls originate from the node host (not a pod), so they appear as node IP traffic and require an `ipBlock` rule covering `10.0.0.0/24`.

### backstage

PostgreSQL is **explicitly isolated** — only backstage app pods can reach it on port 5432. This replaces the earlier broad `allow-same-namespace` rule.

```yaml
policies:
  - default-deny-ingress
  - allow-ingress-nginx           # ingress-nginx → backstage app pods (port 7007)
  - allow-postgres-from-backstage # backstage app pods → postgresql:5432 only
  - allow-monitoring-scrape
```

The PostgreSQL podSelector targets `app.kubernetes.io/name=postgresql, instance=backstage`. No other namespace or pod can reach the database directly.

### ai (Open WebUI + Ollama)

The ai namespace has **both ingress and egress** restrictions. Egress is restricted to block internet access while allowing cluster-internal communication (model serving, DNS, kube-apiserver).

```yaml
policies:
  - default-deny-ingress
  - allow-same-namespace          # open-webui ↔ ollama
  - allow-ingress-nginx           # Open WebUI browser access
  - allow-monitoring-scrape
  - default-deny-egress           # block all outbound by default
  - allow-dns-egress              # kube-system:53 (DNS resolution)
  - allow-cluster-internal-egress # ipBlock 10.0.0.0/8 (cluster IPs + node IPs)
```

Verification: `curl https://google.com` from open-webui-0 → exit code 7 (blocked). `curl http://ollama.ai.svc.cluster.local:11434/api/tags` → model list returned (allowed).

### observability

```yaml
policies:
  - default-deny-ingress
  - allow-same-namespace        # Promtail → Loki (both in observability)
  - allow-monitoring-read-loki  # monitoring namespace → loki:3100 (Grafana datasource)
  - allow-monitoring-scrape     # Prometheus scrapes Loki and Promtail metrics
```

### Extended namespaces (2026-06-27)

| Namespace | Ingress allow rules | Special |
|---|---|---|
| cert-manager | same-namespace, apiserver-webhook (10.0.0.0/24), monitoring | Webhook called by kube-apiserver |
| chaos-mesh | same-namespace, apiserver-and-nodes (10.0.0.0/24), ingress-nginx, monitoring | Dashboard + daemon webhook |
| external-secrets | same-namespace, apiserver-webhook (10.0.0.0/24), monitoring | Webhook called by kube-apiserver |
| falco | same-namespace, monitoring | No ingress exposed; runs as DaemonSet |
| gatekeeper-system | same-namespace, apiserver-webhook (10.0.0.0/24), monitoring | Admission webhook from all node IPs |
| gitops-demo | same-namespace, ingress-nginx, monitoring | platform-demo app namespace |
| homer | same-namespace, ingress-nginx | Static dashboard |
| ingress-nginx | same-namespace, http-https (0.0.0.0/0 → 80/443), cluster-nodes (10.0.0.0/24), monitoring | Must accept internet traffic |
| keda | same-namespace, apiserver-webhook (10.0.0.0/24), monitoring | Admission + metrics-server webhook |
| ktayl-web | same-namespace, ingress-nginx | Static Astro site |
| messaging | same-namespace, ingress-nginx, cluster-clients (10.42.0.0/16 → 4222), monitoring | NATS pub/sub from pod CIDR |
| nfs-provisioner | same-namespace, cluster-nodes (10.0.0.0/24) | Node NFS mounts |
| nextcloud (existing) | same-namespace, ingress-nginx, monitoring | — |
| podinfo | same-namespace, ingress-nginx, monitoring | Demo app |
| velero | same-namespace, monitoring | No external ingress |

**Webhook namespaces** (cert-manager, chaos-mesh, external-secrets, gatekeeper-system, keda): The `allow-apiserver-webhook` rule uses `ipBlock: 10.0.0.0/24` — kube-apiserver runs on the node (not a pod) and calls admission webhooks from the control-plane node IP. Without this rule, all admission requests fail and the entire cluster becomes inoperable.

---

## ResourceQuotas

Quotas count **configured resource requests/limits in pod specs** — not actual `kubectl top` usage. The Helm chart values determine what counts, not what the pod is currently consuming.

| Namespace | CPU req / lim | Mem req / lim | Pods | ~Actual usage |
|---|---|---|---|---|
| argocd | 2 / 4 | 1Gi / 3Gi | 20 | 21m / 515Mi |
| monitoring | 2 / 4 | 4Gi / 8Gi | 30 | 195m / 1700Mi |
| observability | 1 / 2 | 1Gi / 3Gi | 15 | 85m / 670Mi |
| harbor | 2 / 4 | 1Gi / 3Gi | 20 | 13m / 233Mi |
| authentik | 1 / 3 | 2Gi / 4Gi | 15 | 197m / 889Mi |
| vault | 1 / 2 | 512Mi / 1Gi | 10 | 5m / 65Mi |
| backstage | 1 / 2 | 1Gi / 2Gi | 10 | 9m / 249Mi |
| ingress-nginx | 500m / 2 | 256Mi / 512Mi | 10 | 2m / 76Mi |

"Actual usage" is from `kubectl top pods` at the time of implementation. Quotas are set at roughly 3–10x actual usage.

### LimitRange defaults

Every namespace also has a LimitRange that injects `requests` and `limits` into containers that don't set them explicitly. Without this, pods with no resource spec would bypass the quota entirely.

Example LimitRange for `argocd`:

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: argocd-limits
  namespace: argocd
spec:
  limits:
    - type: Container
      default:
        cpu: 200m
        memory: 256Mi
      defaultRequest:
        cpu: 10m
        memory: 64Mi
      max:
        cpu: "2"
        memory: 2Gi
```

---

## GitOps Structure

```
minicloud-gitops/
  apps/
    network-policies.yaml     ArgoCD App → manifests/network-policies
    quotas.yaml               ArgoCD App → manifests/quotas
  manifests/
    network-policies/         22 files, 98 NetworkPolicy objects total
      argocd.yaml
      authentik.yaml
      backstage.yaml          PostgreSQL isolation: allow-postgres-from-backstage
      cert-manager.yaml       Webhook allow from 10.0.0.0/24
      chaos-mesh.yaml         Webhook + dashboard + daemon
      external-secrets.yaml   Webhook allow from 10.0.0.0/24
      falco.yaml
      gatekeeper-system.yaml  Webhook allow from 10.0.0.0/24
      gitops-demo.yaml
      harbor.yaml
      homer.yaml
      ingress-nginx.yaml      Allows 0.0.0.0/0 on 80/443
      keda.yaml               Webhook allow from 10.0.0.0/24
      ktayl-web.yaml
      messaging.yaml          NATS clients from pod CIDR
      monitoring.yaml
      nfs-provisioner.yaml
      nextcloud.yaml
      observability.yaml
      ai.yaml                 Egress: deny internet, allow 10.0.0.0/8
      podinfo.yaml
      vault.yaml
      velero.yaml
    quotas/
      argocd.yaml             ResourceQuota + LimitRange
      monitoring.yaml         ResourceQuota + LimitRange
      observability.yaml      ResourceQuota + LimitRange
      harbor.yaml             ResourceQuota + LimitRange
      authentik.yaml          ResourceQuota + LimitRange
      vault.yaml              ResourceQuota + LimitRange
      backstage.yaml          ResourceQuota + LimitRange
      ingress-nginx.yaml      ResourceQuota + LimitRange
```

Both ArgoCD Apps use `ServerSideApply=true` and `prune: true` — removing a policy file from git removes the policy from the cluster.

---

## Gotchas

### 1. "Connection refused" ≠ NetworkPolicy blocked

When testing a NetworkPolicy, use a port the target service actually listens on:

```bash
# Wrong — argocd doesn't listen on port 80, gets TCP RST → "Connection refused"
kubectl run test --image=busybox --restart=Never --rm -i -- \
  wget -T3 http://argo-cd-argocd-server.argocd.svc.cluster.local

# Right — argocd-server listens on 8080; NP drop produces "No route to host"
kubectl run test --image=busybox --restart=Never --rm -i -- \
  wget -T3 http://argo-cd-argocd-server.argocd.svc.cluster.local:8080
# → wget: can't connect to remote host: No route to host ✓
```

### 2. Helm chart resource specs count against quota, not actual usage

Example: Vault's Helm chart sets `requests.memory: 256Mi` on vault-0 + `requests.memory: 64Mi` on vault-agent-injector = 320Mi total. An initial quota of 256Mi rejected both pods even though actual usage was only 65Mi.

Always check pod-spec limits with:
```bash
kubectl get pods -n <namespace> -o custom-columns='NAME:.metadata.name,CPU_REQ:.spec.containers[*].resources.requests.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory,CPU_LIM:.spec.containers[*].resources.limits.cpu,MEM_LIM:.spec.containers[*].resources.limits.memory'
```

### 3. kube-prometheus-stack configures much more than pods use

The kube-prometheus-stack Helm chart sets generous memory limits (5568Mi total across all pods in `monitoring`) while actual usage is ~1700Mi. Set the monitoring quota to at least 6Gi limits — we used 8Gi for headroom.

### 4. Boot order: Backstage must start after PostgreSQL

Backstage's new backend system (Backstage ≥ 1.30) does not retry database connections after startup failures. If Backstage starts before its PostgreSQL pod is `Ready`, all plugins fail immediately and the process enters a permanent "started but not ready" state (liveness 200, readiness 503, readiness body: `Backend has not started yet`).

Backstage's new backend system does not retry — the process enters a permanent `liveness:200, readiness:503` state (`Backend has not started yet`). `kubectl rollout restart` gets stuck because the old pod never becomes ready and Kubernetes won't kill it while serving liveness probes.

**Correct fix:** force-delete the pod and let the controller recreate it with PostgreSQL already running:
```bash
kubectl delete pod -n backstage -l app.kubernetes.io/name=backstage --force --grace-period=0
```

StatefulSet/Deployment recreates cleanly → 1/1 Ready in ~22s. This is a known Backstage ≥ 1.30 ordering problem in environments where app and database start simultaneously (e.g. after a node reboot).

---

## Verification

### Test NetworkPolicy enforcement

```bash
# From a pod in default namespace — should be blocked
kubectl run netpol-test --image=busybox:1.36 --restart=Never --rm -i -- \
  wget -T5 http://argo-cd-argocd-server.argocd.svc.cluster.local:8080
# Expected: "wget: can't connect to remote host (10.43.x.x): No route to host"

# From a pod in ingress-nginx namespace — should succeed (allowed by allow-ingress-nginx)
kubectl run netpol-test -n ingress-nginx --image=busybox:1.36 --restart=Never --rm -i -- \
  wget -qO- http://argo-cd-argocd-server.argocd.svc.cluster.local:8080 | head -c 100
# Expected: HTML/JSON response
```

### Check ArgoCD App sync status

```bash
kubectl get applications -n argocd network-policies quotas \
  -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'
```

### Check quota usage

```bash
# All namespaces with quotas
kubectl get resourcequota -A --no-headers | grep -v 'collab\|insurance\|gatekeeper'

# Full detail for one namespace
kubectl describe resourcequota -n monitoring
```

### Check LimitRange is active

```bash
kubectl get limitrange -A --no-headers | grep -v 'collab\|insurance'
```

### Check all policies in a namespace

```bash
kubectl get networkpolicies -n argocd
```

---

## Operational Notes

```bash
# Watch for quota violations when deploying new workloads
kubectl get events -n <namespace> --field-selector reason=FailedCreate | grep exceeded

# Add a new namespace to the NetworkPolicy managed set:
# 1. Create manifests/network-policies/<namespace>.yaml following the standard pattern
# 2. Commit + push — ArgoCD picks it up automatically (the App watches the whole directory)

# Temporarily allow traffic for debugging (remove after):
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: debug-allow-all
  namespace: <namespace>
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - {}
EOF
# Remove after debugging:
kubectl delete networkpolicy debug-allow-all -n <namespace>

# Raise a quota if a deployment is blocked (resource-quota exceeded event):
# Edit manifests/quotas/<namespace>.yaml → commit → push
# ArgoCD updates the ResourceQuota object within ~60s
```
