---
id: cyber-recovery
title: Cyber Recovery — the immutable third backup layer
sidebar_position: 8
---

# Cyber Recovery — immutable, independent-provider backups (AWS S3 Object Lock)

> **As-built, verified 2026-11-26/27.** The third storage layer of the platform's DR, closing the gap a
> normal off-site backup leaves open. Decision of record: [`ADR-0003`](https://github.com/andrelair-platform/minicloud-cloud/blob/main/docs/adr-0003-s3-cyber-recovery.md).
> Objectives live in the [DR RTO/RPO Matrix](./07-dr-rto-rpo-matrix.md).

## Why this exists — **DR ≠ Cyber Recovery**

Two *different* failures need two *different* answers:

| | Disaster Recovery | **Cyber Recovery** |
|---|---|---|
| Question | "my site/controller is **destroyed** — rebuild it" | "my infra is **compromised** and my backups may be **deleted** — recover a known-good state anyway" |
| Here | Cloudflare **R2** (off-site) | **AWS S3 + Object Lock** |

The platform already had DR: the crown jewels (the k3s **kine** control-plane DB + the **Vault** raft
snapshot) mirror off-site to R2. But **every R2 object is deletable by anyone holding the creds** — so R2
survives a *dead controller*, **not** a *compromised operator or ransomware that wipes the backups
themselves*. That second failure needs **immutable** copies on an **independent provider**.

## The three-layer model

```
MinIO (operational)   →   Cloudflare R2 (Disaster Recovery)   →   AWS S3 + Object Lock (Cyber Recovery)
LAN, fast restore          off-site, deletable                     immutable (WORM), independent provider
```

## Architecture

```
controller (05:35 daily cron: cyber-copy.sh)
   │  1. mint SHORT-LIVED STS  ──────────────▶  Vault AWS engine  (aws/sts/cyber-recovery-write)
   │                                             └─ assumes IAM role ktayl-cyber-recovery-writer (ADD-ONLY)
   │  2. aws s3 cp  kine + Vault snapshot  ──▶  s3://minicloud-cyber-recovery-…  (Object Lock COMPLIANCE 35d)
   │     (timestamped keys · skips existing · no static key on disk)
```

- **Immutability — Object Lock `COMPLIANCE`, 35 days.** No one — not the writer, not an admin, **not
  root** — can delete or shorten retention before it expires. It is the anti-ransomware guarantee. (It is
  a one-way door: the bucket cannot be `tofu destroy`ed while locked objects `< 35d` exist — by design.)
- **Least privilege, no static key.** The copy job mints **short-lived STS** via the Vault AWS secrets
  engine (an `assumed_role` that attaches an **add-only** S3 policy — `PutObject`, no `Delete`, no
  `BypassGovernanceRetention`). Nothing static lands on disk, in Git, or in Terraform state.
- **Independent provider.** AWS ≠ Cloudflare, so the vault also survives a Cloudflare-account compromise.
- **Scope.** Only the crown jewels (kine + the Vault raft snapshot, ~650 MiB) — the data without which
  you cannot rebuild. Object Lock is on this **self-managed** vault *only*, never on tool-GC'd stores
  (Velero/Longhorn/CNPG-barman must delete old backups to manage their chains).

## How to verify it's working

```bash
# newest objects in the vault (run on the controller with AWS creds from Vault):
aws s3 ls s3://minicloud-cyber-recovery-625830750465/ --recursive
# an object is immutable (mode + lock-until date):
aws s3api get-object-retention --bucket minicloud-cyber-recovery-625830750465 \
  --key vault/<snapshot>.snap --query 'Retention'
# the cron:
crontab -l | grep cyber-copy          # 35 5 * * * …
tail ~/.local/log/cyber-copy.log
```

## Recovery — proven, not assumed

**Normal restore** (cluster alive, mint Reader via Vault): pull a snapshot from the vault → restore into a
Vault instance. **Drilled 2026-11-26: RTO ≈ 15 s** (snapshot → throwaway Vault via the same KMS seal →
read a witness value back intact).

**Off-cluster break-glass** (the cyber scenario — cluster + Vault gone): recovery must **not** depend on
the on-cluster Vault (circular). A least-privilege IAM identity `cyber-recovery-break-glass` (S3-read +
the Vault-seal KMS ops) exists for exactly this; its access key is **age-encrypted off-cluster**
(`~/.cyber-recovery-reader.age`, never in Terraform state). **Drilled 2026-11-26: the break-glass key
*alone* restored Vault end-to-end — RTO 37 s**, with no cluster and no on-cluster Vault.

### The recovery kit (keep OFF-cluster — offline + Vaultwarden break-glass)
1. the **break-glass key** `~/.cyber-recovery-reader.age` (read the vault + `kms:Decrypt`/`Encrypt` the Vault seal),
2. the **Vault root token** `~/.vault-root-token.age` (read the restored secrets),
3. the **age identity** (decrypts 1 + 2 — in Vault `secret/platform/k3s-backup-age` + Vaultwarden),
4. this runbook + a host with Docker + the AWS Vault **KMS key** accessible.

### The drill, end to end
```
pull snapshot from S3  →  run a throwaway Vault (same image + awskms seal, same KMS key)
→  operator init (auto-unseal via KMS)  →  raft snapshot restore -force
→  it re-unseals with the restored prod keyring (same KMS key)  →  read a secret with the prod root token
```
The witness check (the non-secret `publicKey` of `secret/platform/k3s-backup-age`) matched source-to-
restore → the snapshot is genuinely restorable. The throwaway (holding all prod secrets, encrypted at
rest) is torn down immediately.

## Where the pieces live
- **IaC:** `minicloud-cloud` — `s3-cyber-recovery.tf` (bucket + Object Lock + add-only/read IAM policies),
  `s3-cyber-recovery-vault-auth.tf` (the assumed-role + the break-glass identity). Decision: `docs/adr-0003-s3-cyber-recovery.md`.
- **Copy job:** `minicloud-ops/scripts/backup/cyber-copy.sh` (deployed to `~/bin/` on the controller, run by cron).
- **Vault config:** AWS engine role `aws/sts/cyber-recovery-write` + policy `cyber-copy` + the scoped controller token `~/.vault-cyber-copy-token`.

## Numbers
| Metric | Value |
|---|---|
| Immutability | Object Lock **COMPLIANCE**, 35 days (undeletable even by root) |
| Scope / size | kine + Vault snapshot, ~650 MiB |
| Cost | ~$0.02/mo (within the account-wide $15 budget) |
| **RTO — normal restore** | **≈ 15 s** (drilled) |
| **RTO — off-cluster break-glass** | **37 s** (drilled, key-alone) |
| Static keys on disk | **0** (STS for the job; age-encrypted break-glass for recovery) |
