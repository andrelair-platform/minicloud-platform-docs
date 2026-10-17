---
id: code-review
title: Code Review Standard
sidebar_label: 🔍 Code Review
---

# Code Review Standard

:::note Map + pointer
How we review a change — adapted from **[Google's Engineering Practices — "How to do a code review"](https://google.github.io/eng-practices/review/reviewer/)**
and mapped onto this platform's real review machinery. The decision of record is the rule
[`.claude/rules/code-review.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/code-review.md);
this page is its published map.
:::

## The one principle above all
> **Approve a change once it *definitely improves the overall code health* of the system — even if it isn't
> perfect.** There is no perfect code, only *better* code. The reviewer stops health from degrading; they
> do **not** block forward progress on polish.

A merely-preferred tweak → `Nit:` (non-blocking). Facts & data beat opinion; **design is engineering, not
taste**; linters/style-guide are authoritative; consistency wins unless it degrades health. **Never
deadlock a change over a disagreement** — resolve on principle or escalate.

## Our three review layers (where this applies)
Code here is largely written by **AI agents**, reviewed in three layers (`bmad-compliance.md`), scaled by
delivery path (A/B/C/E):

| Layer | What | Who |
|---|---|---|
| 1 — self-review | `/bmad-build`'s own review + the test pyramid | the build agent |
| 2 — independent AI pass | **`/bmad-code-review` in a FRESH context** — no memory of writing it (the real "second pair of eyes") | a fresh agent |
| 3 — human review | **CODEOWNERS** approval that gates prod + CI (Trivy/kubeconform/SAST) | the owner |

Google's reviewer principles apply to layers 2 + 3. `/bmad-walkthrough` adds a risk-focused pass for
auth / schema / public-API / security diffs.

## The reviewer checklist (priority order)
**Design** (does it fit / belong here?) · **Functionality** (intent + users; edge cases, concurrency —
backstopped by the [live QA gate](/platform/engineering-standards/testing-strategy)) · **Complexity** (no
over-engineering / YAGNI) · **Tests** (right layers, in the same CL, *fail when the code breaks*) ·
**Naming / Comments** (comments say *why*, not *what*) · **Style** (linter-clean; keep style out of a logic
CL) · **Consistency** · **Documentation** (updated in the same effort — the DoD gate) · **Every line**
(read all of it; ask when unclear; pull a specialist) · **Context** (judge against the whole system) ·
**Good things** (call out what was done well — mentoring value).

## How to review (order) + speed
1. **Broad view** — should this change exist at all? If not, say so now, with an alternative.
2. **Main parts first** — review the core logic + **send major design feedback immediately**; ask to split
   an over-large change.
3. **The rest in sequence** — read the **tests first** to learn intent.

**Speed:** respond within **one business day** (respond ≠ finish); fast *responses* beat fast *turnaround*;
`LGTM` + comments when you trust the author on the minors; **never trade the standard for imagined velocity.**

## Writing comments
- **Comment on the code, not the person**; **explain why**; it's the **author's job to fix**, so prefer
  *pointing out the problem* over prescribing.
- **Label severity:** `Nit:` (trivial) · `Optional:` / `Consider:` (not required) · `FYI:` (informational).
  Unlabelled = expected to address.
- **Unclear code → ask for a rewrite, not an explanation in the thread** — the next reader needs the
  clarity in the code, not the PR.

## Pushback
The author may be right (they're closer to the code) — concede if their reasoning holds on *health* grounds;
otherwise keep advocating, **politely**. **"Clean it up in a later CL" → no**: new complexity is cleaned up
before submission unless it's an emergency; genuinely out-of-scope problems get **recorded** (`deferred-work.md`
/ a filed issue + `TODO(#issue)`), not waved through.

## The merge path — `gh pr merge --admin` is break-glass only

`--admin` **bypasses branch protection** (review + required checks). It is **break-glass only** — reflexive
use is how an unverified or broken change can reach `main` (it defeats the gate the review is supposed to be).
The default is a **plain merge**, because the rulesets already make it safe:

- Both repos' `main` ruleset = `required_approving_review_count: 0` + signed commits + no force-push, with
  **code-owner review required only on CODEOWNERS paths** (gitops: prod overlays, `services/*/helm`, `apps/`,
  `helm-values/`, `.claude/`, security; platform-docs: none).
- **So a PR touching no CODEOWNERS path merges on a normal `gh pr merge --squash` — no `--admin`.** Most
  docs/non-gated PRs are exactly this.
- A PR touching a **CODEOWNERS path** still needs the owner's approval. For a solo owner who can't
  self-approve, the sanctioned path is a **review-bot CODEOWNER** that approves after CI (the `--admin`
  *elimination* follow-up), **not** reflexive `--admin`.

> **Follow-up hardening:** make the CI validation job a **required status check** so even the plain path
> can't merge a change that fails to build/validate (this would have caught conflict markers reaching
> `main`). Caveat: a path-filtered check must be made *always-reporting* first, or a docs-only PR deadlocks
> on an "expected" check that never runs.

## Don't double-count the gates
Review (judgement) + **CI** (L0–L4) + the **live QA gate** (L5) + **CODEOWNERS** (enforcement) are
*distinct* evidence — none replaces another.

## Related
- [Testing strategy](/platform/engineering-standards/testing-strategy) · [Documentation Standard](/platform/engineering-standards/documentation-standard) · [Decision records](/platform/engineering-standards/decision-records)
- [End-to-End Delivery Workflow](/platform/developer-platform/delivery-workflow) · [Deploy a new business service](/platform/app-deployment/new-business-service)
- Upstream: [Google eng-practices — reviewer guide](https://google.github.io/eng-practices/review/reviewer/)
