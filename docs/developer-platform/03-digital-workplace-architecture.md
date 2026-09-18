---
id: digital-workplace-architecture
title: Digital Workplace (M365 Alternative) — architecture & the Nextcloud Hub decision
sidebar_label: 🗂 Digital Workplace (M365 alt)
---

# Digital Workplace — architecture & the Nextcloud Hub decision

> The ktayl-solution IS runs a **self-hosted M365 alternative** — the "digital workplace" (GitHub
> Projects **board #10**, home repo `ktayl-workplace`). This page is the **map**: what replaces what,
> the deliberate **best-of-breed** design, and a recorded **decision on Nextcloud Hub** (why we do *not*
> consolidate onto it today). It fits the BYOD / browser-first posture (see the
> [EA Blueprint scope boundary](../insurance-platform/enterprise-architecture-blueprint)).

## What replaces M365 (deployed today)

Everything below is **deployed and running**, each behind **Authentik SSO + MFA**, reached over
Tailscale / Cloudflare — an intentionally BYOD, zero-trust shape.

| M365 capability | ktayl tool | Notes |
|---|---|---|
| OneDrive / SharePoint (files) | **Nextcloud** | file storage + sharing |
| Word/Excel/PowerPoint (office) | **Nextcloud + ONLYOFFICE** | in-browser document editing |
| Teams — chat | **Matrix (Synapse) + Element** | federated chat |
| Teams — video/meetings | **Jitsi Meet** | conferencing |
| Outlook — mail (server) | **Stalwart** | SMTP/IMAP/JMAP mail server; SES outbound relay |
| Outlook — calendar | **Nextcloud Calendar** | ✅ enabled (v6.5.1); CalDAV live at `/remote.php/dav` |
| Outlook — contacts | **Nextcloud Contacts** | ✅ enabled (v8.7.4); CardDAV live |
| E-signature | **Docuseal** | (not an M365 feature, but part of the workplace) |
| Automation / flows (Power Automate) | **n8n** | low-code integration |
| Identity (Entra ID / SSO) | **Authentik** | the sovereign workforce IdP |

**Design principle: best-of-breed, not a suite.** Each capability is the strongest self-hostable OSS
tool for that job, unified by **SSO** rather than by one monolith. This is a deliberate choice — see the
Nextcloud Hub decision below for the trade-off.

## Gaps (honest)

- **Calendar + Contacts** — **already deployed and working** (verified 2026-09-18): Nextcloud Calendar
  6.5.1 + Contacts 8.7.4 are enabled, CalDAV/CardDAV endpoints return 401 (healthy, auth-required) at
  `cloud.devandre.sbs/remote.php/dav`. Users can manage calendars/contacts in the Nextcloud UI and sync
  them to phone/desktop clients. *(An earlier draft of this doc wrongly listed these as a gap — corrected.)*
- **Mail delivery — resolved (2026-09-18).** During the swift-mac outage aftermath, external send **and**
  receive were briefly broken. Root causes were **not** Stalwart: outbound needed SES-direct
  ([swift-mac PM](../observability/incident-2026-09-16-swift-mac-outage)); inbound was a bug in the
  `ses-inbound` bridge (relaying external recipients → Stalwart rate-limit storm), fixed in the bridge
  ([inbound mail stall PM](../observability/incident-2026-09-18-inbound-mail-stall)). Mail is now working
  both directions, with SPF+DKIM+DMARC aligned via a [custom MAIL FROM](./amazon-ses). *A transport
  problem, since resolved — not a workplace-architecture problem.*

## Decision: Nextcloud Hub — evaluated, NOT adopted (2026-09-18)

**Nextcloud Hub** is the all-in-one Nextcloud bundle (Files + Office + **Talk** chat/video + **Mail**
client + **Calendar/Contacts** + Deck/Notes…). It's the closest single-product M365 equivalent, and a
reasonable default for a *greenfield* self-hosted workplace.

**Why we do NOT consolidate onto it here:**

1. **Most of Hub is already deployed as best-of-breed** — Files+Office (Nextcloud/ONLYOFFICE), chat
   (Matrix), video (Jitsi) all exist and work. Adopting Hub's Talk/Mail would **duplicate** capability,
   not add it — with real migration cost and a period of two-tools-for-one.
2. **Best-of-breed is stronger per-capability.** Matrix (federated, portable) > Nextcloud Talk for chat;
   Jitsi is a dedicated conferencing stack; Stalwart is a full mail *server*. Hub's versions are
   convenient but generally less capable.
3. **Nextcloud Mail does not fix mail.** It is a webmail **client**, not a server — it still needs
   Stalwart/SES underneath. It would **not** resolve the current outage (gitops#1154); it only changes
   the inbox UI.
4. **SSO already provides the "one login" unification** that Hub's main UX benefit promises — without a
   monolith.

**What we DO take from the evaluation:** Nextcloud's **Calendar + Contacts** — which turned out to be
**already enabled and working**, so the workplace already covers that Outlook capability with no work needed.

**Revisit trigger:** reconsider full Hub consolidation if operational overhead of N separate tools
becomes the bottleneck, or if a unified end-user UX becomes a hard requirement (e.g. real non-technical
employees at volume). Until then, best-of-breed + SSO is the standard. Apply the
[`cloud-adoption.md` need-first gate](../insurance-platform/enterprise-architecture-blueprint) logic:
don't consolidate for uniformity's sake.

## Where the detail lives
- Per-tool docs: [Nextcloud](./nextcloud) · [Matrix/Element](./matrix-synapse-element-web) ·
  [Jitsi](./jitsi-meet) · [Stalwart mail](./stalwart-mail) · [Amazon SES](./amazon-ses) ·
  [Docuseal](./docuseal)
- Mail incident + capability scope: [swift-mac postmortem](../observability/incident-2026-09-16-swift-mac-outage)
- Board: Digital Workplace **#10** · home repo `ktayl-workplace`
