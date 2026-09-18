---
id: incident-2026-09-18-inbound-mail-stall
title: "Incident postmortem — inbound mail stall (ses-inbound relay storm) + ArgoCD down (2026-09-18)"
sidebar_label: "PM: inbound mail stall (2026-09)"
---

# Incident postmortem — inbound mail stall (ses-inbound relay storm) + ArgoCD outage

**Date:** 2026-09-18 · **Severity:** SEV-3 (degraded capability, no data loss) · **Status:** Resolved

> Inbound e-mail stopped delivering to mailboxes. It looked like a corrupt mail server begging for a
> volume restore. It was neither corrupt nor the mail server: a **bridge design flaw** turned a backlog
> into a self-inflicted rate-limit storm. Underneath it, a **stale node cordon had taken all of ArgoCD
> offline for ~3h** — which is why the fix wouldn't sync at first. This documents both, because the
> tempting fix (restore the PVC) was the wrong one.

## TL;DR
- **Inbound mail path** is `SES receives → S3 → SQS → ses-inbound bridge pod → SMTP :25 → Stalwart →
  mailbox` — *not* raw internet→:25.
- The **`ses-inbound` bridge relayed every SES recipient to Stalwart**, including **external** To/Cc
  addresses (e.g. `…@gmail.com`) that SES had *already delivered directly*. Stalwart correctly refused
  to relay them (`550 Relay not allowed`), and the **backoff-less retry loop over the backlog** tripped
  Stalwart's **rate limiter** (`452`) so even the *local* recipient stopped delivering — a self-inflicted
  storm, triggered when the [2026-09-16 outage](./30-incident-2026-09-16-swift-mac-outage.md) re-queued a
  backlog.
- **The mail was never corrupt.** The backlog was safe in S3/SQS; a PVC restore would have wiped state
  and fixed nothing.
- Fixed in the **bridge, not the mail server** (gitops #1165 + #1167): filter to local recipients +
  rate-limit-aware backoff + drop poison-pill messages.
- While deploying the fix, ArgoCD wouldn't advance — because **`argocd-server` + `argocd-repo-server`
  were `nodeSelector`-pinned to `fast-skunk`, which carried a stale cordon** (leftover from a completed
  k3s upgrade). Uncordoning the healthy node restored ArgoCD.

## Impact
| Area | Impact |
|---|---|
| **Inbound e-mail** | not delivering to mailboxes; a backlog of ~60 messages held (safe) in S3/SQS |
| **Outbound e-mail** | unaffected (already on SES-direct — see the [swift-mac PM](./30-incident-2026-09-16-swift-mac-outage.md)) |
| **ArgoCD (server + repo-server)** | Pending ~3h (git-sync + UI down) — deployments couldn't reconcile |
| Data | **none lost** — inbound mail preserved in S3/SQS throughout |

## Root cause

### 1. The ses-inbound bridge relayed external recipients (the primary fault)
The bridge (`manifests/stalwart/03-ses-inbound.yaml`, a Python `smtplib` injector) took the SES
`destination` list — **every** To/Cc address — and passed it verbatim to Stalwart:

```
RCPT TO:<kanmegnea@devandre.sbs> → 250 OK            (local, accepted)
RCPT TO:<kanmegnea@gmail.com>    → 550 Relay not allowed   (external — correctly refused)
```

The backlog was Alertmanager alerts addressed to **both** `devandre.sbs` **and** `gmail.com`. The gmail
copy had **already been delivered directly by SES**; relaying it via Stalwart was pointless and earned a
`550` every time. With **no backoff** and **no deletion of failed messages**, the injector hammered
Stalwart in a tight loop over the same poison-pill backlog → tripped Stalwart's **rate limiter, keyed on
the sender identity** (`EHLO ses-inbound.mail.svc.cluster.local`) → even the local recipient then got
`452 Rate limit exceeded` → permanent storm. Live proof:

```
{'kanmegnea@devandre.sbs': (452, 'Rate limit exceeded'), 'kanmegnea@gmail.com': (550, 'Relay not allowed')}
```

Stalwart was behaving **correctly** the entire time (refusing to be an open relay; throttling an abusive
sender). The bug was entirely in the bridge.

### 2. Stale node cordon took ArgoCD offline (the hidden blocker)
`fast-skunk` carried an `unschedulable` cordon added `2026-09-18T03:17:38Z` — a **leftover from a
completed k3s system-upgrade** (the Plan cordons, upgrades, and should uncordon; the uncordon didn't
fire). The node itself was healthy (`Ready`, no resource pressure). But `argocd-server` **and**
`argocd-repo-server` are hard-pinned with `nodeSelector: kubernetes.io/hostname: fast-skunk`, so both had
been **Pending for ~3h** — ArgoCD couldn't fetch new commits, which is why the first fix wouldn't sync.

## Diagnosis method (what isolated it fast)
1. **A fresh-source SMTP probe delivered a full message to BOTH `admin@` and `kanmegnea@devandre.sbs` in
   ~1.2s** → proved the server + mailboxes + SMTP path were 100% healthy, ruling out corruption and
   isolating the fault to the *ses-inbound sender's* throttle bucket.
2. **Replaying one real S3 message** with `smtp.set_debuglevel(1)` showed the exact
   `RCPT TO:<gmail> → 550` + `RCPT TO:<local> → 452` — the smoking gun.
3. Checking `kubectl get pods -n argocd` (during a stuck sync) revealed the Pending ArgoCD pods →
   `FailedScheduling: didn't match Pod's node affinity` → the stale `fast-skunk` cordon.

**Key lesson:** *"inbound broken"* was really *"one client hammering a healthy server with un-relayable
recipients."* Diagnose by **layer** (SES pipeline → SMTP hop → recipient envelope → rate limiter), not
by pattern-matching "mail broken → restore the volume."

## Resolution (what was delivered)
| # | Change | PR |
|---|---|---|
| 1 | Uncordon the healthy `fast-skunk` → ArgoCD `server` + `repo-server` schedule; git-sync restored | (ops) |
| 2 | **ses-inbound: filter recipients to `LOCAL_DOMAINS`** (default `devandre.sbs`) before injecting — external addresses SES already delivered are dropped, killing the `550` storm | [#1165](https://github.com/andrelair-platform/minicloud-gitops/pull/1165) |
| 3 | **Rate-limit-aware backoff** — on a transient `452`, back off `RATE_LIMIT_BACKOFF`=60s so Stalwart's window drains and delivery self-paces under the limit; **drop poison-pill messages** whose local recipient is permanently refused (`550 mailbox does not exist`) instead of retrying forever | [#1167](https://github.com/andrelair-platform/minicloud-gitops/pull/1167) |
| 4 | Pod-template `ses-inbound/injector-version` annotation so a ConfigMap-script change rolls the pod (the running process doesn't re-read the mounted file) | #1165/#1167 |

Stalwart's safe posture is unchanged — it still refuses open relay
(`Allow Relaying = !is_empty(authenticated_as)`). New inbound mail delivers immediately (proven); the
backlog drains automatically as Stalwart's rate window ages out the storm.

## How to verify / operate
```bash
# Inbound path health — deliver a fresh message to a local mailbox (from a fresh source):
kubectl run smtpprobe -n mail --rm -i --restart=Never --image=python:3.12-slim --quiet --command -- \
  python3 -c 'import smtplib; s=smtplib.SMTP("stalwart.mail.svc.cluster.local",25,timeout=20); \
  s.ehlo("probe.test"); s.sendmail("probe@gmail.com",["admin@devandre.sbs"], \
  b"From: probe@gmail.com\r\nTo: admin@devandre.sbs\r\nSubject: probe\r\n\r\nhi\r\n"); print("OK"); s.quit()'

# Bridge behaviour — should show "Delivered … → ['…@devandre.sbs']" and, when throttled,
# "Rate limited, backing off 60s" (NOT a tight 550/452 loop):
kubectl logs -n mail deploy/ses-inbound --tail=20

# Backlog depth (drains to 0 as the window recovers):
kubectl exec -n mail deploy/ses-inbound -- python3 -c \
 'import os,boto3;print(boto3.client("sqs",region_name="eu-west-1").get_queue_attributes(\
  QueueUrl=os.environ["SQS_QUEUE_URL"],AttributeNames=["ApproximateNumberOfMessages"])["Attributes"])'

# Node cordon check (the ArgoCD blocker) — no node should be SchedulingDisabled unexpectedly:
kubectl get nodes | grep -i SchedulingDisabled
```

## Follow-ups
- **ArgoCD single-node pin (fragility):** `argocd-server` + `argocd-repo-server` are `nodeSelector`-pinned
  to `fast-skunk`; if that node is down/cordoned, ArgoCD goes offline. Remove the pin or spread the
  components across nodes.
- **k3s-upgrade uncordon:** the upgrade Plan left `fast-skunk` cordoned. Verify the Plan's uncordon step,
  or add a post-upgrade cordon sweep (k3s system-upgrade Plans use `cordon: true`; the uncordon must run).
- **Alert on stuck cordons / Pending ArgoCD pods** so a stale cordon is caught before it silently blocks
  deployments for hours.

## Related
- [swift-mac node outage postmortem (2026-09-16→18)](./30-incident-2026-09-16-swift-mac-outage.md) — the
  outage that re-queued the inbound backlog and set this off.
- Mail stack: SES relay + inbound pipeline; Stalwart mail server (RocksDB config).
