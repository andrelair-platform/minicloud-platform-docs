---
id: access-governance-ktayl-iam
title: Access Governance — ktayl-iam (custom IGA) · as-built
sidebar_label: 🔑 Access Governance (ktayl-iam)
sidebar_position: 11
---

# Access Governance — ktayl-iam (custom IGA)

:::note Status
🟢 **IGA v1→v3 live on dev AND prod (2026-10-05).** The full governed path — **request → four-eyes dual
approval → Authentik group provisioning → who-has-what + audit** (v1) — plus **multi-user login** (v2)
and the **HR Joiner/Leaver lifecycle** (v3: HR event → auto-provision identity + mailbox + birthright
access on a Joiner; auto-revoke **all** access the day after a Leaver's HR leave date) is built,
unit-tested (98 backend tests), QA'd on live dev, and promoted to **prod** (`iam.10.0.0.200.nip.io`,
ArgoCD Synced/Healthy) via the Kargo → CODEOWNERS gate. Detailed design (PRD, solution architecture,
NFR register, threat model, ADRs) lives in the **`ktayl-iam` repo** (`docs/`); this page is the org-site map.
:::

**ktayl-iam** is the ktayl-solution **Access Governance / IGA platform**, board **#17** (IS Foundations)
— a **custom-built** product (NestJS + Next.js + PostgreSQL), **not** off-the-shelf MidPoint (which is
the rejected buy-instead in ADR-006). It is the governance layer on top of **Authentik** (the IdP where
every employee lives + logs in): the platform manages **Application → Roles → user assignments** and
**provisions Authentik groups/memberships** so login enforces them. It never re-implements auth — if the
platform is down, already-granted access still works (Authentik holds the groups).

Why custom + why it matters: the IS is **BYOD / browser-first**, so **identity is the perimeter** — a
governed, least-privilege, auditable access model is *the* primary control, not a config afterthought.

## The core control — dual approval (four-eyes, ADR-007)

A role request is granted **only** when **both** the requester's **manager** (from ERPNext HR) **and**
the **role owner** approve — two *distinct* people, **no self-approval**. Either denial stops it;
**nothing reaches Authentik until both approve**. This is the SoD/T1 control the whole product is built around.

## As-built — the IGA v1 slice (S001–S007)

| Story | What's live |
|---|---|
| **S001** scaffold + SSO | NestJS API + Next.js console + Postgres; Authentik OIDC login, **admin-only** (`Platform Admins`) |
| **S002** catalog | `application`/`role`/`assignment`/`request`/`audit_log` schema + seed (Homer-eng, Grafana, ArgoCD); a role **must** have an owner |
| **S003** directory + manager | read-only Authentik directory + **ERPNext HR** manager resolution (keyed on matricule; flagged fallback when HR can't resolve) |
| **S004** dual-approval | request → two frozen approver legs (manager + owner), four-eyes with no-self-approval + distinct-approver reassignment; either-denial rejects; both-approved → `active` (pending-sync) assignment; every step audited |
| **S005** Authentik sync | idempotent `ensureGroup`/`add`/`removeUserFromGroup`; **provision on both-approved**, **revoke** on revoke; **hourly reconcile** heals drift (DB authoritative); failed sync stays pending + self-heals |
| **S006** evidence | per-user / per-app / matrix **who-has-what**, audit list, **CSV/JSON export**; audit **append-only at the DB** (rewrite rules block UPDATE/DELETE) |
| **S007** cutover | the first apps' roles/groups are in the catalog; access flows request → dual-approval → sync instead of by-hand Authentik edits |

**Stack / deploy:** NestJS (backend) + Next.js standalone (frontend), dual-workload **GAP wrapper chart**
`services/ktayl-iam/helm/`, **git-Warehouse Kargo** (one commit → both images), ESO→Vault
(`secret/platform/ktayl-iam` dev / `secret/platform/ktayl-iam-prod` prod), ns `ktayl-iam` / `ktayl-iam-prod`.
Hosts: dev `iam-dev.10.0.0.200.nip.io`, prod `iam.10.0.0.200.nip.io` (internal/Tailscale).

## As-built — the HR Joiner/Leaver lifecycle (IGA v3, S015–S017)

ktayl-iam is the **authoritative consumer of the HR J/M/L event stream** — the identity side of the
*birthright → request → dual-approval → provision → revoke* loop. ERPNext HR (the system of record)
emits a normalised `joiner`/`mover`/`leaver` event (schema `ktayl.hr.lifecycle/v1`, HMAC-SHA256 signed)
onto **NATS JetStream** (stream `HR_LIFECYCLE`); ktayl-iam's durable consumer turns it into identity
state. **Exactly ONE environment owns the durable** — **prod** is the authoritative consumer
(`HR_NATS_URL` is set only on the prod overlay; dev's is blank so the two don't split/compete the stream).

| Story | What's live |
|---|---|
| **S015** HR event bus | ERPNext HR → NATS `HR_LIFECYCLE` (signed J/M/L events); ktayl-iam durable consumer (`HrLifecycleConsumer`), HMAC verified over Python-canonical JSON |
| **S016** Joiner handler | on a Joiner: derive the workplace email `firstname.lastname@devandre.sbs` (collision-safe) → **provision the Stalwart mailbox** (JMAP) → **create the Authentik user** (username = matricule) + add to the **`Workplace Users` birthright group** → persist an `Identity` (keyed by matricule) so the person becomes a requestable **subject** of the dual-approval flow. Idempotent + best-effort per leg |
| **S017** Leaver | HR sets the relieving date → the system **auto-revokes ALL access the day STRICTLY AFTER** it: a daily 02:00 sweep (`@Cron`) revokes every due leaver — removes every active DB assignment **and** its business Authentik group, removes the `Workplace Users` birthright group, **disables the Authentik user** (`is_active=false`, the catch-all SSO block), and **archives the Stalwart mailbox** (clears credentials → direct IMAP/SMTP refused, mail **preserved** for retention). A backdated leave date revokes immediately. Idempotent |

**Birthright access model:** every new employee gets the whole **workplace suite by default** via the
`Workplace Users` group (Nextcloud, mail, Matrix/Element, Jitsi, Vaultwarden, Plane, ERPNext self-service,
BookStack intranet). **Technical/LOB apps are NOT birthright** — they go through request → dual-approval.
This is the *least-privilege-by-default-for-business, earn-it-for-sensitive* shape.

**Mailbox archival vs SSO disable (why both on a leaver):** disabling the Authentik user cuts every
**SSO/browser** path, but the Stalwart principal still accepts **direct IMAP/SMTP** with the mailbox
password — so the leaver sweep **also** clears the Stalwart credential. Clearing (vs destroying) keeps the
account + mail for retention and is reversible. Verified live: `credentials:{}` → IMAP `AUTHENTICATIONFAILED`,
mail preserved.

## Security by design (threat model)

- **Four-eyes** two distinct approvers, no self-approval — enforced at request creation (reassign to a
  backup) **and** again at decision time (T1).
- **Least-privilege Authentik token (T4):** the `ktayl-iam-svc` account holds exactly
  `view_user, view_group, add_group, change_group, add_user_to_group, remove_user_from_group` — it can
  create governance groups + manage membership and **nothing else** (verified: group delete → 403).
- **Safe reconcile (T5):** always *re-adds* dropped memberships (heals hand-removal), but *removes*
  hand-adds **only** on platform-**exclusive** groups — so it can never nuke a hand-managed group like
  `Platform Admins`; every drift is audited (alert).
- **Immutable audit (T8):** `audit_log` is append-only at the database (PostgreSQL rewrite rules reject
  UPDATE/DELETE), so even a compromised app role cannot rewrite history.
- **Manager from HR, never the payload (T3);** break-glass = the built-in local admin, audited.

## Operate / verify
```bash
# health + that the governed routes are live & guarded (internal, Tailscale + minicloud CA):
/usr/bin/curl --cacert ~/minicloud-ca.crt -s -o /dev/null -w "%{http_code}\n" https://iam-dev.10.0.0.200.nip.io/api/health      # 200
/usr/bin/curl --cacert ~/minicloud-ca.crt -s -o /dev/null -w "%{http_code}\n" https://iam-dev.10.0.0.200.nip.io/api/requests    # 401 (admin-only)
ssh controller "kubectl get application ktayl-iam-dev -n argocd"            # Synced / Healthy
# grant the sync engine its least-privilege Authentik perms (reusable, idempotent):
ssh controller "cd ~/minicloud-ops && bash scripts/authentik/grant-service-group-perms.sh ktayl-iam-svc"
# trigger a reconcile on demand (also runs hourly): POST /api/sync/reconcile ; export audit: /api/access/audit/export?format=csv
# HR lifecycle consumer — PROD is the authoritative env (dev's HR_NATS_URL is blank by design):
ssh controller "kubectl logs -n ktayl-iam-prod deploy/ktayl-iam-backend | grep -i HrLifecycleConsumer"   # 'subscribed' on prod; 'disabled' on dev
```
Console: `/admin` (catalog) → `/admin/requests` (request · approve both legs · who-has-what · reconcile · export).

## Compliance mapping
**DORA** (access control + ICT change governance — the request/approval/grant trail is evidence) ·
**ISO-27001 A.9 / A.5.15–18** (access control, least-privilege, SoD) · **GDPR** (who-can-see-what + audit).
Certification: **BC03 (déployer & sécuriser)**.

## Status honesty — what's deferred (documented, not gaps)
- **Multi-user login is live (v2)** — regular employees log in as requesters/approvers, so true
  four-eyes no longer needs the single-admin `ALLOW_APPROVER_OVERRIDE` demo shim (kept dev-only).
- **Mover (S018) is minimal** — a Mover currently updates identity attributes; full
  *grant-new-role / revoke-stale-role on a department change* is the next lifecycle increment.
- **Initial mailbox password is deliver-then-rotate (MVP)** — the Joiner stores a generated password to
  hand off; a self-service first-login rotation is a follow-up.
- **MemoryStore sessions** (single-replica) → move to a shared store before prod HA.

Full detail + rationale: `ktayl-iam` repo `docs/` (brief · prd · `architecture/solution-architecture` ·
`nfr-register` · `threat-model` · `adr` · access-role-model · app-authz-bindings) + the HR-lifecycle module
`backend/src/lifecycle/` (Joiner/Leaver handler, Stalwart JMAP client, NATS consumer); and the platform
memories `project_iam_custom_access_governance`, `project_iam_deploy_specifics`,
`reference_stalwart_jmap_provisioning` + `feedback_hr12_glpi_n8n_gotchas`.
