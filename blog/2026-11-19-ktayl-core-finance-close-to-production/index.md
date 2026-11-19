---
slug: ktayl-core-finance-close-to-production
title: "Closing the Books: an Auditable Period Close — and Why the 'Lock' Is a Polite Fiction"
authors: [andrelair]
tags: [ktayl-core, finance, modular-monolith, spring-modulith, observability, production]
date: 2026-11-19
description: "Shipping the ktayl-core finance module — GL reconciliation and an auditable period close — to production. The interesting part wasn't the code; it was discovering that a 'period lock' can't physically exist without breaking the architecture, and what an honest close does instead."
---

The insurance monolith (`ktayl-core`) could already turn a bound policy into cash and post it to the general
ledger — premium → invoice → payment → double-entry Journal Entries in ERPNext. What it couldn't do was
answer the question an auditor actually asks: **"does the ledger agree with what you billed this month, and
is the period closed?"**

That's the `finance` module, now live in production. Two capabilities: a **reconciliation** (the billing
subledger's posted total vs the GL, the drift between them, and the count of *stuck* postings) and a
**period close** — lock a month, with a tamper-evident record of who closed it and the figures they attested.

{/* truncate */}

## The interesting problem: you cannot actually lock the books

My first instinct was the obvious one: closing a period should *prevent* new postings landing in it. A hard
lock — billing checks "is this period closed?" before it writes.

That's architecturally impossible here, and the reason is a good one. `finance` already depends on `billing`
(it reads the ledger view). A hard lock would make `billing` depend on `finance` — a **dependency cycle**,
which the Spring Modulith boundary test (`ApplicationModules.verify()`) rejects at build time, by design.
Billing must stay oblivious to finance.

At first this felt like the tooling getting in my way. It wasn't — it was the tooling telling me my mental
model of "a close" was wrong. On an **asynchronous** subledger (billing posts to the GL via a drained
outbox), a "lock" is a fiction anyway: there's always a posting in flight. Real finance closes don't pretend
otherwise. They **attest and detect**:

- You may only close a period whose subledger is **settled** (no pending/failed postings) and **reconciled**
  (zero drift, or an explicit `force` + a written reason). The close records that attested state, immutably.
- After close, a `postCloseMovement` signal **detects** anything that moves — the sanctioned response is a
  *reopen → adjust → re-close*, exactly how a human finance team handles a late entry.

So the close is a **control, not a padlock** (I wrote it up as ADR-019). The module boundary didn't block a
good design; it refused a dishonest one.

## Minor units, immutable audit, and a boundary you can't cheat

The unglamorous disciplines are what make it trustworthy: money is integer eurocents end to end (never a
float); the closing audit is **append-only** (rows are written, never updated or deleted — the attested
snapshot *is* the evidence); and `finance` reaches into `billing` only through a published `ledger-view`
interface, never its tables. 222 tests, including the full close lifecycle against a real Postgres.

## The bonus: production verification earned its keep (again)

Promoting to prod, the deploy went clean — pods healthy, migrations applied, endpoints gated — but the
ArgoCD app flipped **Degraded**. Not my change: *every* app was degraded. A power event earlier that day had
left the external-secrets operator unable to reach the API server from the one flaky node it happened to sit
on, so all 126 ExternalSecrets had been failing to refresh for hours. Running pods were fine (their secrets
were already materialised), but any restart needing a fresh secret would have failed cluster-wide — a latent
outage nobody had noticed.

One Cilium-agent restart on that node fixed it; 126 → 0 in two minutes. The finance deploy didn't cause it —
but **verifying the finance deploy end-to-end is what surfaced it.** Green CI and a healthy pod would never
have shown it. That's the whole argument for checking the real system, not just the pipeline.

## What's next

The money thread now runs submission → underwriting → policy → billing → **close**. Next on this epic
(FINCLOSE-03): a close dashboard across periods and a Prometheus alert on outbox drift, so a stuck ledger
posting pages someone *before* it becomes a month-end surprise — rather than being found by a human looking.
