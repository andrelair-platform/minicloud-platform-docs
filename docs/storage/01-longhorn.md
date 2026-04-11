---
id: longhorn
title: Phase 5 — Longhorn
sidebar_position: 1
---

# Longhorn — Distributed Block Storage

Longhorn gives your cluster persistent, replicated storage. Without it, any pod that writes data and gets rescheduled to a different node loses that data. Longhorn solves this by replicating volumes across all 3 nodes automatically.

---

## How It Works

```text
Pod on set-hog writes to /data
        │
        ▼
Longhorn Volume (replicated)
  ├── Replica on set-hog   (primary)
  ├── Replica on fast-skunk
  └── Replica on fast-heron

Node dies → Longhorn promotes another replica → pod resumes with same data
```

---

## Prerequisites

Install on all 3 nodes:

```bash
sudo apt install -y open-iscsi nfs-common
sudo systemctl enable --now iscsid
```

---

## Install Longhorn

```bash
kubectl apply -f https://raw.githubusercontent.com/longhorn/longhorn/v1.6.0/deploy/longhorn.yaml
```

Wait for all pods:

```bash
kubectl get pods -n longhorn-system --watch
```

---

## Access the Longhorn UI

```bash
kubectl port-forward svc/longhorn-frontend -n longhorn-system 9000:80
```

Open: `http://localhost:9000`

You'll see a visual map of your nodes, disks, and replicas.

---

## Set Longhorn as Default StorageClass

```bash
kubectl patch storageclass longhorn \
  -p '{"metadata": {"annotations": {"storageclass.kubernetes.io/is-default-class": "true"}}}'
```

Now any PersistentVolumeClaim without a storageClass specified uses Longhorn automatically.

---

## Create a Persistent Volume (example)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 10Gi
```

```bash
kubectl apply -f pvc.yaml
kubectl get pvc
```

---

## Snapshot & Backup

### Manual snapshot

In Longhorn UI → Volumes → select volume → Create Snapshot

### Scheduled backup to S3

In Longhorn UI → Settings → Backup Target:

```text
s3://your-bucket@region/
```

Set credentials:

```bash
kubectl create secret generic longhorn-backup-secret \
  -n longhorn-system \
  --from-literal=AWS_ACCESS_KEY_ID=xxx \
  --from-literal=AWS_SECRET_ACCESS_KEY=xxx \
  --from-literal=AWS_ENDPOINTS=https://s3.amazonaws.com
```

---

## Cluster Capacity for Storage

| Node | Disk | Available for Longhorn |
|---|---|---|
| set-hog | 512 GB | ~400 GB (after OS) |
| fast-skunk | 512 GB | ~400 GB |
| fast-heron | 512 GB | ~400 GB |
| **Total raw** | **1.5 TB** | **~1.2 TB** |
| **With 2 replicas** | | **~600 GB usable** |
| **With 3 replicas** | | **~400 GB usable** |

---

## Done When

```text
✔ All Longhorn pods Running
✔ 3 nodes visible in Longhorn UI with disks
✔ PVC created and bound
✔ Longhorn set as default StorageClass
```
