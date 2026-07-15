---
id: vpa-auto
title: Phase 74 — VPA Auto Mode
sidebar_label: Phase 74 — VPA Auto Mode
---

# Phase 74 — VPA Auto Mode

Phase 74 flips three VPA objects from `updateMode: "Off"` (recommendations only) to `updateMode: "Auto"` (VPA evicts and restarts pods to apply the recommended requests).

VPA was installed in Phase 70 (automation layer). After ~8 hours of live data, the recommendations were stable enough to enable Auto mode on stateless Deployments.

---

## Decisions per Workload

| Workload | Kind | New Mode | Reason |
|---|---|---|---|
| `backstage` | Deployment | **Auto** | Recommendation (15m/380Mi) ≈ current requests; safe stateless restart |
| `langfuse-web` | Deployment | **Auto** | Had 8 OOMKill restarts; VPA will upsize memory to recommendation (1312Mi) |
| `litellm` | Deployment | **Auto** | AI gateway; recommendation (100m/1312Mi) confirmed realistic |
| `langfuse-clickhouse` | StatefulSet | Off | RWO PVC — forced eviction causes Multi-Attach conflict |
| `prometheus` | Prometheus CRD | Off | CRD-managed StatefulSet; Prometheus operator manages pod lifecycle, VPA conflicts |

---

## VPA Recommendations at the Time of Switch (8h data)

```
backstage          15m CPU    380Mi RAM
langfuse-web      100m CPU   1312Mi RAM
litellm           100m CPU   1312Mi RAM
langfuse-clickhouse 1168m CPU  2539Mi RAM  (StatefulSet — kept Off)
prometheus           11m CPU     50Mi RAM  (capped by minAllowed: 200m/512Mi — kept Off)
```

The backstage VPA recommendation for CPU (15m) is below the minAllowed (100m), so VPA will apply 100m — same as the current Helm values. Effectively a no-op for CPU, with minor memory tuning.

---

## How Auto Mode Works

When `updateMode: "Auto"`:

1. VPA Admission Controller intercepts new pod creation and patches CPU/memory requests to match the recommendation.
2. For existing running pods whose requests deviate significantly from the recommendation, VPA evicts the pod. Kubernetes restarts it, and the Admission Controller applies the new requests on startup.

**Net effect:** pods gradually get right-sized without human intervention. No HPA conflicts since none of these services use HPA.

:::caution Expect brief evictions
Enabling Auto on a running Deployment triggers an immediate eviction of pods whose requests are far from the recommendation. Plan for a 10–30 second restart on each affected service. For `langfuse-web`, this is desirable — it was OOMKilling and will come back with adequate memory.
:::

## Gotcha — VPA Auto + short startup probes

When VPA Auto evicts a pod and it restarts, the Admission Controller applies the recommendation at pod creation. If the recommendation is very low (e.g. `15m CPU` for Backstage based on steady-state usage) and the service has a slow startup, a tight startup probe window causes a restart loop:

```
VPA evicts pod → new pod starts with 15m CPU → Node.js takes 90s to start
→ startup probe (failureThreshold:3, periodSeconds:10 = 30s window) expires
→ kubelet kills pod → loop repeats
```

**Fix applied for Backstage:**
1. `startupProbe.failureThreshold: 30` (10s × 30 = **5 min** window) — in `backstage-values.yaml`
2. `minAllowed.cpu: 200m` — VPA never assigns requests below what Node.js needs to start

The general rule: **set `minAllowed.cpu` to the CPU needed for startup, not for steady state.** The startup probe window should be at least 2× the observed worst-case startup time. After startup completes, VPA sees the real steady-state usage and adjusts on the next eviction cycle — automatically, without manual intervention.

---

## Configuration Change

```yaml
# manifests/vpa/00-vpa-objects.yaml — before:
updatePolicy:
  updateMode: "Off"

# after (backstage, langfuse-web, litellm):
updatePolicy:
  updateMode: "Auto"
```

Comments in the file document when Auto was enabled and the recommendation values at that time.

---

## Monitoring VPA Activity

```bash
# See current recommendations:
kubectl get vpa -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,CPU:.status.recommendation.containerRecommendations[0].target.cpu,MEM:.status.recommendation.containerRecommendations[0].target.memory

# See VPA events (evictions):
kubectl get events -A --field-selector reason=EvictedByVPA

# Via Grafana — kube-prometheus-stack includes VPA dashboards
```

---

## Upgrade Path — ClickHouse and Prometheus

### ClickHouse (langfuse)

ClickHouse runs as a StatefulSet with `ReadWriteOnce` Longhorn PVCs. VPA Auto would evict the pod, but the PVC can only attach to one node. If the evicted pod reschedules to a different node before the volume is released, it gets stuck in `Multi-Attach error`.

To safely enable Auto on ClickHouse:
1. Manually right-size the StatefulSet to match the VPA recommendation (1168m/2539Mi)
2. Keep VPA at Off for ongoing recommendations
3. Or: migrate ClickHouse to a ReadWriteMany storage class (requires Longhorn RWX support)

### Prometheus

The `kube-prometheus-stack` Prometheus operator owns the `kube-prometheus-stack-prometheus` StatefulSet and resets its resource requests on each reconcile loop. VPA Auto would fight the operator in a continuous loop. Keep VPA at Off for Prometheus and update resources via `helm upgrade` in `helm-values/kube-prometheus-stack-values.yaml`.
