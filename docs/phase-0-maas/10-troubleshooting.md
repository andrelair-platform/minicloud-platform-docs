---
id: troubleshooting
title: Troubleshooting
sidebar_position: 10
---

# Issues Encountered & Fixes

Real issues hit during this build — documented for future reference.

---

## Issue 1 — SSH Permission Denied

**Symptom:**
```text
ubuntu@10.0.0.x: Permission denied (publickey)
```

**Cause:**
cloud-init `users` block was overriding MAAS's SSH key injection.

**Fix:**
```text
✔ Remove the entire users: block from cloud-init
✔ Let MAAS inject the SSH key from your profile
✔ Redeploy the node
```

---

## Issue 2 — IPv6 Conflicts (Wrong Subnet Selected)

**Symptom:**
Node receives an IPv6 address instead of 10.0.0.x, or MAAS deploys to wrong subnet.

**Cause:**
MAAS was selecting the IPv6 subnet (2a02:...) over the intended 10.0.0.0/24.

**Fix:**
```text
✔ Delete the IPv6 subnet from MAAS UI (Subnets → delete)
✔ Disable IPv6 via cloud-init sysctl
✔ Verify only 10.0.0.0/24 has DHCP enabled
```

---

## Issue 3 — Alias Interface (enp0s31f6:1)

**Symptom:**
MAAS shows two interfaces for one NIC, causing IP conflicts or failed commissioning.

**Fix:**
```text
✔ Delete the alias interface in MAAS machine network config
✔ Keep only the primary interface (enp0s31f6)
✔ Recommission the node
```

---

## Issue 4 — MAAS 502 Error

**Symptom:**
Accessing `http://10.0.0.1:5240/MAAS` returns 502 Bad Gateway.

**Cause:**
MAAS URL binding was pointing to wrong address after installation.

**Fix:**
```bash
sudo snap set maas url=http://10.0.0.1:5240/MAAS
sudo snap restart maas
```

---

## Issue 5 — Node Stuck at "Disk Erasing"

**Symptom:**
Node deployment hangs indefinitely at the disk erasing phase.

**Fix:**
```text
1. Abort the deployment from MAAS UI
2. Mark node as Broken
3. Mark node as Ready (via Actions)
4. Redeploy
```

The node will go through commissioning again cleanly.

---

## Issue 6 — PXE Boot Loop (dhcpd Missing After Controller Reboot)

**Symptom:**
Node powers on, shows Lenovo logo, attempts "PXE boot over IPv4", then resets and loops endlessly — never reaches Ubuntu.

**Diagnose:**
```bash
# Run on the MAAS controller (10.0.0.1)
pgrep -af dhcpd
```
If this returns no output, dhcpd is not running. Nodes send DHCP DISCOVER on boot but receive no response, so PXE times out and the machine resets.

**Cause:**
This was originally diagnosed as a dhcpd "crash", but log analysis showed the real cause is a **boot-time startup race inside the MAAS snap**:

1. On controller boot, `pebble` (MAAS's internal service supervisor) starts `regiond`, `apiserver`, and `rackd` in parallel.
2. `rackd` calls `regiond`'s HTTP endpoint at `http://10.0.0.1:5240/MAAS` to fetch the DHCP config.
3. If `regiond` isn't yet listening when `rackd` asks, `rackd` logs `"Region is not advertising RPC endpoints"`, retries a few times, and **gives up without ever telling pebble to start `dhcpd`**.
4. From the user's perspective the MAAS UI works (regiond + http are up), but the cluster nodes can't PXE-boot.

You can confirm this in the journal — look for these lines around boot time:
```bash
journalctl --since "<controller boot time>" | grep -E "(rackd.*Region|dhcpd)"
```
A failed boot shows `Region not available: Connection refused` and **no `dhcpd` start lines**. A successful boot shows `Service "dhcpd" starting`.

**Manual fix (still useful for ad-hoc situations):**
```bash
sudo snap restart maas
```
Wait ~30 seconds, then power-cycle the affected nodes. By the time `rackd` asks `regiond` for RPC info on a clean restart, `regiond` is already listening, so `dhcpd` starts cleanly.

**Verify dhcpd is back:**
```bash
pgrep -af dhcpd
# Should show two lines: one with `-f -4` (IPv4) and one with `-f -6` (IPv6)
```

### Permanent fix — boot reconciler

A small systemd timer fires 120 s after every boot, checks whether `dhcpd` is running, and runs `snap restart maas` automatically if it isn't. This makes the cluster self-healing on cold boot — no manual intervention needed.

**Three files:**

`/usr/local/sbin/maas-dhcpd-reconciler`
```bash
#!/bin/bash
# Restart the MAAS snap once if dhcpd didn't come up at boot.
# Triggered by maas-dhcpd-reconciler.timer ~120s after boot.

set -euo pipefail
LOG_TAG="maas-dhcpd-reconciler"

if pgrep -f '/snap/maas/.*/usr/sbin/dhcpd -f -4' >/dev/null; then
    logger -t "$LOG_TAG" "dhcpd is running; nothing to do"
    exit 0
fi

logger -t "$LOG_TAG" "dhcpd not running 120s after boot; restarting MAAS snap"
/usr/bin/snap restart maas
logger -t "$LOG_TAG" "MAAS snap restart complete"
```

`/etc/systemd/system/maas-dhcpd-reconciler.service`
```ini
[Unit]
Description=Restart MAAS snap if dhcpd did not start at boot
After=snap.maas.pebble.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/maas-dhcpd-reconciler
StandardOutput=journal
StandardError=journal
```

`/etc/systemd/system/maas-dhcpd-reconciler.timer`
```ini
[Unit]
Description=Reconcile MAAS dhcpd 120s after boot

[Timer]
OnBootSec=120s
Unit=maas-dhcpd-reconciler.service

[Install]
WantedBy=timers.target
```

**Install:**
```bash
sudo chmod +x /usr/local/sbin/maas-dhcpd-reconciler
sudo systemctl daemon-reload
sudo systemctl enable --now maas-dhcpd-reconciler.timer
```

**Verify it's enabled:**
```bash
systemctl list-timers --all | grep maas-dhcpd-reconciler
journalctl -t maas-dhcpd-reconciler -n 20
```

After installation, every boot logs either `"dhcpd is running; nothing to do"` (happy path) or `"dhcpd not running 120s after boot; restarting MAAS snap"` (race hit, auto-recovered).

:::tip Boot order still recommended
The reconciler removes the *requirement* to power on the controller before the cluster nodes, but it still adds ~2 minutes of recovery time on a bad boot. Powering on the MAAS controller first and waiting ~30 seconds is still the cleanest sequence.
:::

---

## Issue 7 — Node Boots with Wrong Hostname (Auto-Renamed by MAAS)

**Symptom:**
Node boots successfully but the login screen shows a random `adjective-animal` hostname (e.g. `needed-lion`) instead of the correct name (`fast-heron`, `set-hog`, etc.).

**Cause:**
During a PXE boot loop, MAAS can accidentally trigger a re-deploy and assign the node a new auto-generated hostname. The OS gets installed with that temporary name.

**Fix:**
```bash
# SSH in using the IP (still correct even if hostname is wrong)
ssh ubuntu@10.0.0.7

# Set the correct hostname
sudo hostnamectl set-hostname fast-heron

# Update /etc/hosts to match
sudo sed -i 's/needed-lion/fast-heron/g' /etc/hosts

# Exit and verify
exit
ssh ubuntu@10.0.0.7 "hostname"
```

Then update MAAS to stay in sync (run on controller):
```bash
maas admin machine update q6m3px hostname=fast-heron
```

Replace `q6m3px` with the correct system_id for the affected node:

| Node | system_id |
|---|---|
| set-hog | `nbc6cx` |
| fast-skunk | `sby3w7` |
| fast-heron | `q6m3px` |
