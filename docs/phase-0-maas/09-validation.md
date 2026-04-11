---
id: validation
title: Validation
sidebar_position: 9
---

# Validation Commands

After deployment, verify each node is accessible and correctly configured.

---

## SSH Access

```bash
ssh ubuntu@10.0.0.2   # set-hog
ssh ubuntu@10.0.0.4   # fast-skunk
ssh ubuntu@10.0.0.7   # fast-heron
```

MAAS injects your SSH key automatically — no password needed.

---

## System Check (run on each node)

```bash
hostname         # verify correct hostname
ip a             # verify IP is in 10.0.0.0/24, no IPv6
free -h          # verify ~15.9 GiB RAM
df -h            # verify ~512 GB disk
```

---

## Network Connectivity Test (run from controller)

```bash
ping -c 2 10.0.0.2
ping -c 2 10.0.0.4
ping -c 2 10.0.0.7
```

All should respond with 0% packet loss.

---

## Expected Final State

```text
✔ 3 machines deployed
✔ Clean network (10.0.0.0/24)
✔ No IPv6 addresses
✔ SSH working on all nodes
✔ MAAS fully operational
```
