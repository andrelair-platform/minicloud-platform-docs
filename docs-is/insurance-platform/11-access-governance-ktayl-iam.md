---
id: access-governance-ktayl-iam
title: Access Governance — ktayl-iam (custom IGA) · as-built
sidebar_label: 🔑 Access Governance (ktayl-iam)
sidebar_position: 11
tags: [explanation]
---

# Access Governance — ktayl-iam (custom IGA)

:::note Status
🟢 **IGA v1→v3 live on dev AND prod (2026-10-05).** The full governed path — **request → four-eyes dual
approval → Authentik group provisioning → who-has-what + audit** (v1) — plus **multi-user login** (v2)
and the **HR Joiner/Leaver lifecycle** (v3: HR event → auto-provision identity + mailbox + birthright
access on a Joiner; auto-revoke **all** access the day after a Leaver's HR leave date) is built,
unit-tested, QA'd on live dev, and promoted to **prod** (`iam.10.0.0.200.nip.io`, ArgoCD Synced/Healthy)
via the Kargo → CODEOWNERS gate. **Extended since (2026-11-19):** **IGA-06 governed service accounts**
(non-human identities, four-eyes + Vault-stored token), **IGA-07 external collaborators** (governed
human non-employees — sponsor + Security four-eyes, hard expiry, daily sentinel), and a full
**shadcn/ui console redesign** with an **axe a11y gate** (RGAA) — all merged (154 backend tests). Detailed
design (PRD, solution architecture, NFR register, threat model, ADRs) lives in the **`ktayl-iam` repo**
(`docs/`); this page is the org-site map.
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
| **S016** Joiner handler | on a Joiner: derive the workplace email `firstname.lastname@devandre.sbs` (collision-safe across employees **and** external collaborators) → **create the Authentik user** (username = matricule) **with `email` = that mailbox address** + add to the **`Workplace Users` birthright group** → persist an `Identity` so the person becomes a requestable **subject** of the dual-approval flow. **ADR-016:** under the Mail↔Authentik LDAP federation the mailbox **is** the Authentik email — Stalwart auto-creates the box on first delivery; IAM does **not** call Stalwart `createMailbox` (forbidden for LDAP-directory accounts + redundant). Idempotent + best-effort per leg |
| **S017** Leaver | HR sets the relieving date → the system **auto-revokes ALL access the day STRICTLY AFTER** it: a daily 02:00 sweep (`@Cron`) revokes every due leaver — removes every active DB assignment **and** its business Authentik group, removes the `Workplace Users` birthright group, and **disables the Authentik user** (`is_active=false`) — which, under the LDAP federation, blocks **both** SSO **and** mail (Stalwart binds against Authentik → a disabled user can't IMAP/SMTP either). A backdated leave date revokes immediately. Idempotent |

**Birthright access model:** every new employee gets the whole **workplace suite by default** via the
`Workplace Users` group (Nextcloud, mail, Matrix/Element, Jitsi, Vaultwarden, Plane, ERPNext self-service,
BookStack intranet). **Technical/LOB apps are NOT birthright** — they go through request → dual-approval.
This is the *least-privilege-by-default-for-business, earn-it-for-sensitive* shape.

**Mail block on a leaver (ADR-016 — one control, not two):** since the **Mail↔Authentik LDAP federation**,
Stalwart has no local password to clear — it **binds against Authentik** for every IMAP/SMTP login. So
**disabling the Authentik user** (`is_active=false`) is the single catch-all that blocks SSO **and** direct
IMAP/SMTP at once; the mailbox store + its mail are left intact (retention) and the block is reversible by
re-enabling the user. *(Pre-federation this needed a second step — clearing the Stalwart credential; that
`createMailbox`/credential path is retired under LDAP, ADR-016.)*

**Password recovery — help-desk-assisted, by deliberate decision (ADR-016).** Authentik now has a **recovery
flow** (the token-path, set as the brand's `flow_recovery`), so an admin can issue a one-time reset link for
any user (`createRecoveryLink`) + an external collaborator sets their own initial password via the same invite
link. **Full *user-initiated* self-service reset is intentionally NOT enabled yet** — and *email* self-service
can't be the answer here: this is a **unified-credential** platform (mail auth = the SSO password via LDAP), so
a reset email to the user's own `@devandre.sbs` mailbox is unreadable when they've forgotten that password
(chicken-and-egg), and most users have no second channel (1/27 have TOTP; no secondary recovery email). So
reset is **help-desk-assisted** (verify out-of-band → issue the link) — a standard, secure enterprise pattern.
**Planned (later): mandatory MFA + a TOTP-based self-reset flow** (identify → verify authenticator → set
password — no email) → tracked as `ktayl-iam#131`; trigger = when TOTP enrollment can be mandated for all users.

## As-built — self-service "My Access" + batch access-requests (ADR-017)

Two user-facing additions (live dev+prod):
- **My Access** (`/me/access`, `GET /access/me`) — any employee sees their **own complete access picture** in a
  table, each row tagged by **why** they have it: **Governed** (earned via four-eyes — the governance platform's
  assignments), **Birthright** (the `Workplace Users` baseline), or **Direct** (another Authentik group). It
  merges the governed assignments with the user's **live Authentik group memberships**. Self-scoped (the matricule
  comes from the session, never the path); read-only — grants only ever change via request → four-eyes. The
  admin-only who-has-what/audit views are unchanged (`@AdminOnly` moved to those methods).
- **Batch access-requests** — request **several roles as one *demande*** under a single trackable **`batch_id`
  instance**. Crucially **each role keeps its own two-leg four-eyes** (manager + *that role's* owner) — the batch
  is a grouping, not a combined approval — so a role is **granted as soon as its own two approvals clear**, and a
  batch is "complete" only when every role's four-eyes does. `POST /requests/batch` + `GET /requests/batch/:id`
  (a tracking view with a derived summary) make it obvious **which role is blocked and on which leg** (e.g.
  *Underwriting: manager ✓ / owner ⏳ → waiting on the owner*). The request form gains a multi-role basket;
  **My requests** groups by batch instance. Per-leg approval tracking + the stable `request.id` already existed —
  this adds the self-view + the batch grouping on top, with the four-eyes guarantee unchanged.

## As-built — governed service accounts (IGA-06, S021–S024)

Non-human (service/technical) identities, governed with the **same four-eyes discipline** as human access.
A `service_account` is distinct from a human `identity`: no HR record, no manager, no mailbox — accountable
to a human **owner**, provisioned to Authentik as a `service_account` user in one or more `GROUP_<name>`
groups, with its credential kept **only as a Vault ref** (never stored in the IAM DB or audit log).

| Story | What's live |
|---|---|
| **S021** entity + persistence | the `service_account` table (unique name, type, owner, scoped groups, status) |
| **S022** request + dual-approval | reuses the human four-eyes resolver — **Security approver** leg (no HR manager for a non-human) + **owner** leg; mandatory justification; nothing reaches Authentik until both approve |
| **S023** provision | on approval → Authentik `service_account` user + each group + **minted app-password token written to Vault KV-v2** (config-gated; the token value never touches the DB/audit); idempotent + retryable |
| **S024** recertification + UI | owner/admin re-attestation (stamps `last_recertified_at`) + a due-campaign query; the admin console surface |

## As-built — external collaborators (IGA-07, ADR-009 + S025–S030)

Governed onboarding of **human non-employees** (contractors, brokers, auditors, partners) who need scoped
access but are **not in the HR system**. **IT/Admin-only** (`collaborators:manage`) — never HR, never
employee self-service. Shaped like IGA-06 plus the human/sponsor/expiry rules, cleared through an
**architecture + security governance gate** (ADR-009) before build.

| Story | What's live |
|---|---|
| **S025** entity | the `external_collaborator` table (sponsor, scoped groups, hard `expires_at`, status `requested→active→expired/flagged/disabled`) |
| **S026** request + four-eyes | **Sponsor + Security** approval; the **sponsor is validated as an ACTIVE employee** at request time (rejected otherwise); expiry **capped at a 180-day ceiling** |
| **S027** provision | on approval → Authentik user (filed under `external-collaborators`) + the **scoped** groups + an **invitation/recovery link** so the human sets their own credential (**no machine token**). **ADR-015: also the SAME workplace tier as an employee** — the `Workplace Users` birthright group + a company mailbox (`firstname.lastname@devandre.sbs`), so a contractor can actually collaborate (Nextcloud/Matrix/Jitsi/…) while **business apps stay request→four-eyes** |
| **S028** expiry + renewal | `renew` (extend ≤ ceiling + stamp recert) + a `due` worklist + endpoints |
| **S029** sponsor-Leaver sentinel | a **self-contained daily `@Cron` sweep**: expired → auto-suspend (status + Authentik disable **+ company mailbox disable**, ADR-015 leaver parity); sponsor no longer active → `flagged` + disable. Chosen over a one-shot JML hook — re-checks daily, catches a sponsor deactivated for any reason, so orphaned access can never stand |
| **S030** admin UI | the `/admin/external-collaborators` console (lifecycle cards, expiry countdown, flagged banner, renew/provision) |

**The HR boundary (decisive):** the console **never creates employees** and **IAM never writes to
ERPNext** — employee identity + J/M/L lives in the HR system and *feeds* IAM. Full model: the repo's
[`operation-authorization-model.md`](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/operation-authorization-model.md)
+ [`external-collaborator-onboarding.md`](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/external-collaborator-onboarding.md).

:::note Revised by ADR-012/013 (2026-11-20)
The original "external collaborators are IAM-only identities with **no workforce record**" boundary was
**deliberately revised** — see the next section. They now DO get a **non-payroll ERPNext HR worker**, created
by **n8n** on an event. IAM still never writes ERPNext directly (n8n is the only writer) — so the ADR-009
boundary holds while the person is correctly modelled as a *worker*, not left out of HR.
:::

## As-built — the workforce engagement model + n8n onboarding (ADR-012 / ADR-013)

The owner corrected the model: an external collaborator is a **worker** (employed by an **ESN**, or
**freelance**) — **not a supplier** and **not our payroll employee**. (*"Paid" ≠ "salary"*: a prestataire is
paid by **invoice** via Accounts Payable at the firm level, never payroll — payroll would be *salariat
déguisé*.) Engagement type, grade, salary and dates are **HR master data → ERPNext HR is the system of
record**; IAM consumes a projection and reads its user directory from **Authentik**, never from ERPNext.

**The engagement taxonomy (ERPNext `Employment Type`):**

| Engagement | Our employee? | Paid via | Payroll? | End date |
|---|---|---|---|---|
| CDI (cadre/non-cadre) · CDD · Alternance | yes | salary | ✅ | CDI none; others fixed |
| Stage | no (student) | *gratification* | ⚠️ not real | fixed |
| **Prestataire** (ESN) · **Freelance** | **no** | **invoice (AP)** | ❌ (no Salary Structure) | mission |

**The onboarding loop (live + QA-verified on dev, 2026-11-20):**
```
collaborator provisioned → IAM emits signed `onboarded` event → n8n webhook
  → n8n creates the non-payroll ERPNext Employee (Prestataire/Freelance, NO Salary Structure → never payroll)
  → n8n binds the HR-EMP id back → IAM `hr_worker_ref` (the console flips from `pending` to HR-EMP-xxxxx)
```
IAM carries an `hr_worker_ref` (replaces the earlier mislabelled `supplier_ref`), emits the event + accepts a
**service-key-guarded** writeback (`X-IAM-Service-Key`, fail-closed); **n8n is the only ERPNext writer**
(ADR-009). `cadre`/`non-cadre` = native `Employee Grade` (internal-only); `gender`/`date_of_birth` were made
non-mandatory for externals. Decisions: ADR-012 (engagement model) + ADR-013 (webhook transport + service-key
bind-back), repo
[`architecture/adr/000-index.md`](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/architecture/adr/000-index.md);
the n8n workflow + wiring: [`integration/n8n/`](https://github.com/andrelair-platform/ktayl-iam/tree/main/integration/n8n).
**Prod enablement** waits on adding the IAM-callback base-URL to the event (dev/prod routing).

## As-built — the console redesign (shadcn/ui, persona-gated, a11y-gated)

The whole admin + employee console was rebuilt on a **shadcn/ui + Tailwind v4** design system (Phases 0–5):
a role-aware app shell, **lifecycle-over-lists** (a request is a card with a status stepper, not a row),
people resolved to **name · matricule**, real states/toasts/confirm dialogs, and an **axe accessibility gate
in CI** (RGAA / BC02). Authorization is by **capability flags** (`can('collaborators:manage')`), not a raw
`isAdmin`, so an `IT Operator` split is a config change. Spec:
[`frontend-redesign.md`](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/frontend-redesign.md).

:::note OIDC session-login fix
A `super.logIn()`-missing bug in `OidcAuthGuard` meant the token exchange succeeded but the session never
persisted `passport.user` → a "please sign in" loop despite a 200 exchange. Fixed by overriding the guard's
`canActivate` to establish the passport session on a successful callback (ktayl-iam #92/#93).
:::

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

**Internal-employee contract-end access-expiry (ADR-014) — BUILT + LIVE on dev+prod (2026-11-20).** A
fixed-term employee (CDD/Alternance/Stage) now ties access-expiry to their ERPNext `contract_end_date` by
**reusing the existing leaver sweep** (scheduled revocation; CDI = open-ended, no expiry). The identity mirrors
`employment_type` + `contract_end_date` from the HR-lifecycle event; `onJoinerOrMover` revokes immediately if the
contract already ended (catch-up), and the daily sweep revokes fixed-term identities whose contract end has passed
— one `revokeAccess` path shared with the Leaver flow (DRY). Shipped as the IAM mirror (ktayl-iam #124) + the
ERPNext producer emitting the two fields (minicloud-erpnext #29). Verified end-to-end on prod through the real
signed producer: future-dated CDD → mirror only; past-dated CDD → mirror + auto-revoke. It is **inert for CDI**
(today all internal staff are CDI) so it waits harmlessly for the first fixed-term hire.

Full detail + rationale: `ktayl-iam` repo `docs/` (brief · prd · `architecture/solution-architecture` ·
`nfr-register` · `threat-model` · `adr` · access-role-model · app-authz-bindings) + the HR-lifecycle module
`backend/src/lifecycle/` (Joiner/Leaver handler, Stalwart JMAP client, NATS consumer); and the platform
memories `project_iam_custom_access_governance`, `project_iam_deploy_specifics`,
`reference_stalwart_jmap_provisioning` + `feedback_hr12_glpi_n8n_gotchas`.

## Related

- [Regulatory Operating Model](./regulatory-operating-model)
- [Governance Intranet](./governance-intranet)
- [System of Record](./system-of-record)
- [Architecture at a Glance](./architecture-at-a-glance)
