---
id: bmad-operating-model
title: BMAD Operating Model — Enterprise SDLC
sidebar_label: BMAD Operating Model
---

# BMAD Operating Model

> **What:** how BMAD is used as the org's AI-assisted software-delivery operating model —
> intent → planning → implementation → review — scaled to the size and risk of the work.
> **Map, not library:** this page summarizes + links. The **authoritative** rules live with the
> code in `minicloud-gitops/.claude/rules/` (auto-loaded every session):
> [`bmad-compliance.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/bmad-compliance.md)
> (paths + artefact chain + gates), [`bmad.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/bmad.md)
> (per-product sync + tools), [`agile-execution.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/agile-execution.md)
> (hierarchy), [`project-governance.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/project-governance.md)
> (roles/RACI). For *how to author + sync a sprint*, see [BMAD Workflow](./bmad-workflow.md).

## The one-line model
**BMAD governs intent → implementation → review.** The platform owns everything around it:
CI builds + proves → **Kargo** promotes → **ArgoCD** deploys → **CODEOWNERS** gates → observability.
BMAD produces code; it never deploys. (See [Delivery Workflow](../developer-platform/35-delivery-workflow.md).)

## Scale to the work — pick a delivery path

The artefact burden gates on the **path, not the repo** — a one-liner does not get a PRD; a new
product does not skip one.

| Path | When | Planning artefacts before code |
|---|---|---|
| **A — Small** | bug / config / chore, one session, no new architecture | **none** (rules + tests + PR/CODEOWNERS always apply) |
| **B — Feature / Epic** | multi-story, new service on an existing product | **spec-first**: SPEC per epic + stories + readiness (PRD/architecture only if the design is new) |
| **C — New product** | own backlog, > ~20 build sessions | the **full chain** below + the governance gate |
| **E — Emergency** | prod incident / hotfix | none up front — fix first, backfill story + `deferred-work.md` + retro |

**Spec-first is the default.** Most work goes straight to `/bmad-spec`; the **PRD is the exception**
— only when non-doers must approve *what the product is*, several epics must stay aligned, or a
regulator needs named evidence.

## The pre-code artefact chain (Path C — full; B runs the subset)

Each artefact removes a different ambiguity, top-to-bottom (architecture precedes story breakdown):

```
Brief → PRD → UX(if UI) → Architecture spine → SPEC per epic → Epics+Stories → Readiness → sprint-status → BUILD
 business  product   interaction   technical      epic          impl-scope     cross-doc     eng-view
```

| Artefact | Owner (role) | Tool |
|---|---|---|
| `project-context.md` (constitution) | DO/Eng | manual |
| Research · **Product Brief** · (PRFAQ) | BA / PM | `/bmad-deep-recon` · `/bmad-product-brief` · `/bmad-prfaq` |
| **PRD** — the product contract (+ NFR/security/compliance/cost) | PM / PO | `/bmad-prd` |
| **UX** `DESIGN.md` + `EXPERIENCE.md` (if UI) | UX/UI | `/bmad-ux` |
| **Architecture** spine | SA / TL | `/bmad-architecture` |
| **SPEC per epic** `specs/spec-<x>/SPEC.md` | TL / BE | `/bmad-spec` |
| **Epics + Stories** (ACs, deps, DoD) | PM + TL | `/bmad-create-epics-and-stories` |
| **Readiness gate** + `sprint-status.yaml` | TL / Eng | `/bmad-sprint-planning` |

**BMAD drafts; the owner approves.** Each document has exactly one writer and one owner.
The **SPEC layer** is the scalability move: `/bmad-build` works against the *epic's* SPEC, not the
whole PRD, so bounded pieces run in parallel.

## Five sign-off moments (put existing approvals here — each = audit evidence)

| Moment | Blocks |
|---|---|
| PRFAQ / brief verdict | writing the PRD |
| PRD validate | design + architecture |
| **Architecture spine review** (+ **security review** for boundary changes) | writing epic SPECs |
| **Readiness gate** (PASS/CONCERNS/FAIL) | generating sprint tracking |
| Retrospective verdict | starting the next epic |

## Operating disciplines (once it's an organization)

- **One source of truth — change flows from the source outward.** Reviewers read copies; apply a
  change to the doc it *belongs* to (product → PRD, cross-epic → spine, one-epic → SPEC), then re-run
  the downstream skill. **Never hand-edit a derived doc** to patch around an upstream one.
- **Brownfield is the normal case** (retrieva, ktayl-*, the agents pre-exist). Existing PRD/code is
  the *input*: `/bmad-prd` Validate/Update, `/bmad-architecture` reads the live code and records
  existing conventions, `[ASSUMPTION]` tags flag filled gaps.
- **Trackers coexist:** `sprint-status.yaml` is the engineering view; the **GitHub Project board is
  the org system of record** — no auto-sync, no duplication.
- **Mid-flight change:** `/bmad-prd` Update → spine → `/bmad-spec` (stable capability IDs) → re-plan;
  `/bmad-correct-course` for a change too big for one story. Finished work stays finished.

## Implementation + review (defence in depth, scaled by path)

`/bmad-build` is a bounded unit — clarify → plan → human checkpoint → implement → test → self-review
→ record; out-of-scope finds go to **`deferred-work.md`** (never an inline detour). Review layers:

1. **self** — build's own review + tests ([L0–L4](./testing-strategy.md))
2. **AI-independent** — `/bmad-code-review` in a **fresh context** (before the human PR)
3. **human** — CODEOWNERS on gated paths + CI (Checkov / kubeconform / SAST)
4. `/bmad-walkthrough` for auth/schema/public-API/security diffs

## Governance above BMAD

BMAD proposes; **humans own** the architecture/security call; the platform (CI + CODEOWNERS + Kargo)
**enforces** it. A **named governance gate** (architecture review by SA/TL + security review by SEC)
clears Path C and any boundary-crossing change (authz, data model, NetworkPolicy, secrets/Vault,
public API, IAM, supply-chain), recorded in the project RACI (`project-governance.md`).
The human owns comprehension — *"could I rebuild this if the AI vanished?"* — not just a green check.

## Adoption
`ktayl-policy-service` + `retrieva` are the reference implementations. Other products run Path A/B as
their work warrants — which is correct: the paths exist so the process fits the change.
