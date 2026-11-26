---
id: backups-overview
title: Backups & recovery — where everything lives
sidebar_label: Backups & recovery (start here)
tags: [explanation]
---

# Backups & recovery — where everything lives

> **Explanation.** The one-screen answer to *"how is this backed up, and how do I get it back?"* Each row
> links to the detail. For targets (RTO/RPO) and the honest gaps, see the
> [DR matrix](/platform/backup-dr/dr-rto-rpo-matrix).

## Three storage layers (each answers a different failure)

| Layer | Where | Answers | Status |
|---|---|---|---|
| **Operational** | MinIO (controller, on the LAN) | fast local restore | ✅ live |
| **Disaster Recovery** (off-site) | Cloudflare R2 | physical loss of the controller / site | ✅ live |
| **Cyber Recovery** (immutable) | AWS S3 + Object Lock | deletion / corruption / ransomware | ❌ target |

*DR ≠ Cyber Recovery: R2 is off-site but its objects are **deletable** by anyone with the creds — see the
[DR matrix](/platform/backup-dr/dr-rto-rpo-matrix) for why the immutable layer matters.*

## What gets backed up, how, and where

| Data | Mechanism | Frequency | Lives on | Detail |
|---|---|---|---|---|
| Kubernetes objects + volumes | Velero | daily | MinIO → R2 | [Velero](/platform/backup-dr/velero) |
| Longhorn persistent volumes | Longhorn RecurringJob | daily | MinIO → R2 | [Longhorn backup](/platform/backup-dr/longhorn-backup) |
| k3s control plane (kine / SQLite) | `sqlite3` backup | hourly + daily | controller → MinIO → R2 | [kine / etcd backup](/platform/backup-dr/etcd-backup) |
| PostgreSQL (app-consistent) | `pg_dump` / CNPG PITR | daily / continuous | MinIO `db-backups/` → R2 | [Database backup](/platform/backup-dr/database-backup) |
| Vault secrets | raft snapshot | daily | MinIO `db-backups/vault` → R2 | [DR matrix](/platform/backup-dr/dr-rto-rpo-matrix) |

## Restore & objectives

- **How to recover** (scenario by scenario) → [DR Runbook](/platform/backup-dr/dr-runbook)
- **Targets (RTO/RPO) + honest gaps** → [DR matrix](/platform/backup-dr/dr-rto-rpo-matrix)
- **Retention & controller disk budget** → [Disk management](/platform/backup-dr/disk-management)

## Related

- [DR Runbook](/platform/backup-dr/dr-runbook) — recovery procedures
- [DR matrix (RTO/RPO + gaps)](/platform/backup-dr/dr-rto-rpo-matrix) — targets & honest posture
