---
id: hardware
title: Hardware
sidebar_position: 4
---

# Hardware Used

## Cluster Nodes — 4x Lenovo ThinkPad + 1x MacBook Pro

All four nodes run on Lenovo ThinkPad laptops with identical specs:

```text
✔ CPU: Intel Core i7 (8 cores)
✔ RAM: 16 GB (15.9 GiB usable)
✔ Storage: 512.1 GB SSD
✔ Network: 1 Gbps Ethernet (Intel I219-V)
✔ OS: Ubuntu 24.04 LTS "Noble Numbat"
```

---

## Node Details

### fast-heron — 10.0.0.7

![fast-heron machine detail](/img/fast-heron-detail.png)

| Field | Value |
|---|---|
| Model | Lenovo ThinkPad T490 (20N2000LFR) |
| CPU | Intel Core i7-8565U, 8 cores |
| RAM | 15.9 GiB |
| Storage | 512.1 GB |
| NIC | Intel I219-V 0.5-3 |
| Serial | PF1BQWYP |
| Firmware | UEFI (N2IETA5W 1.83) |

---

### fast-skunk — 10.0.0.4

![fast-skunk machine detail](/img/fast-skunk-detail.png)

| Field | Value |
|---|---|
| Model | Lenovo ThinkPad T490 (20N2000LFR) |
| CPU | Intel Core i7-8565U, 8 cores |
| RAM | 15.9 GiB |
| Storage | 512.1 GB |
| NIC | Intel I219-V 0.5-3 |
| Serial | PF1BSCNM |
| Firmware | UEFI (N2IETA5W 1.83) |

---

### set-hog — 10.0.0.2

![set-hog machine detail](/img/set-hog-detail.png)

| Field | Value |
|---|---|
| Model | Lenovo ThinkPad T15 Gen 1 (20S6001XFR) |
| CPU | Intel Core i7-10510U, 8 cores |
| RAM | 15.9 GiB |
| Storage | 512.1 GB |
| NIC | Intel I219-V 0.6-4 |
| Serial | PF2V7JYG |
| Firmware | UEFI (N2XET43W 1.33) |

---

### star-kitten — 10.0.0.8

| Field | Value |
|---|---|
| Model | Lenovo ThinkPad T490 |
| CPU | Intel Core i7-8565U, 8 cores |
| RAM | 15.9 GiB |
| Storage | 512.1 GB |
| NIC | Intel I219-V (enp0s31f6) |
| MAAS system_id | dr3cnm |
| Added | 2026-07-04 |

---

### swift-mac — 10.0.0.10

| Field | Value |
|---|---|
| Model | Apple MacBook Pro 13-inch Mid 2012 |
| CPU | Intel Core i5-3210M (Ivy Bridge), 2 cores / 4 threads |
| RAM | 8 GiB DDR3 1600 MHz |
| Storage | 480 GB SSD |
| NIC | Broadcom BCM57765 (built-in RJ45, `enp1s0f0`) |
| Serial | C02JL20WDTY4 |
| OS | Ubuntu 22.04.5 LTS (manual USB install — Apple EFI incompatible with MAAS PXE) |
| Added | 2026-07-12 |

:::note Non-MAAS install
Apple hardware uses a proprietary NetBoot protocol incompatible with standard PXE/MAAS. swift-mac was provisioned via USB installer. See [Adding a Non-MAAS Node](add-node#apple-hardware--non-maas-path) for the full procedure.
:::

---

## Total Cluster Capacity

Figures from `kubectl` node capacity (live, 2026-07-12):

| Resource | set-hog | fast-heron | fast-skunk | star-kitten | swift-mac | **Total** |
|---|---|---|---|---|---|---|
| CPU cores | 8 | 8 | 8 | 8 | 4 | **36** |
| RAM (usable) | 15.6 GiB | 15.6 GiB | 15.6 GiB | 15.6 GiB | 7.8 GiB | **~70 GiB** |
| Disk (usable) | 468 GB | 468 GB | 468 GB | 468 GB | 437 GB | **~2.3 TB** |
| Max pods | 110 | 110 | 110 | 110 | 110 | **550** |

---

## Live Resource Utilization

Measured 2026-07-12 with 162 running pods across 57 ArgoCD apps:

| Node | RAM used / total | RAM free | Disk used / total | Disk free |
|---|---|---|---|---|
| set-hog | 8.4 GiB / 15 GiB | 6.9 GiB | 137 GB / 468 GB | 308 GB (69%) |
| fast-heron | 6.5 GiB / 15 GiB | 8.8 GiB | 150 GB / 468 GB | 295 GB (66%) |
| fast-skunk | 4.5 GiB / 15 GiB | 10 GiB | 91 GB / 468 GB | 354 GB (79%) |
| star-kitten | 6.3 GiB / 15 GiB | 9.0 GiB | 143 GB / 468 GB | 302 GB (67%) |
| swift-mac | 1.2 GiB / 7.7 GiB | 6.1 GiB | 16 GB / 437 GB | 403 GB (96%) |
| **Cluster total** | **~27 GiB / ~68 GiB** | **~41 GiB free** | **~537 GB / ~2.3 TB** | **~1.66 TB free** |

CPU allocation (requests/limits across all pods):

| Node | CPU requested | CPU limit | Cores |
|---|---|---|---|
| fast-heron | 4.7 / 8 (59%) | 15.0 (187% — overcommit) | 8 |
| fast-skunk | 3.4 / 8 (43%) | 17.0 (211% — overcommit) | 8 |
| set-hog | 3.7 / 8 (46%) | 15.1 (188% — overcommit) | 8 |
| star-kitten | 4.2 / 8 (51%) | 13.7 (171% — overcommit) | 8 |
| swift-mac | 0.9 / 4 (23%) | 3.7 (91%) | 4 |

CPU limits exceed physical cores intentionally — this is standard Kubernetes overcommit. Limits are only enforced under CPU pressure; actual utilization stays well below capacity.

---

## Equivalent Cloud Cost Comparison

The cluster (36 vCPU, ~68 GiB RAM, ~2.3 TB storage) maps to the following on major cloud providers:

### AWS

| Instance | vCPU | RAM | Storage | Monthly Cost (est.) |
|---|---|---|---|---|
| `m6i.2xlarge` × 4 | 8 each / 32 total | 32 GiB each / ~128 GiB total | EBS separately | ~$470–$600/mo |
| Equivalent EBS (2.3 TB gp3) | — | — | 2.3 TB | ~$185/mo |
| **Total AWS** | | | | **~$655–$785/mo** |

### Azure

| Instance | vCPU | RAM | Storage | Monthly Cost (est.) |
|---|---|---|---|---|
| `Standard_D8s_v5` × 4 | 8 each / 32 total | 32 GiB each / ~128 GiB total | Managed disk separately | ~$510–$640/mo |
| Equivalent Managed Disk (2.3 TB P30) | — | — | 2.3 TB | ~$155/mo |
| **Total Azure** | | | | **~$665–$795/mo** |

### GCP

| Instance | vCPU | RAM | Storage | Monthly Cost (est.) |
|---|---|---|---|---|
| `n2-standard-8` × 4 | 8 each / 32 total | 32 GiB each / ~128 GiB total | Persistent disk separately | ~$480–$615/mo |
| Equivalent Persistent Disk (2.3 TB SSD) | — | — | 2.3 TB | ~$230/mo |
| **Total GCP** | | | | **~$710–$845/mo** |

### Your Bare-Metal Setup

| Resource | Value | Monthly Cost |
|---|---|---|
| Hardware (4× ThinkPad + MacBook Pro 2012) | 36 cores / ~68 GiB / ~2.3 TB | ~$0 (already owned) |
| Electricity (est. ~225 W total, 24/7) | 5× laptops at idle/load | ~$20–$35/mo |
| **Total bare-metal** | | **~$20–$35/mo** |

:::tip Cost advantage
Running this infrastructure bare-metal saves approximately **$630–$810/month** compared to equivalent cloud instances. Over a year that is **$7,560–$9,720 in cloud spend avoided** — while giving you full hardware control, no egress fees, and no vendor lock-in.
:::
