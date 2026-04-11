---
id: etcd-backup
title: Phase 15 — Etcd Backup
sidebar_position: 2
---

# Etcd Backup & Node Recovery

Etcd is the database of your Kubernetes control plane — it stores the entire cluster state (all deployments, services, secrets, configmaps). If `set-hog` (your control plane) dies and etcd data is lost, the cluster is gone.

This page covers automated etcd snapshots and the full recovery procedure.

---

## k3s Etcd Snapshot

k3s has built-in etcd snapshot support — no extra tools needed.

---

## Manual Snapshot

```bash
ssh ubuntu@10.0.0.2

sudo k3s etcd-snapshot save \
  --name manual-$(date +%Y%m%d-%H%M%S)
```

Snapshots are saved to:

```text
/var/lib/rancher/k3s/server/db/snapshots/
```

---

## Automatic Scheduled Snapshots

Enable in k3s config:

```bash
sudo nano /etc/rancher/k3s/config.yaml
```

```yaml
etcd-snapshot-schedule-cron: "0 */6 * * *"   # every 6 hours
etcd-snapshot-retention: 10                    # keep last 10 snapshots
etcd-snapshot-dir: /var/lib/rancher/k3s/server/db/snapshots
```

Restart k3s:

```bash
sudo systemctl restart k3s
```

Verify snapshots are being created:

```bash
sudo k3s etcd-snapshot list
```

---

## Copy Snapshots Off-Node

Snapshots on the node itself don't help if the node dies. Copy them to a safe location:

```bash
# From your local machine via Tailscale
rsync -avz ubuntu@10.0.0.2:/var/lib/rancher/k3s/server/db/snapshots/ \
  ~/k3s-snapshots/

# Or to MinIO (if Velero/MinIO is set up)
mc alias set minio http://10.0.0.200:9000 minioadmin minioadmin
mc mirror /var/lib/rancher/k3s/server/db/snapshots/ minio/etcd-snapshots/
```

---

## Restore Procedure

### Scenario: set-hog is dead, new node provisioned

**1. Provision new control plane node via MAAS**

Assign IP `10.0.0.2` (or update workers with new IP).

**2. Copy snapshot to new node**

```bash
scp ~/k3s-snapshots/latest.db ubuntu@10.0.0.2:/tmp/
```

**3. Restore from snapshot**

```bash
ssh ubuntu@10.0.0.2

sudo k3s server \
  --cluster-reset \
  --cluster-reset-restore-path=/tmp/latest.db
```

**4. Start k3s normally**

```bash
sudo systemctl start k3s
sudo kubectl get nodes
```

Workers will reconnect automatically (they keep trying).

**5. Verify**

```bash
sudo kubectl get all --all-namespaces
```

All namespaces, deployments, and services should be restored.

---

## Snapshot Schedule Recommendation

| Frequency | Snapshot | Retention |
|---|---|---|
| Every 6 hours | On-node | 10 snapshots (2.5 days) |
| Daily | Copied to MinIO | 30 days |
| Weekly | Copied to external drive / S3 | 12 weeks |

---

## Recovery Time Objectives

| Scenario | Recovery Steps | Estimated Time |
|---|---|---|
| Control plane crash (data intact) | Restart k3s | 2–5 min |
| Control plane disk failure (snapshot available) | New node + restore | 15–25 min |
| Full cluster wipe | MAAS reprovision + k3s + restore | 45–60 min |

---

## Done When

```text
✔ Automatic snapshots running every 6 hours
✔ Snapshots copied to MinIO daily
✔ Test restore verified on a staging node
✔ Recovery runbook documented and tested
```
