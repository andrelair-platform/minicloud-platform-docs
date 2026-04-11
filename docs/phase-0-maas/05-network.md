---
id: network
title: Network Configuration
sidebar_position: 5
---

# Network Configuration

## Subnet Design

```text
Primary cluster network:
✔ 10.0.0.0/24

Removed to avoid conflicts:
❌ 192.168.1.0/24  (home network — no DHCP from MAAS)
❌ IPv6 subnet (2a02:...)  (disabled entirely)
```

**Rule:** MAAS DHCP runs **only** on the isolated 10.0.0.0/24 network.

---

## MAAS Controller Network Interfaces

```bash
ip a
```

```text
enx00e04c6802b8 → 10.0.0.1/24    (cluster network — Ethernet)
wlp0s20f3       → 192.168.1.x    (internet — WiFi)
```

The controller bridges internet access (WiFi) to the isolated cluster network (Ethernet), acting as the default gateway.

---

## DHCP Configuration

```text
✔ DHCP enabled ONLY on 10.0.0.0/24 (managed by MAAS)
✔ DHCP disabled on 192.168.1.0/24 (home router handles it)
✔ IPv6 DHCP disabled
```

---

## IP Assignment Table

| Host | IP | Assignment |
|---|---|---|
| MAAS Controller | 10.0.0.1 | Static |
| set-hog | 10.0.0.2 | MAAS DHCP |
| fast-skunk | 10.0.0.4 | MAAS DHCP |
| fast-heron | 10.0.0.7 | MAAS DHCP |

---

## Why Disable IPv6?

MAAS has issues selecting the correct subnet when IPv6 is present alongside IPv4. Disabling IPv6 entirely eliminates subnet selection ambiguity and simplifies the provisioning pipeline.

IPv6 is disabled via cloud-init sysctl settings on each node:

```text
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
```
