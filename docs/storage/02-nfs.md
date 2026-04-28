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

---

## Result on this cluster

Installed and verified on 2026-04-28:

- **NFS server:** `nfs-kernel-server` running on `set-hog` (10.0.0.2), exporting `/srv/nfs/data` to `10.0.0.0/24`.
- **Helm chart:** `nfs-subdir-external-provisioner` installed in namespace `nfs-provisioner` (v4.0.18 chart).
- **StorageClass:** `nfs` (not default — Longhorn is default). Provisioner: `cluster.local/nfs-provisioner-nfs-subdir-external-provisioner`.

### RWX test passed

A 1 GiB `ReadWriteMany` PVC, mounted simultaneously by **2 busybox pods** placed on different nodes via `podAntiAffinity` (one on `fast-skunk`, one on `fast-heron`). Each pod appended a line every 5 seconds to the same `/shared/log.txt`:

```text
nfs-test-…-nbxmt at 2026-04-28T18:05:39+00:00   ← from fast-heron
nfs-test-…-pvfhf at 2026-04-28T18:05:55+00:00   ← from fast-skunk
nfs-test-…-nbxmt at 2026-04-28T18:05:44+00:00
nfs-test-…-pvfhf at 2026-04-28T18:06:00+00:00
nfs-test-…-nbxmt at 2026-04-28T18:05:49+00:00
```

Both pods saw each other's writes — that's the RWX guarantee Longhorn cannot provide.

### Helm setup (one-time, on the controller)

The doc above assumes `helm` is available, but it isn't installed on the MAAS controller by default. Install once into `~/.local/bin` (no sudo):

```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
  -o /tmp/get-helm-3.sh && chmod +x /tmp/get-helm-3.sh
HELM_INSTALL_DIR=$HOME/.local/bin USE_SUDO=false /tmp/get-helm-3.sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

This is a controller-side prerequisite for Phase 5 onwards (Harbor, cert-manager, Prometheus all use Helm).

### Default `archiveOnDelete: true`

When a PVC is deleted, the chart **renames** the underlying NFS subdirectory rather than deleting the data — you'll see entries like `archived-default-myapp-pvc-…` under `/srv/nfs/data` after a deletion. This is the safer default; for fully-automatic cleanup, install with `--set nfs.reclaimPolicy=Delete --set storageClass.archiveOnDelete=false`.
