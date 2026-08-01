---
id: longhorn-backup
title: Phase 83 — Longhorn Offsite Backup (MinIO)
sidebar_position: 6
---

# Longhorn Offsite Backup to MinIO

**Deployed:** 2026-08-01 | **Longhorn:** v1.6 | **Target:** MinIO `longhorn` bucket on controller

Longhorn volumes hold the persistent state for all critical workloads. This page documents the offsite backup layer: daily snapshots + daily backup to the controller MinIO, covering 21 volumes across 12 namespaces.

---

## Architecture

```
Longhorn volumes (cluster)
        │
  RecurringJob: daily-snapshot (01:00 UTC, 7-day retention)
        │  local snapshot — fast rollback, no network I/O
        │
  RecurringJob: daily-backup (02:00 UTC, 14-day retention)
        │  kopia → S3 → MinIO on controller (10.0.0.1:9000)
        ▼
  minilocal/longhorn bucket
  ~/.local/bin/mc ls minilocal/longhorn
```

Credentials flow: Vault `platform/minio` → ESO ExternalSecret → `longhorn-backup-credentials` Secret → Longhorn backup target.

---

## GitOps layout

```
manifests/longhorn/
├── 00-backup-credentials.yaml  # ESO → longhorn-backup-credentials secret
├── 01-settings.yaml            # Longhorn Settings: backup-target + credential-secret
├── 02-recurring-jobs.yaml      # daily-snapshot + daily-backup RecurringJobs
├── 03-label-pvcs.yaml          # PostSync Job: labels volume CRs for backup group
└── 04-backup-check.yaml        # CronJob: fires Alertmanager alert if no backup in 26h
```

---

## Backup target configuration

```yaml
backup-target: s3://longhorn@us-east-1/
backup-target-credential-secret: longhorn-backup-credentials
```

The `longhorn-backup-credentials` secret must contain:
- `AWS_ACCESS_KEY_ID` — MinIO access key
- `AWS_SECRET_ACCESS_KEY` — MinIO secret key
- `AWS_ENDPOINTS` — `http://10.0.0.1:9000`

The region string (`us-east-1`) is arbitrary for MinIO — it just needs to be non-empty.

---

## Recurring jobs

| Job | Schedule | Task | Retention | Concurrency |
|-----|----------|------|-----------|-------------|
| `daily-snapshot` | `0 1 * * *` | snapshot (local) | 7 days | 5 |
| `daily-backup` | `0 2 * * *` | backup (MinIO) | 14 days | 2 |

Both jobs target volumes in the `backup` recurring-job group.

---

## Labeled volumes (21 total)

| Namespace | PVC / Volume | Service |
|-----------|-------------|---------|
| `authentik` | `data-authentik-postgresql-0` | Authentik PostgreSQL |
| `vault` | `data-vault-0` | HashiCorp Vault |
| `vaultwarden` | `vaultwarden-data` | Vaultwarden |
| `erp` | `data-erpnext-mariadb-sts-0`, `erpnext` | ERPNext MariaDB + site |
| `mail` | `data-stalwart-0` | Stalwart mail |
| `productivity` | `pvc-plane-ce-pgdb-*`, `pvc-plane-ce-minio-*` | Plane CE DB + files |
| `chat` | `matrix-synapse` | Matrix Synapse |
| `sign` | `docuseal-data` | DocuSeal |
| `ai` | `data-postgresql-ai-0`, `open-webui` | AI PostgreSQL + Open WebUI |
| `backstage` | `data-backstage-postgresql-0` | Backstage PostgreSQL |
| `harbor` | `database-data-harbor-database-0`, `harbor-registry` | Harbor DB + registry |
| `langfuse` | `data-langfuse-clickhouse-shard0-0` | Langfuse ClickHouse |
| `messaging` | `nats-js-nats-0/1/2` | NATS JetStream ×3 |
| `nextcloud` | `data-nextcloud-postgresql-0`, `nextcloud-nextcloud` | Nextcloud DB + files |

**Skipped (ephemeral/reconstructable):** Prometheus TSDB, Loki, Tempo, all Redis/Valkey caches, Harbor Trivy + jobservice, Alertmanager, Grafana (dashboards in gitops), ZooKeeper.

---

## Gotchas discovered during setup

### 1. `spec.name` required on RecurringJob

The Longhorn webhook validator requires `spec.name` in addition to `metadata.name`:
```yaml
spec:
  name: daily-backup   # REQUIRED — distinct from metadata.name
  cron: "0 2 * * *"
```

### 2. PVC labels don't propagate to existing volumes in Longhorn v1.6

The sync controller fires only on PVC creation/binding events. For already-attached volumes, label the Longhorn volume CR directly:
```bash
vol=$(kubectl get pvc $pvc -n $ns -o jsonpath='{.spec.volumeName}')
kubectl label volumes.longhorn.io $vol -n longhorn-system \
  recurring-job-group.longhorn.io/backup=enabled --overwrite
```

### 3. ArgoCD PostSync Jobs need `BeforeHookCreation` delete policy

`HookSucceeded` leaves failed jobs in place. ArgoCD SSA cannot update the immutable Job pod template, so a stale image persists on every subsequent sync. Use `BeforeHookCreation` to force deletion before recreation.

### 4. `bitnami/kubectl` and `registry.k8s.io/kubectl` not pullable from fast-heron

Use `docker.io/alpine:3.21` + `apk add curl` + direct Kubernetes REST API calls:
```bash
curl -sf --cacert "$CA" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/merge-patch+json" \
  -X PATCH -d '{"metadata":{"labels":{"recurring-job-group.longhorn.io/backup":"enabled"}}}' \
  "https://kubernetes.default.svc/apis/longhorn.io/v1beta2/namespaces/longhorn-system/volumes/$volname"
```

### 5. Stuck hook job with `argocd.argoproj.io/hook-finalizer`

```bash
kubectl patch job <name> -n longhorn-system \
  -p '{"metadata":{"finalizers":[]}}' --type=merge
kubectl delete job <name> -n longhorn-system --force --grace-period=0
```

---

## Health checks

```bash
# Recurring jobs are defined
kubectl get recurringjob -n longhorn-system

# 21 volumes are labeled
kubectl get volumes.longhorn.io -n longhorn-system \
  -l recurring-job-group.longhorn.io/backup=enabled --no-headers | wc -l

# BackupTarget is available
kubectl get backuptarget default -n longhorn-system \
  -o jsonpath='{.status.available}'

# Backup objects (after first run at 02:00 UTC)
kubectl get backups.longhorn.io -n longhorn-system | head -10

# MinIO objects
~/.local/bin/mc ls --recursive minilocal/longhorn | head -10
```

---

## Backup health alerting

Since Longhorn exposes no `longhorn_backup_*` Prometheus metrics, a CronJob (`longhorn-backup-check`, `30 3 * * *`) queries `backup.longhorn.io` CRs directly and POSTs a `LonghornNoRecentBackup` critical alert to Alertmanager if zero backups completed in the last 26 hours.

---

## Real-world skills demonstrated

| Skill | Industry context |
|-------|-----------------|
| **Offsite PV backup for stateful workloads** | Standard DR requirement — CSI-level backup complements Velero object backup |
| **Longhorn recurring jobs + groups** | Declarative backup scheduling via CRD — same pattern as Velero Schedules |
| **ESO-managed S3 credentials** | Credentials rotate in Vault, propagate to Longhorn automatically |
| **Custom monitoring for CRD-level state** | When the metrics exporter doesn't exist, build a CronJob probe — standard pattern for proprietary operators |
