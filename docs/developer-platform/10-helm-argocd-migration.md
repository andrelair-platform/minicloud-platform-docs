---
id: helm-argocd-migration
title: Full Helm → ArgoCD Migration (22 Apps)
sidebar_label: Full Helm→ArgoCD Migration
---

# Full Helm → ArgoCD Migration

**Completed:** 2026-07-07
**Result:** 54/54 ArgoCD apps Synced+Healthy — 100% GitOps coverage

This runbook documents the migration of all 22 remaining direct-Helm releases to ArgoCD multi-source Applications, and the gotchas that came up during adoption.

---

## What Was Migrated

Before this phase, a subset of platform tools (Vault, Nextcloud, Langfuse, Polaris) had already been migrated to ArgoCD. The following 22 tools were migrated in this session:

| ArgoCD App | Chart | Values file |
|---|---|---|
| `argo-cd` | argoproj/argo-cd | `argocd-values.yaml` |
| `authentik` | goauthentik.io/authentik | `authentik-values.yaml` |
| `backstage` | backstage/backstage | `backstage-values.yaml` |
| `cert-manager` | jetstack/cert-manager | `cert-manager-values.yaml` |
| `chaos-mesh` | chaos-mesh/chaos-mesh | `chaos-mesh-values.yaml` |
| `falco` | falcosecurity/falco | `falco-values.yaml` |
| `gatekeeper` | gatekeeper/gatekeeper | `gatekeeper-values.yaml` |
| `harbor` | harbor/harbor | `harbor-values.yaml` |
| `keda` | kedacore/keda | `keda-values.yaml` |
| `kube-prometheus-stack` | prometheus-community/kube-prometheus-stack | `kube-prometheus-stack-values.yaml` |
| `loki` | grafana/loki | `loki-values.yaml` |
| `nats` | nats/nats | `nats-values.yaml` |
| `nfs-provisioner` | nfs-subdir-external-provisioner | `nfs-provisioner-values.yaml` |
| `nginx-ingress` | nginx-stable/nginx-ingress | `nginx-ingress-values.yaml` |
| `ollama` | otwld/ollama | `ollama-values.yaml` |
| `ollama-secondary` | otwld/ollama | `ollama-secondary-values.yaml` |
| `ollama-tertiary` | otwld/ollama | `ollama-tertiary-values.yaml` |
| `open-webui` | open-webui/open-webui | `open-webui-values.yaml` |
| `podinfo` | podinfo/podinfo | `podinfo-values.yaml` |
| `postgresql-ai` | bitnami/postgresql | `postgresql-ai-values.yaml` |
| `promtail` | grafana/promtail | `promtail-values.yaml` |
| `velero` | vmware-tanzu/velero | `velero-values.yaml` |

All values files live in `minicloud-gitops/helm-values/`. The `minicloud-ansible/helm-values/` directory is now **bootstrap-only** — do not edit it for running workloads.

---

## Multi-Source Application Pattern

Every migrated tool uses the same two-source pattern:

```yaml
sources:
  - repoURL: https://helm.releases.hashicorp.com   # upstream chart
    chart: vault
    targetRevision: "0.33.0"
    helm:
      releaseName: vault
      valueFiles:
        - $values/helm-values/vault-values.yaml    # ref to second source
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    ref: values                                    # named reference
```

The `ref: values` source does not generate manifests — it is a named Git pointer used by `$values` in the first source's `valueFiles`. This keeps the values file version-controlled in the same commit graph as all other platform config.

---

## AppProject Changes

The `minicloud-platform` AppProject required updates to accommodate all 22 new apps:

**sourceRepos added (19 total):**
- `https://argoproj.github.io/argo-helm`
- `https://goauthentik.io/helm`
- `https://backstage.github.io/charts`
- `https://charts.jetstack.io`
- `https://charts.chaos-mesh.org`
- `https://falcosecurity.github.io/charts`
- `https://open-policy-agent.github.io/gatekeeper/charts`
- `https://helm.goharbor.io`
- `https://kedacore.github.io/charts`
- `https://prometheus-community.github.io/helm-charts`
- `https://grafana.github.io/helm-charts`
- `https://nats-io.github.io/k8s/helm/charts/`
- `https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/`
- `https://helm.nginx.com/stable`
- `https://otwld.github.io/ollama-helm/`
- `https://open-webui.github.io/helm-charts/`
- `https://stefanprodan.github.io/podinfo`
- `https://charts.bitnami.com/bitnami`
- `https://vmware-tanzu.github.io/helm-charts`

**clusterResourceWhitelist additions:** `IngressClass` (networking.k8s.io), `APIService` (apiregistration.k8s.io) — required by nginx-ingress and kube-prometheus-stack metrics-server.

**destinations additions:** `kube-system` — required by cert-manager and kube-prometheus-stack admission webhooks.

---

## Gotchas Fixed During Migration

### 1. Duplicate OLLAMA_HOST env var (otwld/ollama chart 1.x)

**Symptom:** All three Ollama ArgoCD apps show `Unknown` with:
```
error calculating structured merge diff: error building typed value from config resource:
.spec.template.spec.containers[name="ollama"].env: duplicate entries for key [name="OLLAMA_HOST"]
```

**Root cause:** ollama chart 1.x natively sets `OLLAMA_HOST=0.0.0.0:<port>` from the `ollama.port` config value. The three values files also explicitly set `OLLAMA_HOST` in `extraEnv`. This created a duplicate env var in the generated template. ArgoCD's SSA diff engine rejects duplicate array keys.

**Fix — values file:** Remove `OLLAMA_HOST` from `extraEnv` in all three values files:
```yaml
# Before (broken):
extraEnv:
  - name: OLLAMA_HOST
    value: "0.0.0.0:11434"
  - name: OLLAMA_NUM_PARALLEL
    value: "4"

# After (correct):
extraEnv:
  - name: OLLAMA_NUM_PARALLEL
    value: "4"
```

**Fix — live resource:** The live Deployment already had the duplicate because of prior helm upgrades. `kubectl patch --type=strategic` returns success but does **not** deduplicate arrays. The only fix is `kubectl replace` with a deduplicated manifest:
```bash
kubectl get deployment ollama -n ai -o json \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
envs = d['spec']['template']['spec']['containers'][0]['env']
seen = {}
deduped = []
for e in envs:
    if e['name'] not in seen:
        seen[e['name']] = True
        deduped.append(e)
d['spec']['template']['spec']['containers'][0]['env'] = deduped
print(json.dumps(d))
" | kubectl replace -f -
```

---

### 2. Duplicate POSTGRES_* env vars (backstage chart 2.7)

**Symptom:** `backstage` app shows `Unknown` with:
```
error building typed value from live resource:
.spec.template.spec.containers[name="backstage-backend"].env: duplicate entries for key [name="POSTGRES_HOST"]
```

**Root cause:** backstage chart 2.7.0 automatically injects `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` from its built-in postgresql subchart when `postgresql.enabled: true`. These were also present in `backstage-values.yaml` under `backend.extraEnvVars`.

**Fix:** Remove the four POSTGRES_* entries from `extraEnvVars`. The chart provides them automatically. Same `kubectl replace` approach required to clean the live Deployment.

---

### 3. NATS StatefulSet persistent OutOfSync

**Symptom:** `nats` app always shows `OutOfSync` even after sync completes.

**Root cause:** Two categories of diff:

1. **`spec.updateStrategy`**: The NATS chart template has no `updateStrategy` block, but Kubernetes adds `{type: RollingUpdate, rollingUpdate: {partition: 0}}` at creation time. Ignoring only `/spec/updateStrategy/rollingUpdate/partition` (jsonPointer) doesn't cover the full object diff.

2. **VolumeClaimTemplate metadata**: Kubernetes adds `apiVersion: v1`, `kind: PersistentVolumeClaim`, `spec.volumeMode: Filesystem`, and `status: {}` to every VCT entry. jsonPointers cannot target array elements with wildcards.

**Fix:** Use `jqPathExpressions` (not `jsonPointers`) with array wildcard syntax:

```yaml
ignoreDifferences:
  - group: apps
    kind: StatefulSet
    name: nats
    namespace: messaging
    jqPathExpressions:
      - .spec.revisionHistoryLimit
      - .spec.persistentVolumeClaimRetentionPolicy
      - .spec.updateStrategy          # whole object — Kubernetes sets defaults, chart omits
      - .spec.volumeClaimTemplates[].apiVersion
      - .spec.volumeClaimTemplates[].kind
      - .spec.volumeClaimTemplates[].spec.volumeMode
      - .spec.volumeClaimTemplates[].status
```

Key difference: `jqPathExpressions` supports `[].field` for array element access. `jsonPointers` requires exact index (`/spec/volumeClaimTemplates/0/apiVersion`) and cannot use wildcards.

---

### 4. nginx-ingress Service persistent OutOfSync

**Symptom:** `nginx-ingress` app shows `OutOfSync` after every sync on the controller Service.

**Root cause:** The nginx-ingress chart renders a `type: LoadBalancer` Service. Kubernetes assigns several fields at creation time that are absent from the chart template:
- `spec.clusterIP` / `spec.clusterIPs` — assigned by kube-proxy
- `spec.ipFamilies` / `spec.ipFamilyPolicy` — IP family defaults
- `spec.allocateLoadBalancerNodePorts` — LoadBalancer default
- `spec.internalTrafficPolicy` — defaults to `Cluster`
- `spec.healthCheckNodePort` — assigned for `externalTrafficPolicy: Local`
- `spec.sessionAffinity` / `spec.sessionAffinityConfig` — defaults
- `spec.ports[].nodePort` — assigned port numbers

**Fix:** Ignore all controller-assigned Service fields via `jqPathExpressions`:
```yaml
ignoreDifferences:
  - kind: Service
    name: nginx-ingress-controller
    namespace: ingress-nginx
    jqPathExpressions:
      - .spec.clusterIP
      - .spec.clusterIPs
      - .spec.ipFamilies
      - .spec.ipFamilyPolicy
      - .spec.allocateLoadBalancerNodePorts
      - .spec.internalTrafficPolicy
      - .spec.healthCheckNodePort
      - .spec.sessionAffinity
      - .spec.sessionAffinityConfig
      - .spec.ports[].nodePort
```

All ignoreDifferences on Helm apps require `RespectIgnoreDifferences=true` in `syncOptions` to also affect the OutOfSync status calculation (not just the sync operation).

---

### 5. kube-prometheus-stack blocked by ResourceQuota

**Symptom:** `kube-prometheus-stack` stays `OutOfSync`. Describe shows:
```
Error creating: pods "kps-admission-create-xxxxx" is forbidden: exceeded quota: monitoring-quota,
requested: limits.memory=512Mi, used: limits.memory=7744Mi, limited: limits.memory=8Gi
```

**Root cause:** The `kps-admission-create` Helm hook Job requests 512Mi memory. The monitoring namespace quota was 8Gi, which was already at 7744Mi from the normal workloads. No room for the hook pod.

**Fix:** Increase monitoring namespace quota:
```yaml
# manifests/quotas/monitoring.yaml
limits.memory: 12Gi   # was 8Gi
requests.memory: 6Gi  # was 4Gi
```

---

### 6. ArgoCD repo-server OOMKill

**Symptom:** Multiple apps show `Unknown` with:
```
rpc error: code = Unavailable desc = connection error:
desc = "transport: Error while dialing: dial tcp 10.43.93.118:8081: connect: connection refused"
```

**Root cause:** ArgoCD's `repo-server` pod was CrashLoopBackOff due to OOMKill (exit code 137). 512Mi is insufficient when 54 Helm chart apps refresh concurrently — each requires a Helm template call in-process.

**Fix:**
1. Increase repo-server memory limit in `argocd-values.yaml`:
```yaml
repoServer:
  resources:
    requests: { cpu: 50m,  memory: 256Mi }
    limits:   { cpu: 1000m, memory: 1500Mi }
```
2. Increase ArgoCD namespace quota in `manifests/quotas/argocd.yaml`:
```yaml
limits.memory: 5Gi  # was 3Gi
```
3. Trigger a hard refresh before resyncing to pick up the new values:
```bash
kubectl annotate app argo-cd -n argocd argocd.argoproj.io/refresh=hard --overwrite
```

---

## Operational Impact After Migration

### What changed

| Before | After |
|---|---|
| `ssh controller "helm upgrade <tool> ..."` | Edit `helm-values/<tool>-values.yaml`, commit, push |
| Values in controller `~/minicloud-ktaylorganisation/ansible/helm-values/` | Values in `minicloud-gitops/helm-values/` (version-controlled) |
| No drift detection on third-party tools | ArgoCD detects and corrects drift on all 54 apps |
| Manual coordination between Git state and cluster state | Git is the single source of truth; ArgoCD enforces it |

### How to change a Helm value

```bash
# Edit locally
vim ~/Developer/cloudplateform/minicloud-gitops/helm-values/vault-values.yaml

# Commit and push (ArgoCD polls every 3 minutes)
cd ~/Developer/cloudplateform/minicloud-gitops
git add helm-values/vault-values.yaml
git commit -m "chore(vault): increase memory limit to 512Mi"
git push origin main
```

ArgoCD auto-syncs within 3 minutes. No SSH, no `helm upgrade`, no manual steps.

### How to pin a chart version upgrade

```yaml
# apps/vault.yaml
sources:
  - repoURL: https://helm.releases.hashicorp.com
    chart: vault
    targetRevision: "0.34.0"   # bump this
```

Commit the Application YAML — ArgoCD runs `helm upgrade` automatically.

---

## Manual Sync (no argocd CLI)

When you need to force an immediate sync without waiting for the 3-minute poll:

```bash
kubectl patch application <app-name> -n argocd --type merge -p '{
  "operation": {
    "initiatedBy": {"username": "kubectl"},
    "sync": {
      "revision": "HEAD",
      "syncOptions": [
        "ServerSideApply=true",
        "CreateNamespace=true",
        "RespectIgnoreDifferences=true"
      ]
    }
  }
}'
```

Force cache invalidation first if the app is using stale manifests:
```bash
kubectl annotate app <app-name> -n argocd argocd.argoproj.io/refresh=hard --overwrite
```

---

## Verification

Confirm all apps are healthy:
```bash
kubectl get applications -n argocd --no-headers \
  | awk '{print $2, $3}' | sort | uniq -c
```

Expected output:
```
53 Synced Healthy
 1 Synced Progressing   ← Harbor (normal during rollout)
```

Check for any Unknown apps (SSA diff errors):
```bash
kubectl get applications -n argocd --no-headers | grep -v "Synced"
```
