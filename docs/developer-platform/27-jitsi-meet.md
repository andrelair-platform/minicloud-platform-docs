---
id: jitsi-meet
title: Phase 77 — Jitsi Meet + Coturn
sidebar_position: 27
---

# Phase 77 — Jitsi Meet + Coturn TURN Server

**Deployed:** 2026-07-26 | **Version:** Jitsi Meet v2.21.0 | **Namespace:** `collab`

Jitsi Meet provides self-hosted video conferencing. The platform deploys the full Jitsi stack (web, prosody, jicofo, JVB) plus a Coturn TURN server on the controller for clients that cannot establish direct peer connections.

---

## Architecture

```
External caller
   │
   ├─ IPv6 capable → JVB direct (star-kitten:10000/udp, hostNetwork)
   │
   └─ IPv4 only → TURN relay (SFR DS-Lite blocks inbound IPv4 at AFTR
                               → TURN IPv4 relay not currently reachable
                               → AWS Lightsail VPS planned for future)

JVB (Jitsi Video Bridge) — star-kitten (10.0.0.8), hostNetwork, UDP 10000
Prosody / Jicofo / Web  — collab namespace, nginx ingress
Coturn TURN server      — Docker + systemd on controller (192.168.1.130:3478)
```

| Component | Detail |
|-----------|--------|
| Helm chart | `jitsi-contrib/jitsi-meet` |
| JVB node | star-kitten (`10.0.0.8`) — pinned via nodeSelector |
| JVB port | UDP 10000, hostNetwork (bypasses kube-proxy) |
| Auth | Authentik forward auth (provider pk 15, `forward_single`) |
| Coturn | v4.6, Docker on controller, `192.168.1.130:3478`, relay `49152–49199` |
| DNS | `turn.devandre.sbs → 37.65.57.112` (unproxied, UDP) |
| TURN credentials | Vault `platform/jitsi` → prosody `extraEnvFrom` |

---

## IPv6 direct path fix (2026-07-28)

SFR DS-Lite WAN blocks all inbound IPv4 at the AFTR carrier, so Coturn IPv4 TURN relay cannot work for external callers. Jitsi still works for mobile/IPv6 callers via a direct IPv6 path:

**Root cause:** UFW on star-kitten had an empty `ufw6-user-input` chain (policy DROP) — packets arrived at the NIC but were dropped before reaching the JVB socket.

**Fix applied:**
```bash
# On star-kitten (persistent across reboots)
sudo ufw allow 10000/udp
```

SFR box IPv6 firewall rule added for JVB: `jvb-v6` → star-kitten `fa75:a4ff:fef9:2fe9` UDP 10000.

Coturn updated with IPv6 listeners and relay IPs. Confirmed: SFR 5G phone (`2a0d:e487:…`) → JVB IPv6 direct, DTLS 1.2 complete.

---

## TURN server — current status

Coturn is running on the controller (`docker ps --filter name=coturn`) with both IPv4 and IPv6 listeners configured. IPv4 TURN relay for external callers is blocked by SFR DS-Lite and cannot be fixed at the router level.

**Planned fix:** Coturn on AWS Lightsail eu-west-1 ($3.50/month, public IPv4 included, joins Tailscale to reach JVB). `turn.devandre.sbs` DNS will point to the Lightsail IP.

---

## Coturn config (controller)

```
~/.coturn/turnserver.conf
listening-ip=192.168.1.130
listening-ip=<controller-ipv6>
external-ip=37.65.57.112/192.168.1.130
listening-port=3478
realm=devandre.sbs
relay-ip=192.168.1.130
relay-ip=<controller-ipv6>
min-port=49152
max-port=49199
```

Restart: `docker restart coturn`

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
| **Authentik proxy for WebRTC apps** | Forward auth that doesn't break WebSocket or long-polling connections |
