---
id: software-evaluation
title: Software Evaluation & Selection
sidebar_label: Software Evaluation
---

# Software Evaluation & Selection

> How the **ktayl-solution IS** decides which third-party software to adopt — the organisational
> *process*, and the *tool* that executes it. This page is the **map**; the authoritative process is the
> committed rule linked below (docs-as-map — this does not restate it).

## Two layers — don't conflate

| Layer | What | Cert |
|---|---|---|
| **Process** (this page) | IS governance — *how the insurer decides what software to run* | **BC01** (cadrage / pilotage) |
| **Execution + evidence** | **Retrieva** — the DORA third-party-ICT / vendor-risk **product** that runs *on* the platform (register → two-lane score → decision pack → DORA Art. 28/30 clauses) | **BC02 / BC03** |

**ktayl-solution IS is Retrieva's first internal user (dogfooding).** The process is the *how*; Retrieva
is the *tool of record* that runs and evidences a given evaluation. The loop is the bridge between the two
layers, not a merge of them.

## The process — 8 steps, assembled from gates that already exist

It does **not** re-implement existing policy — it chains it:

1. **Need-first** — name the gap it closes today, or don't adopt it.
2. **Adopt-vs-build** — adopt a tool, build custom LOB, or extend an existing tool?
3. **Shortlist (2–3)** — screen on hard constraints: sovereignty · FOSS · self-hostable · licence.
4. **Weighted score** — the sovereign-first scorecard (below).
5. **PoC on the dev cluster** — real Authentik SSO / Vault / NetworkPolicy — *not* a vendor sales demo.
6. **Security / compliance review** — threat surface + data class (P0–P3) + DORA class ([Security Evaluation](/platform/observability/security-evaluation)).
7. **Decision record** — an ADR (Context · Options · **Trade-offs** · Decision · Consequences) + RACI.
8. **Record in Retrieva** — the live evaluation, score, decision pack and DORA clauses (the record of truth).

Path-scaled: a Path-A dev utility = steps 1–2 + a one-line note; a Path-C / boundary / P0–P3 tool = the
full chain, with step 6 non-optional.

## The sovereign-first scorecard (at a glance)

Adapted to a **FOSS-first, self-hosted, sovereign, solo** stack — so **TCO = operational burden** (not
licence negotiation) and the "demo" is a **PoC on the real dev cluster**. Criteria: need-fit ·
self-hostability / **sovereignty** · FOSS/licence · **SSO-able** (Authentik) · golden-path fit
(Vault/ESO · GitOps · NetworkPolicy) · observability · **DORA class + data class** · **exit/portability**
(one-command leave) · operational TCO.

## Where it all lives

| Artefact | Home |
|---|---|
| The process (source of truth) | [`.claude/rules/software-evaluation.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/software-evaluation.md) |
| The scorecard template | [`docs/templates/software-evaluation-scorecard.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/templates/software-evaluation-scorecard.md) |
| The decision register (ADR home) | [`docs/software-adoption-decisions.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/software-adoption-decisions.md) |
| A live evaluation (record of truth) | **Retrieva** |

Reuses: need-first (`cloud-adoption`), adopt-vs-build (`architecture-strategy`), the governance gate
(`bmad-compliance`), RACI + SA artefacts ([Project Governance Standard](./01-project-governance-standard.md)).
