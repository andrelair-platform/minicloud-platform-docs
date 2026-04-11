---
id: architecture
title: Architecture
sidebar_position: 2
---

# Global Architecture

## Network Diagram

```text
                🌐 Home Network (192.168.1.x)
                          |
                    (WiFi interface)
                          |
               💻 MAAS Controller Machine
               (Ubuntu + Dual Network)
                ├── WiFi → Internet
                └── Ethernet → 10.0.0.1
                          |
                       🔌 Switch
                          |
        ┌───────────────┬───────────────┬───────────────┐
        ↓               ↓               ↓
  🖥 set-hog      🖥 fast-skunk     🖥 fast-heron
  10.0.0.2        10.0.0.4         10.0.0.7
```

---

## MAAS Dashboard — 3 Machines Deployed

![MAAS machines overview](/img/maas-machines-overview.png)

All 3 machines show status **Deployed** with Ubuntu 24.04 LTS, each with 8 cores, ~15.9 GiB RAM, and 512 GB storage.

---

## Node Summary

| Node | IP Address | Role (k3s) | Model |
|---|---|---|---|
| set-hog | 10.0.0.2 | Control Plane | ThinkPad T15 Gen 1 |
| fast-skunk | 10.0.0.4 | Worker | ThinkPad T490 |
| fast-heron | 10.0.0.7 | Worker | ThinkPad T490 |

---

## MAAS Controller Role

The MAAS controller machine sits between:
- The home WiFi network (internet access)
- The isolated cluster network (10.0.0.0/24)

It acts as the **gateway, DHCP server, DNS server, and provisioning engine** for all cluster nodes.
