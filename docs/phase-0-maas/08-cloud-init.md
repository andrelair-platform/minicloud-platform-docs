---
id: cloud-init
title: Cloud-Init Configuration
sidebar_position: 8
---

# Cloud-Init Configuration

## Final cloud-init Used

This is the production cloud-init applied during node deployment:

```yaml
#cloud-config

hostname: needed-lion

package_update: true
package_upgrade: true

packages:
  - curl
  - vim
  - htop
  - net-tools
  - ca-certificates

write_files:
  - path: /etc/sysctl.d/99-disable-ipv6.conf
    content: |
      net.ipv6.conf.all.disable_ipv6=1
      net.ipv6.conf.default.disable_ipv6=1
      net.ipv6.conf.lo.disable_ipv6=1

runcmd:
  - sysctl --system
  - timedatectl set-timezone UTC

final_message: "Node ready 🚀"
```

---

## What Each Section Does

| Section | Purpose |
|---|---|
| `hostname` | Sets the node hostname |
| `package_update` / `package_upgrade` | Ensures OS is fully updated |
| `packages` | Installs essential tools |
| `write_files` | Creates sysctl config to disable IPv6 |
| `runcmd` | Applies sysctl settings, sets timezone |

---

## Critical Warning

:::danger Do NOT add a `users` block
```yaml
# ❌ NEVER do this with MAAS
users:
  - name: ubuntu
    ...
```

MAAS automatically injects the SSH public key you configured in your profile. If you define a `users` block in cloud-init, it **overrides MAAS's key injection** and you will be locked out (SSH Permission Denied).

✔ Remove the `users` block entirely — MAAS handles it.
:::

---

## Adapting for Each Node

Change the `hostname` field per node:

```yaml
# set-hog
hostname: set-hog

# fast-skunk
hostname: fast-skunk

# fast-heron
hostname: fast-heron
```

All other settings remain identical across nodes.
