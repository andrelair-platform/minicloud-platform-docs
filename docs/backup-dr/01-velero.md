---
id: velero
title: Phase 14 — Velero (off-cluster backup)
sidebar_position: 1
---

# Velero — Cluster Backup & Disaster Recovery

Velero captures **Kubernetes objects** (Deployments, Services, ConfigMaps,
Secrets, RBAC, Ingresses) plus **persistent-volume data** (file-system level,
via the node-agent DaemonSet) into an S3-compatible bucket. Combined with
the hourly k3s SQLite snapshots on the same controller (see
[Phase 14 — Etcd / SQLite snapshots](./etcd-backup)), this is the platform's
full backup-and-DR layer.

The original plan called for a cluster-internal MinIO. We **deliberately
pivoted to running MinIO on the MAAS controller** — outside the cluster —
because backups stored inside the system being backed up are useless when
the system fails. This page documents the controller-side architecture in
full.

---

## Architecture

```text
    Cluster (3 nodes)                    Controller (separate machine)
    ┌────────────────┐                   ┌─────────────────────────────┐
    │ k3s control    │                   │ MinIO (Docker container)    │
    │ plane (set-hog)│                   │   binds 10.0.0.1:9000 (S3)  │
    │                │                   │         10.0.0.1:9001 (UI)  │
    │ Velero pod ────┼── S3 protocol ───▶│   bucket: velero            │
    │ + 3 node-agent │                   │   data:   /srv/backups/minio│
    │ pods (PV bkp)  │                   │   config: /srv/config/minio │
    │                │                   │                             │
    │                │                   │ systemd: minio.service      │
    │                │                   │   restarts on failure       │
    │                │                   │   bind-mounts data + config │
    └────────────────┘                   └─────────────────────────────┘
```

The cluster pods reach MinIO via the cluster subnet `10.0.0.0/24` — no
public exposure, no Ingress required. The controller is a separate
physical machine, so a complete cluster wipe leaves backups intact.

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Backup target location | **MinIO on the MAAS controller**, not in-cluster | Survives cluster failure (the canonical reason — backup storage living inside the thing it's backing up is circular) |
| MinIO install method | Docker + systemd, bind-mounted volumes | Standard "managed-on-host" pattern; survives image upgrades; doesn't consume cluster resources |
| Network binding | `10.0.0.1:9000` and `10.0.0.1:9001` only | Port 9000 already taken on `127.0.0.1` by another controller-local service (likely MAAS internal) |
| MinIO admin password | Generated to `~/.minio-admin` (mode 600), bind-mounted into the container as `/run/secrets/minio_admin` | Same out-of-band pattern as Harbor/Grafana/ArgoCD; password file never lives in git or in process args |
| Velero install | Helm chart `vmware-tanzu/velero` v12.0.1 (App v1.18.0) | Standard install path; configurable values; matches the rest of the platform |
| Velero plugin | `velero-plugin-for-aws:v1.13.0` | Talks to any S3-compatible (MinIO included) |
| Storage credentials | Out-of-band Secret `velero-credentials` in the `velero` namespace, created via `kubectl create secret generic` from a local credentials INI | Standard pattern; chart reads via `existingSecret`; rotated by re-creating the Secret |
| Volume backups | **`deployNodeAgent: true`** + `defaultVolumesToFsBackup: true` | Without this, only k8s objects are captured — no PV data, no actual app state. The node-agent uses Kopia to file-system-copy PV contents. |
| Snapshot location | Disabled (MinIO doesn't do CSI VolumeSnapshots) | Phase 15 will revisit if Longhorn CSI snapshots become useful; not needed for file-system-level backup |
| Schedule | Daily full-cluster at **03:00 UTC**, 7-day TTL | Daily granularity, weekly retention is the common baseline for non-critical homelab workloads |
| Excluded namespaces | `velero`, `kube-system`, `kube-public`, `kube-node-lease`, `backup-test` | velero excluded so it doesn't back up itself; kube-* excluded because k3s recreates them on bootstrap; backup-test is the per-restore-test scratch namespace |

---

## Pre-flight

- Controller has Docker (`docker --version` ≥ 24)
- Controller user is in the `docker` group (so `docker run` doesn't need sudo)
- 75+ GiB free at `/srv` on the controller
- Cluster is healthy (regression check passes)

---

## Install MinIO on the controller

### 1. Generate admin password (mode 600)

```bash
openssl rand -base64 24 > ~/.minio-admin
chmod 600 ~/.minio-admin
```

### 2. Create the host-side directories (one-time `sudo`)

```bash
sudo mkdir -p /srv/backups/minio /srv/config/minio
sudo chown -R "$USER:$USER" /srv/backups /srv/config
sudo chmod 700 /srv/backups/minio /srv/config/minio
```

### 3. systemd unit at `/etc/systemd/system/minio.service`

```ini
[Unit]
Description=MinIO S3-compatible object storage (Phase 14 backup target)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=simple
Restart=on-failure
RestartSec=10s

# Remove any leftover container before starting — only if it actually exists,
# so first-boot doesn't log a spurious "No such container" stderr line.
ExecStartPre=/bin/bash -c 'if /usr/bin/docker container inspect minio >/dev/null 2>&1; then /usr/bin/docker rm -f minio; fi'

# Bind to TWO specific IPs:
#   - 10.0.0.1       (cluster switch — for kubelet → MinIO pulls from cluster nodes)
#   - 100.88.123.8   (Tailscale interface — for browser access from any tailnet device)
# DO NOT bind to 0.0.0.0 — port 9000 is already taken on 127.0.0.1 by MAAS,
# and binding 0.0.0.0:9000 fails with EADDRINUSE.
ExecStart=/usr/bin/docker run \
    --name minio --rm \
    -p 10.0.0.1:9000:9000 \
    -p 100.88.123.8:9000:9000 \
    -p 10.0.0.1:9001:9001 \
    -p 100.88.123.8:9001:9001 \
    -e MINIO_ROOT_USER=admin \
    -e MINIO_ROOT_PASSWORD_FILE=/run/secrets/minio_admin \
    -v /srv/backups/minio:/data \
    -v /srv/config/minio:/root/.minio \
    -v /home/<user>/.minio-admin:/run/secrets/minio_admin:ro \
    quay.io/minio/minio:latest \
    server /data --console-address ":9001" --address ":9000"

ExecStop=/usr/bin/docker stop minio

[Install]
WantedBy=multi-user.target
```

### 4. Start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable minio.service
sudo systemctl start minio.service

# Verify (cluster-side bind)
curl -sf http://10.0.0.1:9000/minio/health/live -o /dev/null -w "S3 API (cluster):     %{http_code}\n"
curl -sf http://10.0.0.1:9001/                  -o /dev/null -w "Console (cluster):    %{http_code}\n"
# Verify (Tailscale-side bind — what makes the Mac access work)
curl -sf http://100.88.123.8:9000/minio/health/live -o /dev/null -w "S3 API (tailnet):     %{http_code}\n"
curl -sf http://100.88.123.8:9001/                  -o /dev/null -w "Console (tailnet):    %{http_code}\n"
# All four should return 200
```

### 4a. Accessing the MinIO console from outside the controller

From any Tailscale-connected device (Mac, phone, second laptop), browse to:

```text
http://100.88.123.8:9001
```

— login `admin` + the password from `~/.minio-admin` on the controller. Use **`http://`** (not `https://`); the console is served HTTP-only for simplicity, behind the Tailscale auth boundary.

The reason this works after the dual-IP bind: Tailscale advertises the controller as `100.88.123.8`, and when MinIO is bound to that interface specifically, packets arriving over the WireGuard tunnel hit the listening socket without needing Linux `rp_filter` to forgive asymmetric routing. A naive `0.0.0.0` bind is blocked by the `127.0.0.1:9000` collision; a bind to only `10.0.0.1` excludes the Tailscale path. Two explicit `-p` lines per port is the right shape.

#### Real install gotchas (discovered 2026-06-15)

| Symptom | Cause | Fix |
|---|---|---|
| `systemctl status minio.service` showed `Error response from daemon: No such container: minio` on every boot | The original cleanup hooks (`docker stop minio` / `docker rm minio`) always ran even on first-boot when no container existed | Replaced with a single `bash -c` conditional: `if docker container inspect minio; then docker rm -f minio; fi` |
| MAC browser couldn't reach `http://10.0.0.1:9001` even with Tailscale connected and subnet routes accepted | Linux's reverse-path filter dropped packets arriving on `tailscale0` destined for `10.0.0.1` (configured on a different interface) | Added explicit `-p 100.88.123.8:9001:9001` line — the Tailnet bind avoids the cross-interface routing entirely |
| First attempt at the dual-IP fix used `-p 9000:9000` (bind all interfaces) | Docker tried `0.0.0.0:9000` which collided with MAAS's `127.0.0.1:9000` → exit code 125 crashloop | Bind to specific addresses (`10.0.0.1` + `100.88.123.8`), never `0.0.0.0` |

### 5. Create the `velero` bucket via `mc`

```bash
# Install MinIO client (no root needed)
curl -sLO https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc && mv mc ~/.local/bin/

# Configure alias
mc alias set minilocal http://10.0.0.1:9000 admin "$(cat ~/.minio-admin)"

# Create bucket
mc mb minilocal/velero
```

---

## Install Velero in the cluster

### 1. Install the Velero CLI on the controller

```bash
curl -sLO https://github.com/vmware-tanzu/velero/releases/download/v1.18.0/velero-v1.18.0-linux-amd64.tar.gz
tar -xzf velero-v1.18.0-linux-amd64.tar.gz velero-v1.18.0-linux-amd64/velero
mv velero-v1.18.0-linux-amd64/velero ~/.local/bin/velero
chmod +x ~/.local/bin/velero
velero version --client-only
```

### 2. Create namespace + credentials secret (out of band)

```bash
kubectl create namespace velero

cat > /tmp/cloud-credentials <<EOF
[default]
aws_access_key_id=admin
aws_secret_access_key=$(cat ~/.minio-admin)
EOF
chmod 600 /tmp/cloud-credentials

kubectl create secret generic velero-credentials \
  -n velero --from-file=cloud=/tmp/cloud-credentials
rm /tmp/cloud-credentials
```

### 3. `velero-values.yaml`

```yaml
initContainers:
  - name: velero-plugin-for-aws
    image: velero/velero-plugin-for-aws:v1.13.0
    imagePullPolicy: IfNotPresent
    volumeMounts:
      - mountPath: /target
        name: plugins

configuration:
  backupStorageLocation:
    - name: default
      provider: aws
      bucket: velero
      default: true
      config:
        region: minio
        s3ForcePathStyle: "true"
        s3Url: http://10.0.0.1:9000
        publicUrl: http://10.0.0.1:9000

  volumeSnapshotLocation: []           # MinIO doesn't do CSI snapshots
  defaultBackupStorageLocation: default
  defaultVolumesToFsBackup: true

credentials:
  useSecret: true
  existingSecret: velero-credentials

deployNodeAgent: true                  # the DaemonSet that does file-system PV backup
nodeAgent:
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 1000m, memory: 1Gi }

resources:
  requests: { cpu: 100m, memory: 256Mi }
  limits:   { cpu: 1000m, memory: 1Gi }

schedules:
  daily-full:
    disabled: false
    schedule: "0 3 * * *"
    template:
      ttl: "168h"   # 7 days
      includedNamespaces: ["*"]
      excludedNamespaces:
        - velero
        - kube-system
        - kube-public
        - kube-node-lease
        - backup-test

metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    additionalLabels:
      release: kube-prometheus-stack
```

### 4. Helm install

```bash
helm repo add vmware-tanzu https://vmware-tanzu.github.io/helm-charts
helm repo update vmware-tanzu

helm install velero vmware-tanzu/velero \
  -n velero \
  -f velero-values.yaml \
  --wait --timeout 5m
```

### 5. Verify

```bash
$ kubectl get pods -n velero
NAME                      READY   STATUS    RESTARTS   AGE
node-agent-cl6xg          1/1     Running   0          51s
node-agent-dp6fx          1/1     Running   0          51s
node-agent-pvq2w          1/1     Running   0          51s
velero-597b886f5b-cnkqf   1/1     Running   0          51s

$ velero backup-location get
NAME      PROVIDER   BUCKET/PREFIX   PHASE       LAST VALIDATED   ACCESS MODE   DEFAULT
default   aws        velero          Available   …                ReadWrite     true

$ velero schedule get
NAME                STATUS    SCHEDULE    BACKUP TTL   LAST BACKUP
velero-daily-full   Enabled   0 3 * * *   168h0m0s     n/a
```

---

## End-to-end restore test

Create a throwaway namespace, back it up, destroy it, restore it, verify
the data is identical.

```bash
# 1. Create test workload
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Namespace
metadata: {name: backup-test}
---
apiVersion: v1
kind: ConfigMap
metadata: {name: tiny-config, namespace: backup-test}
data: {hello.txt: "Hello from before the backup!"}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: tiny-app, namespace: backup-test}
spec:
  replicas: 1
  selector: {matchLabels: {app: tiny-app}}
  template:
    metadata: {labels: {app: tiny-app}}
    spec:
      containers:
        - name: tiny
          image: ghcr.io/stefanprodan/podinfo:6.11.2
          ports: [{containerPort: 9898}]
EOF

# 2. Take a backup (synchronous)
velero backup create test-backup --include-namespaces backup-test --wait

# 3. Bundle on disk (15 KiB total, 9 objects — Velero metadata + the
#    tar.gz of all manifests)
mc ls -r minilocal/velero/backups/test-backup/

# 4. Destroy the namespace
kubectl delete namespace backup-test --wait

# 5. Restore
velero restore create test-restore --from-backup test-backup --wait

# 6. Verify
kubectl get all,configmap -n backup-test
kubectl get cm tiny-config -n backup-test -o jsonpath='{.data.hello\.txt}'
# → "Hello from before the backup!"

# 7. Cleanup
kubectl delete namespace backup-test
velero backup delete test-backup --confirm
```

The restore succeeds — same Pod name, same ConfigMap data — within ~5
seconds. Without PVs, this is a metadata-only round trip; for workloads
with PVs, the node-agent reconstructs file-system contents from the Kopia
restic-style backup.

---

## ArgoCD interaction warning

If the namespace being restored is managed by ArgoCD (e.g. our `homer`,
`whoami`, `platform-demo`), ArgoCD's `selfHeal: true` may interpret the
restored manifests as drift from the gitops repo and try to revert them
mid-restore. Always:

1. **Pause sync** on affected Applications first:
   ```bash
   kubectl patch app -n argocd <app-name> \
     --type merge \
     -p '{"spec":{"syncPolicy":{"automated":null}}}'
   ```
2. Run the restore.
3. Verify it landed.
4. Re-enable sync once verified:
   ```bash
   kubectl patch app -n argocd <app-name> \
     --type merge \
     -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
   ```

This is a real "two declarative systems on the same cluster" conflict,
documented in the Velero issue tracker. The restore-then-pause pattern is
standard practice in any GitOps + Velero shop.

---

## Disaster Recovery Runbook

### Scenario A: a single namespace is corrupted

```bash
# Pause ArgoCD if applicable
kubectl patch app -n argocd <name> --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'

# Find the latest backup
velero backup get | grep <namespace>

# Restore
velero restore create --from-backup <backup-name> --include-namespaces <namespace>

# Verify; re-enable ArgoCD
```

**RTO**: ~5 min for metadata-only namespaces, longer for workloads with PVs.

### Scenario B: full cluster wipe, set-hog SSD dies

1. Reprovision set-hog via MAAS (Phase 0 procedures).
2. Install k3s control plane (Phase 1).
3. Re-join `fast-skunk` and `fast-heron` (Phase 1).
4. Copy `/srv/backups/k3s/state.db.<latest>` from controller to set-hog only if rebuilding cluster from scratch isn't possible — see [Phase 14 — Etcd / SQLite snapshots](./etcd-backup) for the SQLite restore path.
5. Re-install Velero (`helm install velero vmware-tanzu/velero -n velero -f velero-values.yaml`) — same chart, same values, same MinIO endpoint.
6. `velero restore create --from-backup velero-daily-full-<latest>` — pulls all namespaces + PV data from the controller's MinIO.
7. Verify each namespace.

**RTO**: 45–60 min, dominated by MAAS reimage time.

### Scenario C: controller dies (MinIO + snapshots gone)

This is the **uncovered failure mode**. We have one off-cluster backup
target; if the controller's SSD dies we lose backups. Phase 15+ will add
an off-site copy (e.g., to Backblaze B2 or an external USB drive on a
weekly cron). For homelab portfolio purposes this is documented as a
known limitation, not a TODO.

---

## Done When

```text
✔ minio.service active on the controller, container has Up status
✔ http://10.0.0.1:9000/minio/health/live returns 200
✔ Velero pods (1 server + 3 node-agent) all Running in the cluster
✔ velero backup-location get shows default Available
✔ velero schedule get shows velero-daily-full Enabled
✔ One end-to-end test (backup → delete → restore) verified
✔ Bundle visible at /srv/backups/minio/velero/backups/<name>/
```

---

## Incident: PartiallyFailed backups — rate limiter fix (2026-08-01)

Daily backups were completing `PartiallyFailed` with 74 identical errors:
```
failed to list node-agent pods: client rate limiter Wait returned an error: context deadline exceeded
```

**Root cause:** `defaultVolumesToFsBackup: true` caused Velero to call `list node-agent pods` for every pod in the backup scope — 3030 items in this cluster. The default rate limiter (5 QPS / 10 burst) could not drain the queue before pod context deadlines expired.

**Fix in `helm-values/velero-values.yaml`:**
```yaml
configuration:
  # Opt-in FS backup only — annotate pods with backup.velero.io/backup-volumes
  # defaultVolumesToFsBackup: true caused 74 "context deadline exceeded" errors
  # per backup: every pod triggered a node-agent list, saturating 5 QPS default.
  defaultVolumesToFsBackup: false

  # Raised from defaults (5 QPS / 10 burst) for 3000+ item cluster
  clientQPS: 100
  clientBurst: 200
```

Only 3 volumes were actually completing kopia backups before the fix (ollama ×2, litellm-cache — all local-path, re-downloadable). Switching to opt-in lost nothing. Persistent-volume data for critical workloads is now covered by [Longhorn offsite backup to MinIO](./longhorn-backup).

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Decoupling backup storage from the source system** | The single most important rule of DR; same as "always store backups off-site" in traditional sysadmin |
| **MinIO as a self-hosted S3 substitute** | Standard pattern in air-gapped, on-prem, and homelab Kubernetes. Same shape as production teams running MinIO Operator on dedicated nodes. |
| **systemd + Docker for host services** | Canonical way to run a third-party container on a bare metal host (vs. running it as a k8s pod when k8s is the thing being backed up) |
| **Velero with file-system PV backup (Kopia)** | The default for any cluster without CSI VolumeSnapshot support — covers Longhorn, NFS, hostPath, etc. |
| **Out-of-band credential injection** | The `~/.minio-admin` → bind-mount into container → environment variable pattern. Same shape as Vault Agent injection. |
| **ArgoCD/Velero coexistence pattern** | Real production challenge — solved by pausing ArgoCD `selfHeal` during restore. Documented runbook is the actual deliverable. |
| **Honest failure-mode documentation** | The "controller dies → backups lost" gap is real. A portfolio that names the gap is more credible than one that pretends everything is recoverable. |
