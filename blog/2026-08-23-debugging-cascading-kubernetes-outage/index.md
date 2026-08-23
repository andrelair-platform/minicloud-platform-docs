---
slug: debugging-cascading-kubernetes-outage
title: "Anatomy of a Cascading Kubernetes Outage: When the First Symptom Is Three Layers From the Cause"
authors: [andrelair]
tags: [kubernetes, sre, incident-response, post-mortem, k3s, longhorn, gitops, argocd, cilium, reliability, storage, dns]
date: 2026-08-23
description: "A disk filled up. Then cluster DNS died. Then storage volumes refused to rebuild. The obvious cause was a symptom — the real culprit was a bloated SQLite write-ahead log starving the storage layer. Here is the full debugging trail, the fix, and the prevention that shipped afterward."
---

A monitoring alert fired: the platform watchdog was `DOWN`. Within minutes the picture looked ugly — cluster DNS was refusing connections, and shortly after, distributed-storage volumes stopped rebuilding. A textbook cascade.

This is the full post-mortem: how the outage propagated, why the *obvious* cause turned out to be a symptom three layers from the root, the fix, and — more importantly — the prevention that shipped so it can't recur the same way. Every change referenced here is a public, reviewable pull request.

The platform in question — **minicloud** — is a production-grade Kubernetes environment running on refurbished ThinkPads, built and operated solo as a simulation of an enterprise information system. Bare metal, no managed control plane, no safety net. Which is exactly why it's a good teacher.

{/* truncate */}

## The cascade, top to bottom

The alert said "DNS down." Chasing that first would have been a waste of an hour. Here is what was actually happening, from symptom down to root:

```
watchdog DOWN (the alert)
  └─ cluster DNS refusing connections
       └─ the controller's DNS service (bind9) had crashed
            └─ its database (MAAS-bundled PostgreSQL) had crashed
                 └─ the controller's root disk had hit 100% full
```

The disk had filled because a backup group kept rebuilding two large, re-creatable volumes (a container registry cache and an analytics store) that should have been excluded — the exclusion existed in code, but a stale label on the live objects kept them in the backup set. Classic drift between "what git says" and "what's actually running."

So the *first* fix was mundane: reclaim the disk (delete the orphaned backup data through the object store's own API, since a 100%-full disk blocks most other approaches), then restart the DNS service. DNS came back. Alert cleared.

If that were the whole story, it wouldn't be worth writing about.

## The second, deeper failure: storage that wouldn't heal

With the cluster reachable again, the storage layer (Longhorn) was a mess — roughly twenty volumes showed `degraded`, each running on a single replica instead of three. Normally Longhorn just rebuilds the missing replicas. It wasn't.

I'd kick a reconcile, watch a burst of rebuild activity start… and then stall. The rebuilds would begin and give up, repeatedly. No obvious errors. Plenty of free disk and schedulable nodes. The setting that governs rebuild concurrency was correct.

This is the part that matters, because the answer wasn't in the storage layer at all.

## Root cause: a write-ahead log was starving the rebuild loop

k3s stores cluster state in SQLite (via kine) rather than etcd — common on bare metal. When a cluster is *crash-stopped* (power cut, hard reboot) instead of shut down cleanly, kine never gets to checkpoint its **write-ahead log (WAL)**. The WAL bloats. On restart, every API read has to replay a huge WAL, and the whole Kubernetes API slows to a crawl.

A slow API has a non-obvious downstream victim: **Longhorn's rebuild controller depends on timely API calls to coordinate replica rebuilds.** When the API is molasses, the rebuild loop kicks off work, can't drive it to completion in time, and backs off. It *looks* like a storage problem. It's actually a control-plane-datastore problem wearing a storage costume.

The fix was a clean restart of k3s on the control-plane node, which forces kine to checkpoint the WAL:

```text
# WAL size, before → after a clean checkpoint:
state.db-wal   914 MB  →  111 MB

# API responsiveness, during the incident → after:
kubectl get nodes   >15s (timed out)  →  0.7s
```

The moment the API was fast again, the rebuilds flowed and completed. Verified after recovery:

```console
$ kubectl get nodes
NODE            STATUS   VERSION
fast-heron      Ready    v1.36.3+k3s1
fast-skunk      Ready    v1.36.3+k3s1
loving-gannet   Ready    v1.36.3+k3s1
set-hog         Ready    v1.36.3+k3s1
star-kitten     Ready    v1.36.3+k3s1
swift-mac       Ready    v1.36.3+k3s1

$ # kubectl get nodes latency:
717ms          # during the incident: timed out (>15s)

$ # Longhorn volume health:
robustness: {'healthy': 42, 'unknown': 1}   # 1 = a detached/idle volume, not degraded
```

## Fixing the fix: prevention, not just recovery

Recovering an outage is table stakes. The real work is making sure the same class of failure can't recur silently. Three things shipped:

**1. Never crash-stop the cluster again.** The entire WAL-bloat problem exists only because the cluster was hard-stopped. So I wrote a graceful shutdown script that cordons workers, stops the agents, and cleanly stops k3s on the control-plane node — which *checkpoints the WAL as part of a clean stop*. A matching startup script waits for the API and uncordons. Cold starts now come back in minutes with a small WAL, not hours of rebuild storms.

**2. Self-healing DNS.** The DNS service can get left disabled after a crash or an automated restart of the provisioning stack. A small systemd guard now re-asserts it on boot and on a short interval, so DNS can't stay down for more than a couple of minutes regardless of what knocked it over. It proved itself the same week — a node reboot brought DNS back with zero intervention.

**3. A backup that can't livelock.** The control-plane backup was doing `sqlite3 .backup`, which uses the online-backup API — and that API *restarts the copy whenever the source is written.* On a busy, now-larger database, it livelocked and never finished. Switched it to `VACUUM INTO`, a single-transaction consistent snapshot that also compacts the database: it completes in seconds instead of hanging for ten-plus minutes. The image was also made self-contained so a backup never depends on reaching the internet mid-incident.

## The changes (public, reviewable)

Everything above landed as pull requests on the GitOps repository — timestamped, CI-checked, reviewable:

| PR | What |
|----|------|
| **#765** | Storage labeler actively strips the stale backup label (the drift that filled the disk) |
| **#766** | Control-plane backup: self-contained image + `VACUUM INTO` (no livelock, no internet dependency) |
| **#767** | Admission-policy exemption hygiene (a stale security finding, correctly re-scoped to the real subject) |
| **#768** | Network micro-segmentation for the AI-agent and workflow namespaces (default-deny egress, internet blocked, cluster-internal allowed) |
| **#770** | GitOps drift fix: ignore an operator-managed status field on a CRD (so *real* drift stands out) |
| **#771** | Removed a stale manifest for a deleted namespace that was silently failing every sync of that app |

A representative verification, post-change — the AI-agent namespace can reach its internal LLM gateway but is blocked from the public internet, and the hardened admission policies report zero violations:

```console
$ # egress enforcement from an AI-agent pod:
internal LiteLLM   : reachable
public internet    : BLOCKED

$ # Gatekeeper policy violations after remediation:
no-privileged-containers: totalViolations=0
block-net-raw:            totalViolations=0
```

## What I'd underline for anyone operating bare-metal Kubernetes

- **The first symptom is almost never the root cause.** "DNS is down" was four layers up from "the disk filled because of config drift." Chase the chain, not the top of it.
- **A slow control-plane API has blast radius you won't predict.** It didn't just make `kubectl` sluggish — it silently broke self-healing storage. When something *should* be recovering and isn't, check whether the control plane can keep up.
- **Clean shutdown is a feature, not a nicety.** On SQLite-backed k3s, a graceful stop that checkpoints the WAL is the difference between a two-minute reboot and a two-hour rebuild storm. It's free. Write the script.
- **Fix the recurrence, not just the incident.** The outage was ~fixed in the first hour. The next four hours — the prevention scripts, the backup rewrite, the drift fixes — are what actually made the platform more reliable than it was before it broke.

Same week, on the now-healthy cluster, I also added a sixth node end-to-end via bare-metal PXE provisioning (network-boot → hardware inventory → OS install → cluster join), which is why the `kubectl get nodes` output above shows six. Growth and hardening in the same stretch — which is roughly the point of running your own platform: every failure is a curriculum.

---

*minicloud is a solo-built, production-grade Kubernetes platform on refurbished hardware, delivered entirely through GitOps. If you operate bare-metal or edge Kubernetes and hit something similar, I'd genuinely like to compare notes.*
