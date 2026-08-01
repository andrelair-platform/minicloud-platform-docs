---
id: stalwart-mail
title: Phase 78 — Stalwart Mail Server
sidebar_position: 28
---

# Phase 78 — Stalwart Mail Server

**Deployed:** 2026-07-24 | **Version:** Stalwart v0.16.13 | **Namespace:** `mail`

Stalwart is a modern all-in-one mail server (SMTP, IMAP, JMAP). This deployment makes `@devandre.sbs` a fully bidirectional mail domain: outbound via Amazon SES relay, inbound via SES receipt rules → Lambda → Stalwart SMTP.

---

## Architecture

```
Outbound:   Stalwart SMTP → SES eu-west-1 → recipient
Inbound:    sender → SES MX (inbound.devandre.sbs) → Lambda → Stalwart LMTP
Internal:   Alertmanager / n8n → stalwart.mail.svc.cluster.local:587 STARTTLS
```

| Component | Detail |
|-----------|--------|
| Image | `ghcr.io/stalwartlabs/mail-server:v0.16.13` |
| Storage | Longhorn 1Gi RWO PVC (`data-stalwart-0`) — config + RocksDB |
| Auth | Authentik SSO via `auth.devandre.sbs` (OIDC) |
| Outbound relay | SES eu-west-1 SMTP (`email-smtp.eu-west-1.amazonaws.com:587`) |
| Credentials | Vault `platform/mail` + `platform/ses` |
| Admin UI | `https://mail.devandre.sbs` (Authentik protected) |

---

## Configuration persistence

All Stalwart configuration (domains, rules, users, DKIM keys, relay settings) is stored in RocksDB on the Longhorn PVC — **not** in the gitops manifests. The JMAP API (`/api/` endpoint) is the management interface.

This means:
- Config survives pod restarts and rescheduling
- Config does **not** survive PVC deletion
- The PVC is in the Longhorn backup group — included in daily MinIO backups

**Backup the config:**
```bash
kubectl exec -n mail stalwart-0 -- stalwart-cli export > /tmp/stalwart-config.json
```

---

## Internal SMTP relay (for cluster services)

Alertmanager, n8n, and other cluster services send mail via:
```
host: stalwart.mail.svc.cluster.local
port: 587
user: admin@devandre.sbs
STARTTLS: true (insecure_skip_verify: true for internal CA)
```

The `smtp_require_tls: true` + `insecure_skip_verify: true` combination is required — Go's `smtp.PlainAuth` refuses PLAIN auth on non-TLS non-localhost connections.

---

## SES outbound relay

Outbound mail is relayed through SES eu-west-1. SES production access was approved 2026-07-26. DKIM, SPF, and DMARC are all configured for `devandre.sbs`.

SMTP credentials are in Vault at `platform/ses` (`smtp_user`, `smtp_password`).

---

## Inbound pipeline (SES → Lambda → Stalwart)

See [Phase 80 — Amazon SES](./amazon-ses) for the full inbound pipeline.

---

## Real-world skills demonstrated

| Skill | Industry context |
|-------|-----------------|
| **Self-hosted mail with SES relay** | SES handles deliverability and IP reputation — the cluster handles routing and storage |
| **JMAP for mail server config** | Modern alternative to config files — fully API-driven, versionable |
| **Bidirectional custom domain mail** | Full inbound + outbound pipeline with DKIM/SPF/DMARC — enterprise email hygiene |
| **Cluster-internal SMTP relay** | Standard pattern: one trusted internal relay for all cluster services |
| **RocksDB on Longhorn** | Config persistence outside gitops — tradeoff between GitOps purity and operational flexibility |
