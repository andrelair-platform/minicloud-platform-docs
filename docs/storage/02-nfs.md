---
id: nfs
title: Phase 5 — NFS
sidebar_position: 2
---

# NFS Server — Simple Shared Storage

NFS (Network File System) is a simpler alternative to Longhorn. One node acts as the NFS server and exports a directory — all pods on any node can mount it as shared storage. Less resilient than Longhorn (single point of failure) but much easier to set up.

---

## Architecture

```text
set-hog (NFS Server)
  └── /srv/nfs/data  → exported via NFS

fast-skunk (NFS Client)   fast-heron (NFS Client)
  └── mounts /srv/nfs/data    └── mounts /srv/nfs/data

All pods see the same files.
```

---

## Step 1 — Set Up NFS Server on set-hog

```bash
ssh ubuntu@10.0.0.2

sudo apt install -y nfs-kernel-server

sudo mkdir -p /srv/nfs/data
sudo chown nobody:nogroup /srv/nfs/data
sudo chmod 777 /srv/nfs/data
```

Add export:

```bash
echo '/srv/nfs/data 10.0.0.0/24(rw,sync,no_subtree_check,no_root_squash)' \
  | sudo tee -a /etc/exports

sudo exportfs -a
sudo systemctl enable --now nfs-server
```

Verify:

```bash
showmount -e 10.0.0.2
```

---

## Step 2 — Install NFS Client on Worker Nodes

```bash
# On fast-skunk and fast-heron
sudo apt install -y nfs-common
```

Test mount:

```bash
sudo mount -t nfs 10.0.0.2:/srv/nfs/data /mnt
ls /mnt
sudo umount /mnt
```

---

## Step 3 — NFS Provisioner in Kubernetes

Install the NFS subdir external provisioner so Kubernetes can create PVCs automatically:

```bash
helm repo add nfs-subdir-external-provisioner \
  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/

helm install nfs-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --set nfs.server=10.0.0.2 \
  --set nfs.path=/srv/nfs/data \
  --set storageClass.name=nfs \
  --set storageClass.defaultClass=false
```

---

## Step 4 — Create a PVC using NFS

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-data
spec:
  accessModes:
    - ReadWriteMany    # multiple pods can read+write simultaneously
  storageClassName: nfs
  resources:
    requests:
      storage: 20Gi
```

`ReadWriteMany` is the key advantage of NFS over Longhorn — multiple pods on different nodes can write to the same volume at the same time.

---

## NFS vs Longhorn

| | NFS | Longhorn |
|---|---|---|
| Setup complexity | Simple | Moderate |
| Resilience | Single node failure = data loss | Replicated across nodes |
| ReadWriteMany | Yes | No (RWO only) |
| Performance | Network-bound | Local disk speed |
| UI | None | Full web UI |
| Best for | Shared config, media, logs | Databases, stateful apps |

---

## Done When

```text
✔ NFS server running on set-hog
✔ nfs-provisioner pod Running in cluster
✔ PVC with storageClass: nfs binds successfully
✔ Data visible from multiple pods simultaneously
```
