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

## Issue 6 — PXE Boot Loop (dhcpd Crashed)

**Symptom:**
Node powers on, shows Lenovo logo, attempts "PXE boot over IPv4", then resets and loops endlessly — never reaches Ubuntu.

**Cause:**
The MAAS dhcpd process crashed on the controller (stale PID file). Nodes send DHCP DISCOVER on boot but receive no response, so PXE times out and the machine resets.

**Diagnose:**
```bash
# Run on the MAAS controller (10.0.0.1)
ps aux | grep dhcpd | grep -v grep
```
If this returns no output, dhcpd is dead.

**Fix:**
```bash
sudo snap restart maas
```
Wait ~30 seconds, then power-cycle the affected nodes. They will boot normally once dhcpd is responding.

**Verify dhcpd is back:**
```bash
ps aux | grep dhcpd | grep -v grep
# Should show two lines: one for IPv4 (-4) and one for IPv6 (-6)
```

:::warning Boot order matters
Always power on the MAAS controller first and wait ~30 seconds before turning on the cluster nodes. Nodes PXE boot on every startup and require dhcpd to be ready. If all machines are powered on simultaneously, nodes may start before dhcpd is up and enter this loop.
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
