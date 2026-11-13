---
id: evidence-and-proof
title: Evidence & Proof — case studies, proof catalog, KPIs
sidebar_label: 🧾 Evidence & proof
---

# Evidence & Proof

:::note Map + pointer
Summary + pointer page. The registers of record live **with the GitOps config** in the
`minicloud-gitops` repo (`docs/evidence/`, `docs/productization/`) — this page is the discoverable
map entry. Snapshot: **2026-11-13**.
:::

The platform's goal is **not** "I learned 50 technologies" — it's *"I have 30–50 proofs that I can
solve real engineering problems."* Every substantial workstream leaves three interview-grade artifacts:
a **case study**, a **proof-catalog entry**, and (when it uses one) a **system-design pattern entry**.
This is the output side of the engineering discipline — the registers below are the single sources of truth.

## The registers (source of truth in GitOps)

| Register | What it holds | Source (click through) |
|---|---|---|
| **Proof catalog** | the competency → concrete-proof matrix (target: 30–50 proofs) | [`docs/evidence/proof-catalog.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/evidence/proof-catalog.md) |
| **KPI scorecard** | business · technical · AI KPIs the synthetic enterprise makes measurable | [`docs/evidence/kpi-scorecard.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/evidence/kpi-scorecard.md) |
| **System-design patterns** | each classic pattern + the proof you built + the 30-second interview framing | [`docs/evidence/system-design-patterns.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/evidence/system-design-patterns.md) |
| **Case-study template** | the 9-step architect's dossier (Problem → Options → Trade-offs → … → Lesson) | [`docs/evidence/case-study-template.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/evidence/case-study-template.md) |

## Related — productization

The brick → product map and the external-validation log (the one honest "real user" layer) live alongside:

- [`docs/productization/product-backlog.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/productization/product-backlog.md) — platform brick → candidate product.
- [`docs/productization/validation-log.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/productization/validation-log.md) — expert validation sessions (role · brick · feedback · changes).

## Discipline

- **No proof without a number or an artifact** — a graph/log/metric/PR, never "it works".
- **Options + Trade-offs are mandatory** in a case study — that's the problem-solver signal.
- **One source of truth** — the ADR holds the decision, the case study holds the story, the proof-catalog
  indexes it. Don't duplicate the body; link it. See the [Decision records index](./decision-records).
