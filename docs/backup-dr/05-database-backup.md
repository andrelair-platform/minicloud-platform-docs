---
id: database-backup
title: Database Backup (pg_dump)
sidebar_position: 5
---

# Database Backup — Logical pg_dump

Gap 11 gap closure — 2026-07-01. Three PostgreSQL instances backed up daily via logical `pg_dump` to MinIO `db-backups/` bucket.

Velero captures PVC data at filesystem level (kopia blocks), which is crash-consistent but **not application-consistent** for a running PostgreSQL instance. This logical backup layer provides clean, importable SQL dumps.

---

## Architecture

```text
Controller (daily 02:00 UTC)
  db-backup script
    ├─ kubectl exec → backstage-postgresql-0 → pg_dumpall → gzip
    ├─ kubectl exec → nextcloud-postgresql-0 → pg_dump nextcloud → gzip
    ├─ kubectl exec → authentik-postgresql-0 → pg_dump authentik → gzip
    └─ docker exec minio mc cp → myminio/db-backups/
                                   ├── backstage/YYYYMMDDTHHMMSSZ.sql.gz
                                   ├── nextcloud/YYYYMMDDTHHMMSSZ.sql.gz
                                   └── authentik/YYYYMMDDTHHMMSSZ.sql.gz

MinIO lifecycle policy: 30-day expiry on db-backups/ bucket
```

---

## Database Coverage

| Instance | Namespace | Pod | User | Databases | Backup type |
|---|---|---|---|---|---|
| Backstage | `backstage` | `backstage-postgresql-0` | `postgres` (superuser) | 9 plugin DBs | `pg_dumpall` |
| Nextcloud | `nextcloud` | `nextcloud-postgresql-0` | `nextcloud` (app user) | `nextcloud` | `pg_dump` |
| Authentik | `authentik` | `authentik-postgresql-0` | `authentik` (app user) | `authentik` | `pg_dump` |

:::note Authentik postgres superuser
The Authentik chart disables TCP password auth for the `postgres` superuser (peer-only local socket). The `authentik` app user has sufficient grants to dump the `authentik` database.
:::

---

## Script

Located at `/home/ktayl/.local/bin/db-backup` on the controller.

Credentials are read at runtime from the pods' mounted secret files and Kubernetes secrets — no passwords hardcoded in the script. Password rotation is picked up automatically on the next run.

**Schedule** (ktayl user crontab):
```
0 2 * * * /home/ktayl/.local/bin/db-backup >> /home/ktayl/db-backup.log 2>&1
```

---

## Verify Backups

```bash
# Check recent dumps in MinIO
docker exec minio mc ls myminio/db-backups/backstage/ | tail -3
docker exec minio mc ls myminio/db-backups/nextcloud/ | tail -3
docker exec minio mc ls myminio/db-backups/authentik/ | tail -3

# View last run log
tail -20 ~/db-backup.log

# Run immediately
~/.local/bin/db-backup
```

**First verified run (2026-07-01):**
- Backstage: 4.5M dump (all 9 plugin databases) ✅
- Nextcloud: 4.0K dump (empty database, app just deployed) ✅
- Authentik: 7.8M dump (full identity provider state) ✅

---

## Restore a Database

See [Disaster Recovery Runbook — Scenario D](./dr-runbook#scenario-d--database-restore).

---

## Prometheus Alerts

`backup-dr` PrometheusRule in `monitoring` namespace includes:
- `VeleroNoRecentBackup` — last successful Velero backup > 25h ago
- `VeleroBackupFailed` — failed backup in last 26h
- `VeleroBackupStorageLocationUnavailable` — MinIO unreachable
- `MinioDiskFull` — controller disk < 10% free

These alert on Velero-level failures. Database backup failures log to `~/db-backup.log` and syslog (`logger -t db-backup`); check with `journalctl -t db-backup -n 20`.
