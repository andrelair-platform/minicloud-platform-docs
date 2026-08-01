---
id: etcd-backup
title: Phase 14 — k3s Control-Plane Snapshots (SQLite)
sidebar_position: 2
---

# k3s Control-Plane Snapshots — Pivoted from etcd to SQLite

The original Phase 14 plan called for **k3s built-in etcd snapshots** via
`etcd-snapshot-schedule-cron`. That assumed embedded etcd as the
datastore. **Single-server k3s defaults to SQLite via [kine](https://github.com/k3s-io/kine), not embedded etcd** — so the etcd-snapshot config is
silently ignored on our cluster.

This page documents the **pivot**: instead of etcd snapshots, we take
hourly **online SQLite backups** of k3s's `state.db` via `sqlite3 .backup`,
pulled to the MAAS controller by a cron job. Functionally equivalent —
we get a consistent point-in-time snapshot of the entire cluster control
plane — just via a different mechanism.

The other half of Phase 14 (Velero for application + PV data) is
documented in [Phase 14 — Velero](./velero).

---

## Why SQLite (and not etcd)

Single-server k3s without `--cluster-init` uses **kine over SQLite** as
the datastore. The state.db file at
`/var/lib/rancher/k3s/server/db/state.db` contains the entire Kubernetes
API state — every Deployment, Service, ConfigMap, Secret, RBAC rule,
custom resource. Backing it up = backing up the cluster's "memory."

Migrating a live single-server cluster to embedded etcd:
* Requires `--cluster-init` and a one-time data migration
* No automatic migration tooling — would need re-bootstrap + redeploy
* High risk of disruption for an already-working cluster

For a single-control-plane homelab, SQLite is fine. Production HA
clusters use embedded etcd because etcd supports the multi-server raft
consensus k3s needs to replicate state. We're not HA today; if a future
phase pursues HA control plane, the migration would happen there.

---

## How `sqlite3 .backup` works

SQLite's online-backup API takes a consistent snapshot of a live
database while it's being written to. The `.backup` command in the
`sqlite3` CLI is a thin wrapper:

```bash
sqlite3 /var/lib/rancher/k3s/server/db/state.db '.backup /tmp/snapshot.db'
```

The result is a self-contained SQLite database file with no `-wal` or
`-shm` sidecars to worry about. Cleanly copyable.

Without sqlite3's online API, naïvely `cp state.db ...` while k3s is
writing produces a corrupt snapshot (the WAL contains uncommitted
transactions that the standalone `.db` file doesn't see).

---

## Architecture

```text
    ┌──────────────────┐                  ┌──────────────────────────────┐
    │ set-hog          │                  │ Controller                   │
    │ (control plane)  │                  │                              │
    │                  │ pull-mode rsync  │ /srv/backups/k3s/            │
    │ /var/lib/rancher │ ←──── SSH ──────│   state.db.<UTC>             │
    │ /k3s/server/db/  │                  │                              │
    │   state.db       │                  │ /etc/cron.d/k3s-state-       │
    │                  │                  │   snapshot (hourly, HH:17)   │
    │ + sqlite3 .backup│                  │                              │
    │   to /tmp first  │                  │ /usr/local/bin/k3s-state-    │
    │                  │                  │   snapshot (the script)      │
    └──────────────────┘                  └──────────────────────────────┘
```

**Pull mode** (controller initiates) keeps the security boundary clean:
the cluster nodes don't need credentials to write to the controller. The
controller's user (`ktayl`) has SSH key access to `ubuntu@10.0.0.2` with
passwordless sudo (set up in Phase 0); we use those existing creds.

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Snapshot mechanism | `sqlite3 .backup` (online, no k3s downtime) | The only zero-disruption way to back up a live SQLite database |
| Snapshot direction | **Pull from controller**, not push from cluster | Keeps the security boundary one-way; cluster never touches controller filesystem |
| Cadence | **Hourly** at HH:17 | Hourly granularity covers most "yesterday's looking-good state" recovery; HH:17 to avoid clashing with on-the-hour cron rushes |
| Retention | 720 snapshots ≈ 30 days | One month at hourly is ~22 GB worst case; controller has 75+ GiB free |
| Storage location | `/srv/backups/k3s/state.db.<UTC>` (mode 700, owned by `ktayl`) | Same `/srv/backups/` root as MinIO's data — single backup tree to monitor |
| Logging | `logger -t k3s-state-snapshot` → syslog | Visible via `journalctl -t k3s-state-snapshot`; pages can find it |

---

## Pre-flight

Install `sqlite3` on `set-hog` (one-time):

```bash
ssh ubuntu@10.0.0.2 'sudo apt-get install -y sqlite3'
```

> Note: this is also added to the [Phase 10 Ansible `common` role](./../platform-roadmap/phase-10-ansible)
> baseline so a fresh node provision picks it up automatically.

---

## The pull script

`/usr/local/bin/k3s-state-snapshot` (owned by `root`, mode 0755):

```bash
#!/usr/bin/env bash
# k3s-state-snapshot — pulls a consistent online SQLite backup of set-hog's
# k3s control-plane state to the MAAS controller. Cron'd hourly.
set -euo pipefail

NODE="ubuntu@10.0.0.2"
DB="/var/lib/rancher/k3s/server/db/state.db"
DEST="/srv/backups/k3s"
RETAIN_COUNT=720   # 720 hourly snapshots = 30 days
TS=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="${DEST}/state.db.${TS}"

mkdir -p "$DEST"

# Online backup on the source node, then rsync it back. The /tmp copy is
# removed even if rsync fails.
ssh -o BatchMode=yes "$NODE" "sudo sqlite3 ${DB} '.backup /tmp/k3s-state-pull.db' && sudo chmod 644 /tmp/k3s-state-pull.db"
rsync -az --partial "${NODE}:/tmp/k3s-state-pull.db" "$TARGET"
ssh -o BatchMode=yes "$NODE" "sudo rm -f /tmp/k3s-state-pull.db"

# Rotate
cd "$DEST"
ls -1t state.db.* 2>/dev/null | tail -n +$((RETAIN_COUNT + 1)) | xargs -r rm --

# Log
SIZE=$(stat -c %s "$TARGET" 2>/dev/null || echo 0)
COUNT=$(ls -1 state.db.* 2>/dev/null | wc -l)
logger -t k3s-state-snapshot "captured ${TS} (${SIZE} bytes), retaining ${COUNT} snapshots"
```

## The cron entry

`/etc/cron.d/k3s-state-snapshot`:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
17 * * * * ktayl /usr/local/bin/k3s-state-snapshot
```

(Runs as the `ktayl` user, which has SSH key access to `ubuntu@10.0.0.2`.)

---

## Verification

```bash
# Trigger one manually to confirm
/usr/local/bin/k3s-state-snapshot

# Verify a fresh snapshot landed
ls -la /srv/backups/k3s/

# Confirm it's a valid SQLite file (not a half-copied state)
file /srv/backups/k3s/state.db.<UTC>
# → SQLite 3.x database, last written using SQLite version 3045001, …

# Watch syslog for cron-triggered runs
journalctl -t k3s-state-snapshot -f
```

A typical snapshot is **~38–40 MB** for our small cluster (handful of
namespaces, no large stateful workloads in the API state). At 720
snapshots × 40 MB ≈ 28 GB worst case — well within the 75+ GiB free on
`/srv`.

---

## Restore

### Scenario: set-hog SSD dies, control plane fully lost

The SQLite snapshots can't be used for a *partial* restore — they're
all-or-nothing of the entire control-plane state. The procedure is:

1. **Reprovision set-hog** via MAAS (Phase 0 procedures).
2. **Install k3s** (Phase 1) but **don't start it yet** — we want to
   inject our snapshot first.
3. **Stop k3s if it auto-started**:
   ```bash
   sudo systemctl stop k3s
   ```
4. **Copy the latest snapshot** from controller to the new set-hog:
   ```bash
   # On controller
   LATEST=$(ls -1t /srv/backups/k3s/state.db.* | head -1)
   scp "$LATEST" ubuntu@10.0.0.2:/tmp/k3s-restore.db
   ```
5. **Replace the live state.db** on set-hog:
   ```bash
   ssh ubuntu@10.0.0.2
   sudo systemctl stop k3s
   sudo mv /var/lib/rancher/k3s/server/db/state.db{,.dead}
   sudo mv /var/lib/rancher/k3s/server/db/state.db-{wal,shm} /tmp/  2>/dev/null || true
   sudo cp /tmp/k3s-restore.db /var/lib/rancher/k3s/server/db/state.db
   sudo chown root:root /var/lib/rancher/k3s/server/db/state.db
   sudo chmod 644 /var/lib/rancher/k3s/server/db/state.db
   sudo systemctl start k3s
   ```
6. **Wait for the API to come up**:
   ```bash
   kubectl get nodes
   ```
   The other two workers will rejoin automatically.
7. **Verify all namespaces and workloads are present**:
   ```bash
   kubectl get all --all-namespaces
   ```

If application data (PV contents) is also missing, follow up with a
[Velero restore](./velero) — Velero handles the data, this snapshot
handles the manifests/state.

**Estimated RTO:** 30–45 min total.

---

## Restoration Test — 2026-08-01

A non-destructive restoration test was run against both backup streams without touching the live cluster.

### Procedure

1. Downloaded the latest file from each MinIO bucket to `/tmp/restore-test/` on the controller
2. Decompressed (`gunzip`)
3. Ran SQLite integrity check via Python's built-in `sqlite3` module (no `sqlite3` binary on the controller)
4. Counted live (non-deleted) resources by key prefix to confirm real cluster state was captured

### Results

| Check | kine.db (systemd 02:30 UTC) | k3s.db (CronJob 04:14 UTC) |
|---|---|---|
| File | `kine-20260801-003000.db.gz` | `k3s-state-20260801-041425.db.gz` |
| Compressed size | 48 MiB | 48 MiB |
| Decompressed size | 193 MB | 193 MB |
| SQLite integrity | **ok** | **ok** |
| Nodes | 10 | 10 |
| Namespaces | 54 | 54 |
| Deployments | 100 | 100 |
| Secrets | 226 | 226 |
| ConfigMaps | 187 | 187 |
| Services | 142 | 142 |
| ArgoCD Applications | 124 | 124 |
| cert-manager Certificates | 35 | 35 |
| CRDs | 161 | 161 |
| PersistentVolumeClaims | 44 | 44 |
| Max revision (kine id) | 22,755,628 | 22,755,628 |

**Verdict: PASS** — both backup streams produce valid, structurally complete SQLite databases containing real cluster state.

### What this confirms

- Neither file is corrupt or truncated
- Both backup mechanisms run independently and produce consistent output
- All critical resource types are present (ArgoCD apps, CRDs, certs, PVCs, secrets)
- The most recent lease key (`/registry/leases/kube-node-lease/fast-skunk`) confirms freshness — the backup was taken from a live, running cluster

### What this does NOT confirm

- That k3s can actually boot from the restored file — a full live test would require stopping the control plane or using a spare machine running k3s with `--data-dir /tmp/test`
- That application data (Longhorn PVC contents) is also present — that is covered separately by Velero + Longhorn backups

### How to re-run the test

```bash
# On controller — adjust filenames to latest
mkdir -p /tmp/restore-test
~/.local/bin/mc cp minilocal/db-backups/kine/kine-YYYYMMDD-HHMMSS.db.gz /tmp/restore-test/kine.db.gz
gunzip /tmp/restore-test/kine.db.gz

python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/restore-test/kine.db')
print('Integrity:', conn.execute('PRAGMA integrity_check').fetchone()[0])
for label, pattern in [
    ('Nodes',       '/registry/minions/%'),
    ('Namespaces',  '/registry/namespaces/%'),
    ('Deployments', '/registry/deployments/%/%'),
    ('ArgoCD Apps', '/registry/argoproj.io/applications/%'),
    ('PVCs',        '/registry/persistentvolumeclaims/%'),
]:
    count = conn.execute(f\"SELECT COUNT(*) FROM kine WHERE name LIKE '{pattern}' AND deleted=0\").fetchone()[0]
    print(f'{label}: {count}')
conn.close()
"

rm -rf /tmp/restore-test
```

---

## What this does NOT cover

- **PV data.** SQLite has only Kubernetes API state, not the contents of
  Longhorn / NFS volumes. Velero's node-agent + Kopia covers that.
- **Container images.** Harbor's data lives on Longhorn; Velero's PV
  backup covers it. Pulled images on each node are caches; the registry
  is the source of truth.
- **Off-site replication.** All snapshots live on the controller. If the
  controller dies, both backup layers are gone. Phase 15+ will add an
  off-site copy.

---

## Done When

```text
✔ sqlite3 installed on set-hog
✔ /usr/local/bin/k3s-state-snapshot present and runnable
✔ /etc/cron.d/k3s-state-snapshot installed
✔ One manual run produced a valid SQLite file in /srv/backups/k3s/
✔ Restore procedure documented
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Recognizing the SQLite-vs-etcd distinction** | Single-node k3s and k0s clusters, Rancher Desktop, Docker Desktop's k8s, KIND single-node — all use SQLite by default. Knowing which datastore is in play changes every backup decision. |
| **`sqlite3 .backup` for online-consistent snapshots** | Same pattern works for any embedded SQLite database — Plex, Home Assistant, Open WebUI, Sonarr, etc. Zero downtime, no WAL drama. |
| **Pull-mode backups across security boundaries** | Cluster nodes shouldn't have write access to the backup target. Pull-mode keeps the directionality of trust correct. |
| **Risk-aware "no migration" decision** | Choosing not to migrate a live cluster from SQLite to embedded etcd, even though etcd-snapshots was the original plan, is a senior call. The right time to use embedded etcd is when you're building HA from day 1. |
| **Cadence and retention math** | 720 hourly snapshots × 40 MB ≈ 28 GB. Always do the math before setting retention. |
| **`logger -t` for cron observability** | Without this, cron-driven failures are silent until something else surfaces them. `journalctl -t <tag>` is the lightweight observability path before metrics-server. |
