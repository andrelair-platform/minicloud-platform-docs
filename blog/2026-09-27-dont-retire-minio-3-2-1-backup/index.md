---
slug: dont-retire-minio-3-2-1-backup
title: "3-2-1, Not 1: Why I Kept MinIO Instead of Going Cloud-Only for Backups"
authors: [andrelair]
tags: [backup, disaster-recovery, minio, cloudflare-r2, velero, dora, 3-2-1, object-storage, platform-engineering, reliability]
date: 2026-09-27
description: "It's tempting to delete the backup server and push everything to cheap cloud object storage. On the ktayl-solution platform I decided not to — and an hour later I fat-fingered a bucket delete that proved exactly why. This is the reasoning behind keeping a local MinIO alongside Cloudflare R2, and where the cloud instinct is actually right."
---

While hardening disaster recovery on the ktayl-solution information system, a fair question came up: *we already mirror backups to Cloudflare R2 — so why keep a MinIO server running on the controller at all? Couldn't we retire it and go cloud-only?*

R2's free tier is generous, cloud object storage is durable, and one less service to operate is always appealing. So it's a reasonable instinct. It's also **wrong** — and about an hour after I talked myself through why, I proved it the hard way by deleting the wrong bucket prefix. This post is that reasoning, and the honest incident that validated it.

{/* truncate */}

## The rule the instinct forgets: 3-2-1

The backup discipline that has survived every fashion cycle is **3-2-1**: at least **3** copies of your data, on **2** different media/locations, with **1** off-site. The whole point is that the copies fail *independently* — a fire, a ransomware event, a billing lockout, or a human fat-finger should never be able to take out more than one of them at a time.

The mistake in "let's go cloud-only" is treating MinIO and R2 as **redundant**. They're not — they're the two *halves* of a 3-2-1:

|                        | MinIO (on the controller)                                 | Cloud (R2 / Blob / S3)                                |
| ---------------------- | --------------------------------------------------------- | ----------------------------------------------------- |
| **Role**               | local **primary** — fast restore; the drills read from it | **off-site DR** — geographic + provider separation    |
| **Restore speed**      | LAN, instant, free                                        | WAN + egress (R2 is zero-egress ✓; S3/Azure bill it)  |
| **Internet-independent** | ✅ restores work during an ISP outage                   | ❌ needs the internet to be up                        |
| **Cost**               | free (just disk)                                          | free within limits; egress risk on S3/Azure           |

Retiring MinIO to go cloud-only isn't "simplifying to two copies." It's collapsing **from 3-2-1 to one location**. That is strictly *less* resilient, not more.

## Why MinIO-on-the-controller is good design, not tech debt

Three properties make the local copy pull real weight:

**1. It lives outside the thing it backs up.** MinIO runs on the *controller* — a separate machine from the six k3s nodes it protects. Backups should never live inside the cluster they back up; if the cluster dies, in-cluster backups die with it. A separate failure domain is correct hygiene, not a SPOF waiting to happen.

**2. Restores are LAN-fast and free.** The daily restore drill — which actually loads a dump into a throwaway Postgres and asserts row counts, because *a backup you haven't restored is a hypothesis* — reads from MinIO over the local network. Instant, no egress. Go cloud-only and every drill and every real recovery now pays WAN latency and (on S3/Azure) egress fees. You'll be tempted to drill less. Don't build an architecture that punishes you for testing recovery.

**3. It's air-gapped from your cloud account.** This is the one people underweight. A cloud account can be billing-locked, credential-compromised, or — my personal favourite — **fat-fingered**.

## The incident that proved the point (an hour later)

While migrating a CloudNativePG cluster's backup target to a dedicated bucket, I deleted the *old* WAL-archive prefix to clean up. It was the right operation on the wrong assumption: a Postgres standby was mid-`pg_rewind`, and `pg_rewind --restore-target-wal` fetches missing WAL **from that archive**. I'd just removed the segments it needed. The replica went into a crash-loop.

It was fully recoverable — the primary was healthy, so I re-bootstrapped the standby from scratch and codified the lesson (*keep the old WAL until every replica is healthy on the new store*). No data was lost. But sit with the counterfactual for a second: **if that archive had been my only copy of a primary's backups, a single careless `rm` would have been unrecoverable.** That is the failure mode 3-2-1 exists to prevent, and it's exactly the failure mode "cloud-only" walks straight into. Human error doesn't respect a provider's eleven 9s of durability — durability protects you from *their* disk dying, not from *you* deleting the object.

## Where the cloud instinct is genuinely right

None of this means "avoid the cloud." The off-site half of 3-2-1 **is** cloud, and it should be. On this platform MinIO mirrors to **Cloudflare R2** — 10 GB always-free with **zero egress**, which is the single best off-site object target of the three big options (S3 and Azure Blob both charge to pull your data back out *when you can least afford friction* — during a restore).

The correct place to spend the "more cloud" instinct is **diversifying the off-site tier**, not replacing the local one. Adding a *second* cloud (Azure Blob or S3) as an additional off-site copy buys you **multi-cloud DR** — protection against a single provider outage or account lockout, which for a regulated insurer maps directly to **DORA Art. 28–29 (ICT concentration risk)**. But it's an *addition*, sized to a free tier, not a substitute. And honestly, R2's zero-egress + 10 GB already covers the need well enough that a second cloud is a nice-to-have, not urgent.

## The net, and how it shows up in the design

> Keep **MinIO** (local, primary, LAN-fast, air-gapped) **+ R2** (off-site, zero-egress). Optionally add a second cloud off-site later for concentration-risk cover. Never trade the local copy away for the off-site one.

This isn't abstract — it decides where new backups *go*. When I built app-consistent logical dumps for the two most business-critical databases (the insurance policy DB and the ERP), they write to **MinIO** `db-logical/`, which then mirrors to R2. That gives each of them the full 3-2-1: the volume snapshot (Velero), the local logical dump (MinIO), and the off-site copy (R2) — three copies, two media, one off-site.

The lesson isn't "cloud bad, local good." It's that **resilience comes from *independent* copies, and the cheapest way to lose that independence is to talk yourself into deleting one.** I almost did — and then a stray `rm` reminded me why I hadn't.
