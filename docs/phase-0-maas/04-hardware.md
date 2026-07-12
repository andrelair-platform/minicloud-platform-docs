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

| Resource | Per Node (ThinkPad) | swift-mac | Total (5 nodes) |
|---|---|---|---|
| CPU Cores | 8 | 4 (2C/4T) | 36 |
| RAM | 15.9 GiB | 8 GiB | ~71.6 GiB |
| Storage | 512 GB | 480 GB | ~2.5 TB |

---

## Equivalent Cloud Cost Comparison

The cluster above (24 vCPU, ~48 GiB RAM, ~1.5 TB storage) maps to the following on major cloud providers:

### AWS

| Instance | vCPU | RAM | Storage | Monthly Cost (est.) |
|---|---|---|---|---|
| `m6i.2xlarge` x3 | 8 each / 24 total | 32 GiB each / ~96 GiB total | EBS separately | ~$350–$450/mo |
| Equivalent EBS (1.5 TB gp3) | — | — | 1.5 TB | ~$120/mo |
| **Total AWS** | | | | **~$470–$570/mo** |

### Azure

| Instance | vCPU | RAM | Storage | Monthly Cost (est.) |
|---|---|---|---|---|
| `Standard_D8s_v5` x3 | 8 each / 24 total | 32 GiB each / ~96 GiB total | Managed disk separately | ~$380–$480/mo |
| Equivalent Managed Disk (1.5 TB P30) | — | — | 1.5 TB | ~$100/mo |
| **Total Azure** | | | | **~$480–$580/mo** |

### GCP

| Instance | vCPU | RAM | Storage | Monthly Cost (est.) |
|---|---|---|---|---|
| `n2-standard-8` x3 | 8 each / 24 total | 32 GiB each / ~96 GiB total | Persistent disk separately | ~$360–$460/mo |
| Equivalent Persistent Disk (1.5 TB SSD) | — | — | 1.5 TB | ~$150/mo |
| **Total GCP** | | | | **~$510–$610/mo** |

### Your Bare-Metal Setup

| Resource | Value | Monthly Cost |
|---|---|---|
| Hardware (4x ThinkPad + MacBook Pro 2012) | 36 cores / 71.6 GiB / 2.5 TB | ~$0 (already owned) |
| Electricity (est. ~225W total) | 24/7 | ~$20–$35/mo |
| **Total bare-metal** | | **~$20–$35/mo** |

:::tip Cost advantage
Running this infrastructure bare-metal saves approximately **$600–$750/month** compared to equivalent cloud instances. Over a year that is **$7,200–$9,000 in cloud spend avoided** — while giving you full hardware control and no vendor lock-in.
:::
