---
id: access-governance-ktayl-iam
title: Access Governance — ktayl-iam (custom IGA) · as-built
sidebar_label: 🔑 Access Governance (ktayl-iam)
sidebar_position: 11
---

# Access Governance — ktayl-iam (custom IGA)

:::note Status
🟢 **IGA v1 slice live on dev (2026-10-04).** The full governed path — **request → four-eyes dual
approval → Authentik group provisioning → who-has-what + audit** — is built, unit-tested and deployed
to dev (`iam-dev.10.0.0.200.nip.io`, ArgoCD Synced/Healthy). Detailed design (PRD, solution
architecture, NFR register, threat model, ADRs) lives in the **`ktayl-iam` repo** (`docs/`); this page
is the org-site map.
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
`services/ktayl-iam/helm/`, per-image **Kargo**, ESO→Vault (`secret/platform/ktayl-iam`), ns `ktayl-iam`.
Hosts: dev `iam-dev.10.0.0.200.nip.io`, prod `iam.10.0.0.200.nip.io` (internal/Tailscale).

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
```
Console: `/admin` (catalog) → `/admin/requests` (request · approve both legs · who-has-what · reconcile · export).

## Compliance mapping
**DORA** (access control + ICT change governance — the request/approval/grant trail is evidence) ·
**ISO-27001 A.9 / A.5.15–18** (access control, least-privilege, SoD) · **GDPR** (who-can-see-what + audit).
Certification: **BC03 (déployer & sécuriser)**.

## Status honesty — what's deferred (documented, not gaps)
- **Admin-only login today.** The console requires `Platform Admins`; requesters/approvers are modelled
  by matricule. A dev-only `ALLOW_APPROVER_OVERRIDE` lets the single admin console demo both legs (the
  server still rejects self-approval + any non-assigned approver). **Real multi-user login** (regular
  employees as requesters/approvers) is the next increment — until then true four-eyes needs two humans.
- **MemoryStore sessions** (single-replica) → move to a shared store before prod HA.
- **Prod promotion** is a separate gated step: the live **QA gate** (adversarial pass on dev) +
  CODEOWNERS Kargo PR must pass first; dev ≠ prod.

Full detail + rationale: `ktayl-iam` repo `docs/` (brief · prd · `architecture/solution-architecture` ·
`nfr-register` · `threat-model` · `adr` · access-role-model · app-authz-bindings) and the platform memories
`project_iam_custom_access_governance` + `project_iam_deploy_specifics`.
