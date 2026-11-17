---
id: incident-2026-11-17-control-plane-saturation
title: "Incident postmortem — control-plane node OOM-wedge + capacity fix (2026-11-17)"
sidebar_label: "PM: control-plane saturation (2026-11)"
---

# Incident postmortem — control-plane node saturation + OOM-wedge

**Date:** 2026-11-17 · **Severity:** SEV-2 (cluster API down ~2 min, workers healthy, no data loss) · **Status:** Resolved

> The k3s control-plane node silently accreted **91 pods** because nothing kept it light, ran out of memory,
> and **wedged the apiserver**. It self-recovered via the kernel OOM-killer, but the incident exposed that
> these laptop nodes have **no out-of-band power control** — a hard-wedged node can't be remotely
> power-cycled. Fixed with scheduling (dedicate the control plane), capacity (bring a cordoned node back),
> and right-sizing the observability stores — no SaaS, no new hardware.

## TL;DR
- **set-hog** (the k3s control-plane node) hit **99% CPU / 89% mem / load 63**, OOM-thrashed, and the
  **apiserver (`:6443`) stopped responding** (`kubectl`/ArgoCD/Kargo all dead). ICMP still answered.
- **Root cause:** set-hog had **no control-plane taint** → k3s left it schedulable → it accumulated **91
  pods**. A cordoned node (swift-mac, 3 weeks) had removed a node of capacity, concentrating load.
- **Recovery:** the kernel **OOM-killer** evicted the thrashing process and the apiserver returned on its
  own (~2 min). It could **not** be power-cycled remotely (no BMC; MAAS power-off needs SSH, which was dead).
- **Fix (non-evicting):** taint set-hog `control-plane:NoSchedule` + uncordon swift-mac (compute-only) +
  right-size Prometheus/Loki/Tempo. Load fell **63 → 4**. Baked the taint into the k3s node config so it
  survives a rebuild.

## Impact
| Area | Impact |
|---|---|
| **Cluster API** | down ~2 min (apiserver wedged); no deploys/kubectl during the window |
| Worker nodes (×5) | **all healthy throughout** — running pods kept serving |
| ktayl-core RC-02 prod promotion | **paused** (correctly — would have added load to a 99%-CPU node) |
| yente-prod deploy | stalled until the API returned, then reconciled from git |
| nats-0 | rescheduled off the wedged node; stuck on a Longhorn mount timeout (nudged back; quorum held) |
| Data | **none lost** (k3s state is kine/SQLite, WAL-safe + backed up daily) |

## Timeline (UTC, 2026-11-17)
- **~08:00** — set-hog memory pressure builds (yente-prod's OpenSearch — a fresh JVM — the tipping contributor).
- **~09:00–09:25** — apiserver `:6443` unreachable; SSH to set-hog flaps then hard-times-out ("banner exchange"). ICMP still OK → OS-level starvation, not a network/whole-node failure.
- **09:27** — `kubectl get --raw /readyz` returns `ok`: the **OOM-killer** cleared the thrasher, apiserver back.
- **09:2x–09:3x** — diagnosis: set-hog load 63, 91 pods, no control-plane taint; swift-mac cordoned since 2026-10-24.
- **09:3x** — fix applied: taint set-hog + uncordon swift-mac. Load **63 → 46 → 13 → 4**; avail mem 482Mi → ~1.5Gi.
- **~10:0x** — right-sizing merged (Prometheus/Loki/Tempo); nats-0 nudged → NATS 3/3.

## Root cause (why it saturated)
1. **No control-plane taint.** k3s does not taint the server node by default, so set-hog was treated as a
   general worker and **accreted 91 pods** (it should stay light — the "keep the control plane light / no
   node-pin SPOF" scheduling rule). This is the real defect.
2. **A cordoned node removed capacity.** swift-mac had been cordoned ~3 weeks, so its would-be workloads
   piled onto the other five nodes, concentrating pressure on the already-untainted control plane.
3. **A fresh JVM tipped it.** yente-prod's OpenSearch (standing up the prod sanctions engine) added memory
   pressure that pushed the saturated node over into OOM-thrash. Contributor, not cause.

## The no-out-of-band-power lesson (important)
These are consumer **ThinkPads / a MacBook — no BMC/IPMI**. MAAS `power_type=webhook`, and the broker
**powers off via SSH** (power-on via Wake-on-LAN). So a node wedged badly enough to refuse an SSH shell
**cannot be power-cycled remotely** — the only levers are (a) the kernel OOM-killer self-recovering, or (b)
a physical power-button press. Design consequence: **keep the control plane light so it never wedges**,
because you can't reboot it remotely. (This one self-recovered via OOM-kill.)

## Fix (all non-evicting, no SaaS, no new hardware)
1. **Dedicate the control plane** — `kubectl taint nodes set-hog node-role.kubernetes.io/control-plane=:NoSchedule`.
   `NoSchedule` **repels new** non-tolerating pods (daemonsets tolerate + stay); it does **not** evict, so
   the existing pods drift off as they restart. Baked into the k3s node config (a `config.yaml.d/` drop-in,
   minicloud-ansible) so a rebuilt set-hog comes back dedicated.
2. **Add capacity** — `kubectl uncordon swift-mac` (healthy at rest: 1Gb NIC, idle, 6.2Gi free; Longhorn
   `allowScheduling=false` kept it **compute-only**, so no storage-replica storm).
3. **Right-size the stores** (the cluster-wide memory reclaim) — Prometheus `10d→7d` + **drop
   high-cardinality cAdvisor series** (`kubelet.serviceMonitor.cAdvisorMetricRelabelings`), Loki `30d→7d`,
   Tempo `14d→3d`. Keeps the golden-signal metrics dashboards use.

Result: set-hog **load 63 → 4**, available memory **482Mi → ~1.5Gi**; the cluster stabilized and the
paused prod promotion resumed safely.

## Why *not* "move observability to Grafana Cloud free"
Considered and rejected: discarding Grafana frees ~nothing (it's a ~200Mi frontend; the memory is in
Prometheus/Loki/Tempo). Moving the whole pipeline to Grafana Cloud free is blocked by its **10k-active-series
cap** (kube-prometheus-stack emits 50k–200k+) and breaks the self-hosted / EU-sovereign / offline thesis.
Grafana Cloud free only fits as a small **external SLO/uptime DR monitor** (curated &lt;10k series), additive —
not a replacement.

## Lessons / action items
- ✅ **Keep the control plane light — enforce it.** The taint is now in the node config (survives rebuild).
- ✅ **Right-size vendor-chart retention/cardinality early** — kube-prometheus-stack defaults are heavy for a lab.
- ✅ **A cordoned node is removed capacity** — don't leave one cordoned indefinitely; it concentrates load.
- 🔭 **No out-of-band power on laptop nodes** — accepted constraint; mitigate by never wedging the control plane.
- 🔭 **Spread, don't pin** — `topologySpreadConstraints` on heavy workloads so no single node (least of all the control plane) absorbs them.
