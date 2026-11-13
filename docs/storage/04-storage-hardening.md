---
id: storage-hardening
title: Storage resilience hardening
sidebar_label: 🛡️ Storage hardening
---

# Storage resilience hardening

:::note Map + pointer
Summary + pointer page. The storage-resilience ADR, the execution plan, the validation plan and the
runbooks live **with the GitOps config** in `minicloud-gitops/docs/storage-hardening/` — this page is
the discoverable map entry. Snapshot: **2026-11-13**.
:::

Longhorn on a 5-node laptop cluster is the platform's most failure-prone layer (node churn, flaky
links, stale mounts). The storage-hardening initiative is the decision + plan + evidence that make it
survivable: the resilience **ADR**, the phased **execution plan**, a **reliability-validation plan**, and
the **runbooks** used during incidents. Pairs with [Longhorn](./longhorn) (the capability) and the
[DR runbook](../backup-dr/dr-runbook).

## The documents of record (in GitOps)

| Document | What it holds | Source (click through) |
|---|---|---|
| **Overview** | the initiative map + how the pieces fit | [`docs/storage-hardening/README.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/README.md) |
| **ADR-0001 — storage resilience** | the decision of record (tiers, RF, data-locality, OCI DR anchor) | [`docs/storage-hardening/adr-0001-storage-resilience.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/adr-0001-storage-resilience.md) |
| **Phase-1 execution plan** | the staged rollout | [`docs/storage-hardening/phase1-execution-plan.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/phase1-execution-plan.md) |
| **Implementation backlog** | the work items | [`docs/storage-hardening/implementation-backlog.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/implementation-backlog.md) |
| **Reliability-validation plan** | how the hardening is proven | [`docs/storage-hardening/reliability-validation-plan.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/reliability-validation-plan.md) |
| **Evidence matrix** | control → evidence mapping | [`docs/storage-hardening/evidence-matrix.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/evidence-matrix.md) |
| **Runbooks** | the hands-on recovery procedures | [`docs/storage-hardening/runbooks.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/storage-hardening/runbooks.md) |

See also the storage-tiering standard [`docs/reliability-storage-tiering.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/reliability-storage-tiering.md) and the Longhorn upgrade record [`docs/reliability-longhorn-upgrade.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/reliability-longhorn-upgrade.md) (both auto-listed in the [Decision records index](/platform/engineering-standards/decision-records)).
