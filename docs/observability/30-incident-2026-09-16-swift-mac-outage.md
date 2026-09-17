---
id: incident-2026-09-16-swift-mac-outage
title: "Incident postmortem — swift-mac node outage + silent alerting + mail 502 (2026-09-16→18)"
sidebar_label: "PM: swift-mac outage (2026-09)"
---

# Incident postmortem — swift-mac node outage, silent alerting, and the mail 502

**Date:** 2026-09-16 → 2026-09-18 · **Severity:** SEV-2 (degraded platform, no data loss) ·
**Status:** Resolved

> One node failure cascaded into ~40 unhealthy pods, went **14 hours with no notification**, and
> surfaced two further latent problems (a broken alert-email transport and a stale ingress datapath).
> This documents all three, because the interesting failures were the *hidden* ones.

## TL;DR
- **swift-mac** (the MacBook Pro 2012 Longhorn storage node) went `NotReady` ~2026-09-16 13:31 UTC for
  ~14h. Its Longhorn RWO volumes stuck → dependent workloads (retrieva dev DB/Redis, litellm's Postgres,
  Grafana, etc.) could not reschedule → **~40 pods degraded**.
- **No alert reached the owner for 14h.** Two independent failures in the notification path.
- Recovery began when the node was powered back on (Longhorn detached the volumes and pods recovered).
- Investigation then fixed: alert **routing** (node-down was email-blind), the alert **transport**
  (Alertmanager→SES direct, Stalwart relay bypassed), and later a **mail webadmin 502** (stale Cilium
  state on the ingress controller).

## Impact
| Area | Impact |
|---|---|
| retrieva **dev** | backend CrashLoopBackOff (~80 restarts) — DB + Redis unreachable |
| retrieva **prod** | fragile: prod Postgres pod stuck `Terminating`; API on one surviving pod (near-miss) |
| litellm (AI gateway) | crashlooping (separate 6-day incident, see below) |
| Grafana, open-webui, mlflow, langfuse, plane, matrix, … | Pending / Terminating |
| **Alerting** | **silent for 14h** |
| Data | **none lost** |

## Timeline (UTC)
- **09-16 13:31** — swift-mac kubelet stops (`NodeStatusUnknown`). Longhorn volumes on it stick.
- **09-16 13:31 → 09-17 ~03:xx** — ~40 pods degraded; **no notification** delivered.
- **09-17 ~03:00** — owner notices via retrieva dev issues during unrelated work; investigation starts.
- **09-17** — node powered back on → `Ready`; Longhorn detaches; pods recover (40 → ~11).
- **09-17** — alert **routing** fixed (#1143); alert **transport** moved to SES-direct (#1152);
  litellm restored (GC'd Postgres image re-pushed from a node's containerd cache).
- **09-18** — mail webadmin **502** root-caused (stale Cilium state on the ingress controller) and fixed
  by a controller rolling-restart; a wrong keepalive change was made and reverted along the way.

## Root causes

### 1. The node outage (primary)
swift-mac (2012 MacBook, Longhorn storage node) went down. Because it is a **storage** node, its
RWO Longhorn volumes could not detach to a dead node, so every pod bound to those volumes was stuck.
Compounded by **star-kitten being cordoned** since 2026-09-11 (less reschedule capacity).

### 2. Silent alerting — TWO independent failures
This is the most important lesson: **detection worked, delivery didn't.**
- **Routing gap:** `KubeNodeNotReady` is `severity=warning`, which routed to a webhook only — **no
  email**. Only the slower `NodeDown` (`severity=critical`, `for: 10m`) emailed. → **Fix #1143:** a
  dedicated route sends `KubeNodeNotReady|KubeNodeUnreachable|NodeDown|KubeletDown|LonghornNodeNotReady|
  NodeReadonlyFilesystem` to the critical receiver (email + Slack) regardless of severity.
- **Transport gap:** even critical alerts emailed **through in-cluster Stalwart**, whose **outbound SES
  relay silently drops mail** (accepts + queues, never delivers — verified by A/B test; SES→Gmail works
  when sent directly). → **Fix #1152:** Alertmanager now sends **via SES directly**
  (`email-smtp.eu-west-1.amazonaws.com:587`), password via ESO-mounted file (never in the public repo),
  removing the fragile in-cluster hop *and* a previously plaintext-committed Stalwart password.
- **No out-of-band channel:** email via in-cluster mail can itself be an outage casualty (Grafana was
  Pending during this very incident). A phone push (ntfy/Telegram) is still recommended — tracked in #1149.

### 3. Collateral — litellm down 6 days (pre-existing, unrelated to swift-mac)
litellm crashlooped because its Postgres image (`library/postgresql:18.4.0-noavx512`, a custom
no-AVX512 pgvector build for the older ThinkPad CPUs) had been **GC'd out of Harbor**, along with its
Bitnami base. Restored by **exporting the image from a node's containerd cache and `crane push`ing it
back** to Harbor — no rebuild needed. Systemic cause (Harbor GC deleting in-use images) tracked in #1146.

### 4. mail.devandre.sbs 502 — stale Cilium ingress datapath
After the Stalwart pod restarted (new Cilium endpoint identity + pod IP), the long-running (59-day)
**nginx ingress controller** kept **stale conntrack/BPF datapath state** for the *old* Stalwart endpoint
and **RST'd every connection to the new pod** → 502. Fresh pods had clean state and connected fine
(the misleading clue that caused a wrong "keepalive" diagnosis + a global nginx change that was reverted,
#1156/#1158). **Fix:** `kubectl rollout restart deployment/nginx-ingress-ingress-nginx-controller -n ingress-nginx`.
This is why it "worked before": nothing was wrong until Stalwart's pod identity changed and the
controller never refreshed.

## What went well
- No data loss; Longhorn volumes intact.
- The node power-on cleanly triggered auto-recovery of most workloads.
- Root causes were traced to ground truth (packet captures, A/B tests) rather than left as guesses.

## What went wrong / lessons
1. **A node died for 14h with zero notification** — the headline failure. Detection was fine; the
   *delivery* path had two breaks. Alerting is only as good as its least-reliable delivery hop.
2. **Alert email depended on in-cluster components** (Stalwart) that can fail *with* the cluster.
3. **Confident-but-wrong diagnosis** (keepalive) led to a global change that didn't help — reverted.
   The correct anchor was "**it worked before → what changed?**" (Stalwart's pod identity had changed).
4. **Harbor GC keeps deleting in-use images** (the litellm cause) — a recurring systemic issue.

## Action items
| # | Action | Issue | Priority | Status |
|---|---|---|---|---|
| 1 | Node/storage-down alerts always email + Slack | #1143 | P1 | ✅ done |
| 2 | Alertmanager → SES direct (bypass Stalwart) | #1152 | P1 | ✅ done |
| 3 | Out-of-band phone alert (ntfy/Telegram) + verify Gmail delivery + cut noise | #1149 | P2 | ⏳ open |
| 4 | Harden Harbor GC so in-use images aren't deleted | #1146 | P1 | ⏳ open |
| 5 | Fix Stalwart outbound SES relay (all platform mail) | #1154 | P2 | ⏳ open |
| 6 | litellm-cache (Redis) stuck Pending — Longhorn PV affinity | #1147 | P2 | ⏳ open |
| 7 | star-kitten cordoned — uncordon/decommission | #1148 | P3 | ✅ uncordoned |
| 8 | Prune/rotate invalid AWS keys in Vault | #1155 | P3 | ⏳ open |
| 9 | mail 502 — controller stale-datapath (recurrence: restart controller) | #1154 | — | ✅ fixed |

## Runbook — if this recurs
- **A storage node is down / RWO volumes stuck:** power the node back on first (Longhorn auto-detaches);
  if the node is truly dead, migrate Longhorn replicas to healthy nodes before force-deleting stuck pods.
- **"No alert but something's clearly broken":** check Alertmanager is firing (`alertmanager.10.0.0.200.nip.io`)
  and that the **transport** works — send a test critical alert and confirm Gmail receipt. Email path is
  Alertmanager → SES-direct now (not Stalwart).
- **A public service 502s but is healthy internally** (works via `kubectl port-forward svc/... `, fails via
  the URL) after a backend pod restart: **rolling-restart the nginx ingress controller** to clear stale
  Cilium datapath state.
- **An in-use image vanished from Harbor (ImagePullBackOff, NotFound):** check node containerd caches
  (`sudo k3s ctr images ls | grep <image>`), export + `crane push` back; then fix retention (#1146).

**Refs:** issues #1143 #1146 #1147 #1148 #1149 #1152 #1154 #1155 · [Day-2 operations](./lifecycle-day2-operations)
