---
id: host-hardening
title: Host Firewall Hardening (UFW)
sidebar_position: 7
---

# Host Firewall Hardening — Controller Node

## What Was Found

During a routine security audit of the controller node (Tailscale endpoint, MAAS host), two MAAS services were discovered listening on the **public IPv6 address** with no host firewall in place:

```bash
ssh controller "ss -tlnp | grep -E ':22|:5240|:8000'"
# LISTEN  0.0.0.0:22     (SSH — expected)
# LISTEN  0.0.0.0:5240   (MAAS UI/API — exposed)
# LISTEN  [::]:5240      (MAAS UI/API on IPv6 — exposed)
# LISTEN  *:8000         (Squid proxy — exposed)
```

The controller's public IPv6 address (`2a02:8424:6ee0:be01:...`) was reachable from the internet. Anyone who discovered it could reach:

| Port | Service | Risk |
|---|---|---|
| 5240 | MAAS UI + API | Admin interface for bare-metal provisioning — exposed publicly |
| 8000 | Squid HTTP proxy | MAAS apt-cache proxy for provisioned nodes — exposed publicly |

**Why it happened:** MAAS binds both services to `0.0.0.0` / `[::]` by default. `iptables-persistent` was installed but no explicit deny rules had been configured for these ports.

Note: The cluster's public-facing apps (`*.devandre.sbs`) were **not** affected — they go through the Cloudflare Tunnel and never expose the home IP.

---

## Fix — UFW Installation and Configuration

`ufw` was not installed on the controller (Ubuntu 24.04). Installing it removed `iptables-persistent` and `netfilter-persistent` (UFW takes over iptables/nftables management).

```bash
# Install UFW
sudo apt-get install -y ufw

# Policy: block all inbound by default
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Keep SSH open — emergency recovery path if Tailscale fails
sudo ufw allow 22/tcp

# Allow all traffic arriving on the Tailscale interface
# (covers: ssh controller, kubectl, all admin access from any location)
sudo ufw allow in on tailscale0

# Allow cluster nodes (k3s) to reach MAAS and Squid
sudo ufw allow from 10.0.0.0/24

# Enable
sudo ufw --force enable
```

Final verified state:

```
Status: active
Default: deny (incoming), allow (outgoing), deny (routed)

To                           Action      From
--                           ------      ----
22/tcp                       ALLOW IN    Anywhere
Anywhere on tailscale0       ALLOW IN    Anywhere
Anywhere                     ALLOW IN    10.0.0.0/24
22/tcp (v6)                  ALLOW IN    Anywhere (v6)
Anywhere (v6) on tailscale0  ALLOW IN    Anywhere (v6)
```

---

## Verification

**Ports 5240 and 8000 blocked from the internet:**

```bash
# From Mac (not on same LAN as controller):
/usr/bin/curl --connect-timeout 3 http://[<controller-ipv6>]:5240/
# → connection timed out (UFW drops the packet)
```

**Cluster nodes still have internet access (MAAS NAT rules survived):**

```bash
ssh set-hog "curl -s --connect-timeout 3 https://registry.k8s.io -o /dev/null -w '%{http_code}'"
# → 307 (internet reachable from k3s nodes)
```

**All three nodes still Ready:**

```bash
kubectl --context minicloud get nodes
# NAME         STATUS   ROLES           AGE   VERSION
# fast-heron   Ready    <none>          ...
# fast-skunk   Ready    <none>          ...
# set-hog      Ready    control-plane   ...
```

---

## Threat Model After Hardening

| Attack surface | Before | After |
|---|---|---|
| MAAS UI on public IPv6 | Reachable by anyone | Blocked by UFW |
| Squid proxy on public IPv6 | Reachable by anyone | Blocked by UFW |
| SSH on public IPv6 | Open (key-auth only) | Open (key-auth only — intentional recovery path) |
| `*.devandre.sbs` apps | Via Cloudflare Tunnel (home IP hidden) | Unchanged |
| Admin access (kubectl, ssh) | Via Tailscale only | Via Tailscale only |

---

## Remote Access After UFW

UFW does **not** affect remote work via Tailscale. Traffic flow from any external network (university, coffee shop, etc.):

```
Mac (any network)
  → Tailscale (WireGuard, falls back to HTTPS relay if UDP blocked)
    → tailscale0 interface on controller
      → UFW rule: "Anywhere on tailscale0 ALLOW IN"
        → controller / cluster fully accessible
```

Everything that was accessible before UFW is still accessible after, as long as Tailscale is running on the Mac.

---

## Operational Notes

- **`iptables-persistent` was removed** during UFW install. MAAS rack controller re-applies its own NAT rules on startup — no manual iptables rules need to be re-added.
- If you need to allow a new port, always add it via UFW:
  ```bash
  sudo ufw allow <port>/tcp
  sudo ufw status verbose
  ```
- Never disable UFW to "debug" a connectivity issue — use `sudo ufw status numbered` to inspect rules and `sudo ufw allow` to add specific exceptions.
- UFW is enabled on system startup (`ufw enable` sets this automatically).

---

## Checking Current Firewall Status

```bash
ssh -t controller "sudo ufw status verbose"
```
