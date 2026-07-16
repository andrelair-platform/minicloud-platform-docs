---
slug: kubernetes-configmap-auto-reload-stakater-reloader
title: "Automating ConfigMap Reloads: Why We Added Stakater Reloader"
authors: [andre]
description: >
  Kubernetes does not automatically restart pods when a mounted ConfigMap changes — especially
  when using subPath mounts. We added Stakater Reloader to eliminate manual kubectl rollout
  restart calls across Homer, LiteLLM, SearXNG, and Backstage. Here's the problem, the fix,
  and a bonus ArgoCD OOMKill investigation we uncovered along the way.
tags: [kubernetes, gitops, argocd, platform-engineering, reloader, configmap, devops]
date: 2026-07-16
---

Every time I updated the Homer dashboard config, I had to run `kubectl rollout restart deployment/homer -n homer` after ArgoCD finished syncing. Same for LiteLLM when routing changed. Same for Backstage after any catalog or proxy update. The pattern was identical every time: push to git, wait for ArgoCD sync, then manually trigger a pod restart.

That is an operational smell. If git is the only write path, the restart should be automatic too.

{/* truncate */}

## Why Kubernetes Doesn't Auto-Reload ConfigMaps

Kubernetes *does* update ConfigMap data in-place — but only for volume mounts that use the full directory. When you mount a ConfigMap with `subPath` (mounting a single file rather than the whole directory), Kubernetes [intentionally skips the automatic update](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Homer mounts its config with `subPath`:

```yaml
volumeMounts:
  - mountPath: /www/assets/config.yml
    name: config
    subPath: config.yml   # ← this disables automatic propagation
```

This is by design. `subPath` gives you fine-grained control over where a file lands inside a container, but it breaks the inotify watch that Kubernetes would otherwise use to propagate ConfigMap updates. The file the pod sees is frozen at mount time.

The common workaround — which I had in place — is a manual annotation bump on the pod template:

```yaml
template:
  metadata:
    annotations:
      config-checksum: "v17-star-kitten-polaris"  # bump this manually after every config change
```

Changing the annotation forces a new pod-template-hash, which triggers a rolling restart. But this is noise: it clutters the git history, it's easy to forget, and it has nothing to do with the actual change being made.

## The Broader Pattern

It wasn't just Homer. Every ConfigMap-backed deployment in the cluster had the same problem:

| Deployment | ConfigMaps | Required action after change |
|---|---|---|
| `homer` | `homer-config` | Manual `kubectl rollout restart` |
| `litellm` | `litellm-config`, `langfuse-prompt-handler`, `phi3-financial-prompt` | Manual `kubectl rollout restart` |
| `searxng` | `searxng-config` | Manual `kubectl rollout restart` |
| `backstage` | `backstage-app-config`, `backstage-session-config` | Manual `kubectl rollout restart` |

The CLAUDE.md even had a note reminding me to run the restart after every Backstage config push. That note existing is the problem — if a human has to remember to do something after a git push, it will eventually be forgotten.

## The Fix: Stakater Reloader

[Stakater Reloader](https://github.com/stakater/reloader) is a Kubernetes controller that watches ConfigMaps and Secrets, and triggers rolling restarts on any Deployment (or StatefulSet, DaemonSet) that opts in via a single annotation.

The deployment is a single Helm chart in its own namespace:

```yaml
# apps/reloader.yaml
sources:
  - repoURL: https://stakater.github.io/stakater-charts
    chart: reloader
    targetRevision: "2.2.14"   # app v1.4.19
```

And opting in is one line on any Deployment metadata:

```yaml
metadata:
  annotations:
    reloader.stakater.com/auto: "true"
```

Reloader detects all ConfigMaps and Secrets referenced by the Deployment (via `volumes`, `envFrom`, and `env.valueFrom`) and watches them. When ArgoCD syncs a ConfigMap change, Reloader sees the update within seconds and triggers a rolling restart automatically.

The flow is now fully automated:

```
git push → ArgoCD syncs ConfigMap → Reloader detects change → pod rolling restart
```

No human step. No annotation bump. No runbook entry reminding you to remember.

## Removing the Manual Workaround

With Reloader installed, the `config-checksum` annotation in Homer's deployment was noise:

```yaml
# before — manual workaround
template:
  metadata:
    annotations:
      config-checksum: "v17-star-kitten-polaris"

# after — clean
template:
  metadata:
    labels:
      app: homer
      backstage.io/kubernetes-id: homer
```

The deployment metadata gets the Reloader annotation instead:

```yaml
metadata:
  name: homer
  namespace: homer
  annotations:
    reloader.stakater.com/auto: "true"
```

## A Bonus Investigation: ArgoCD OOMKills

While implementing Reloader, I noticed the ArgoCD application controller was in CrashLoopBackOff — 183 restarts over 44 hours:

```
argo-cd-argocd-application-controller-0   0/1   CrashLoopBackOff   183 (4m ago)   44h
```

This explained why syncs were taking forever and why Reloader itself couldn't complete its initial sync. The exit code was 137 — `SIGKILL` from the OOM killer:

```
Last State: Terminated
  Reason:    OOMKilled
  Exit Code: 137
```

The controller had a 1Gi memory limit, set when the cluster managed about 10 applications. It now manages ~40, including multi-source Helm applications with large manifests (Harbor, Authentik, kube-prometheus-stack). The reconciliation loop for 40 apps simply exceeded 1Gi.

The fix is in `helm-values/argocd-values.yaml`:

```yaml
controller:
  resources:
    requests: { cpu: 100m, memory: 512Mi }
    limits:   { cpu: 1000m, memory: 2Gi }   # was 1Gi
```

Applied immediately via `kubectl patch statefulset` without waiting for ArgoCD to self-sync (it couldn't, since the controller was the one crashing). After the patch, the controller came up clean: `1/1 Running 0`.

The lesson: ArgoCD controller memory scales with the number of applications and the complexity of their manifests. If you're adding many Helm apps, keep an eye on it. A `CrashLoopBackOff` on the application controller means nothing syncs — it's the most critical pod in the cluster after the API server.

## What's Deployed

```
Namespace:  reloader
App:        reloader (ArgoCD)
Chart:      stakater/reloader 2.2.14 (app v1.4.19)
Security:   runAsNonRoot, runAsUser 65534, seccompProfile RuntimeDefault,
            capabilities.drop ALL, no privilege escalation
Resources:  10m/32Mi request — 100m/128Mi limit
```

Deployments that now auto-reload on ConfigMap change:
- `homer` — dashboard layout
- `litellm` — AI Gateway model routing, prompt handler, financial guardrails
- `searxng` — search engine settings
- `backstage` — catalog locations, proxy endpoints, auth config

Any future deployment that mounts a ConfigMap gets the same behaviour with one annotation line. The pattern scales for free.

## One Gotcha: Chart Versioning

The Stakater Reloader chart version does **not** match the application version. When I first pinned `targetRevision: "1.4.3"` (matching the app version format), ArgoCD failed:

```
error fetching chart: failed to fetch chart: helm pull --version 1.4.3 --repo https://stakater.github.io/stakater-charts
```

The correct version to use is the chart version, found via:

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm search repo stakater/reloader
# NAME                  CHART VERSION   APP VERSION
# stakater/reloader     2.2.14          v1.4.19
```

Chart `2.2.14` = app `v1.4.19`. Always search before pinning.
