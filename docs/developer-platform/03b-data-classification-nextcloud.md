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
| **Deny download** (web-only) | `files_accesscontrol` rule: *tag = RESTRICTED → deny `read` over `WebDAV`/public* | RESTRICTED |
| **Deny public / anonymous share** | `files_accesscontrol`: tag is `CONFIDENTIAL`/`RESTRICTED` → deny share-link | CONF + RESTRICTED |
| **Deny federated / external share** | `files_accesscontrol` + global sharing config | CONF + RESTRICTED |
| **Secure view + watermark + no-download in the editor** | **OnlyOffice** `review/restrict download` + watermark template | RESTRICTED |
| **No desktop/mobile sync** | deny WebDAV read (above) blocks the sync client too | RESTRICTED |
| **Space isolation + ACL** | **Group Folders** (Corporate / Department / Project / **Restricted** spaces) with group ACLs | all |
| **Auto-classify** (optional) | `files_automatedtagging` — tag by folder/upload location | all |
| **Session / MFA / step-up** | **Authentik** (not Nextcloud) — short session + re-auth for RESTRICTED apps | RESTRICTED |
| **Audit** | `admin_audit` → log → the unified SOC plane (Authentik + app + Falco) | all |
| **Retention** (optional) | `files_retention` by tag | CONF + RESTRICTED |

### Space architecture (Group Folders)
```
Nextcloud
├── Corporate Files        (all staff · INTERNAL)
├── Department Spaces      (per Direction group · CONFIDENTIAL default)
├── Project Spaces         (project groups)
└── Restricted Spaces      (RESTRICTED · web-only · tight ACL · audited)
```
Permission = **group + role + folder + classification** (never "authenticated ⇒ everything").

## Global sharing hardening (the platform default)
Independent of tags, set the safe workplace defaults: **public link creation disabled by default**
(or limited to a named group), **auto-accept of incoming external shares off**, **default share
expiration**, resharing restricted. This is the one change that can affect *existing* shares → apply
after a review of current public links, not blindly.

## Implementation runbook (occ)

Additive/safe parts (no existing file is RESTRICTED yet, so nothing breaks):
```bash
NC(){ kubectl exec -n nextcloud deploy/nextcloud -c nextcloud -- php occ "$@"; }
# 1. enforcement engines
NC app:install files_accesscontrol ; NC app:install groupfolders
# 2. classification tags — restricted (static): admins/DLP assign, users cannot
NC tag:add INTERNAL     restricted
NC tag:add CONFIDENTIAL restricted
NC tag:add RESTRICTED   restricted
# 3. RESTRICTED = web-only: deny download + deny share (Files Access Control rule, tag-scoped)
#    (created via the Flow/Access-Control admin UI or the occ workflow API — rule:
#     "File system tag is RESTRICTED"  →  deny [download, create-share])
```
Reviewed parts (touch existing state — do after checking current shares):
```bash
NC config:app:set core shareapi_allow_links --value=no          # or restrict to a group
NC config:app:set files_sharing outgoing_server2server_share_enabled --value=no
NC config:app:set core shareapi_default_expire_date --value=yes
```
OnlyOffice RESTRICTED secure-view (watermark + no-download) is set in the OnlyOffice admin settings
(restrict download/print/copy + a watermark template keyed on the RESTRICTED tag).

## Verify / audit
`admin_audit` logs every share/download/access with the Authentik identity → who · when · where ·
app · action · resource. Feed it into the unified audit plane for the regulated-insurer trail.

## Status
Design + runbook recorded. Enforcement engines + tags + the RESTRICTED web-only rule are the safe
first apply; global-sharing hardening + department Group-Folders follow after a shares review.
Tracked on the Digital Workplace board (#10).
