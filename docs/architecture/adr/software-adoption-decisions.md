---
title: "Software-Adoption Decision Register"
sidebar_label: "📥 Software-Adoption Decisions"
---

# Software-Adoption Decision Register

The **decision-record home** for the software-evaluation process (`.claude/rules/software-evaluation.md`,
step 7). Every decision to adopt (or reject, or retire) a third-party tool is recorded so the "why"
survives — the auditable trail for **BC01** (IS cadrage/governance).

## Where a decision is recorded (the rule)
- **Org-wide tool** (no single owning product — e.g. a platform capability, a shared service) → a **row
  in this register**; if the decision is weighty (a datastore, an identity system, a boundary-crossing or
  P0–P3 tool) also write a **full flat ADR** `docs/<slug>.md` (it auto-appears on the central ADR index)
  and link it from the row.
- **Product-specific tool** → the ADR lives in **that product's** `docs/architecture/adr/`, not here;
  add a register row pointing to it so the org-wide view stays complete.
- **The live evaluation evidence** (the weighted score, the decision pack, the DORA Art. 28/30 clauses)
  is the **record of truth in Retrieva** — this register links to it, it does not restate it.

## ADR shape (keep it decision-focused)
`Context` · `Options` (2–3 real alternatives) · **`Trade-offs`** (why each wins/loses) · `Decision` ·
`Consequences` · `Exit test` (the one-command way to remove it) · `Re-evaluation trigger`. The two steps
that separate an engineer-who-decides from a technician are **Options** and **Trade-offs** — never skip
them (`evidence-and-proof.md`).

## Register

| Date | Tool / capability | Gap it closes | Verdict | Scorecard | ADR | Retrieva | Status |
|---|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | | |

> Add a row when a decision is made. `Verdict` = adopt · reject · extend-existing · retire.
> `Scorecard` → the filled `docs/templates/software-evaluation-scorecard.md` copy. `Status` =
> proposed · adopted · in-PoC · retired. A Path-A utility may have a register row with no full ADR;
> a Path-C / boundary / P0–P3 tool must have the ADR + the security review + the Retrieva record.

Related: `.claude/rules/software-evaluation.md` (the process), `docs/templates/software-evaluation-scorecard.md`
(the scorecard), `.claude/rules/cloud-adoption.md` (need-first + exit test), `.claude/rules/architecture-strategy.md`
(adopt-vs-build), `.claude/rules/bmad-compliance.md` (governance gate). Executed + evidenced in **Retrieva**.
