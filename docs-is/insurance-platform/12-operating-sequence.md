---
id: operating-sequence
title: Operating Sequence — what to build next, and why
sidebar_label: 🧭 Operating Sequence (priority map)
sidebar_position: 12
---

# Operating Sequence — the program priority map

:::note What this is
A **decision aid**, not a status report — it answers *"what do we build next so the insurer can
actually operate?"* Per-app live/scaffold status is authoritative in
[Business Applications Catalog](./business-applications-catalog); this page **sequences** that work.
As-of **2026-10-04**.
:::

## The principle

**Sequence by "can the business operate," not by "is the project done."** A solo-built insurer IS wins
with a **coherent operating spine + deliberately-scoped boundaries** — not 25 boards each 30% built.
Half a mesh operates nothing. (The **BYOD scope decision** — no managed endpoints — is the model: a
documented *"we deliberately don't do X"* beats a half-built everything.) So
**"build it all" is the wrong finish line** — the *must* is the operating core; the rest is sequenced
or deliberately deferred with a revisit trigger.

## The rubric (score every candidate, in this order)

1. **Operability** — does the core business stop without it? (spine vs enrichment)
2. **Dependency / leverage** — does other work unblock when it ships? (foundations pay once)
3. **Risk-if-absent** — a compliance/security landmine even if small? (e.g. leaver-deprovision = dangling access)
4. **Cost-to-operate** — the solo-dev tax; every new *service* drags CI/Kargo/CNPG/QA/docs → favour
   *finishing* + the modular-monolith over starting new services.

## The highest-leverage unlock (do first)

Almost everything is **admin-only or single-user today** — Policy, Underwriting, GLPI, the intranet are
up, but **no simulated employee can log in and do their job.** So the single biggest unlock for "the
business can operate" is **IAM v2 — real multi-user login** (board #17, issues #48–#53). The moment it
ships: an employee logs in → gets workspace birthright → requests/receives business-app access → *uses*
the live apps. That one sprint turns a pile of deployed apps into an operable business.

## The insurance operating spine (depth-first — the money chain)

```
Distribution/Submission intake → Underwriting → Policy (PAS) → Billing/Finance → Claims
        🟡 #13/#27                  🟡 dev #12     ✅ prod #6     🟡 #14         ✅ prod #11
```
Policy + Claims are **prod**; Underwriting is **dev**. So the spine's real gaps are **the intake front
door (#13/#27)** and **Billing (#14)**, plus **promoting Underwriting to prod**. Close *this thread*
end-to-end before starting any new domain.

## The sequence

| Tier | What | Boards | Why now |
|---|---|---|---|
| **T0 — foundations the spine can't run without** (finish, don't expand) | **IAM v2 multi-user login** · HR Sprint 1 (foundation + leave) · IAM v3 **Leaver** (no dangling access) | #17, #8 | nobody can *use* the apps without login; leaver is a small high-risk control |
| **T1 — close the insurance spine** (depth-first) | **Billing (#14)** · **Underwriting → prod (#12)** · **Distribution / Submission intake (#13/#27)** | #14, #12, #13, #27 | Policy+Claims already prod; fill the holes so one risk flows intake→bind→bill→claim |
| **T2 — run-the-business layer** | **ITSM/GLPI (#16)** (incidents/SLA) · **Compliance + Retrieva (#15/#2)** (DORA/GDPR control spine + cert evidence) · **Data/BI (#5)** (see the business operate) | #16, #15, #2, #5 | a regulated insurer "operating" implies support + controls + reporting |
| **T3 — enrichment, deliberately deferred** (keep as scaffolds/briefs + a revisit trigger) | Risk-Engineering #21 · Reinsurance #22 · International Programs #23 · MDM #20 · AI Copilot #19 · Knowledge #18 · DMS #24 · Integration #25 · richer HR workflows | — | the business operates **without** these; parking them with a trigger is a feature, not a gap |

## The tensions to hold

- **Depth > breadth** — resist a new domain while the spine has holes.
- **Dependencies gate, not ambition** — IAM v2 and HR Sprint 1 have **no** cross-dependency → parallel
  now; the JML seam (ERPNext HR-12 ↔ IAM v3 S015) and recert wait for v2.
- **Finish + modular-monolith over new services** — each new service is the full per-service tax for one
  person (the modular-monolith-first strategy).

## Next 3 moves (recommended)

1. **IAM v2 (S008 + S009)** — multi-user login + RBAC (the unlock). *(In progress.)*
2. **HR Sprint 1 (HR-01 + HR-02)** — ERPNext foundation + leave (parallel, no dependency).
3. **Billing (#14)** — the biggest insurance-spine hole once people can log in.

> Revisit this map at each sprint boundary; it's a living view over the
> [catalog](./business-applications-catalog), not a fixed roadmap.
