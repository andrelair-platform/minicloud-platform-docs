---
id: argo-rollouts
title: Phase 73 — Argo Rollouts
sidebar_label: Phase 73 — Argo Rollouts
---

# Phase 73 — Argo Rollouts

Argo Rollouts replaces Kubernetes `Deployment` objects with a `Rollout` CRD that adds canary and blue-green deployment strategies, traffic shaping, and automated analysis using Prometheus metrics. When a new image is promoted, the rollout controller manages the transition between stable and canary ReplicaSets before completing (or aborting) the update.

---

## What Was Deployed

| Component | Change |
|---|---|
| `apps/argo-rollouts.yaml` | New ArgoCD Application — Argo Rollouts controller in `argo-rollouts` ns |
| `manifests/argocd-project/00-project.yaml` | Added `argo-rollouts` namespace to destinations |
| `gatekeeper-policies/` (8 files) | Added `argo-rollouts` to namespaceSelector NotIn exclusion lists |
| `services/platform-demo/base/deployment.yaml` | Converted `Deployment` → `Rollout` (canary strategy) |
| `services/platform-demo/base/analysis-template.yaml` | New `AnalysisTemplate` using Prometheus success rate (`count: 5`) |
| `services/platform-demo/base/kustomization.yaml` | Added `analysis-template.yaml` to resources |
| `services/platform-demo/overlays/dev/` + `overlays/staging/` | Switched to JSON 6902 patches with `target:` (CRD atomic list fix) |
| `apps/platform-demo-dev.yaml` + `platform-demo-staging.yaml` | Added `SkipDryRunOnMissingResource`, updated `ignoreDifferences` group |

---

## Controller Installation

```yaml
# apps/argo-rollouts.yaml
source:
  repoURL: https://argoproj.github.io/argo-helm
  chart: argo-rollouts
  targetRevision: "2.41.0"   # app v1.9.0
  helm:
    values: |
      controller:
        containerSecurityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: [ALL]
        podSecurityContext:
          runAsNonRoot: true
          seccompProfile:
            type: RuntimeDefault
      dashboard:
        enabled: true
```

The controller watches for `Rollout` objects cluster-wide and creates/manages stable and canary ReplicaSets. The optional dashboard runs in the same namespace and provides a UI for rollout status.

---

## Canary Strategy on platform-demo

platform-demo was chosen as the canary demo target: it's the simplest service (Go binary, no stateful dependencies) and is already deployed across dev and staging.

```yaml
# services/platform-demo/base/deployment.yaml (abridged)
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: platform-demo
spec:
  replicas: 2
  strategy:
    canary:
      steps:
        - setWeight: 50        # send 50% traffic to the new version
        - pause: {duration: 30s}
        - analysis:            # run AnalysisTemplate — checks Prometheus success rate
            templates:
              - templateName: http-success-rate
        - setWeight: 100       # complete rollout if analysis passes
```

**Step trace for a new image push:**

```
Image pushed to Harbor
  → ArgoCD detects new tag in overlays/dev/kustomization.yaml
  → Creates canary ReplicaSet (1 pod = 50% of 2 replicas)
  → Pauses 30s (observable in ArgoCD / rollout dashboard)
  → Runs AnalysisRun against Prometheus
  → If success rate ≥ 95%: promotes → sets canary RS as stable
  → If success rate < 95% (3 consecutive fails): aborts → old RS kept, canary deleted
```

---

## AnalysisTemplate

```yaml
# services/platform-demo/base/analysis-template.yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: http-success-rate
spec:
  metrics:
    - name: success-rate
      interval: 30s
      successCondition: result[0] >= 0.95
      failureLimit: 3
      provider:
        prometheus:
          address: http://kube-prometheus-stack-prometheus.monitoring.svc:9090
          query: |
            sum(rate(http_requests_total{service="platform-demo",code!~"5.."}[2m]))
            /
            sum(rate(http_requests_total{service="platform-demo"}[2m]))
```

The query measures the ratio of non-5xx responses over the past 2 minutes. If it drops below 95% three times in a row, the rollout is aborted and the stable version remains running.

---

## Gatekeeper Exclusions

The Argo Rollouts controller itself runs in the `argo-rollouts` namespace. The controller pods need certain capabilities that Gatekeeper would block. `argo-rollouts` was added to the `NotIn` exclusion list in all 8 Pod-matching constraint files:

```
10-constraint-block-latest-tag
11-constraint-no-privileged
12-constraint-require-resource-limits
13-constraint-allowed-registries
14-constraint-require-non-root
15-constraint-no-privilege-escalation
19-constraint-block-net-raw
20-constraint-block-capabilities
```

Rollout objects in other namespaces (like `platform-demo-dev`) are still subject to all Gatekeeper constraints since the restrictions target `argo-rollouts` namespace specifically.

---

## ArgoCD Sync Considerations

The `Rollout` CRD doesn't exist in the cluster until the `argo-rollouts` ArgoCD app syncs. To prevent `platform-demo-dev` from failing a dry-run against a missing CRD, both apps include:

```yaml
syncOptions:
  - SkipDryRunOnMissingResource=true
```

`ignoreDifferences` was also updated from `group: apps / kind: Deployment` to `group: argoproj.io / kind: Rollout` to suppress replica-count drift from manual scaling.

---

## Gotcha — Deployment → Rollout migration

Kubernetes does not accept a resource change from `apps/v1 Deployment` to `argoproj.io/v1alpha1 Rollout` via `kubectl apply` — the group/kind mismatch causes a conflict. ArgoCD handles this correctly via `prune: true`: on the next sync it deletes the old Deployment and creates the Rollout.

**The cluster experiences a brief downtime** during this transition (old Deployment pods deleted, new Rollout pods starting). For platform-demo this is acceptable (dev/staging only, no prod overlay). For any service with a prod overlay, plan a maintenance window.

---

## Gotcha — Kustomize strategic merge patches strip fields on Rollout CRDs

When using `patches:` with a strategic merge patch file against a `Rollout` object, kustomize treats the `containers` list as **atomic** (no `x-kubernetes-list-map-keys` markers in the CRD schema). This means the patch entry **replaces the entire container** instead of merging into it — stripping `image`, `ports`, `readinessProbe`, `livenessProbe`, and `securityContext`.

**Symptom:** Pod creation fails with `admission webhook denied: must not use or retain the NET_RAW capability` because `capabilities.drop: [ALL]` was stripped.

**Fix:** Use JSON 6902 patches (`op: replace`) with a `target:` in `kustomization.yaml` to surgically replace only the fields that differ between overlays:

```yaml
# overlays/dev/kustomization.yaml
patches:
  - path: patch-resources.yaml
    target:
      group: argoproj.io
      version: v1alpha1
      kind: Rollout
      name: platform-demo
```

```yaml
# overlays/dev/patch-resources.yaml (JSON 6902 format)
- op: replace
  path: /spec/replicas
  value: 1
- op: replace
  path: /spec/template/spec/containers/0/resources
  value:
    requests: {cpu: 10m, memory: 16Mi}
    limits:   {cpu: 100m, memory: 64Mi}
```

This only modifies the two specified paths and leaves all other container fields intact. Apply this pattern to any CRD that has list fields — not just Rollouts.

---

## Gotcha — AnalysisTemplate metrics must have a finite `count`

When an `AnalysisTemplate` is referenced from an inline canary step, every metric must include `count:`. Without it, the Argo Rollouts controller rejects the Rollout spec with:

```
spec.strategy.canary.steps[N].analysis.templates: Invalid value: "http-success-rate":
AnalysisTemplate http-success-rate has metric success-rate which runs indefinitely.
Invalid value for count: <nil>
```

**Fix:** Add `count:` alongside `interval:`:

```yaml
metrics:
  - name: success-rate
    count: 5          # run exactly 5 times (5 × 30s = 2.5 min of analysis)
    interval: 30s
    successCondition: result[0] >= 0.95
    failureLimit: 3
```

`count` is not required for background analysis (where the metric runs for the duration of the rollout), but it is required for step-level analysis references.

---

## Gotcha — Stale stableRS from a broken initial deploy

If the Rollout's first deploy fails (e.g. due to either of the above issues), the broken ReplicaSet gets recorded as `stableRS`. On the next sync with a fixed spec, the controller creates a new canary RS but tries to hold 50% traffic on the broken stable RS — which Gatekeeper blocks. The rollout stalls at step 0 indefinitely.

**Symptom:** `kubectl get rollout` shows `Progressing step=0 waiting for all steps to complete` with no pods running from the stable RS.

**Fix:** Delete the broken stable RS manually. The controller immediately promotes the healthy canary RS to stable:

```bash
# Identify the stuck stableRS
kubectl get rollout platform-demo -n platform-demo-dev \
  -o jsonpath='{.status.stableRS}'

# Delete it — controller promotes the canary within seconds
kubectl delete rs platform-demo-<staleHash> -n platform-demo-dev
```

This situation only arises on the very first deploy after a migration. Subsequent rollouts start from a healthy stable baseline and this scenario cannot recur.

---

## Observing a Rollout

```bash
# Via kubectl plugin (install: kubectl argo rollouts)
kubectl argo rollouts get rollout platform-demo -n platform-demo-dev --watch

# Via the dashboard (requires port-forward):
kubectl port-forward -n argo-rollouts svc/argo-rollouts-dashboard 3100:3100
# Open http://localhost:3100
```
