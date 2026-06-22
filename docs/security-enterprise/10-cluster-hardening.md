---
id: cluster-hardening
title: Phase 63 — Cluster Hardening
sidebar_position: 10
---

# Phase 63 — Cluster Hardening

Implemented 2026-06-22. Hardened the k3s cluster against a structured 8-criteria checklist covering node access, API server exposure, audit logging, secrets at rest, and runtime versions.

---

## Assessment Before Hardening

| Criterion | Pre-hardening | Gap |
|---|---|---|
| Disable anonymous access | ⚠️ Partial | `--anonymous-auth` not explicitly false |
| Protect API server | ⚠️ Partial | RBAC + OIDC OK; no audit logs |
| Restrict SSH to nodes | ❌ Fail | Password auth on; no UFW on nodes |
| Keep k3s updated | ⚠️ Partial | v1.34.6 running vs v1.36.1 latest |
| Audit logs | ❌ Fail | Nothing configured |
| Encrypt secrets at rest | ❌ Fail | No encryption-provider-config |
| Private networking | ✅ Pass | Nodes on 10.0.0.x, jump host only |
| Firewall the API server | ⚠️ Partial | UFW inactive on nodes |

**Score: 1 pass / 4 partial / 3 fail → 7/8 passing after hardening.**

---

## 1. SSH Hardening — All 3 Cluster Nodes

All nodes had default Ubuntu `sshd_config` (all lines commented out, so `PasswordAuthentication yes` applied by default).

**Fix — drop-in config file on each node:**

```bash
for node in set-hog fast-skunk fast-heron; do
  ssh $node "sudo tee /etc/ssh/sshd_config.d/99-hardening.conf > /dev/null << 'CONF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
CONF
sudo sshd -t && sudo systemctl restart ssh && echo '$node done'"
done
```

Drop-in files in `/etc/ssh/sshd_config.d/` override the main `sshd_config` — safer than editing the main file directly. Validate with `sshd -t` before restarting.

**Verify key-based auth still works before restarting sshd** — if you lose SSH access there is no console fallback on these nodes.

Note: on Ubuntu 24.04, the service is `ssh.service`, not `sshd.service`.

---

## 2. UFW on All 3 Cluster Nodes

All nodes had UFW inactive. The cluster network (`10.0.0.0/24`) is private and only reachable via the controller jump host — so a single subnet allow rule is sufficient to cover all k3s inter-node ports (6443, 8472, 10250, etc.) without enumerating them.

```bash
for node in set-hog fast-skunk fast-heron; do
  ssh $node "sudo ufw default deny incoming && \
    sudo ufw default allow outgoing && \
    sudo ufw allow from 10.0.0.0/24 && \
    sudo ufw --force enable && \
    sudo ufw status verbose"
done
```

**Resulting rules on each node:**

```
Default: deny (incoming), allow (outgoing)
Anywhere   ALLOW IN   10.0.0.0/24
```

**Why this is sufficient for 6443:** The Mac reaches `10.0.0.2:6443` via Tailscale subnet routing. The controller (10.0.0.1) NATs the traffic, so set-hog sees source IP `10.0.0.1` — already within `10.0.0.0/24`. No additional rule for the Tailscale range is needed.

---

## 3. Disable Anonymous Auth

```bash
# Add to /etc/rancher/k3s/config.yaml on set-hog
kube-apiserver-arg:
  - "anonymous-auth=false"
```

Restart k3s and verify:

```bash
ssh set-hog "sudo systemctl restart k3s"
# Wait ~60s for API server to come back
curl -sk https://10.0.0.2:6443/api
# → {"status":"Failure","message":"Unauthorized","code":401}
```

Before hardening this returned the full API discovery response to unauthenticated requests.

---

## 4. Audit Logs

**Audit policy file** at `/etc/rancher/k3s/audit-policy.yaml` on set-hog:

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: None
    users: ["system:kube-proxy"]
    verbs: ["watch"]
    resources:
      - group: ""
        resources: ["endpoints", "services", "services/status"]
  - level: None
    nonResourceURLs:
      - /healthz
      - /readyz
      - /livez
  - level: Metadata
    resources:
      - group: ""
        resources: ["secrets", "configmaps"]
  - level: RequestResponse
    users: ["oidc:kanmegnea"]
  - level: Metadata
```

**Flags added to `/etc/rancher/k3s/config.yaml`:**

```yaml
kube-apiserver-arg:
  - "audit-log-path=/var/log/k3s/audit.log"
  - "audit-log-maxage=30"
  - "audit-log-maxbackup=3"
  - "audit-log-maxsize=100"
  - "audit-policy-file=/etc/rancher/k3s/audit-policy.yaml"
```

**Tail audit events:**

```bash
ssh set-hog "sudo tail -f /var/log/k3s/audit.log" | python3 -m json.tool
```

**Verify the flags loaded** — k3s embeds the apiserver as a goroutine so `/proc/<pid>/cmdline` doesn't help. Check the startup log instead:

```bash
ssh set-hog "sudo journalctl -u k3s --since '5 minutes ago' --no-pager | grep 'Running kube-apiserver'"
# Look for --audit-log-path and --encryption-provider-config in the output
```

---

## 5. Secrets Encryption at Rest

k3s uses **kine** (SQLite backend), not embedded etcd — there is no `etcdctl` binary available on the node. Encryption is applied at the kube-apiserver layer and works identically regardless of backend.

### Generate the key

```bash
ssh set-hog "head -c 32 /dev/urandom | base64 | tr -d '\n'"
```

Store the output — it cannot be recovered if lost. Without it all secrets become unreadable after a k3s restart.

### Write the encryption config

```bash
sudo tee /var/lib/rancher/k3s/server/encryption-config.yaml > /dev/null << 'EOF'
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: <base64-32-byte-key>
      - identity: {}
EOF
sudo chmod 600 /var/lib/rancher/k3s/server/encryption-config.yaml
```

The `identity: {}` provider at the end is required — it allows reading pre-existing plaintext secrets during the migration window.

### Enable in k3s config

```yaml
# /etc/rancher/k3s/config.yaml on set-hog
kube-apiserver-arg:
  - "encryption-provider-config=/var/lib/rancher/k3s/server/encryption-config.yaml"
```

```bash
sudo systemctl restart k3s
# Wait for all 3 nodes to be Ready
```

### Re-encrypt all existing secrets

New secrets are encrypted on write. Existing secrets remain plaintext until touched. Force a re-encrypt:

```bash
kubectl get secrets -A -o json | kubectl replace -f -
```

### Verify encryption

k3s uses kine/SQLite. Always query with `ORDER BY id DESC` — kine is log-structured and old rows persist:

```bash
ssh set-hog "sudo sqlite3 /var/lib/rancher/k3s/server/db/state.db \
  \"SELECT hex(substr(value,1,50)) FROM kine WHERE name LIKE '/registry/secrets/<ns>/<name>' ORDER BY id DESC LIMIT 1;\""
```

Expected prefix: `6B38733A656E633A6165736362633A76313A6B6579313A` = `k8s:enc:aescbc:v1:key1:`

If you see `6B387300` (`k8s\0`) the row is the old unencrypted version — re-run the re-encrypt command and query again.

:::danger Key rotation
If you rotate the encryption key, add the new key first AND keep the old key as a second entry. Remove the old key only after all secrets have been re-encrypted with the new one. Removing the old key before re-encryption makes all secrets permanently unreadable.
:::

---

## 6. k3s Rolling Upgrade (v1.34.6 → v1.36.1)

**Order: workers first, then control plane.** Never upgrade the control plane before the workers — the apiserver would be ahead of kubelet and could reject requests from older nodes.

### Pre-upgrade: take a Velero backup

```bash
ssh controller "velero backup create pre-upgrade-$(date +%Y%m%d) --wait"
```

### Step 1 — Drain a worker

```bash
kubectl drain fast-skunk --ignore-daemonsets --delete-emptydir-data --timeout=120s
```

If drain blocks on a PodDisruptionBudget (common with Longhorn instance-manager or Gatekeeper):

```bash
kubectl drain fast-skunk --ignore-daemonsets --delete-emptydir-data --disable-eviction
```

`--disable-eviction` force-deletes pods instead of evicting them, bypassing PDB checks. Safe for a node upgrade since pods reschedule on other nodes.

### Step 2 — Upgrade the worker

**Always supply `K3S_URL` and `K3S_TOKEN` for agent nodes.** Without them the installer defaults to server mode and tries to start an embedded apiserver — which fails with `address already in use` on port 6444.

```bash
TOKEN=$(ssh set-hog "sudo cat /var/lib/rancher/k3s/server/agent-token")

ssh fast-skunk "curl -sfL https://get.k3s.io | \
  K3S_URL=https://10.0.0.2:6443 \
  K3S_TOKEN='${TOKEN}' \
  INSTALL_K3S_VERSION=v1.36.1+k3s1 \
  sh -s - agent"
```

The installer creates a **`k3s-agent.service`** (not `k3s.service`). If the node previously had a stale `k3s.service` in server mode, disable it:

```bash
ssh fast-skunk "sudo systemctl disable --now k3s 2>/dev/null; sudo systemctl start k3s-agent"
```

### Step 3 — Kill the old agent process

The installer runs `systemctl stop k3s` to stop the old service, but the original k3s agent process (started before systemd managed it, at boot) is **not killed by this**. It continues running on the old binary.

```bash
# Check for orphaned old agent
ssh fast-skunk "sudo ps aux | grep 'k3s agent' | grep -v grep"
# If pid is old (started Jun 15), kill it:
ssh fast-skunk "sudo kill <old-pid>"
```

Wait for the new agent to register and report the new version:

```bash
until kubectl get node fast-skunk -o jsonpath='{.status.nodeInfo.kubeletVersion}' | grep -q v1.36; do sleep 5; done
kubectl uncordon fast-skunk
```

### Step 4 — Repeat for fast-heron

Same procedure. If Longhorn instance-manager PDB blocks drain, use `--disable-eviction` again.

### Step 5 — Upgrade the control plane

The control plane does **not** get drained — it hosts the apiserver itself. The installer handles the restart:

```bash
ssh set-hog "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.36.1+k3s1 sh -"
```

Wait for the node to rejoin:

```bash
until kubectl get node set-hog -o jsonpath='{.status.nodeInfo.kubeletVersion}' | grep -q v1.36; do sleep 5; done
kubectl get nodes -o wide
```

### Verify all nodes

```bash
kubectl get nodes -o wide
# All 3 nodes: v1.36.1+k3s1 / containerd://2.2.3-k3s1
```

---

## Final State

### Full k3s config on set-hog (`/etc/rancher/k3s/config.yaml`)

```yaml
disable:
  - servicelb
  - traefik
kube-apiserver-arg:
  - "oidc-issuer-url=https://auth.10.0.0.200.nip.io/application/o/kubernetes/"
  - "oidc-client-id=kubernetes"
  - "oidc-username-claim=preferred_username"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-claim=groups"
  - "oidc-groups-prefix=oidc:"
  - "anonymous-auth=false"
  - "audit-log-path=/var/log/k3s/audit.log"
  - "audit-log-maxage=30"
  - "audit-log-maxbackup=3"
  - "audit-log-maxsize=100"
  - "audit-policy-file=/etc/rancher/k3s/audit-policy.yaml"
  - "encryption-provider-config=/var/lib/rancher/k3s/server/encryption-config.yaml"
```

### Post-hardening score

| Criterion | Status |
|---|---|
| Anonymous access disabled | ✅ `--anonymous-auth=false`; API returns 401 |
| API server protected | ✅ RBAC + OIDC + audit logs |
| SSH restricted | ✅ Password auth off; UFW on all nodes |
| k3s up to date | ✅ v1.36.1+k3s1 |
| Audit logs | ✅ Policy + rotating log at `/var/log/k3s/audit.log` |
| Secrets encrypted at rest | ✅ AES-CBC-256; verified via kine SQLite |
| Private networking | ✅ 10.0.0.x; Cloudflare Tunnel for public |
| API server firewalled | ✅ UFW + Tailscale subnet NAT |

---

## Operational Runbook

### Check hardening status

```bash
# SSH config on all nodes
for node in set-hog fast-skunk fast-heron; do
  echo "=== $node ==="; ssh $node "cat /etc/ssh/sshd_config.d/99-hardening.conf"
done

# UFW status on all nodes
for node in set-hog fast-skunk fast-heron; do
  echo "=== $node ==="; ssh $node "sudo ufw status"
done

# Confirm anonymous auth blocked
curl -sk https://10.0.0.2:6443/api
# → 401 Unauthorized

# Check audit log is flowing
ssh set-hog "sudo tail -5 /var/log/k3s/audit.log | python3 -m json.tool"

# Verify a secret is encrypted in kine (use any <ns>/<name> that exists)
ssh set-hog "sudo sqlite3 /var/lib/rancher/k3s/server/db/state.db \
  \"SELECT hex(substr(value,1,30)) FROM kine WHERE name LIKE '/registry/secrets/velero/velero-credentials' ORDER BY id DESC LIMIT 1;\""
# → starts with 6B38733A656E633A... (k8s:enc:aescbc...)
```

### k3s upgrade checklist (future versions)

1. Check release notes at `https://github.com/k3s-io/k3s/releases`
2. Run `velero backup create pre-upgrade-<version> --wait`
3. Drain worker with `--disable-eviction` if PDB blocks
4. Install with `K3S_URL` + `K3S_TOKEN` for agent nodes
5. Kill orphaned old-binary agent process manually after install
6. Uncordon worker, wait for `v<new>` in `kubectl get nodes`
7. Repeat for second worker
8. Upgrade control plane last (no drain needed)
9. Confirm all pods healthy: `kubectl get pods -A | grep -v Running | grep -v Completed`

### Key files

| File | Node | Purpose |
|---|---|---|
| `/etc/ssh/sshd_config.d/99-hardening.conf` | all 3 | SSH hardening drop-in |
| `/etc/rancher/k3s/config.yaml` | set-hog | k3s server flags |
| `/etc/rancher/k3s/audit-policy.yaml` | set-hog | Audit policy |
| `/var/log/k3s/audit.log` | set-hog | Audit log (rotated) |
| `/var/lib/rancher/k3s/server/encryption-config.yaml` | set-hog | Encryption key (mode 600) |
| `/var/lib/rancher/k3s/server/db/state.db` | set-hog | kine SQLite database |
