---
id: add-node
title: Adding a New Node
sidebar_position: 11
---

# Adding a New Node to the Cluster

This runbook documents the full procedure for enrolling a new bare-metal machine in MAAS, deploying Ubuntu, and joining it as a k3s worker. Completed 2026-07-04 for **star-kitten** (10.0.0.8).

---

## Prerequisites

- Machine connected to the cluster switch (same 10.0.0.x LAN as the other nodes)
- No OS required — MAAS deploys Ubuntu from scratch via PXE
- Tailscale active on the Mac (to reach the controller at 100.88.123.8)

---

## Step 1 — Disable Secure Boot

ThinkPad BIOS blocks MAAS's iPXE image by default (unsigned bootloader → "Security Violation Policy" → machine powers off).

1. Power on → press **F1** → **Security** → **Secure Boot** → set to **Disabled**
2. Press **F10** to save and exit

:::caution Required for every new ThinkPad
Secure Boot must be disabled before the first PXE boot. It can remain disabled — cluster nodes don't need it.
:::

---

## Step 2 — PXE Boot into MAAS

1. Power on → press **F12** → select **PXE Boot: Intel Gigabit**
2. The machine gets a DHCP lease from MAAS and downloads the commissioning image
3. MAAS automatically runs hardware discovery scripts (~3–5 minutes)
4. Machine powers off when commissioning completes

Watch for it in MAAS:
```bash
maas admin machines read | python3 -c "
import sys, json
for m in json.load(sys.stdin):
    print(m['hostname'], m['status_name'], m.get('ip_addresses',''))
"
```

The new machine appears with a random animal hostname (MAAS naming convention) and status **New**, then transitions to **Commissioning**, then **Ready**.

---

## Step 3 — Configure Power Type

MAAS requires a power type before it can deploy. ThinkPads have no IPMI, so set it to `manual`:

```bash
SYSTEM_ID=<system_id from step 2>
maas admin machine update $SYSTEM_ID power_type=manual
```

---

## Step 4 — Deploy Ubuntu 24.04

:::warning MAAS 3.7.2 bug — manual power type deploy fails
Both the CLI and UI return **"Error determining BMC task queue"** for `manual` power type machines. Workaround: temporarily set power type to `ipmi` with dummy credentials to unblock the task queue, then reset to `manual` after deploy completes.
:::

```bash
# Workaround: set ipmi temporarily
maas admin machine update $SYSTEM_ID \
  power_type=ipmi \
  power_parameters='{"power_address":"10.0.0.200","power_user":"admin","power_pass":"admin","mac_address":"<NIC MAC>"}'

# Trigger deploy
maas admin machine deploy $SYSTEM_ID distro_series=noble
# → status: Deploying

# Reset to manual
maas admin machine update $SYSTEM_ID power_type=manual
```

Get the NIC MAC from MAAS:
```bash
maas admin machine read $SYSTEM_ID | python3 -c "
import sys, json
d = json.load(sys.stdin)
for i in d['interface_set']:
    print(i['name'], i['mac_address'])
"
```

Once the status changes to `Deploying`, **manually power cycle the machine** (hold power button off, then on). It PXE boots one more time and receives the Ubuntu installer image from MAAS. Installation takes ~5 minutes. Machine reboots into Ubuntu when done — MAAS status becomes **Deployed**.

---

## Step 5 — SSH Access

MAAS deploys with the controller's SSH key. The Mac's key needs to be added manually:

```bash
# From the controller, push the Mac's public key
ssh ubuntu@<NODE_IP> 'mkdir -p ~/.ssh && echo "<MAC_PUBLIC_KEY>" >> ~/.ssh/authorized_keys'
```

Add the SSH alias to `~/.ssh/config` on the Mac:
```text
Host star-kitten
    HostName 10.0.0.8
    User ubuntu
    ProxyJump controller
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Test:
```bash
ssh star-kitten hostname
```

---

## Step 6 — Cluster Hardening

Apply the same hardening as all other cluster nodes:

```bash
# SSH hardening
ssh star-kitten "sudo tee /etc/ssh/sshd_config.d/99-hardening.conf > /dev/null << 'EOF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
sudo systemctl restart ssh"

# UFW firewall
ssh star-kitten "
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw allow from 10.0.0.0/24
  sudo ufw --force enable
"
```

---

## Step 7 — Join the k3s Cluster

```bash
# Get token from control plane
TOKEN=$(ssh set-hog "sudo cat /var/lib/rancher/k3s/server/node-token")

# Install k3s agent on the new node
ssh star-kitten "curl -sfL https://get.k3s.io | \
  K3S_URL=https://10.0.0.2:6443 \
  K3S_TOKEN=$TOKEN \
  sh -"
```

Verify:
```bash
kubectl get nodes
# star-kitten   Ready   <none>   Xm   vX.XX.X+k3s1
```

Daemonset pods (Longhorn, Falco, MetalLB, node-exporter, Promtail, Velero node-agent) schedule automatically.

---

## Step 8 — Fix EFI Boot Order

After MAAS deploys Ubuntu, the EFI boot order has **PXE first** but **no Ubuntu fallback entry**. If the controller is offline during a power-on, PXE times out and the machine fails to boot.

Create the Ubuntu EFI entry and set the correct boot order:

```bash
# Find the EFI partition number
ssh star-kitten "lsblk -o NAME,FSTYPE,MOUNTPOINT | grep vfat"
# nvme0n1p1  vfat  /boot/efi  → partition 1

# Create Ubuntu boot entry
ssh star-kitten "sudo efibootmgr --create \
  --disk /dev/nvme0n1 --part 1 \
  --label 'Ubuntu' \
  --loader '\\EFI\\ubuntu\\shimx64.efi'"

# Set boot order: PXE first (MAAS can still manage), Ubuntu second (offline fallback)
ssh star-kitten "sudo efibootmgr --bootorder 0032,0000,002D"
# 0032 = PXE BOOT, 0000 = Ubuntu (just created), 002D = NVMe0
```

Verify:
```bash
ssh star-kitten "efibootmgr | grep -E 'BootOrder|Boot0000|Boot0032'"
```

:::tip Why PXE stays first
Keeping PXE first lets MAAS re-deploy or re-commission the node in future. MAAS responds to a deployed machine's PXE request with a "boot local" directive (because `netboot=False`), so normal power-ons boot Ubuntu transparently. If MAAS is offline, the Ubuntu entry is the fallback.
:::

---

## Step 9 — Reboot Test

```bash
ssh star-kitten "sudo reboot"

# Wait ~4 minutes, then verify node rejoined
kubectl get node star-kitten
# Ready
ssh star-kitten "systemctl is-active k3s-agent"
# active
```

---

## Summary

| Step | Command / Action |
|---|---|
| Disable Secure Boot | BIOS F1 → Security → Secure Boot → Disabled |
| PXE boot → commission | F12 → Intel Gigabit; wait for Ready in MAAS |
| Deploy Ubuntu | `maas admin machine deploy` (ipmi workaround for MAAS 3.7.2) |
| SSH access | Push Mac public key; add `~/.ssh/config` alias |
| Hardening | SSH config + UFW (same as other nodes) |
| k3s agent | `curl get.k3s.io | K3S_URL=... K3S_TOKEN=... sh -` |
| EFI boot order | `efibootmgr --create` Ubuntu entry + `--bootorder PXE,Ubuntu,NVMe` |
| Reboot test | Node rejoins cluster automatically in ~4 minutes |
