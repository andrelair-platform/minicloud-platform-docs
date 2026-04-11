---
id: core-concepts
title: Core Concepts
sidebar_position: 3
---

# Core Concepts

## MAAS (Metal as a Service)

```text
✔ Bare-metal provisioning tool by Canonical
✔ Automates OS installation via PXE
✔ Manages DHCP, DNS, IP assignment
✔ Injects SSH keys automatically
```

MAAS treats physical machines the same way cloud platforms treat virtual machines — you enlist, commission, and deploy them through a UI or API.

---

## PXE Boot

```text
✔ Network boot instead of disk boot
✔ Used for automated OS deployment
✔ Triggered via BIOS (F12 → Network Boot)
```

When a node boots via PXE:
1. It receives an IP from MAAS DHCP
2. Downloads a boot image over the network
3. MAAS installs the OS automatically
4. Machine is ready for SSH access

---

## Cloud-init

```text
✔ Industry-standard post-install configuration system
✔ Used for:
  - hostname assignment
  - package installation
  - system configuration (sysctl, timezone)
```

:::warning Important lesson
Do **NOT** define `users` in cloud-init when using MAAS. MAAS handles SSH key injection automatically. Overriding this causes SSH access failures.
:::

---

## Key Principle

```text
Provisioning → MAAS
Configuration → Cloud-init
```

Keep these responsibilities separated. MAAS handles *getting the OS on the machine*, cloud-init handles *configuring it*.
