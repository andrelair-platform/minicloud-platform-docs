---
id: minio
title: MinIO (Object Storage)
sidebar_position: 3
---

# MinIO — S3-Compatible Object Storage

MinIO runs on the **controller** (not inside the k3s cluster) as a Docker container managed by systemd. It provides S3-compatible object storage used by Velero for cluster backups and available as a general-purpose bucket store for workloads that need object storage.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│  Controller (ktayl-ThinkPad-X390)                       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  systemd: minio.service                          │   │
│  │  Docker: quay.io/minio/minio:latest              │   │
│  │                                                  │   │
│  │  S3 API  → 10.0.0.1:9000  (in-cluster)          │   │
│  │            100.88.123.8:9000  (Tailscale)        │   │
│  │  Console → 100.88.123.8:9001  (Tailscale)        │   │
│  │                                                  │   │
│  │  Data    → /srv/backups/minio/  (19 GiB)         │   │
│  │  Config  → /srv/config/minio/                    │   │
│  │  Secret  → /home/ktayl/.minio-admin (mode 600)   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │
         │ S3 API (http://10.0.0.1:9000)
         ▼
  k3s cluster — Velero BackupStorageLocation
  bucket: velero  │  region: minio  │  s3ForcePathStyle: true
```

Running on the controller rather than inside k3s is intentional: Velero needs its backup target to survive a complete cluster failure.

---

## Access

| Endpoint | URL | Use |
|---|---|---|
| S3 API (in-cluster) | `http://10.0.0.1:9000` | Velero, workloads inside k3s |
| S3 API (Tailscale) | `http://100.88.123.8:9000` | External tools, `mc` CLI from Mac |
| Console UI | `http://100.88.123.8:9001` | Browser admin — requires Tailscale |

Admin credentials are in `~/.minio-admin` on the controller (mode 600, never committed).

---

## Buckets

| Bucket | Created by | Contents |
|---|---|---|
| `velero` | Phase 14 | Velero cluster backups (Kopia snapshots) |

---

## Systemd Service

```bash
# Check status
systemctl status minio

# Restart (e.g. after config change)
sudo systemctl restart minio

# View logs
journalctl -u minio -f
```

The service is enabled at boot and runs `docker run --rm` — the container is recreated on each start, state lives in the volume mounts.

---

## mc CLI Quick Reference

```bash
# Add the controller as an alias (from Mac over Tailscale)
mc alias set minicloud http://100.88.123.8:9000 admin <password>

# List buckets
mc ls minicloud/

# List Velero backups
mc ls minicloud/velero/

# Check disk usage
mc du minicloud/velero/

# Download a specific backup
mc cp minicloud/velero/<backup-name>/ ./ --recursive
```

---

## Velero Integration

Velero was configured in Phase 14 to use this MinIO instance as its `BackupStorageLocation`:

```yaml
# BackupStorageLocation (default)
provider: aws   # S3-compatible
objectStorage:
  bucket: velero
config:
  s3Url: http://10.0.0.1:9000
  publicUrl: http://10.0.0.1:9000
  region: minio
  s3ForcePathStyle: "true"
```

```bash
# Check BSL is healthy
kubectl get backupstoragelocation -n velero
# Expected: phase = Available

# List all backups
kubectl get backups -n velero

# Trigger a manual backup
velero backup create manual-$(date +%Y%m%d) --wait
```

---

## Authentik SSO (Phase 23)

MinIO's console authenticates via Authentik OIDC. The Docker container is started with:

```
MINIO_IDENTITY_OPENID_CONFIG_URL=https://auth.10.0.0.200.nip.io/application/o/minio/.well-known/openid-configuration
MINIO_IDENTITY_OPENID_CLIENT_ID=3Zk8cVuqEprRJpzeFIaaSkIWLsdgDRpLd305VUnR
MINIO_IDENTITY_OPENID_DISPLAY_NAME=Authentik
MINIO_IDENTITY_OPENID_SCOPES=openid,profile,email,groups
MINIO_IDENTITY_OPENID_CLAIM_NAME=policy
MINIO_IDENTITY_OPENID_REDIRECT_URI=http://100.88.123.8:9001/oauth_callback
```

:::note OIDC startup race
MinIO fetches the OIDC discovery document at container start. If Authentik is not yet ready (e.g., right after a controller reboot), MinIO logs `Unable to initialize OpenID: status(404 Not Found)`. Restart MinIO after Authentik is fully up: `sudo systemctl restart minio`.
:::

---

## Health Check

```bash
# From Mac (Tailscale connected)
curl -s http://100.88.123.8:9000/minio/health/live && echo "MinIO API OK"

# From inside the cluster
kubectl run -it --rm minio-check --image=curlimages/curl --restart=Never -- \
  curl -s http://10.0.0.1:9000/minio/health/live && echo "MinIO API reachable from cluster"

# Check backup storage is Available
kubectl get backupstoragelocation -n velero
```
