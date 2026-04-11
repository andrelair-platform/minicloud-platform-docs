---
id: velero
title: Phase 15 — Velero
sidebar_position: 1
---

# Velero — Cluster Backup & Disaster Recovery

Velero backs up your entire Kubernetes cluster — namespaces, deployments, services, configmaps, secrets, and persistent volume data — and can restore everything to a new cluster in minutes.

---

## What Velero Backs Up

```text
A namespace backup includes:
  ✔ All Kubernetes objects (Deployments, Services, ConfigMaps, Secrets...)
  ✔ Persistent Volume data (via snapshots or file copy)
  ✔ RBAC rules and ServiceAccounts

Restore creates:
  ✔ Identical namespace on any cluster
  ✔ Data restored to new PVs
```

---

## Storage Backend

Velero stores backups in an S3-compatible bucket. Options:

| Provider | Notes |
|---|---|
| AWS S3 | Standard |
| MinIO (self-hosted) | Run in your cluster — no cloud needed |
| Backblaze B2 | Cheap S3-compatible |
| GCS / Azure Blob | Also supported |

**Recommended for this cluster: MinIO** — keeps everything local and offline-capable.

---

## Step 1 — Deploy MinIO (local S3)

```bash
kubectl create namespace minio

kubectl apply -n minio -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  namespace: minio
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
        - name: minio
          image: minio/minio
          args: ["server", "/data", "--console-address", ":9001"]
          env:
            - name: MINIO_ROOT_USER
              value: minioadmin
            - name: MINIO_ROOT_PASSWORD
              value: minioadmin
          ports:
            - containerPort: 9000
            - containerPort: 9001
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: minio-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-pvc
  namespace: minio
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 100Gi
---
apiVersion: v1
kind: Service
metadata:
  name: minio
  namespace: minio
spec:
  type: LoadBalancer
  selector:
    app: minio
  ports:
    - name: api
      port: 9000
      targetPort: 9000
    - name: console
      port: 9001
      targetPort: 9001
EOF
```

Access MinIO console: `http://10.0.0.200:9001` (MetalLB IP)
Create a bucket named `velero-backups`.

---

## Step 2 — Install Velero CLI

```bash
curl -L https://github.com/vmware-tanzu/velero/releases/latest/download/velero-linux-amd64.tar.gz \
  | tar xz

sudo mv velero-*/velero /usr/local/bin/
velero version
```

---

## Step 3 — Install Velero in the Cluster

```bash
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.9.0 \
  --bucket velero-backups \
  --secret-file ./minio-credentials \
  --use-volume-snapshots=false \
  --backup-location-config \
    region=minio,s3ForcePathStyle=true,s3Url=http://minio.minio.svc:9000
```

`minio-credentials` file:

```ini
[default]
aws_access_key_id=minioadmin
aws_secret_access_key=minioadmin
```

---

## Backup Commands

### Manual backup of a namespace

```bash
velero backup create argocd-backup --include-namespaces argocd
velero backup describe argocd-backup
velero backup logs argocd-backup
```

### Schedule automatic nightly backup

```bash
velero schedule create nightly-full \
  --schedule="0 2 * * *" \
  --ttl 168h0m0s   # keep 7 days
```

### Backup everything

```bash
velero backup create full-cluster-backup
```

---

## Restore Commands

### Restore a namespace

```bash
velero restore create --from-backup argocd-backup
velero restore describe <restore-name>
```

### Restore to a different cluster

```bash
# On the new cluster — point velero to the same MinIO bucket
# Then:
velero restore create --from-backup full-cluster-backup
```

---

## Disaster Recovery Runbook

```text
Scenario: set-hog (control plane) dies and cannot be recovered

1. Provision new node via MAAS
2. Install k3s control plane
3. Join workers back
4. Install Velero pointing to MinIO backup bucket
5. velero restore create --from-backup <latest-backup>
6. Verify all namespaces restored
7. Total downtime: ~20–30 minutes
```

---

## Done When

```text
✔ MinIO running with persistent storage
✔ Velero installed and connected to MinIO
✔ Nightly backup schedule created
✔ Test restore verified in a staging namespace
```
