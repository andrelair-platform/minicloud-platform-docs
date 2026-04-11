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
