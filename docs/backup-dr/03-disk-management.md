---
id: disk-management
title: Controller Disk Management
sidebar_position: 3
---

# Controller Disk Management

The MAAS controller (`/dev/nvme0n1p5`, 98 GB) hosts MinIO backup storage, k3s SQLite snapshots, Docker images, and system logs on a single partition. Without retention policies, this fills up and silently breaks Velero backups.

---

## Disk Budget

| Consumer | Size | Notes |
|---|---|---|
| MinIO backup data | ~40 GB | Velero daily backups, 7-day TTL |
| k3s SQLite snapshots | ~6.5 GB | 48 snapshots × 134 MB, 2-day retention |
| OS + Docker + k3s packages | ~15 GB | Fixed |
| **Headroom** | **~36 GB** | |

---

## k3s Snapshot Retention

k3s uses SQLite (kine) as its datastore. An hourly cron job at `/etc/cron.d/k3s-state-snapshot` pulls a live backup via `sqlite3 .backup` from `set-hog` and stores it at `/srv/backups/k3s/state.db.<UTC>`.

**Default `RETAIN_COUNT=720`** (30 days × 24 h) allows up to 720 × 134 MB = **96 GB** — which overflows the disk when combined with MinIO's 40 GB.

**Fix (one-time, requires sudo):**

```bash
sudo sed -i 's/RETAIN_COUNT=720/RETAIN_COUNT=48/' /usr/local/bin/k3s-state-snapshot
grep RETAIN_COUNT /usr/local/bin/k3s-state-snapshot
# RETAIN_COUNT=48   # 48 hourly snapshots = 2 days
```

The script self-rotates: once `RETAIN_COUNT=48` is set, no manual cleanup is ever needed.

**Check current snapshot count:**

```bash
ls /srv/backups/k3s/ | wc -l
ls /srv/backups/k3s/ | tail -3   # most recent
```

---

## MinIO Disk-Full Recovery

:::danger MinIO caches the disk-full state in memory
Freeing disk space alone does **not** unblock MinIO writes. MinIO marks a drive unhealthy when it hits the minimum free threshold (~1%) and does not re-evaluate until it restarts. Velero Kopia jobs keep failing with `PutBlob rejected: Storage backend has reached its minimum free drive threshold` even after 18 GB of space is freed.
:::

**Full recovery procedure (in order):**

```bash
# Step 1 — free disk space (non-sudo)
# Clean old k3s snapshots (emergency only — RETAIN_COUNT=48 handles this normally):
ls /srv/backups/k3s/ | sort | head -n -48 | xargs -I{} rm /srv/backups/k3s/{}

# Clean old Claude Code versions (keep only the latest):
ls /home/ktayl/.local/share/claude/versions/ | sort -V | head -n -1 \
  | xargs -I{} rm -rf /home/ktayl/.local/share/claude/versions/{}

# Clean Trash and Firefox snap cache:
rm -rf /home/ktayl/.local/share/Trash/files/* /home/ktayl/snap/firefox/common/.cache

# Step 2 — vacuum journal (requires interactive sudo):
sudo journalctl --vacuum-size=200M

# Step 3 — restart MinIO to clear cached threshold (critical):
docker restart minio && sleep 5 && docker ps --filter name=minio --format '{{.Status}}'

# Step 4 — clean up stale Velero Error pods (pre-restart failures):
kubectl get pods -n velero --no-headers \
  | grep 'kopia-maintain' | grep Error \
  | awk '{print $1}' \
  | xargs kubectl delete pod -n velero

# Step 5 — verify next kopia job succeeds:
kubectl get pods -n velero --no-headers | grep 'kopia-maintain' | grep -v Error | tail -5
# Should show Completed pods within ~10 minutes
```

---

## Quick Disk Triage

```bash
# Overall disk + top consumers:
df -h / && du -sh /srv/backups/k3s/ /srv/backups/minio/ \
  /home/ktayl/.local/share/claude/versions/* \
  /var/log/journal/ 2>/dev/null | sort -rh

# Check if MinIO is accepting writes (health API):
curl -sf http://localhost:9000/minio/health/live && echo "MinIO healthy"
```

---

## Journald Cap (Persistent)

Journald is capped at 500 MB, 14-day retention via `/etc/systemd/journald.conf.d/maxsize.conf`:

```ini
[Journal]
SystemMaxUse=500M
MaxRetentionSec=14day
```

This was applied once with sudo. It survives reboots. No ongoing action needed.

---

## Velero Daily Backup TTL

The `velero-daily-full` schedule keeps backups for 7 days (`168h0m0s`). Backups older than 7 days are auto-deleted by Velero's GC loop. If the disk fills up and MinIO rejects writes, Velero's deletion requests also fail (same `PutBlob` path) — this is another reason the MinIO restart must come before expecting GC to complete.

---

## Done When

```text
✔ df -h / shows ≥ 5 GB free (target: ~36 GB)
✔ ls /srv/backups/k3s/ | wc -l ≤ 48
✔ docker ps shows minio Up
✔ kubectl get pods -n velero | grep kopia-maintain shows Completed (not Error)
✔ velero backup-location get shows default Available
```
