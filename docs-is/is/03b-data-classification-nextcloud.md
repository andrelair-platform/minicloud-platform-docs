---
id: data-classification-nextcloud
title: Data Classification → Nextcloud Handling Tiers (BYOD DLP)
sidebar_label: 🔐 Data Classification (Nextcloud tiers)
---

# Data Classification → Nextcloud handling tiers

> The browser-first BYOD workplace protects *application access* well and *data-after-download*
> barely — the known trade-off (see the [Workplace Architecture principle](./digital-workplace-architecture#the-architecture-principle--browser-first-data-server-side-identity-enforced)).
> This page closes the top data-layer gap: a **data-classification model** enforced as concrete
> **Nextcloud handling tiers**, so sensitive corporate information stays server-side. It is direct
> **DORA / GDPR** evidence (a control that limits data egress from an unmanaged endpoint).

## The three tiers (mapped to the existing P0–P3 data classes)

| Tier | From P-class | Meaning | Handling |
|---|---|---|---|
| **INTERNAL** | P0 (public) + P1 (internal) | day-to-day corporate content | download OK · internal share OK · **no public/anonymous share** |
| **CONFIDENTIAL** | P2 | business-sensitive (risk reports, contracts) | **browser-preferred** · download restricted where feasible · **no public/anonymous/federated share** · internal share only |
| **RESTRICTED** | P3 (PII / regulated / privileged) | claims, financial, legal, sanctions, exec | **WEB-ONLY** · **download DENIED** · **no sync** · **no share** beyond an explicit grant · short session + strong MFA (Authentik) · **watermark** · audited |

### Insurance data → tier (the worked mapping)
Public documentation → **INTERNAL** · Risk-Engineering reports → **CONFIDENTIAL** ·
Claims documents → **RESTRICTED** · Financial / legal / sanctions → **RESTRICTED**.

## How Nextcloud enforces each tier (real mechanisms, NC 33)

Classification is a **restricted system tag** (`INTERNAL` / `CONFIDENTIAL` / `RESTRICTED`) — only
admins / the DLP flow may assign it, so a user can't down-classify their own file. Enforcement:

| Control | App / setting | Applies to |
|---|---|---|
| **Web-only document experience — no download/print/copy + watermark** | **OnlyOffice Secure View** (the real "web-only" for office docs, which is the bulk of content) | RESTRICTED |
| **No public / anonymous / federated share on sensitive data** | **global sharing guardrails** (applied: password + 30-day expiry enforced, federated off) + the "never publicly share RESTRICTED/CONFIDENTIAL" policy | CONF + RESTRICTED |
| **Access gate — RESTRICTED files only reachable by the authorised group** | `files_accesscontrol` rule: *tag = RESTRICTED AND user ∉ restricted-group → **deny access***. NB: this denies access **entirely** (it is binary — it cannot "allow view but block download"); pair it with the tight Group-Folder ACL. | RESTRICTED |
| **Space isolation + ACL** (deny reshare on Restricted) | **Group Folders** (Corporate / Department / Project / **Restricted**) — scriptable via `occ groupfolders:*` | all |
| **Session / MFA / step-up** | **Authentik** (not Nextcloud) — short session + re-auth for RESTRICTED apps | RESTRICTED |
| **Audit** | `admin_audit` → log → the unified SOC plane (Authentik + app + Falco) | all |
| **Auto-classify / Retention** (optional) | `files_automatedtagging` (tag by folder) · `files_retention` (by tag) | all |

> **Honest limit (matches the reference's own §24).** Nextcloud cannot natively "allow browser view but
> block download" for an *arbitrary* file — that granularity doesn't exist. The strong, layered controls
> are: **OnlyOffice Secure View** (web-only for documents — the main content type), **no public link** for
> sensitive tags, a **tight Restricted Group-Folder ACL**, **audit**, and — for the truly sensitive
> minority — the **VDI / browser-isolation** sensitive-workforce tier. Full download-proofing of any binary
> is not a config toggle; it's the VDI tier.

### Space architecture (Group Folders)
```
Nextcloud
├── Corporate Files        (all staff · INTERNAL)
├── Department Spaces      (per Direction group · CONFIDENTIAL default)
├── Project Spaces         (project groups)
└── Restricted Spaces      (RESTRICTED · web-only · tight ACL · audited)
```
Permission = **group + role + folder + classification** (never "authenticated ⇒ everything").

## Global sharing hardening (applied 2026-09-30 — "restrict with guardrails")
Independent of tags. **Chosen posture: keep public links *possible* but *controlled*** (an insurer has
legitimate broker/vendor sharing). Applied: public links require a **password** + an **enforced 30-day
expiry**; **auto-accept of external shares off**; **federated (server-to-server) sharing disabled**.
A pre-change **audit showed 0 existing shares**, so nothing broke. Employee login access from the
internet is unaffected — this only governs anonymous share-*links*, never authenticated access.

## Implementation — what's APPLIED vs remaining

**Applied live 2026-09-30 (via `occ`):**
```bash
NC(){ kubectl exec -n nextcloud deploy/nextcloud -c nextcloud -- php occ "$@"; }
NC app:install files_accesscontrol ; NC app:install groupfolders          # engines
NC tag:add INTERNAL restricted ; NC tag:add CONFIDENTIAL restricted ; NC tag:add RESTRICTED restricted
# global sharing guardrails (audit first showed 0 existing shares → nothing broke):
NC config:app:set core shareapi_enforce_links_password --value=yes        # public links MUST have a password
NC config:app:set core shareapi_enforce_expire_date    --value=yes        # expiry mandatory
NC config:app:set core shareapi_expire_after_n_days     --value=30
NC config:app:set core shareapi_auto_accept_share       --value=no
NC config:app:set files_sharing outgoing_server2server_share_enabled --value=no   # federated off
NC config:app:set files_sharing incoming_server2server_share_enabled --value=no
```

**Group-Folder spaces — scriptable (run when the department→group mapping is confirmed):**
```bash
ID=$(NC groupfolders:create "Restricted Spaces")                 # returns the folder id
NC groupfolders:group "$ID" "Direction Sinistres" read write     # grant the owning group
NC groupfolders:permissions "$ID" -e                             # enable advanced ACL, then deny reshare
NC groupfolders:quota "$ID" 50GB
```

**Remaining — admin UI (see the walkthrough below):**
- **`files_accesscontrol` rule** (Settings → Administration → **Flow** → *Files access control* → *Add new
  flow*): condition **File system tag** *is* **RESTRICTED** [+ *Group membership* *is not* the authorised
  group] → the rule **denies access**. (Access-control is binary — the *web-only-view* comes from OnlyOffice
  Secure View, below, not from here.)
- **OnlyOffice Secure View** (Settings → Administration → **ONLYOFFICE** → *Secure view*): enable
  **restrict download / copy / print** + a **watermark** (e.g. `{userId} — RESTRICTED — {date}`), scoped to
  the RESTRICTED tag/group. This is the real web-only document experience.

## Verify / audit
`admin_audit` logs every share/download/access with the Authentik identity → who · when · where ·
app · action · resource. Feed it into the unified audit plane for the regulated-insurer trail.
**Test:** tag a throwaway file RESTRICTED → confirm (1) it opens in OnlyOffice with a watermark and no
download button, (2) a non-authorised user gets access-denied, (3) a public link can't be made without a
password + expiry.

## Status (2026-09-30)
✅ Design + runbook · ✅ enforcement engines (`files_accesscontrol`, `groupfolders`) · ✅ classification
tags (restricted) · ✅ global sharing guardrails (audit showed 0 shares → safe). ⏳ Remaining (admin-UI,
additive): the access-control rule + OnlyOffice Secure View; Group-Folder spaces (scriptable, pending the
group mapping). Tracked on the Digital Workplace board (#10).
