---
id: cnpg-standard
title: CloudNativePG — the Postgres standard
sidebar_label: 🐘 CNPG standard
---

# CloudNativePG is the Postgres standard

:::note Verified, live
Summary + pointer page. The decision of record (with the full Langfuse migration runbook + the
remaining-debt list) is the ADR in the GitOps repo — this page is the discoverable map entry.
Snapshot: **2026-10-06**.
:::

PostgreSQL is the house relational engine, historically deployed **three inconsistent ways** (CNPG
operator · custom-base StatefulSet · plain/vendor StatefulSet — see the
[Data stores inventory](../insurance-platform/data-stores-inventory)). The standard is now explicit:

> **CloudNativePG (CNPG) is the standard for every Postgres we operate.** New databases are born as a
> CNPG `Cluster`; raw/vendor instances are migration candidates (need-first, not a big-bang sweep). Each
> cluster is a **dedicated instance per workload** (no cross-namespace shared DB), backs up to **R2 with
> PITR** (daily `ScheduledBackup` + WAL archiving), and ships a `PodMonitor` + stale-backup/unhealthy alerts.

## Why

- **PITR + automated backup** — CNPG archives WAL + base backups to R2; raw StatefulSets have none.
- **No shared-instance coupling** — a DB hosted inside another app's Postgres (across namespaces) drags
  a cross-ns dependency + noisy-neighbour + a shared SPOF. A dedicated cluster per workload removes all three.
- **Consistent operations** — one backup/restore/monitoring shape for every DB (restore drills, alerts).

## First migration — Langfuse (2026-10-06)

Langfuse's metadata DB (projects / API keys / managed prompts — the LLMOps auth anchor) was moved off the
shared `postgresql-ai` StatefulSet (ai ns, custom `-noavx512` base, no PITR) onto a dedicated
`langfuse-postgres` CNPG cluster in the `langfuse` namespace. Additive-first (cluster proven healthy +
R2 backup landing before touching Langfuse), then a `pg_dump`→restore at **exact parity** (71 tables;
70 prompts / 166 models / 3 api_keys), then a one-line `host:` cutover (same Vault password → drop-in).
New pod logged "412 migrations, **No pending migrations to apply**" — zero schema drift.

## Operate / verify

```bash
kubectl -n langfuse get cluster langfuse-postgres -o wide            # Cluster in healthy state
kubectl -n langfuse get scheduledbackup,backups.postgresql.cnpg.io  # daily schedule + R2 backups
```

## Full ADR

The decision, the step-by-step migration runbook (incl. the peer-auth / 18→17 restore gotchas), and the
remaining-debt list live in the GitOps ADR:
[**`docs/cnpg-standard.md`**](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/cnpg-standard.md).
Backup/restore operations: [Database backup](../backup-dr/database-backup).
