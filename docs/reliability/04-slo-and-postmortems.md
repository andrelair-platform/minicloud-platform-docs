---
id: slo-and-postmortems
title: SLOs, error budgets & postmortems
sidebar_label: 📉 SLOs & postmortems
---

# SLOs, error budgets & postmortems

:::note Map + pointer
Summary + pointer page. The SLO register, the postmortem template, and the signed postmortems live
**with the GitOps config** in `minicloud-gitops/docs/reliability/` — this page is the discoverable map
entry. Snapshot: **2026-11-13**.
:::

"How do you *know* it's reliable?" is answered with **SLO → SLIs → error budget → alerts → incident
response → postmortem → chaos testing**, not *"I run Kubernetes."* A prod-grade service is not "done"
without an SLO contract, and every Game Day ends in a blameless postmortem + a KPI-scorecard update.
Complements the [Chaos Game Days](./chaos-mesh) and the [DR runbook](../backup-dr/dr-runbook).

## The documents of record (in GitOps)

| Document | What it holds | Source (click through) |
|---|---|---|
| **SLO register** | per-service SLIs/SLOs, error budgets, RTO/RPO, the standing failure-scenario catalog | [`docs/reliability/slo-register.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/reliability/slo-register.md) |
| **Postmortem template** | the blameless structure every incident/Game Day write-up follows | [`docs/reliability/postmortem-template.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/reliability/postmortem-template.md) |

## Signed postmortems

| Date | Incident | Source |
|---|---|---|
| 2026-10-17 | Chaos Game Day — CNPG primary-kill failover + NATS pod-kill (no data loss) | [`.../2026-10-17-chaos-gameday-db-nats.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/reliability/postmortems/2026-10-17-chaos-gameday-db-nats.md) |
| 2026-10-17 | CNPG DR restore — the WAL-gap "WAL ends before end of online backup" | [`.../2026-10-17-cnpg-dr-restore-wal-gap.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/reliability/postmortems/2026-10-17-cnpg-dr-restore-wal-gap.md) |

## Discipline

- **Modest, honest SLOs** — a met lab target beats a faked 99.99%.
- **Induce on dev first**; a prod Game Day is deliberate + announced.
- **An induced failure with no write-up is wasted evidence** — the postmortem is the deliverable.
