---
slug: dr-is-not-cyber-recovery
title: "DR Is Not Cyber Recovery — Building an Immutable, Ransomware-Proof Backup Vault"
authors: [andrelair]
tags: [backup, disaster-recovery, cyber-recovery, aws, object-lock, vault, security, dora, sre, carnets]
date: 2026-11-27
description: "Reviewing the platform's DR, I realised the off-site backups were deletable — which survives a dead server but not a compromised operator or ransomware. So I added a third storage layer: an immutable AWS S3 Object Lock vault, and proved I could recover Vault from it in 37 seconds using a single off-cluster key. Here's the distinction DR hides, and the trade-offs I made."
---

I went to double-check the platform's disaster recovery and found something uncomfortable. The crown
jewels — the k3s **kine** control-plane database and the **Vault** raft snapshot — *were* mirrored
off-site to Cloudflare R2. Good. But every object in R2 is **deletable by anyone holding the creds.**

That protects me from one failure (my controller dies, the site burns down — I rebuild from R2) and
leaves me wide open to a very different one: **a compromised operator, or ransomware, that deletes the
backups themselves.** Off-site is not the same as un-deletable.

{/* truncate */}

## The distinction DR hides

Two failures, two different answers:

| | **Disaster Recovery** | **Cyber Recovery** |
|---|---|---|
| The question | "my site is destroyed — rebuild it" | "my infra is compromised and my backups may be deleted — recover a known-good state anyway" |
| What it needs | an off-site copy | an **immutable** copy an attacker **cannot erase** |
| Here | Cloudflare R2 | **AWS S3 + Object Lock** |

I had DR. I didn't have Cyber Recovery. So I built the third layer:

```
MinIO (operational)  →  Cloudflare R2 (Disaster Recovery)  →  AWS S3 + Object Lock (Cyber Recovery)
LAN, fast restore        off-site, deletable                   immutable (WORM), independent provider
```

## What I built

A daily job on the controller copies the crown jewels (~650 MiB) into an **S3 bucket with Object Lock**.
Three properties mattered:

- **Immutable (WORM).** Object Lock in **COMPLIANCE** mode: once written, no one — not the writer, not an
  admin, **not root** — can delete or shorten retention for 35 days. That's the anti-ransomware guarantee.
- **No static key anywhere.** The copy job mints **short-lived STS** via Vault's AWS secrets engine (an
  `assumed_role` with an *add-only* S3 policy — `PutObject`, no `Delete`, no `BypassGovernanceRetention`).
  Nothing static lands on disk, in Git, or in Terraform state.
- **Independent provider.** AWS ≠ Cloudflare, so the vault also survives a Cloudflare-account compromise.
  Meeting DORA's cloud-concentration concern is a side effect, not an afterthought.

## The trade-offs I actually weighed

**R2 Bucket Locks vs AWS S3 Object Lock.** Cloudflare R2 now offers object retention too — so immutability
*alone* didn't force AWS. I chose AWS because it adds **provider independence**, mature **COMPLIANCE-mode**
guarantees, and real IAM-isolation practice. R2 stays the DR layer; it isn't *also* the cyber layer.

**Glacier? No.** Glacier Deep Archive is almost free, but its 9–48 h retrieval would trade my RTO for
pennies. A recovery vault is **S3 Standard** — immediate retrieval. Cheap storage is worthless if you
can't get the data back fast.

**GOVERNANCE → COMPLIANCE.** I ran in GOVERNANCE (a privileged identity can still fix a mistake) until a
restore drill proved the cadence, then flipped to COMPLIANCE. That flip is a **one-way door**: the bucket
can't even be `terraform destroy`-ed while locked objects exist. For a cyber-recovery vault, that's the
point — not a bug.

## An untested backup is a hypothesis

So I tested it. Twice.

1. **Normal restore.** Pull a snapshot from the vault, restore it into a throwaway Vault running the same
   image with the same AWS KMS auto-unseal, read a witness value back. **RTO ≈ 15 seconds.** It matched,
   source to restore.

2. **The real cyber scenario — off-cluster.** In a compromise, the on-cluster Vault may be *gone*, so
   recovery must not depend on it (that would be circular). I provisioned a least-privilege
   `cyber-recovery-break-glass` identity (read the vault + the Vault-seal KMS ops), stored its key
   **age-encrypted off-cluster**, and ran the whole restore with **that key alone** — no cluster, no
   on-cluster Vault. **RTO 37 seconds.** Vault came back, secrets readable.

That's the sentence I can now say honestly: *if my cluster and my secret store are both destroyed, I can
rebuild Vault from an immutable copy an attacker can't touch, in under a minute, with one off-cluster key.*

## Two lessons that stuck

- **Immutability ≠ off-site, and off-site ≠ immutable.** They're orthogonal. You need both, and you need
  to say which failure each one answers.
- **A credential moves from a terminal to its vault — never through a conversation.** I learned this the
  blunt way mid-build (a key pasted where it shouldn't be), rotated it in seconds, and moved on. The
  discipline — rotate-on-exposure, least privilege, no static keys — *is* the deliverable an auditor checks.

*(ktayl is a fictional insurer used as an engineering lab — synthetic data, no real customers. The
engineering, the trade-offs and the measured RTOs are real; the company is a stage.)*
