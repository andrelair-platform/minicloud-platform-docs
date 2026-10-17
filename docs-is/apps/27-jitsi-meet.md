---
id: jitsi-meet
title: Phase 77 — Jitsi Meet + Coturn
sidebar_position: 27
---

# Phase 77 — Jitsi Meet + Coturn TURN Server

**Deployed:** 2026-07-26 | **Version:** Jitsi Meet v2.21.0 | **Namespace:** `collab`

Jitsi Meet provides self-hosted video conferencing. The platform deploys the full Jitsi stack (web, prosody, jicofo, JVB) plus a Coturn TURN server on AWS Lightsail for clients that cannot establish direct peer connections.

---

## Architecture

```
External caller
   │
   ├─ IPv6 capable → JVB direct (star-kitten:10000/udp, hostNetwork)
   │
   └─ IPv4 only → TURN relay → Lightsail turn-coturn-eu (54.171.137.209:3478)
                               → Coturn relays via Tailscale → star-kitten 10.0.0.8:10000

JVB (Jitsi Video Bridge) — star-kitten (10.0.0.8), hostNetwork, UDP 10000
Prosody / Jicofo / Web  — collab namespace, nginx ingress
Coturn TURN server      — AWS Lightsail eu-west-1 (turn-coturn-eu, 54.171.137.209)
```

| Component | Detail |
|-----------|--------|
| Helm chart | `jitsi-contrib/jitsi-meet` |
| JVB node | star-kitten (`10.0.0.8`) — pinned via nodeSelector |
| JVB port | UDP 10000, hostNetwork (bypasses kube-proxy) |
| Auth | Authentik forward auth (provider pk 15, `forward_single`) |
| Coturn | v4.5, AWS Lightsail nano_3_0, `54.171.137.209:3478`, relay `49152–65535` |
| Tailscale | `turn-coturn-eu` (`100.77.251.92`) — relay path to JVB via mesh |
| DNS | `turn.devandre.sbs → 54.171.137.209` (unproxied, UDP) |
| TURN credentials | Vault `platform/jitsi.coturn-secret` → prosody `extraEnvFrom` |
| SSH key | `~/.ssh/lightsail-turn-coturn.pem` (on Mac) |
| Cost | $5/month AWS Lightsail, billed against AWS credit |

---

## IPv6 direct path fix (2026-07-28)

SFR DS-Lite WAN blocks all inbound IPv4 at the AFTR carrier — Coturn IPv4 TURN relay cannot reach the JVB via the home network's public IPv4. Jitsi works for mobile/IPv6 callers via a direct IPv6 path:

**Root cause:** UFW on star-kitten had an empty `ufw6-user-input` chain (policy DROP) — packets arrived at the NIC but were dropped before reaching the JVB socket.

**Fix applied:**
```bash
# On star-kitten (persistent across reboots)
sudo ufw allow 10000/udp
```

SFR box IPv6 firewall rule added for JVB: `jvb-v6` → star-kitten `fa75:a4ff:fef9:2fe9` UDP 10000.

Confirmed: SFR 5G phone (`2a0d:e487:…`) → JVB IPv6 direct, DTLS 1.2 complete.

---

## TURN server — AWS Lightsail (2026-08-01)

IPv4 TURN relay is now fully operational via a dedicated Lightsail instance. SFR DS-Lite still blocks inbound IPv4 at the home network's AFTR, so Coturn runs externally with a public IPv4.

**Why Lightsail over the controller:** The controller's public IPv4 (`37.65.57.112`) is the SFR DS-Lite shared address — inbound IPv4 is blocked at the AFTR before it reaches the home router. No router-level fix is possible. Lightsail provides a dedicated public IPv4 outside the DS-Lite NAT.

### Lightsail instance details

| Item | Value |
|------|-------|
| Instance | `turn-coturn-eu` (eu-west-1a, `nano_3_0`) |
| OS | Ubuntu 22.04 LTS |
| Static IP | `54.171.137.209` |
| Tailscale IP | `100.77.251.92` |
| Relay ports | UDP 49152–65535 |
| Cost | $5.00/month |

### Coturn config (`/etc/turnserver.conf`)

```
listening-port=3478
listening-ip=0.0.0.0
external-ip=54.171.137.209
relay-ip=100.77.251.92
min-port=49152
max-port=65535
realm=devandre.sbs
use-auth-secret
static-auth-secret=<Vault platform/jitsi.coturn-secret>
log-file=/var/log/coturn/turnserver.log
```

### Operations

```bash
# SSH to TURN instance
ssh -i ~/.ssh/lightsail-turn-coturn.pem ubuntu@54.171.137.209

# Coturn status + logs
sudo systemctl status coturn
sudo tail -f /var/log/coturn/turnserver.log

# Restart
sudo systemctl restart coturn

# Tailscale status
sudo tailscale status
```

---

## JVB pinned to star-kitten

JVB uses `hostNetwork: true` — it binds directly to the node's UDP 10000. It must be pinned to the node with the correct firewall rules:

```yaml
nodeSelector:
  kubernetes.io/hostname: star-kitten
```

If star-kitten is NotReady, the JVB pod stays Pending and video calls fail.

---

## Real-world skills demonstrated

| Skill | Industry context |
|-------|-----------------|
| **hostNetwork for media traffic** | Standard for SFU/RTP bridges — avoids double NAT through kube-proxy |
| **TURN server for NAT traversal** | Required for any WebRTC deployment with non-cooperative NATs |
| **IPv6 fallback path** | Carrier-grade NAT (DS-Lite) is common in French ISPs — IPv6 direct is the only reliable path |
| **Lightsail VPS for TURN relay** | Cheap public IPv4 endpoint ($5/month) outside CGNAT — standard pattern for home-lab WebRTC |
| **Tailscale mesh for relay routing** | TURN instance relays to JVB via Tailscale without exposing JVB directly to the internet |
| **Authentik proxy for WebRTC apps** | Forward auth that doesn't break WebSocket or long-polling connections |
