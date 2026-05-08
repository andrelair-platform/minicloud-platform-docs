---
id: phase-12-gitops
title: Phase 12 — GitOps (ArgoCD)
sidebar_position: 7
---

# Phase 12 — GitOps with ArgoCD

GitOps replaces manual `kubectl apply` and `helm install` with **continuous
reconciliation** against a Git repository. The repo becomes the single
source of truth; ArgoCD watches it and brings the cluster back to that
state every few minutes — automatically.

After this phase the question "if I lost the cluster, how would I rebuild
it?" has a one-command answer: `kubectl apply -f bootstrap/root-app.yaml`,
and ArgoCD recreates everything else.

This phase is also the most **disruptive** so far — ArgoCD starts managing
live workloads. We migrated **Homer** (low-risk, stateless) and added a
new greenfield **whoami** demo, but deliberately left the cluster-critical
workloads (Ingress, MetalLB, Harbor, Prometheus, podinfo) helm-managed
until later phases.

---

## Architecture

```text
                    GitHub: andrelair-platform/minicloud-gitops
                    ┌──────────────────────────────────────────┐
                    │  bootstrap/root-app.yaml  (App-of-Apps)  │
                    │  apps/homer.yaml                         │
                    │  apps/whoami.yaml                        │
                    │  manifests/homer/   (5 YAMLs)            │
                    │  manifests/whoami/  (4 YAMLs)            │
                    └────────────────┬─────────────────────────┘
                                     │ git pull every 3 min
                                     ▼
            ┌────────────────────────────────────────────┐
            │  ArgoCD (in-cluster, namespace argocd)     │
            │  ┌──────────────────────────────────────┐  │
            │  │  Application "root" (App-of-Apps)    │  │
            │  │   ↓ syncs apps/                      │  │
            │  │  Application "homer"                 │  │
            │  │   ↓ syncs manifests/homer/           │  │
            │  │  Application "whoami"                │  │
            │  │   ↓ syncs manifests/whoami/          │  │
            │  └──────────────────────────────────────┘  │
            │  Reconciles → Kubernetes API every 3 min   │
            └────────────────────────────────────────────┘
                                     │
                                     ▼
                          Cluster state matches git
```

UI at `http://argocd.10.0.0.200.nip.io`, login `admin` /
`~/.argocd-admin`.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Apps migrated to ArgoCD | **Homer only** + new whoami demo | Smallest blast radius — Homer is stateless, single ConfigMap + Deployment + Service + Ingress |
| Apps left helm-managed | ingress-nginx, MetalLB, Harbor, kube-prometheus-stack, podinfo | Critical-path or stateful; migrating them deserves its own phase. Phase 9's HPA test rig stays intact. |
| Pattern | **App-of-Apps** | Industry standard; one root Application bootstraps the whole platform |
| Sync policy | `automated: prune+selfHeal=true, syncOptions=[CreateNamespace, ServerSideApply]` | Real GitOps — drift gets corrected automatically. ServerSideApply tracks ownership cleanly during adoption. |
| Auth | Built-in admin from auto-generated `argocd-initial-admin-secret`, dumped to `~/.argocd-admin` | Same out-of-band pattern as Harbor / Grafana. Keycloak SSO comes in Phase 15. |
| UI access | `argocd.10.0.0.200.nip.io` via existing NGINX Ingress (HTTP, `server.insecure=true`) | Matches Homer / Harbor / Grafana / podinfo pattern. TLS in Phase 15. |
| GitOps repo | New public **`andrelair-platform/minicloud-gitops`** | Public is fine — no secrets in this repo. Anything sensitive lives in `~/.*` files on the controller. |
| Repo location | Separate repo (not a monorepo) | Each repo has one purpose, clean ArgoCD path, independent CI |

---

## Pre-flight

```bash
# Add the chart repo
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update argo

# Confirm chart and app version
helm search repo argo/argo-cd
# argo/argo-cd  9.5.13  v3.4.1
```

---

## values.yaml

`argocd-values.yaml`:

```yaml
global:
  domain: argocd.10.0.0.200.nip.io

configs:
  params:
    server.insecure: true       # HTTP behind the Ingress; TLS in Phase 15
  cm:
    timeout.reconciliation: 180s

server:
  # F5 NGINX Ingress gets confused when the chart's default Service has
  # both http (port 80 -> 8080) and https (port 443 -> 8080). The
  # duplicate targetPorts make endpointslice resolution fail with
  # "no endpointslices for target port 8080". We later patched the
  # generated Ingress to use port name "http" instead of port number 80,
  # which avoids the issue.
  service:
    type: ClusterIP
    servicePortHttp: 80
    servicePortHttpName: http
    servicePortHttps: 443
    servicePortHttpsName: https
  ingress:
    enabled: true
    ingressClassName: nginx
    hostname: argocd.10.0.0.200.nip.io
    # NB: do NOT add nginx.org/proxy-buffer-size here — see Troubleshooting

  resources:
    requests: { cpu: 50m,  memory: 128Mi }
    limits:   { cpu: 500m, memory: 512Mi }

repoServer:
  resources:
    requests: { cpu: 50m, memory: 128Mi }
    limits:   { cpu: 500m, memory: 512Mi }

controller:
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 1000m, memory: 1Gi }

applicationSet:
  resources:
    requests: { cpu: 25m, memory: 64Mi }
    limits:   { cpu: 250m, memory: 256Mi }

# Keep things lean — Phase 15 will add Keycloak SSO; Phase 21 will add notifications.
dex:
  enabled: false
notifications:
  enabled: false

redis:
  resources:
    requests: { cpu: 25m, memory: 64Mi }
    limits:   { cpu: 250m, memory: 128Mi }
```

---

## Install

```bash
kubectl create namespace argocd
helm install argo-cd argo/argo-cd -n argocd \
  -f argocd-values.yaml \
  --wait --timeout 10m

# Capture the auto-generated initial admin password (length ~16 chars)
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d > ~/.argocd-admin
chmod 600 ~/.argocd-admin
```

Verify:

```bash
kubectl get pods -n argocd
# 5 pods: server, controller, applicationset, repo-server, redis

curl -sI -m 5 http://argocd.10.0.0.200.nip.io/
# HTTP/1.1 200 OK
```

---

## GitOps repo layout

```
minicloud-gitops/
├── README.md
├── bootstrap/
│   └── root-app.yaml         # the App-of-Apps Application
├── apps/                     # one Application per child app
│   ├── homer.yaml
│   └── whoami.yaml
└── manifests/
    ├── homer/                # Namespace, ConfigMap, Deployment, Service, Ingress
    └── whoami/               # Namespace, Deployment, Service, Ingress
```

### `bootstrap/root-app.yaml` (the App-of-Apps)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
  finalizers: [resources-finalizer.argocd.argoproj.io]
spec:
  project: default
  source:
    repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    path: apps
    directory:
      recurse: false
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

### `apps/homer.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: homer
  namespace: argocd
  finalizers: [resources-finalizer.argocd.argoproj.io]
spec:
  project: default
  source:
    repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    path: manifests/homer
  destination:
    server: https://kubernetes.default.svc
    namespace: homer
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

`apps/whoami.yaml` is identical with path `manifests/whoami` and namespace
`gitops-demo`.

---

## Bootstrap

```bash
kubectl apply -f bootstrap/root-app.yaml
```

Within seconds, ArgoCD discovers the apps directory and creates the
`homer` and `whoami` child Applications:

```
$ kubectl get applications -n argocd
NAME     SYNC STATUS   HEALTH STATUS
homer    Synced        Healthy
root     Synced        Healthy
whoami   Synced        Healthy
```

### Adopting Homer (no downtime)

Homer was previously deployed via raw `kubectl apply`, with no ArgoCD
labels or annotations. Naive adoption would conflict ("resource already
exists"). We avoid that by setting `ServerSideApply=true` in the
`syncOptions` — server-side apply uses field managers to take over
ownership cleanly without recreating resources.

After bootstrap, the existing Homer pod kept running (no restart) and
ArgoCD took ownership. The tracking annotation appeared on the live
ConfigMap:

```bash
$ kubectl get cm homer-config -n homer -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}'
homer:/ConfigMap:homer/homer-config
```

---

## The git-push-to-deploy demo

Edit `manifests/homer/01-configmap.yaml` to change the dashboard
subtitle, then push:

```bash
cd minicloud-gitops/
sed -i 's|subtitle: \\"Private Bare-Metal Infrastructure\\"|subtitle: \\"Private Bare-Metal Infrastructure \\u2014 GitOps via ArgoCD\\"|' \
  manifests/homer/01-configmap.yaml
git add manifests/homer/01-configmap.yaml
git commit -m "demo: GitOps callout in Homer subtitle"
git push origin main
```

Watch ArgoCD pick up the new revision:

```bash
$ kubectl get app homer -n argocd -w
NAME    SYNC STATUS   HEALTH STATUS
homer   Synced        Healthy
homer   OutOfSync     Healthy           # detected at +180s
homer   Synced        Progressing       # applied
homer   Synced        Healthy           # rolled out
```

The first sync took **~3 min 24 s** end-to-end — exactly the documented
default reconciliation interval (180 s) plus a small processing delay.

---

## Two real gotchas this phase exposed

### 1. The `nginx.org/proxy-buffer-size` annotation breaks all Ingresses

Initially I added `nginx.org/proxy-buffer-size: "16k"` to ArgoCD's
Ingress annotations as a "just in case" for the 308-redirect concern.
That change made `nginx -s reload` fail with:

```
[emerg] "proxy_busy_buffers_size" must be less than the size of all
        "proxy_buffers" minus one buffer
```

NGINX kept the *previous* config running, but every subsequent change
(including endpoints for new pods) silently failed to apply. Result: a
404 on the new ArgoCD ingress, plus zero updates to anything else
F5 NGINX manages.

**Fix:** remove the annotation. F5 NGINX uses default buffer config and
handles ArgoCD fine without it.

### 2. ConfigMap subPath mounts + ArgoCD selfHeal == checksum annotation

Homer mounts its config like this:

```yaml
volumeMounts:
  - mountPath: /www/assets/config.yml
    name: config
    subPath: config.yml
```

When a ConfigMap is mounted with `subPath`, **Kubernetes does not
auto-propagate** changes to the file. The pod sees the old config until
it restarts.

The obvious fix is `kubectl rollout restart`, but that doesn't survive
ArgoCD's `selfHeal: true`: ArgoCD sees the auto-injected `restartedAt`
annotation as drift and reverts it within seconds.

**The GitOps-correct fix** is to bump a checksum annotation in the pod
template alongside the ConfigMap change:

```yaml
spec:
  template:
    metadata:
      annotations:
        config-checksum: "v3-argocd-whoami-tiles"   # bump on every config change
```

This alters the pod-template-hash, ArgoCD applies it as a normal sync,
and the rolling restart picks up the new ConfigMap. Production teams
automate this with [Reloader](https://github.com/stakater/Reloader) or
kustomize's `configMapGenerator` (which generates suffixed names).

---

## Verification (results)

| Test | Expected | Actual |
|---|---|---|
| Connectivity | `curl http://argocd.10.0.0.200.nip.io/` | `200 OK` ✓ |
| Login | `POST /api/v1/session` returns JWT | token length 257 ✓ |
| Migration | Homer ConfigMap has `argocd.argoproj.io/tracking-id` | `homer:/ConfigMap:homer/homer-config` ✓ |
| Apps healthy | `kubectl get applications -n argocd` | `root` + `homer` + `whoami` all `Synced` + `Healthy` ✓ |
| GitOps loop | Push → cluster reflects change | ~3 min 24 s ✓ |
| New workload | `curl http://whoami.10.0.0.200.nip.io/` | full traefik/whoami response with 2 alternating pod hostnames ✓ |

---

## Done When

```text
✔ ArgoCD UI reachable at http://argocd.10.0.0.200.nip.io
✔ Admin login works with the password from ~/.argocd-admin
✔ kubectl get applications -n argocd shows root + homer + whoami all Synced + Healthy
✔ Homer was migrated without restart (existing pod kept running)
✔ A push to minicloud-gitops triggers a sync within ~3 minutes
✔ http://whoami.10.0.0.200.nip.io/ returns valid traefik/whoami output
✔ Homer dashboard has live ArgoCD and whoami tiles
```

---

## What's NOT migrated to ArgoCD yet

Intentional scope. Migrating these is a future phase:

| Component | Why deferred |
|---|---|
| `ingress-nginx` | Critical path — if ArgoCD breaks the Ingress, half the platform goes down with it |
| `metallb-system` | Critical path — same as above, plus has cluster-scoped resources |
| `harbor` | Stateful, 5 PVCs. Adopting a stateful workload is its own playbook. |
| `kube-prometheus-stack` | Heavyweight chart, complex CRDs, lifecycle hooks |
| `podinfo` | Phase 9's HPA + custom dashboard test rig is too valuable to risk during migration |

The principle: **migrate the cheapest things first, prove the workflow,
then come back for the expensive things in dedicated migration phases**.

---

## Real-world skills demonstrated

| Skill | Where it applies in industry |
|---|---|
| **App-of-Apps pattern** | The standard ArgoCD bootstrapping pattern at every scale, from 5-app clusters to 500-app multi-tenant platforms |
| **Brownfield resource adoption** | Every team that adopts ArgoCD post-hoc has to deal with existing kubectl-applied resources. ServerSideApply is the cleanest path. |
| **Auto-sync + selfHeal in production** | Real GitOps means the cluster auto-corrects drift. The catch — see the "two gotchas" — is real production knowledge. |
| **ConfigMap subPath + checksum-annotation pattern** | Solves a real problem every Kubernetes shop hits. Reloader is the canonical solution; the inline checksum is the manual baseline. |
| **Risk-aware migration scope** | Choosing which workloads to migrate first vs. which to defer is the same calculus every platform team makes. Critical-path apps go last, not first. |
| **Recognizing failed-reload symptoms** | The "404 on a new Ingress that should work" diagnosis pattern — check ingress controller logs for `[emerg]` reload failures — is Day-2 ops 101. |
| **Multi-repo org structure** | One purpose per repo (`minicloud-platform-docs`, `minicloud-ansible`, `minicloud-opentofu`, `minicloud-gitops`) is the canonical setup for real platform teams. |
