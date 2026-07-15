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
| `services/platform-demo/base/analysis-template.yaml` | New `AnalysisTemplate` using Prometheus success rate |
| `services/platform-demo/base/kustomization.yaml` | Added `analysis-template.yaml` to resources |
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

## Observing a Rollout

```bash
# Via kubectl plugin (install: kubectl argo rollouts)
kubectl argo rollouts get rollout platform-demo -n platform-demo-dev --watch

# Via the dashboard (requires port-forward):
kubectl port-forward -n argo-rollouts svc/argo-rollouts-dashboard 3100:3100
# Open http://localhost:3100
```
