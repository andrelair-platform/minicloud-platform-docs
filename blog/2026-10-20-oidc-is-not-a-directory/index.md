---
slug: oidc-is-not-a-directory
title: "OIDC Is Not a Directory: Why I Keep Reaching for LDAP Next to Authentik"
authors: [andrelair]
tags: [identity, authentik, ldap, oidc, scim, sso, platform-engineering, insurance]
date: 2026-10-20
description: "I run a simulated insurer's IS with Authentik as the single sign-on provider — one login for everything. So why did I just bolt an LDAP server onto it for the second time? Because SSO answers one question, and twice I needed a different one. Here's the root cause, and the rule that tells you in advance which protocol you actually need."
---

I run the information system of a simulated insurer on a six-node Kubernetes cluster, and the identity story is clean: **Authentik** is the single sign-on provider, every app is behind it, one login opens everything. That's the whole pitch of SSO — stop sprinkling passwords across forty apps.

So it was a little uncomfortable when, for the **second** time, I found myself standing up an **LDAP** server right next to Authentik. First for mail. Then, this week, for the ITSM. Twice I reached past the shiny OIDC door and opened an older, less fashionable one. The honest question a good engineer asks at that point isn't *"how do I wire LDAP?"* — it's **"why does my beautiful SSO keep failing me here?"**

The answer turned out to be the same both times, and it's worth writing down so I never re-derive it a third time.

{/* truncate */}

## What OIDC actually is (and what it isn't)

OpenID Connect — the protocol behind "Log in with Authentik" — is an **interactive, browser-redirect, per-login** flow. A human lands on an app, gets bounced to Authentik, authenticates, and comes back with a token full of claims. It is very good at exactly one question:

> **"The person in this browser, right now — who are they?"**

That's it. OIDC is an *authentication event*, triggered by a human, in a browser, one user at a time. It is **not** a place you can go and *ask things about users*. There is no "verify this password for me" call, and no "give me everyone" call. OIDC is a turnstile, not a filing cabinet.

Both times I hit the wall, it was because the app needed the filing cabinet.

## Case 1 — Mail: a password with nowhere to check it

The mail server (Stalwart) has to let a desktop or phone mail client log in over **IMAP and SMTP**. Those clients authenticate the ancient way: they send a **username and password over the wire** and expect the server to say yes or no — a "bind."

There is no browser in that conversation. Thunderbird cannot get redirected to Authentik and click through a consent screen; it just has a password in hand and a socket open. OIDC has literally nothing to offer here — the whole protocol *is* the browser redirect that mail can't do.

What a mail server *can* do is **bind against a directory**: "here's a username and password, are they valid?" That's LDAP's native verb. So we turned on Authentik's **LDAP outpost** — which re-exposes the same Authentik users over LDAP — and pointed Stalwart at it. Same person, same password, a protocol the mail client can actually speak.

## Case 2 — ITSM: I needed the list *before* anyone logged in

This week's job was employee **ingestion** into GLPI (our ITSM). The requirement sounds trivial: *"when a ticket comes in, we should know who requested it."* To do that, every employee has to **exist in GLPI as a selectable requester** — ideally before they've ever logged in.

Here's the quiet problem with SSO: with OIDC, a user **pops into existence the first time they log in**, and not a moment sooner. The token tells you about *the one person authenticating* — it can't tell you about the other twenty who haven't shown up yet. There is no OIDC endpoint that means "enumerate my whole workforce." So an OIDC-only ITSM has a half-empty requester list until, one by one, everybody has happened to sign in. You can't assign a ticket to someone who isn't there.

What I needed was to **read the user population and keep it synced** — pull all ~20 employees in now, refresh daily as people join and leave. That's a *directory search*, and again the answer was the Authentik LDAP outpost: GLPI binds with a service account, searches for everyone in the `Workplace Users` group, and imports them as requesters. A daily job re-runs the sync.

And because LDAP also exposes **group membership**, I got the next requirement for free: a GLPI rule that says *"members of `Direction IT / SI` → Technician profile"*, so IT staff can be **assigned** tickets, not just raise them. OIDC claims could carry groups too — but only for the person logging in, and only at login. For a rule that has to apply to people who haven't logged in yet, you need the directory.

## The pattern: SSO and a directory are different organs

Once I saw it twice, the shape was obvious. These are **three different questions**, and they want **three different protocols**:

| The real need | Protocol | The question it answers |
|---|---|---|
| A human logs into a web app | **OIDC / SAML** (Authentik SSO) | "Who is the person in this browser, right now?" |
| A non-browser client authenticates (IMAP, SMTP, LDAP-bind apps, some VPN/RADIUS) | **LDAP** (bind) | "Is this username + password valid?" |
| An app must hold, enumerate, or pre-provision the user list + groups | **LDAP** (search/sync) or **SCIM** (push) | "Who *are* all the users, and what groups are they in?" |

OIDC covers the first row brilliantly and the other two not at all. That's not a flaw in OIDC — it's a category error to expect it to. SSO is a *turnstile*; a directory is a *filing cabinet*; provisioning (SCIM) is a *mailroom that pushes updates*. Different organs.

The decision rule I'll use next time, before I start wiring anything:

- **Human + browser?** → OIDC. Always the default.
- **A client that isn't a browser needs to log in?** → it needs a **bind** → LDAP.
- **An app needs the whole roster, or users to exist before they log in?** → it needs to **read/sync the directory** → LDAP, or **SCIM** if the app can be *pushed* to (GLPI speaks LDAP, not SCIM, so LDAP it was).

If I'd had that table a year ago, neither of these would have felt like a surprise.

## The part that keeps this from becoming a mess

Standing up LDAP twice *sounds* like identity sprawl — two user stores, two sets of passwords, drift waiting to happen. It isn't, and the reason matters: **Authentik is still the one source of truth.** The LDAP outpost is not a second directory with its own users; it's the *same* Authentik users, viewed through a second protocol. One person, one credential, two doors.

That's why, across the whole platform, I'm `kanmegnea@devandre.sbs` everywhere, my mail password *is* my Authentik password, and my GLPI account is the same identity as my SSO login. We added a **protocol**, not an **identity system**. The day there are two places to edit a user is the day this went wrong — and there isn't.

## The lesson I'd hand to past-me

SSO is so good at the login problem that you start believing it's the *identity* problem, whole and entire. It isn't. "We have Authentik" answers *authentication for humans in browsers*. The moment a requirement is about **a non-browser credential** or **the set of users itself**, SSO goes quiet, and the right move is not to fight it — it's to put a directory next to it and keep one source of truth behind both.

Not every old protocol is legacy baggage. LDAP is forty years old and it's still the cleanest answer to "bind this" and "list everyone." Reaching for it next to a modern IdP isn't a step backwards — it's using the right organ for the question.

*ktayl-solution is a fictional insurer used as an engineering laboratory — synthetic data, simulated users, no real customers. The identity design, however, is real and running.*
