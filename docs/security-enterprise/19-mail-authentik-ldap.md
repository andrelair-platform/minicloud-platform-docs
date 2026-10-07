---
id: mail-authentik-ldap
title: Mail ↔ Authentik (one credential, LDAP)
sidebar_position: 19
---

# Mail ↔ Authentik federation — one credential for SSO + mail

> **Status: ✅ live (cutover 2026-10-07).** Mailboxes (Stalwart) now authenticate against **Authentik**
> via an LDAP outpost — an employee uses the **same password** for SSO and for e-mail, and rotates it
> once in Authentik. This page is the map; the full design + security review + rollback live in the ADR.

**Detailed design (source of truth):** [`minicloud-gitops/docs/mail-ldap-federation.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/mail-ldap-federation.md) · **Tracks:** [minicloud-gitops#1686](https://github.com/andrelair-platform/minicloud-gitops/issues/1686) · **Ops script:** `minicloud-ops/scripts/stalwart/stalwart-mail-ops.sh`

---

## Why

Before, a new employee ended up with **two credentials**: an Authentik SSO identity **and** a separate
Stalwart mailbox password. That breaks the workplace principle *identity is the perimeter* and confuses
users. Now there is **one credential, owned by Authentik**; mail authenticates *against* it.

## How it works

```
employee ── SSO ─────────────▶ Authentik  (identity source of truth)
   │                                ▲   ▲
   │ IMAP/SMTP (password)           │   │ LDAP search (svc) + bind-as-user (:3389)
   ▼                                │   │
Nextcloud Mail ── IMAP/SMTP ─▶ Stalwart ─┘  (Authentication Directory = ktayl-ldap outpost)
```

| Piece | What | Where |
|---|---|---|
| **Authentik LDAP outpost** | exposes Authentik users/groups over LDAP (`:3389`), base DN `dc=devandre,dc=sbs` | GitOps `manifests/authentik-ldap-outpost/` (Deployment + Service + ESO token + NetworkPolicy) |
| **Stalwart auth** | `Settings → Authentication → Authentication Directory` = the LDAP directory; **Use Bind Authentication = ON** (Authentik exposes no password hash → Stalwart binds *as* the user) | Stalwart webadmin (data store) |
| **Search service account** | `cn=stalwart-ldap-svc` (superuser, to list users) | Vault `secret/platform/authentik-ldap-outpost` |
| **Onboarding** | the ktayl-iam Joiner sets the **Authentik** password once (scoped `reset_user_password` token) | ktayl-iam #73/#74 |

## What's live
- **Unified login**: existing mailboxes authenticate via Authentik — **no data moved, no mailbox orphaned**
  (Stalwart keys mailboxes by **e-mail**, so it reuses the existing box; proven on a throwaway + confirmed
  on the owner's 7 362-message mailbox).
- **New employees**: no special mail provisioning — the mailbox auto-creates on first delivery.
- **`it@` shared mailbox**: a login-capable shared account added as a **second account in each IT member's
  Nextcloud Mail** (reply-as `it@` native). Stalwart has no shared-folder namespace here, so this
  login-sharing model is used instead of ACL delegation.

## Operate / verify

All actions run through the helper (controller-side; each runs in a transient pod in ns `mail`, creds from Vault):

```bash
# confirm a user logs in via Authentik (IMAP 143 STARTTLS):
ssh controller "bash ~/minicloud-ops/scripts/stalwart/stalwart-mail-ops.sh verify <email> [password]"
# materialise a new joiner's mailbox (send first mail):   ... welcome <email>
# clear a stale Stalwart auth cache (see gotcha below):   ... clear-cache
# add it@ shared mailbox to an IT member's Nextcloud Mail: ... share-it <nc-user-id>
```

**Last verification (2026-10-07) — 4/4 PASS:** `testbox` GONE · `kanmegnea` INBOX=7362 · `sophie` INBOX=1 · `it@` INBOX=5 (all via Authentik).

## Gotchas
- **Stalwart caches auth results** — a login tried *before* the user's password is set stays cached as a
  failure until you `clear-cache` (this blocked a new user until cleared).
- **New LDAP user ⇒ no mailbox until first delivery** — use `welcome`.
- **Directory/principal changes are webadmin-only** (the Stalwart management REST API isn't reachable
  here); mailbox ops are scriptable via IMAP/JMAP.
- **Rollback** = clear the *Authentication Directory* field (→ internal auth); the recovery admin always works.

## Related
- [SSO + IAM via Authentik](./02-sso-authentik.md) · [Access Governance (ktayl-iam)](../insurance-platform/11-access-governance-ktayl-iam.md) · [Stalwart Mail (IS — Digital Workplace)](../is/28-stalwart-mail.md)
