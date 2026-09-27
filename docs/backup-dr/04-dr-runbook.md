---
id: dr-runbook
title: Disaster Recovery Runbook
sidebar_position: 4
---

# Disaster Recovery Runbook

Gap 11 gap closure — 2026-07-01. Covers every failure scenario from a single-pod crash to a full cluster loss.

**RPO targets (after gap closure):**

| Data | Backup mechanism | Cadence | RPO |
|---|---|---|---|
| Cluster objects + PV data | Velero → MinIO | Daily 03:00 UTC | 24h |
| k3s control plane (SQLite) | k3s-state-snapshot → controller | Hourly | 1h |
| Backstage PostgreSQL | pg_dumpall → MinIO db-backups/ | Daily 02:00 UTC | 24h |
| Nextcloud PostgreSQL | pg_dump → MinIO db-backups/ | Daily 02:00 UTC | 24h |
| Authentik PostgreSQL | pg_dump → MinIO db-backups/ | Daily 02:00 UTC | 24h |
| Vault KV secrets | raft snapshot → MinIO db-backups/ | Daily 02:30 UTC | 24h |
| Git repos | GitHub (inherently distributed) | Real-time push | ~0 |

---

## Scenario A — Single Pod Crash

ArgoCD heals automatically via `selfHeal: true`. No action needed unless the pod is stuck:

```bash
# Force-delete a stuck pod (ArgoCD recreates it)
kubectl delete pod -n <namespace> <pod-name> --force --grace-period=0
```

## Scenario B — Node Failure

k3s reschedules pods automatically onto remaining nodes. For a **worker node** (fast-skunk or fast-heron):

```bash
# Check node status
kubectl get nodes

# If node stays NotReady > 5min, cordon and drain (force if PDB blocks)
kubectl cordon <node>
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data --disable-eviction

# Re-image via MAAS if hardware failure
# After re-provision, re-join with k3s agent installer:
# K3S_URL=https://10.0.0.2:6443 K3S_TOKEN=<token> sh -s - agent
```

For the **control-plane node** (set-hog): restore from k3s SQLite snapshot (Scenario E).

## Scenario C — Restore a Namespace from Velero Backup

Use this when a namespace is accidentally deleted or corrupted.

```bash
# List available backups
kubectl get backup.velero.io -n velero

# Restore specific namespace (update policy merges with live resources)
kubectl apply -f - <<EOF
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: restore-<namespace>-$(date +%Y%m%d)
  namespace: velero
spec:
  backupName: <backup-name>
  includedNamespaces:
    - <namespace>
  existingResourcePolicy: update
EOF

# Monitor progress
kubectl describe restore.velero.io -n velero restore-<namespace>-$(date +%Y%m%d)
kubectl get restore.velero.io -n velero restore-<namespace>-$(date +%Y%m%d) \
  -o jsonpath='{.status.phase}'
```

**Verified on 2026-07-01:** restored `podinfo` namespace from `velero-daily-full-20260628030044` → 25 items, Completed, pods remained healthy.

## Scenario D — Database Restore

All pg_dump files are in MinIO `db-backups/` with 30-day retention.

```bash
# List available database dumps
docker exec minio mc ls myminio/db-backups/backstage/
docker exec minio mc ls myminio/db-backups/nextcloud/
docker exec minio mc ls myminio/db-backups/authentik/

# Download a dump
docker exec minio mc cp myminio/db-backups/backstage/<filename>.sql.gz /tmp/
docker cp minio:/tmp/<filename>.sql.gz /tmp/restore.sql.gz

# Restore Backstage (drops and recreates all plugin databases)
gunzip -c /tmp/restore.sql.gz | kubectl exec -i -n backstage backstage-postgresql-0 -- \
  bash -c "PGPASSWORD='$(kubectl exec -n backstage backstage-postgresql-0 -- env | grep '^POSTGRES_PASSWORD=' | cut -d= -f2-)' psql -U postgres"

# Restart Backstage after restore
kubectl delete pod -n backstage -l app.kubernetes.io/name=backstage --force --grace-period=0

# Restore Nextcloud database
gunzip -c /tmp/restore.sql.gz | kubectl exec -i -n nextcloud nextcloud-postgresql-0 -- \
  bash -c "NC_PASS=\$(cat /opt/bitnami/postgresql/secrets/nextcloud-db-password); \
           PGPASSWORD=\$NC_PASS psql -U nextcloud -d nextcloud"

# Restore Authentik database
gunzip -c /tmp/restore.sql.gz | kubectl exec -i -n authentik authentik-postgresql-0 -- \
  bash -c "AUTH_PASS=\$(cat /opt/bitnami/postgresql/secrets/password); \
           PGPASSWORD=\$AUTH_PASS psql -U authentik -d authentik"
```

## Scenario E — Vault Data Loss / Restore from Snapshot

Vault stores all platform secrets. Auto-unseal runs via AWS KMS — Vault comes back unsealed automatically after pod restart. For data loss:

```bash
# List available Vault snapshots
docker exec minio mc ls myminio/db-backups/vault/

# Download snapshot
docker exec minio mc cp myminio/db-backups/vault/<filename>.snap /tmp/
docker cp minio:/tmp/<filename>.snap /tmp/vault-restore.snap

# Copy snapshot into vault pod
kubectl cp /tmp/vault-restore.snap vault/vault-0:/tmp/vault-restore.snap

# Restore (requires root token; Vault must be initialized and unsealed)
ROOT_TOKEN=$(cat ~/.vault-root-token)
kubectl exec -n vault vault-0 -- \
  sh -c "VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=${ROOT_TOKEN} \
         vault operator raft snapshot restore -force /tmp/vault-restore.snap"

# Verify secrets are present
kubectl exec -n vault vault-0 -- \
  sh -c "VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=${ROOT_TOKEN} \
         vault kv list secret/platform"
```

:::danger Root token and recovery keys
Root token: `~/.vault-root-token` (mode 600, controller only)
Recovery keys: `~/.vault-unseal-key-{1,2,3}` (mode 600, controller only — Shamir recovery keys now that KMS handles normal unseal)
These files are the last line of defense. Back up off-cluster on a USB drive for physical DR.
:::

## Scenario F — Full Cluster Rebuild from Scratch

For complete hardware loss or a fresh start. Estimated RTO: 4–6 hours.

**Prerequisites:** MAAS controller is running and reachable via Tailscale.

### Step 1 — Re-provision nodes via MAAS

```bash
# Re-commission and deploy all 3 nodes
# Use MAAS UI at http://100.88.123.8:5240/MAAS or OpenTofu
# Nodes must come back with same IPs: set-hog=10.0.0.2, fast-skunk=10.0.0.4, fast-heron=10.0.0.7
```

### Step 2 — Restore k3s control plane from SQLite snapshot

```bash
# On controller: find most recent snapshot
ls -lth /srv/backups/k3s/ | head -3

# Copy snapshot to set-hog
LATEST=$(ls /srv/backups/k3s/ | sort | tail -1)
scp /srv/backups/k3s/${LATEST} ubuntu@10.0.0.2:/tmp/k3s-restore.db

# On set-hog: restore (stop k3s first)
sudo systemctl stop k3s
sudo cp /var/lib/rancher/k3s/server/db/state.db /var/lib/rancher/k3s/server/db/state.db.bak
sudo cp /tmp/k3s-restore.db /var/lib/rancher/k3s/server/db/state.db
# CRITICAL: remove the stale WAL/SHM — else SQLite replays the old WAL OVER the
# restored DB and you get an inconsistent control plane. See Scenario G.
sudo rm -f /var/lib/rancher/k3s/server/db/state.db-wal /var/lib/rancher/k3s/server/db/state.db-shm
sudo systemctl start k3s

# Verify cluster is back
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

### Step 3 — Restore ArgoCD and wait for GitOps sync

```bash
# If ArgoCD itself needs restoration:
kubectl apply -f ~/minicloud-ktaylorganisation/minicloud-gitops/bootstrap/root-app.yaml

# ArgoCD will auto-sync all 25 applications from minicloud-gitops
# Monitor sync status
kubectl get applications -n argocd
```

### Step 4 — Restore persistent data from Velero

```bash
# Full cluster restore (after k3s is up, ArgoCD not yet deployed)
kubectl apply -f - <<EOF
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: full-restore-$(date +%Y%m%d)
  namespace: velero
spec:
  backupName: velero-daily-full-<LATEST-COMPLETED-BACKUP>
  excludedNamespaces:
    - kube-system
  existingResourcePolicy: update
EOF
```

### Step 5 — Unseal Vault (auto via KMS)

Vault unseals automatically via AWS KMS. If KMS is unreachable:

```bash
# Manual unseal with recovery keys (2-of-3 required)
cat ~/.vault-unseal-key-1 | kubectl exec -i -n vault vault-0 -- \
  sh -c "VAULT_ADDR=http://127.0.0.1:8200 vault operator unseal"
cat ~/.vault-unseal-key-2 | kubectl exec -i -n vault vault-0 -- \
  sh -c "VAULT_ADDR=http://127.0.0.1:8200 vault operator unseal"
```

### Step 6 — Restore databases if PV data is lost

Follow Scenario D for each database. Database dumps are in MinIO `db-backups/`, which survives cluster loss (MinIO runs on the controller, not in-cluster).

---

## Scenario G — Control-Plane (set-hog) Rebuild + Kine Restore

**The targeted single-node control-plane recovery** — use this, not Scenario F, when
**only `set-hog` is lost/corrupt** (the 5 workers are fine). `set-hog` is the sole k3s
server on an **embedded SQLite (kine)** datastore, so it is a single point of failure;
this is how you bring it back and have the workers rejoin **without re-provisioning them**.
Estimated RTO: **20–40 min** (Case A ~5 min).

:::danger The datastore alone is NOT enough — three things beyond `state.db` (rehearsal-proven 2026-09-27)
A live rehearsal (restore into a throwaway k3s) proved a from-scratch rebuild needs, besides the
kine `state.db`, the bootstrap pieces that are **not in the datastore and not regenerable**:
1. **The cluster `token`, BYTE-EXACT.** k3s encrypts the datastore bootstrap with it; the CA is
   derived from it. A one-byte difference — e.g. a **stripped trailing newline** (`$(cat token)` gives
   108 bytes, the file is 109) — fails with `fatal: bootstrap data already found and encrypted with
   different token`. Copy the *file*, don't shell-capture it.
2. **`cred/encryption-config.json`** (+ `encryption-state.json`) — the secrets-at-rest key. Without it
   restored secrets are unreadable: `identity transformer tried to read encrypted data`.
3. **Do NOT restore `tls/`.** k3s regenerates all certs from the datastore CA on start; restoring the
   old `tls/` trips `fatal: certs newer than datastore, could cause a cluster outage`.

**Gap closed:** the in-cluster backup now ships `k3s-bootstrap-<date>.tar.gz` (token +
encryption-config) next to `state.db` (gitops `01-k3s-sqlite-backup.yaml`), offsited to R2. Also keep
`/etc/rancher/k3s/config.yaml` handy (it's small + reproducible from `minicloud-ansible`).
:::

**Facts (verified 2026-09-26):** k3s **`v1.36.3+k3s1`** · datastore = embedded **SQLite**
(`/var/lib/rancher/k3s/server/db/state.db` + `-wal`/`-shm`) · config
`/etc/rancher/k3s/config.yaml` (Cilium: `flannel-backend: none`, `disable-kube-proxy`,
`disable: servicelb,traefik`). Note the `etcd-snapshot-*` lines in that config are **inert**
on a SQLite datastore (k3s only snapshots embedded *etcd*) — which is exactly why the custom
kine backups exist. **Verified restorable backups (all off-set-hog, survive its loss):**
- controller systemd timer → MinIO `db-backups/kine/kine-*.db.gz` (daily, self-integrity-checked; **not** age-encrypted — an in-place same-node restore, Case A)
- in-cluster CronJob → MinIO `k3s-backup/k3s-state-*.db.gz.age` (state) **+ `k3s-backup/k3s-bootstrap-*.tar.gz.age`
  (token + encryption-config — the bootstrap material Case B needs)**, both **age-encrypted** client-side (see Case B)

:::tip Rehearsal-proven (2026-09-27)
Restoring the latest backup into a throwaway k3s brought the control plane up serving the **real
cluster** — all **6 nodes Ready, 78 namespaces, 138 deployments** — from `state.db` + the byte-exact
`token` (tls regenerated from the datastore). Re-run this rehearsal after any change to the restore path.
:::

### Case A — kine DB corrupt, set-hog otherwise healthy (in-place restore, ~5 min)

```bash
# On the controller: pull the latest VERIFIED kine backup (integrity_check runs at backup time)
LATEST=$(~/.local/bin/mc ls minilocal/db-backups/kine/ | tail -1 | awk '{print $NF}')
~/.local/bin/mc cp minilocal/db-backups/kine/${LATEST} /tmp/${LATEST}
gunzip -f /tmp/${LATEST}                                   # → /tmp/kine-YYYYMMDD-HHMMSS.db
python3 -c "import sqlite3;print(sqlite3.connect('/tmp/${LATEST%.gz}').execute('PRAGMA integrity_check').fetchone())"  # expect ('ok',)
scp /tmp/${LATEST%.gz} ubuntu@10.0.0.2:/tmp/kine-restore.db

# On set-hog: stop, swap, REMOVE THE WAL/SHM, start
sudo systemctl stop k3s
sudo cp /var/lib/rancher/k3s/server/db/state.db /var/lib/rancher/k3s/server/db/state.db.bak.$(date +%s)
sudo cp /tmp/kine-restore.db /var/lib/rancher/k3s/server/db/state.db
sudo rm -f /var/lib/rancher/k3s/server/db/state.db-wal /var/lib/rancher/k3s/server/db/state.db-shm  # ← mandatory
sudo systemctl start k3s
```

### Case B — set-hog disk/OS died (full CP node rebuild, ~20–40 min)

**Rehearsal-proven procedure. The order matters: stage the datastore + token + encryption-config
BEFORE k3s ever starts, and do NOT restore `tls/` (k3s regenerates it from the datastore CA).**

:::info Backups are age-encrypted at rest (client-side, asymmetric)
Both objects in `minilocal/k3s-backup/` are `age`-encrypted: `k3s-state-*.db.gz.age` and
`k3s-bootstrap-*.tar.gz.age`. The backup job holds only the **public** recipient key, so a compromised
set-hog cannot decrypt its own offsite backups. Restore needs the **private identity**, which lives in
Vault `secret/platform/k3s-backup-age` **and** a Vaultwarden break-glass copy (so a control-plane
rebuild isn't blocked on Vault being down). Fetch it into `/tmp/age-id` on set-hog first (step 2b);
delete it when done. **Never print or commit the identity.**
:::

```bash
# 1. Re-image set-hog via MAAS (same IP 10.0.0.2). Install the SAME k3s version but DO NOT start it yet:
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.36.3+k3s1 INSTALL_K3S_SKIP_START=true sh -s - server
sudo systemctl stop k3s 2>/dev/null || true
sudo mkdir -p /etc/rancher/k3s /var/lib/rancher/k3s/server/db
#   restore /etc/rancher/k3s/config.yaml (from minicloud-ansible)

# 2. Fetch the latest state + bootstrap backups from MinIO (both survive set-hog's loss):
S=$(~/.local/bin/mc ls minilocal/k3s-backup/ | grep k3s-state-   | tail -1 | awk '{print $NF}')
B=$(~/.local/bin/mc ls minilocal/k3s-backup/ | grep k3s-bootstrap-| tail -1 | awk '{print $NF}')
~/.local/bin/mc cp minilocal/k3s-backup/$S /tmp/$S && ~/.local/bin/mc cp minilocal/k3s-backup/$B /tmp/$B
scp /tmp/$S /tmp/$B ubuntu@10.0.0.2:/tmp/

# 2b. ON set-hog: stage the age PRIVATE identity (from Vault; or Vaultwarden break-glass if Vault is down).
#     This is the ONLY key that can decrypt the backups — handle it out-of-band, never echo it.
VAULT_TOKEN=$(cat ~/.vault-root-token)   # or the break-glass copy
/usr/bin/curl -sk --cacert ~/minicloud-ca.crt -H "X-Vault-Token: $VAULT_TOKEN" \
  "https://vault.10.0.0.200.nip.io/v1/secret/data/platform/k3s-backup-age" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['data']['identity'])" > /tmp/age-id
chmod 600 /tmp/age-id
#   If Vault is down (worst case), paste the Vaultwarden break-glass identity into /tmp/age-id by hand.

# 3. ON set-hog: DECRYPT + stage the datastore + bootstrap material. NOTE what is and ISN'T restored.
#    The state object is gzip-INSIDE-age → decrypt, then gunzip; the bootstrap is tar.gz-INSIDE-age → decrypt, then tar.
age -d -i /tmp/age-id /tmp/$S | gunzip -c | sudo tee /var/lib/rancher/k3s/server/db/state.db >/dev/null
sudo rm -f /var/lib/rancher/k3s/server/db/state.db-wal /var/lib/rancher/k3s/server/db/state.db-shm
age -d -i /tmp/age-id /tmp/$B | sudo tar xz -C /var/lib/rancher/k3s/server  # → token + cred/encryption-config.json
#   ↑ the token restores BYTE-EXACT (the tar preserves it; never `echo`/`cat`-capture it).
#   ↑ NO tls/ is restored — k3s regenerates every cert from the datastore CA on start. If a stale
#     tls/ dir exists from the k3s install, remove it: sudo rm -rf /var/lib/rancher/k3s/server/tls

# 4. Start k3s. It decrypts the datastore bootstrap with the token, regenerates tls/, and comes up.
sudo systemctl start k3s
sudo k3s kubectl get nodes    # the 6 nodes appear; workers rejoin on their own (same derived node-token)
shred -u /tmp/age-id          # 5. destroy the private identity on set-hog once the cluster is up
```

:::warning Why NOT `tls/` (the counter-intuitive bit — rehearsal v3)
Restoring the old `tls/` fails with `fatal: certs newer than datastore, could cause a cluster outage`.
k3s owns cert generation from the datastore CA; hand-restoring certs fights it. Restore only
`state.db` + `token` + `encryption-config.json`; let k3s do the rest.
:::

### Verify (both cases)

```bash
kubectl --context minicloud get nodes                      # all 6 Ready within a few minutes
kubectl --context minicloud get pods -A | grep -vE 'Running|Completed'
ssh controller "minicloud-recovery-check"                  # full platform health sweep
```

:::note WAL-replay caveat (why the `rm -f *-wal *-shm` is mandatory)
The live WAL has been observed at ~200 MB (checkpoints don't truncate while kine holds a
reader). On an **unclean** set-hog loss, a large WAL means longer/edgier replay. Restoring a
**verified** snapshot and deleting the stale WAL/SHM sidesteps replay entirely — you start from
a known-good, checkpointed DB. Never restore `state.db` while leaving the old WAL in place.
:::

### Step 7 — Verify platform

```bash
# Run regression check suite
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://homer.10.0.0.200.nip.io | head -1
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://argocd.10.0.0.200.nip.io | head -1
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://grafana.10.0.0.200.nip.io | head -1
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://backstage.10.0.0.200.nip.io | head -1
kubectl get nodes && kubectl get pods -A | grep -v Running | grep -v Completed
```

---

## Operational: Verify Backup Health

Run these any time to confirm backups are working:

```bash
# Velero — last successful backup timestamp
kubectl get backup.velero.io -n velero --sort-by=.metadata.creationTimestamp | tail -5

# k3s SQLite — last snapshot
ls -lth /srv/backups/k3s/ | head -3

# Database dumps — last run
docker exec minio mc ls myminio/db-backups/backstage/ | tail -3
docker exec minio mc ls myminio/db-backups/nextcloud/ | tail -3
docker exec minio mc ls myminio/db-backups/authentik/ | tail -3

# Vault snapshots
docker exec minio mc ls myminio/db-backups/vault/ | tail -3

# Run database backup immediately
~/.local/bin/db-backup

# Run Vault snapshot immediately
~/.local/bin/vault-snapshot
```

## Operational: Velero Disk-Full Recovery

When MinIO rejects writes (`XMinioStorageFull`):

```bash
# 1. Free disk on controller
ssh controller "du -sh /srv/backups/k3s/ /srv/backups/minio/ && df -h /"

# 2. Restart MinIO to clear cached disk-full state (CRITICAL — must do even after freeing space)
docker restart minio && sleep 5 && docker ps --filter name=minio --format '{{.Status}}'

# 3. Manually trigger a Velero backup to confirm MinIO is accepting writes
kubectl apply -f - <<EOF
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: velero-manual-post-recovery-$(date +%Y%m%d)
  namespace: velero
spec:
  includedNamespaces: ['*']
  excludedNamespaces: [velero, kube-system]
  ttl: 168h
  defaultVolumesToFsBackup: true
EOF
kubectl get backup.velero.io -n velero velero-manual-post-recovery-$(date +%Y%m%d) \
  -o jsonpath='{.status.phase}'
```

---

## Backup Monitoring

PrometheusRule `backup-dr` in `monitoring` namespace fires on:
- `VeleroBackupFailed` — schedule produced a failed backup in last 26h (critical)
- `VeleroNoRecentBackup` — last success > 25h ago (critical)
- `VeleroBackupStorageLocationUnavailable` — BSL not Available (critical)
- `MinioDiskFull` — controller root FS < 10% free (critical)
