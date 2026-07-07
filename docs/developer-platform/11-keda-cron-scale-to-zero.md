---
id: keda-cron-scale-to-zero
title: KEDA Cron Scale-to-Zero for Dev Environments
sidebar_label: KEDA Cron Scale-to-Zero
---

# KEDA Cron Scale-to-Zero for Dev Environments

**Implemented:** 2026-07-07
**Applies to:** `platform-demo-dev`, `platform-demo-staging`

Dev and staging environments don't need to run overnight or on weekends.
A KEDA `ScaledObject` with a cron trigger automatically scales them to 0
replicas outside business hours and back up when the day starts — no manual
intervention, no wasted compute.

---

## How it works

KEDA creates a Kubernetes HPA that owns `spec.replicas` on the target
Deployment. The cron trigger defines an active window. Outside that window,
KEDA drives replicas to `minReplicaCount` (0). Inside the window, it drives
to `desiredReplicas`.

```
Mon–Fri 00:00            08:00                19:00          23:59
         │                 │                    │               │
replicas ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
         0                 1 (dev) / 2 (staging) 0

Sat–Sun: replicas = 0 all day
```

---

## ScaledObject spec

### Dev overlay (`overlays/dev/scaledobject.yaml`)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: platform-demo-cron-scaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: platform-demo
  minReplicaCount: 0
  maxReplicaCount: 1
  cooldownPeriod: 60
  triggers:
    - type: cron
      metadata:
        timezone: Europe/Paris
        start: "0 8 * * 1-5"
        end: "0 19 * * 1-5"
        desiredReplicas: "1"
```

### Staging overlay (`overlays/staging/scaledobject.yaml`)

Same spec, `maxReplicaCount: 2` and `desiredReplicas: "2"` — staging runs
two replicas for anti-affinity spread testing during the day.

---

## ArgoCD integration — the replicas conflict

When KEDA manages a Deployment, it sets `spec.replicas` to 0 at night via
the HPA it creates. ArgoCD compares the live cluster state against Git. The
Git manifest has `replicas: 1` (from `patch-resources.yaml`). Without
additional config, ArgoCD `selfHeal` would restore replicas to 1 every time
KEDA scales to 0 — the two would fight in a loop.

**Fix:** add `ignoreDifferences` for `spec.replicas` on the Deployment, and
`RespectIgnoreDifferences=true` in `syncOptions` so the ignored field also
affects the OutOfSync status calculation:

```yaml
# apps/platform-demo-dev.yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
  syncOptions:
    - ServerSideApply=true
    - RespectIgnoreDifferences=true
ignoreDifferences:
  - group: apps
    kind: Deployment
    name: platform-demo
    namespace: platform-demo-dev
    jqPathExpressions:
      - .spec.replicas
```

Without `RespectIgnoreDifferences=true`, ArgoCD ignores the field only
during sync but still reports OutOfSync in the UI — the app permanently
shows yellow. With the option, both the sync and the status calculation
skip the field.

---

## Kustomize wiring

Each overlay's `kustomization.yaml` includes the ScaledObject as a resource:

```yaml
resources:
  - ../../base
  - scaledobject.yaml
```

The ScaledObject lives in the overlay, not the base, because:
- It sets `minReplicaCount` / `maxReplicaCount` which are environment-specific
- Prod does not get a cron ScaledObject (always-on)
- Each overlay can define a different schedule or replica count

---

## Prod is excluded by design

The `overlays/prod/` directory has no `scaledobject.yaml`. Prod runs 3
replicas continuously. Cron scaling on prod creates the risk of a demo or
customer request arriving at 19:01 and hitting a deployment that is still
warming up. The cost saving does not justify the availability trade-off.

---

## Schedule reference

| Field | Value | Meaning |
|---|---|---|
| `timezone` | `Europe/Paris` | CET/CEST — adjusts automatically for DST |
| `start` | `0 8 * * 1-5` | Scale up at 08:00 Monday–Friday |
| `end` | `0 19 * * 1-5` | Scale down at 19:00 Monday–Friday |
| `minReplicaCount` | `0` | 0 replicas when no trigger is active |
| `cooldownPeriod` | `60` | Seconds KEDA waits before scaling down after trigger deactivates |

Nights (19:00–08:00) and full weekends → 0 replicas.
Approximately **70% of wall-clock hours** the dev/staging namespaces
consume zero compute.

---

## Extending to a new service

1. Create `overlays/dev/scaledobject.yaml` in your service directory,
   targeting your Deployment by name.
2. Add `- scaledobject.yaml` to `resources:` in the overlay `kustomization.yaml`.
3. Add `ignoreDifferences` for `spec.replicas` to the ArgoCD Application
   in `apps/<your-service>-dev.yaml`.
4. Repeat for `overlays/staging/` if staging should also scale to zero.

No changes to the base or prod overlay needed.

---

## Verification

```bash
# Check ScaledObject status
kubectl get scaledobject -n platform-demo-dev
kubectl get scaledobject -n platform-demo-staging

# ACTIVE=True  → inside business hours, running at desiredReplicas
# ACTIVE=False → outside window, scaled to 0

# Check the KEDA-managed HPA
kubectl get hpa -n platform-demo-dev

# Current replica count
kubectl get deployment platform-demo -n platform-demo-dev
```
