---
id: migrations-on-boot
title: Database migrations — self-migrate on boot (decision + trigger)
sidebar_label: 🧱 Migrations on boot
---

# Database migrations: self-migrate on boot

:::note Decision of record lives with the code
Summary + pointer page. The full decision (context, the per-service table, the revisit trigger, and the
target `initContainer` pattern) is the ADR in the GitOps repo — this page is the discoverable map entry.
Snapshot: **2026-10-06**.
:::

Every custom DB-owning service (`ktayl-policy-service`, `ktayl-underwriting`, `ktayl-iam`,
`retrieva-backend`, `ktayl-core`) runs its schema migrations **as a side-effect of process startup** —
an explicit, documented platform standard, surfaced by a 12-factor review.

> **Decision (Accepted 2026-10-06): keep self-migrate-on-boot as the default for now.** It is pragmatic
> for a mostly 1–2-replica lab — the migration always matches the running image, no extra orchestration,
> and all four migrators take an advisory lock so concurrent-replica boots serialise safely.

**The 12-factor tension** is real (migrations are an admin/release process #12, and coupling them to boot
hurts disposability #9). The concrete cost we actually paid was an **in-process side-effect**, not a
race: alembic's `fileConfig()` disabled every logger after the startup migration (zero live logs) — see
the [testing strategy](../engineering-standards/testing-strategy) and the QA-gate write-up.

**Revisit trigger — switch when any of:** a service needs many replicas and boot-migration adds real
latency/contention · another in-process-side-effect bug of the alembic-logging class (underwriting is the
first candidate to move) · a long-running/destructive migration that should be gated separately from the
deploy.

**Target pattern when we switch:** a **same-image `initContainer`** running a `migrate` entrypoint (iam's
standalone `npm run db:migrate` is the reference shape) — keeps "migration matches the image + env",
removes migration from the app process, and avoids the ArgoCD PreSync-Job-wedge class.

**Decision of record (the ADR):**
[`minicloud-gitops/docs/migrations-on-boot.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/migrations-on-boot.md).
