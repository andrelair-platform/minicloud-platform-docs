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
| **Cyber Recovery** (immutable) | **AWS S3 + Object Lock** | *deletion / corruption / ransomware* — a backup an attacker-with-cluster-creds **cannot** erase | ✅ **COMPLETE** 2026-11-26 (`minicloud-cyber-recovery-625830750465`, Object Lock **COMPLIANCE 35d** — undeletable even by root, ADR-0003). Daily `cyber-copy` cron (05:35) pushes **kine + the Vault raft snapshot** via **Vault-minted STS** (add-only, no static key). **Full restore drilled (RTO ≈15 s)**; **off-cluster break-glass recovery proven (RTO 37 s)** with a least-priv age-encrypted key alone (no cluster/Vault). |

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
> **Off-site freshness IS alerted in-cluster** (`MinioR2MirrorStale` on the `backup-offsite-mirror`
> CronJob, 26 h; + `OffsiteRestoreVerifyStale`). The ~3-day lag in the 2026-11-23→26 outage was the
> **whole cluster being off** (Prometheus down too) → an *external* heartbeat is the residual. See gap #6.

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
| `vault` | **secrets — critical** | raft snapshot (`db-backups/vault`) + Velero + **S3 cyber-vault (immutable)** | ≤24 h | **~15 s** (+ KMS auto-unseal) | ✅ **drill-proven 2026-11-26** (snapshot → throwaway Vault via KMS, witness read back; RTO ≈15 s) |
| `langfuse-clickhouse` | LLM traces | Velero volume | ≤24 h | ~20 min | ❌ (low priority — **recreatable**) |
| `ai/qdrant` | vector store | Velero volume | ≤24 h | re-ingest | n/a — **re-ingestable** |
| **kine** (control plane) | **cluster state — critical** | SQLite backup (integrity-checked) + offsite | ≤24 h | ~5–40 min | ✅ integrity-verified + rebuild runbook (DR Scenario G) |
| Redis (nextcloud/langfuse/plane) | caches | — (none) | n/a | recreate | n/a — **ephemeral** |

*RTO estimates assume the primary site is up and the restore target exists; a full site loss adds the
DR-node / rebuild time (see Scenario F/G in the [DR Runbook](./04-dr-runbook.md)).*

## Recovery objectives — targets (by criticality tier)

The matrix above is *today's estimate*; these are the **objectives** that should drive backup frequency,
retention and the immutable-copy scope (objectives first, mechanism second):

| Tier | Scope | RPO target | RTO target |
|---|---|---|---|
| **P0** | Vault · kine / K3s | ≤ 24 h | 30 min – 1 h |
| **P0** | IAM / Authentik | ≤ 15 min (WAL) | 1 h |
| **P1** | Ktayl business data | ≤ 15 min (WAL) | 2 h |
| **P1** | Platform services | ≤ 24 h | 4 h |
| **P2** | AI Platform | ≤ 24 h | 8 h |
| **P3** | Observability history | ≤ 48 h | 24 h |

*The "≤ 15 min" RPO is met **only** where CNPG WAL PITR is wired (authentik etc.); `ktayl-prod` /
`erpnext` are **volume-only** today → see gap #1. Targets are proposed, not yet validated by drill.*

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
5. **Immutable / cyber-recovery copy — ✅ LIVE** (2026-11-26). The **AWS S3 + Object Lock** vault
   (GOVERNANCE 35d, independent provider — ADR-0003, `minicloud-cloud` `s3-cyber-recovery*.tf`) now
   receives the crown jewels daily: the controller **`cyber-copy` cron (05:35)** mints **short-lived STS
   via the Vault AWS engine** (`aws/sts/cyber-recovery-write`, assumed-role, add-only — no static key) and
   copies **kine + the Vault raft snapshot** MinIO→S3 with timestamped, locked keys. Object Lock is on this
   self-managed vault **only**, never the tool-GC'd prefixes. Verified: object retention GOVERNANCE 35d,
   add-only (2nd run skips), restore read-path (GET) works. **Restore drill DONE** (2026-11-26): pulled the
   Vault snapshot from the S3 vault → restored into a throwaway Vault (same image 2.0.2 + same KMS seal) →
   the **prod root token read a witness value back intact** → **RTO ≈ 15 s warm (53 s incl. image pull)**,
   well under the ≤30 min P0 target. Script committed `minicloud-ops/scripts/backup/cyber-copy.sh`.
   **✅ COMPLETE 2026-11-26:** (b) flipped to **COMPLIANCE** (undeletable even by root); (c) the
   **off-cluster break-glass recovery is proven** — a least-priv `cyber-recovery-break-glass` IAM identity
   (S3-read + Vault-seal KMS ops), key **age-encrypted off-cluster** (`~/.cyber-recovery-reader.age`),
   restored Vault **end-to-end with the key alone, no cluster/Vault** (RTO 37 s). **Recovery kit** (keep
   OFF-cluster — offline copy + Vaultwarden break-glass): the break-glass key `.age` + the Vault root-token
   `.age` + the age identity + this runbook. COMPLIANCE is a one-way door (bucket can't be `tofu destroy`ed
   until retention expires — by design).
6. **No EXTERNAL (off-cluster) monitoring for a full-site outage** — in-cluster freshness **is** already
   alerted (`MinioR2MirrorStale` on the `backup-offsite-mirror` CronJob @26 h, `OffsiteRestoreVerifyStale`,
   `K3sSQLiteBackupStale`, `CNPGBackupStale` — all in `00-prometheusrule.yaml`). But those alerts live
   **inside** the cluster: when the whole platform is powered off (the 2026-11-23→26 outage), Prometheus +
   Alertmanager are down too, so the ~3-day off-site lag passed **silently** until power-on. **Action:** an
   **off-cluster heartbeat** (the `cloud-adoption.md` always-free AWS Lambda *Anchor 1*) that watches
   backup freshness / cluster liveness and pages when the platform itself is dark — the one thing in-cluster
   monitoring structurally cannot do.
7. **Full-site rebuild ("from zero") not drilled end-to-end** — Scenario F/G are documented, but the
   RTO/RPO of a complete reconstruction (bootstrap → infra → control-plane → Vault unseal → platform →
   data → IS) is **not measured**. The **break-glass kit** (Shamir recovery keys + R2/S3 reader creds +
   age identity) must be proven reachable **off-cluster** — Vault auto-unseals via **AWS KMS**, so a
   "lost AWS" scenario needs the offline recovery keys, and Vaultwarden (on-cluster) can't be the only home.

## What IS solid today
- Every PVC is offsited (Velero → R2) and the **R2 BSL is `Available`** again (P0-2b).
- **Crown jewels ARE off-site** — kine + the Vault raft snapshot mirror to R2
  `minicloud-backup-offsite/db-backups/` (verified 2026-11-26), **not** MinIO-only. *(What's still
  missing is immutability + external-outage monitoring, not the off-site copy itself — gaps #5/#6.)*
- **Off-site is monitored AND restore-verified in-cluster** — the `backup-offsite-mirror` CronJob
  (04:30 UTC, MinIO→R2) is alerted by `MinioR2MirrorStale`, and `offsite-restore-verify` +
  `OffsiteRestoreVerifyStale` prove the R2 copy actually restores (not just exists). The one blind spot is
  a *full-cluster* outage (in-cluster monitoring is down with it) → gap #6.
- Synapse restore is **continuously proven** (drill + alert).
- Control-plane (kine) backups are **integrity-checked at write time** + have a rehearsable
  [rebuild runbook](./04-dr-runbook.md) (Scenario G).
- authentik-cnpg has **continuous WAL PITR + a streaming replica** (RPO minutes) — the best-protected DB.
