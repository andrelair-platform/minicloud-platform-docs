---
slug: kubernetes-datastore-kine-sqlite-vs-etcd
title: "Your Kubernetes Cluster Doesn't Run etcd — Mine Doesn't Either"
authors: [andre]
description: >
  k3s replaces etcd with Kine/SQLite — one file on one machine. This post explains exactly
  what that means for backups, HA, and recovery on a bare-metal cluster, and contrasts it
  with how EKS, GKE, and AKS manage the same problem invisibly.
tags: [kubernetes, k3s, etcd, kine, sqlite, backup, platform-engineering, bare-metal, eks, gke, aks]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

Every Kubernetes tutorial mentions etcd. The architecture diagrams show a three-node etcd cluster with Raft consensus, leader election, and peer replication. If you run EKS, GKE, or AKS, that cluster exists somewhere — you just can never see it.

If you run k3s, you don't have etcd at all.

This post explains what k3s actually uses, what it means to manage backups and recovery yourself, and where that leaves you compared to a managed provider.

{/* truncate */}

## What etcd Actually Does (One Paragraph)

etcd is a distributed key-value store that Kubernetes uses as its single source of truth. Every object you create — pods, secrets, ConfigMaps, RBAC roles, everything — is written to etcd. When the API server restarts, it reads from etcd to rebuild its in-memory state. When a controller reconciles, it watches etcd for changes.

Lose etcd, and the cluster becomes a read-only snapshot: running pods keep running (kubelet is independent), but no new scheduling, no config changes, no secret rotation. Corrupt etcd without a backup, and the cluster state is gone.

This is why every architecture diagram shows three etcd nodes. Raft consensus requires an odd quorum: three nodes tolerate one failure, five nodes tolerate two. A single etcd node has no tolerance.

## What k3s Actually Uses

k3s replaces etcd with **Kine** — a shim that translates the etcd v3 gRPC API into SQL queries. k3s passes all its normal etcd calls to Kine, and Kine writes them into a **SQLite file**:

```
/var/lib/rancher/k3s/server/db/state.db
```

One file. On one machine. No replication, no consensus, no peer nodes.

On my cluster, that machine is `set-hog` — a ThinkPad X390 running the k3s control plane. The file is about 55 MB after months of running 20+ workloads across 5 nodes.

This is not a compromise or a limitation — it is a deliberate design choice for small clusters. SQLite is [the most widely deployed database engine in the world](https://www.sqlite.org/mostdeployed.html), its WAL mode handles concurrent reads without locking writes, and for a cluster under roughly 1,000 nodes it performs fine. k3s also supports swapping Kine's backend to PostgreSQL or MySQL if you need more throughput or multi-writer access.

The consequence is architectural simplicity: there is no etcd cluster to manage, no TLS peer certs, no quorum to maintain. There is one file to back up and one file to restore.

## The Two Backup Mechanisms

Because the state lives in one file, backup is straightforward — but I run two independent mechanisms because they have different failure modes.

### Mechanism 1 — Controller systemd timer (02:30 UTC)

Runs on the MAAS controller (`ktayl-ThinkPad-X390`), SSH-ing into `set-hog` to copy the file. Crucially, this runs **outside Kubernetes** — it has no dependency on the API server or on any pod being healthy.

```bash
#!/bin/bash
set -euo pipefail

TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)
BACKUP_KEY="kine/kine-${TIMESTAMP}.db.gz"
TMP_DB="/tmp/kine-backup-${TIMESTAMP}.db"

# .backup holds a read transaction for the duration of the copy — WAL-safe.
# It produces a binary snapshot consistent to a single point in time.
ssh ubuntu@10.0.0.2 \
  "sudo sqlite3 /var/lib/rancher/k3s/server/db/state.db \".backup ${TMP_DB}\" \
   && sudo cat ${TMP_DB} \
   ; sudo rm -f ${TMP_DB}" \
  | gzip -9 \
  | mc pipe "minilocal/db-backups/${BACKUP_KEY}"
```

30-day retention. Files named `kine-YYYYMMDD-HHMMSS.db.gz`. This is the backup you can restore from even if k3s itself is the problem.

### Mechanism 2 — Kubernetes CronJob (03:30 UTC)

Runs inside the cluster, one hour after the systemd timer. A pod mounts the SQLite file via hostPath on `set-hog` and writes a binary backup directly to MinIO:

```bash
sqlite3 /db/state.db ".backup /backup/state-$(date +%Y%m%d%H%M%S).db"
```

7-file retention in bucket `k3s-backup/`. **If the control plane is dead, this job cannot run** — which is exactly why the systemd timer exists.

### Why `.backup` and Not `.dump`

SQLite has two export methods: `.dump` produces SQL text (INSERT statements, CREATE TABLE, etc.), and `.backup` produces a binary copy.

The critical difference is consistency. `.dump` reads pages sequentially without holding a snapshot transaction — if k3s writes a new pod object mid-dump, the resulting SQL can describe an inconsistent state. `.backup` holds a single read transaction for the entire operation, so the output is always consistent to one point in time. This matters most under load, but the correct choice is `.backup` regardless.

Both mechanisms now use `.backup`. The compressed binary output is about 55 MB for this cluster.

### Health Check

```bash
ssh controller "systemctl status kine-backup.timer --no-pager && \
  ~/.local/bin/mc ls minilocal/db-backups/kine/ | tail -3 && \
  ~/.local/bin/mc ls minilocal/k3s-backup/ | tail -3"
```

Expected output shows both buckets with a file dated within the last 24 hours.

## HA: Intentionally Absent

A true HA k3s setup requires three server nodes with `--cluster-init` on the first and `--server` on the others. That switches the embedded datastore to real etcd (k3s bundles etcd for this mode) with Raft consensus across the three nodes. Lose one, the cluster keeps scheduling.

The minicloud cluster does not do this. `set-hog` is the single control plane. If it crashes:

- **Running pods keep running.** kubelet on each worker is a separate process; it keeps managing its local pods regardless of API server health.
- **No new scheduling.** No API server means no new pod creation, no ConfigMap updates, no Deployment rollouts.
- **Recovery time = reboot time.** `set-hog` reboots in roughly 90 seconds. k3s starts automatically. The cluster self-heals.

Adding two more control-plane nodes would cost two more machines, two more OS installs, and ongoing management of a Raft cluster — for a portfolio cluster that runs on ThinkPads. The trade-off is clear: single-node control plane, fast recovery, zero quorum complexity.

## Recovery: Disk Replaced or Corruption

This is the procedure when `set-hog` needs a new disk or `state.db` is corrupt:

```bash
# 1. Install fresh k3s on set-hog (same version)
ssh set-hog "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.36.2+k3s1 sh -"

# 2. Stop k3s before touching the database
ssh set-hog "sudo systemctl stop k3s"

# 3. Find the latest binary backup in MinIO
ssh controller "~/.local/bin/mc ls minilocal/db-backups/kine/ | tail -3"
# e.g. kine-20260728-030001.db.gz

# 4. Decompress and transfer to set-hog
ssh controller "~/.local/bin/mc cat minilocal/db-backups/kine/kine-20260728-030001.db.gz \
  | gunzip | ssh ubuntu@10.0.0.2 'sudo tee /var/lib/rancher/k3s/server/db/state.db > /dev/null'"

# 5. Fix ownership and restart
ssh set-hog "sudo chown root:root /var/lib/rancher/k3s/server/db/state.db \
  && sudo systemctl start k3s"

# 6. Verify
ssh controller "kubectl get nodes && kubectl get pods -A | grep -v Running | grep -v Completed"
```

**Data loss window:** up to 23 hours for objects created between the last backup and the crash. Application data lives in Longhorn PVCs (separate physical storage on worker nodes) — PVC data is not in this backup.

**Worker re-registration:** Workers re-register with the API server automatically after it comes back. No action needed.

## How Managed Providers Compare

| | minicloud (k3s/Kine) | EKS | GKE | AKS |
|---|---|---|---|---|
| **Datastore** | SQLite (1 file, 1 machine) | etcd, provider-managed, multi-AZ | etcd, Google-managed | etcd, Azure-managed |
| **HA** | No — single control plane node | Yes — etcd across 3 AZs, provider SLA | Yes — fully opaque, SLA-backed | Yes — fully managed |
| **RPO** | ~23h (nightly backup at 02:30 UTC) | Sub-minute (continuous replication) | Sub-minute | Sub-minute |
| **RTO** | 90s (set-hog reboot) + restore time | Provider restores automatically, usually invisible | Provider restores automatically | Provider restores automatically |
| **Backup format** | Binary SQLite (`.db.gz`) in your MinIO | etcd snapshot — you cannot access it | etcd snapshot — you cannot access it | etcd snapshot — you cannot access it |
| **Restore** | You do it, full procedure above | Not user-accessible | Not user-accessible | Not user-accessible |
| **What you own** | Backup schedule, format, retention, restore procedure | PDB design, workload drain tolerance | PDB design, workload drain tolerance | PDB design, workload drain tolerance |
| **Cost** | Electricity + MinIO storage on existing hardware | $0.10/hr control plane ($73/mo) + etcd storage fees | Free control plane on Standard; Autopilot has per-workload cost | Free control plane; pay for node VMs |
| **Observability** | `sqlite3 state.db ".dbinfo"`, systemd timer logs, MinIO bucket | CloudWatch, EKS upgrade insights | Cloud Logging, GKE upgrade notifications | Azure Monitor |

The managed HA story is straightforward: providers run etcd on infrastructure you never see, replicate it across availability zones, and take automatic snapshots before every upgrade. Sub-minute RPO, automatic recovery, zero operational overhead.

What they take away in exchange: you cannot access the backup, cannot run a point-in-time restore to an arbitrary timestamp, and cannot move the state to a different cloud. If the provider loses your etcd data (which has not happened at scale), your only recourse is their support process.

On bare-metal, the backup files are yours. They live in MinIO on your controller. You can restore them to any compatible k3s install without asking anyone. The operational cost is real — you designed the backup, you verified it runs, you wrote the restore procedure — but the control is yours.

## The Asymmetry That Is Easy to Forget

Managed providers back up etcd automatically. But they do it *for their own recovery purposes*, not yours. The snapshot they take before an upgrade is not something you can trigger, download, or restore from. If you accidentally delete 200 namespaces with `kubectl delete ns --all`, no managed provider will restore your cluster state to five minutes ago.

On minicloud, you can. The binary backup is a complete point-in-time copy of the cluster state. Restore it, restart k3s, and the deleted namespaces come back — minus anything created in the intervening hours.

This is not a reason to prefer bare-metal over managed Kubernetes in general. It is a reason to understand what "backup" means in each model before you assume it covers your scenarios.

## The Actual Costs

**Managed Kubernetes (EKS example):**
- Control plane: $0.10/hr = $73/month
- etcd storage: included
- Backup: included (but not user-accessible for point-in-time restore)
- Total for control plane + datastore: $73/month before any worker nodes

**minicloud:**
- Hardware: ThinkPads already owned
- MinIO: running on controller, storage on existing 98 GB NVMe
- Backup storage per file: ~55 MB compressed, 30-day retention = ~1.6 GB for 30 files
- Total incremental cost for control plane datastore: near zero

The comparison is not "SQLite is better than etcd." SQLite has no HA, no sub-minute RPO, and would be the wrong choice for a production cluster with hundreds of nodes and a team depending on it 24/7. The comparison is about understanding what each model costs and what it gives you — so that when you do use EKS or GKE, you know exactly which part of the problem they are solving and which parts remain yours.
