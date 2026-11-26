---
id: dr-rto-rpo-matrix
title: DR RTO/RPO Matrix
sidebar_position: 7
---

# Disaster Recovery — RTO/RPO Matrix (per critical datastore)

> **Purpose (audit P3 — Recoverability):** make recovery objectives *explicit and honest* per
> datastore, and surface which restores are **proven** (drill-tested) vs merely *assumed*. A backup
> you haven't restored is a hypothesis. DORA Art. 11–12 (business continuity) evidence.

## Storage layers — where each copy lives (3-layer model)

Three layers, each answering a **different** failure (not "more providers for their own sake"):

| Layer | Where | Answers | Status |
|---|---|---|---|
| **Operational** | **MinIO** (controller, LAN `10.0.0.1:9000`) | fast local restore; day-to-day object storage | ✅ live |
| **Disaster Recovery** (off-site) | **Cloudflare R2** | *physical loss* of the controller/site — rebuild the SI | ✅ live — `minicloud-backup-offsite` (kine/vault/db) · `minicloud-velero-offsite` · `minicloud-cnpg-offsite` · `minicloud-longhorn-offsite` |
| **Cyber Recovery** (immutable) | **AWS S3 + Object Lock** | *deletion / corruption / ransomware* — a backup an attacker-with-cluster-creds **cannot** erase | ❌ **not built** (target — crown jewels: Vault raft snapshot + kine + critical CNPG) |

> **DR ≠ Cyber Recovery.** R2 is off-site but its objects are **deletable** by anyone holding the creds —
> it survives a *dead controller*, **not** a *compromised operator / ransomware that wipes the backups*.
> That second failure needs **immutable** copies (Object Lock, independent provider) → the AWS S3 layer.

## The backup tiers (increasing app-consistency)

| Tier | Mechanism | Consistency | Schedule | Off-site (DR → R2) | Immutable (cyber → S3) |
|---|---|---|---|---|---|
| **Volume** | Velero daily-full (all PVCs) | crash-consistent | 03:00 UTC daily | ✅ `minicloud-velero-offsite` | ❌ (tool-GC'd — keep deletable) |
| **Logical** | `pg_dump`/dump → MinIO `db-logical/` + `db-backups/` | **app-consistent** | daily | ✅ mirror → `minicloud-backup-offsite` | ❌ → **target: S3 Object Lock** |
| **CNPG PITR** | barman WAL archive + streaming replica | **app-consistent, continuous** | continuous WAL | ✅ `minicloud-cnpg-offsite` | ❌ (barman-GC'd — keep deletable) |
| **Kine** | k3s SQLite `VACUUM INTO` + integrity-check | app-consistent | daily (+02:30 controller timer) | ✅ `minicloud-backup-offsite/db-backups/kine` | ❌ → **target: S3 Object Lock** |
| **Vault** | raft snapshot (`vault-snapshot`) | app-consistent | daily (02:30 controller timer) | ✅ `minicloud-backup-offsite/db-backups/vault` | ❌ → **target: S3 Object Lock** |

> **Immutable column — the rule (do not get this wrong):** Object Lock = WORM = the object **cannot be
> deleted** until retention expires. Apply it **only** to the **self-managed** copies (kine · Vault raft
> snapshot · logical dumps — *you* own their retention). **Never** on **tool-GC'd** prefixes
> (Velero/Longhorn/barman) — those tools **must** delete old backups to manage incremental chains, and
> Object Lock would break their GC → pile-up/errors.
>
> **Off-site freshness is NOT monitored (gap):** the MinIO→R2 mirror silently lagged **~3 days** during
> the 2026-11-23→26 outage (newest off-site copy = 2026-11-23). See gap #6.

**Only one restore is drill-proven:** `chat/synapse` via `app-restore-drill` (CronJob 02:45 UTC →
restores the latest dump into a throwaway Postgres and asserts table/row counts → `AppRestoreDrillStale`
alert if it stops passing). Everything else's RTO/RPO below is an **estimate from the backup type**,
not a measured restore — those are the gaps to close.

## The matrix

| Datastore | Role / criticality | Backup(s) | RPO | RTO (est.) | Restore-tested? |
|---|---|---|---|---|---|
| `authentik-cnpg` | **SSO — critical** | CNPG PITR + streaming replica + Velero | **~minutes** (WAL) | ~10–20 min (PITR / promote) | ⚠️ replica-rebuild proven 2026-09-27; full PITR **not drilled** |
| `chat/synapse` | Matrix chat | logical dump + Velero | ≤24 h | ~5–15 min | ✅ **drill-proven** (02:45 UTC) |
| `ktayl-prod/ktayl-postgres` | **insurance business — critical** | **Velero volume ONLY** | ≤24 h | ~15–30 min | ❌ + **no app-consistent dump** |
| `erp/erpnext-mariadb` | **HR/ERP — critical** | **Velero volume ONLY** | ≤24 h | ~15–30 min | ❌ + **no logical dump** |
| `retrieva/retrieva-postgres` | cert product | logical dump + Velero | ≤24 h | ~10 min | ❌ not drilled |
| `nextcloud-postgresql` | files/collab | logical dump + Velero | ≤24 h | ~10 min | ❌ |
| `backstage-postgresql` | dev portal | logical dump + Velero | ≤24 h | ~10 min | ❌ |
| `temporal-postgresql` | workflow engine | Velero volume | ≤24 h | ~15 min | ❌ |
| `ai/postgresql-ai` | AI apps | Velero volume | ≤24 h | ~15 min | ❌ |
| `vault` | **secrets — critical** | raft snapshot (`db-backups/vault`) + Velero | ≤24 h | ~10 min (+ KMS auto-unseal) | ❌ (unseal path proven; data restore not drilled) |
| `langfuse-clickhouse` | LLM traces | Velero volume | ≤24 h | ~20 min | ❌ (low priority — **recreatable**) |
| `ai/qdrant` | vector store | Velero volume | ≤24 h | re-ingest | n/a — **re-ingestable** |
| **kine** (control plane) | **cluster state — critical** | SQLite backup (integrity-checked) + offsite | ≤24 h | ~5–40 min | ✅ integrity-verified + rebuild runbook (DR Scenario G) |
| Redis (nextcloud/langfuse/plane) | caches | — (none) | n/a | recreate | n/a — **ephemeral** |

*RTO estimates assume the primary site is up and the restore target exists; a full site loss adds the
DR-node / rebuild time (see Scenario F/G in the [DR Runbook](./04-dr-runbook.md)).*

## Honest DR posture + the gaps to close (priority order)

**Maturity ≈ level 3–4** (automated backups + offsite + documented restore + **one** tested restore).
To reach level 5 (regularly-tested DR), the ordered gaps:

1. **`ktayl-prod` + `erpnext` have NO app-consistent backup** — only crash-consistent Velero volume.
   These are the **highest business criticality** yet the weakest coverage. **Action:** add daily
   `pg_dump` (ktayl) / `mysqldump` (erpnext) CronJobs → MinIO `db-logical/`, same pattern as synapse.
2. **Expand the `app-restore-drill` pattern** beyond synapse to the critical DBs — `ktayl-prod`,
   `erpnext`, `authentik-cnpg` (a CNPG PITR restore drill) — so their RTO/RPO become *measured*.
3. **Drill a full CNPG PITR restore** for `authentik-cnpg` (only the replica-rebuild path is proven).
4. **Vault data-restore drill** (the KMS auto-unseal path is proven; a raft-snapshot data restore is not).

## What IS solid today
- Every PVC is offsited (Velero → R2) and the **R2 BSL is `Available`** again (P0-2b).
- Synapse restore is **continuously proven** (drill + alert).
- Control-plane (kine) backups are **integrity-checked at write time** + have a rehearsable
  [rebuild runbook](./04-dr-runbook.md) (Scenario G).
- authentik-cnpg has **continuous WAL PITR + a streaming replica** (RPO minutes) — the best-protected DB.
