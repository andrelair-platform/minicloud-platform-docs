---
id: power-broker
title: Webhook Power Broker
sidebar_position: 12
---

# MAAS Webhook Power Broker

Deployed 2026-07-31. Replaces `power_type: manual` for all four ThinkPad cluster nodes with a real automated power control path.

---

## Why a Custom Broker

The ThinkPad nodes have no out-of-band management (no IPMI, no Redfish, no iDRAC). MAAS's built-in power drivers require hardware BMC access. The webhook driver fills the gap: MAAS calls an HTTP endpoint, the broker translates the call into the appropriate OS-level action.

| Action | Method |
|--------|--------|
| Power on | Wake-on-LAN magic packet (UDP broadcast on `10.0.0.255`) |
| Power off | SSH → `sudo poweroff` |
| Power reset | SSH → `sudo reboot` |
| Power query | ICMP ping (1 s timeout) |

---

## Deployment

**Service file:** `~/.config/systemd/user/maas-power-broker.service`  
**Script:** `/home/ktayl/bin/maas-power-broker.py`  
**Binding:** `0.0.0.0:5241` (all interfaces, including `10.0.0.1` management)  
**Linger:** enabled — service starts at boot without ktayl login session

```bash
# Check status
systemctl --user status maas-power-broker.service

# Restart after script changes
systemctl --user restart maas-power-broker.service
```

---

## API

All endpoints accept `GET` and `POST` (MAAS uses both depending on context).

| Endpoint | Returns |
|----------|---------|
| `GET/POST http://10.0.0.1:5241/power/on/<hostname>` | `{"status": "wol-sent", "mac": "..."}` |
| `GET/POST http://10.0.0.1:5241/power/off/<hostname>` | `{"status": "stopped"}` or `{"status": "error-ssh-failed"}` |
| `GET/POST http://10.0.0.1:5241/power/reset/<hostname>` | `{"status": "restarting"}` or `{"status": "error-ssh-failed"}` |
| `GET/POST http://10.0.0.1:5241/power/query/<hostname>` | `{"status": "running"}` or `{"status": "stopped"}` |

MAAS webhook regex config:
- `power_on_regex`: `status.*\:.*running`
- `power_off_regex`: `status.*\:.*stopped`

**Node map** (hostnames recognised by the broker):

| Hostname | IP | MAC |
|----------|----|-----|
| `set-hog` | `10.0.0.2` | `38:f3:ab:92:35:3f` |
| `fast-skunk` | `10.0.0.4` | `f8:75:a4:dd:dc:59` |
| `fast-heron` | `10.0.0.7` | `f8:75:a4:dd:e5:2d` |
| `star-kitten` | `10.0.0.8` | `f8:75:a4:f9:2f:e9` |

---

## MAAS Power Parameters

All four machines are configured with `power_type: webhook` pointing at `10.0.0.1:5241`. Using the management IP (not `127.0.0.1`) is required for MAAS 3.7's Temporal dispatch to work — see [Troubleshooting: Issue 8 - MAAS Temporal Power Dispatch Fails](troubleshooting) for the full explanation.

```bash
# View current power params for a machine
maas ktayl machine power-parameters <system_id>

# Update if needed (replace <hostname> and <system_id>)
maas ktayl machine update <system_id> power_type=webhook power_parameters='{
  "power_on_uri":   "http://10.0.0.1:5241/power/on/<hostname>",
  "power_off_uri":  "http://10.0.0.1:5241/power/off/<hostname>",
  "power_query_uri":"http://10.0.0.1:5241/power/query/<hostname>",
  "power_on_regex": "status.*\\:.*running",
  "power_off_regex":"status.*\\:.*stopped",
  "power_verify_ssl":"n",
  "power_user":"", "power_pass":"", "power_token":""
}'
```

---

## Known Limitations

**Wake-on-LAN requires BIOS configuration.** ThinkPads ship with WoL disabled. Enable it in the BIOS under Security → Config → Network (exact path varies by model). Until enabled, `power-on` sends the magic packet but the node does not respond.

**Power-off and reset require SSH.** If `sshd` is not running (e.g. node kernel-panicked, kubelet crash loop with OOM killing sshd), power-off and reset will fail. Use MAAS WoL as a recovery path only after a physical hard reset restores SSH access.

**Power query uses ping only.** A node that is running but has an unreachable network interface will report `stopped`. This is intentional — ping is fast (~1 s) and sufficient for MAAS's lifecycle state machine in this single-subnet setup.

---

## Quick Test

```bash
# Direct broker test (bypasses MAAS Temporal)
curl -s http://10.0.0.1:5241/power/query/fast-skunk | python3 -m json.tool

# Via MAAS CLI (goes through Temporal workflow engine)
maas ktayl machine query-power-state sby3w7
maas ktayl machine power-on sby3w7
```
