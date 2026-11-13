---
id: modular-monolith-first
title: Modular-monolith-first — service granularity
sidebar_label: 🧱 Modular-monolith-first
---

# Modular-monolith-first — service granularity for the ktayl-solution IS

:::note Summary + pointer
Map entry. The decision of record — the ground-truth review, the extraction decision-test, and the
module-discipline rules — is the ADR in the GitOps repo (linked below). Status: **Accepted**
(2026-09-30). Scope: ktayl-solution insurance **business** domains; not platform infra or the AI/data
products. This ADR is also the auto-loaded rule `architecture-strategy.md`.
:::

> **Default for new insurance business domains: a module inside `ktayl-core`, not a new service.**
> Design service boundaries from day one; do not *deploy* them as separate services from day one.

A 2026-09-30 review found 4 domains live as real services (`ktayl-policy-service`, `ktayl-claims`,
`ktayl-underwriting`, `ktayl-iam` — deliberate, justified extractions) and **12 scaffold repos** with
a board + empty CI but no code — a loaded gun pointed at "12 more microservices" for domains with no
team boundary and no scale pressure.

## Why modular-monolith-first

- **Solo-dev tax.** Every new service = repo + BMAD + CI + Kargo + CNPG + Helm chart + NetworkPolicies
  + QA gate + docs + board **+ the full AI-native SDLC harness**, multiplied by service count and paid
  by one person. A modular monolith pays it **once**.
- **The senior signal** in a portfolio / interview / cert is *not* "I ran 20 microservices" — it's "I
  size architecture to the problem, and I know when microservices are the wrong call."
- A strong modular monolith (clear DDD module boundaries, one deployable) gives most of the design wins
  — separation of concerns, independent module evolution — **without** the distributed-systems tax.

## The module discipline (what keeps it from becoming a big ball of mud)

- **One module per business capability** (`src/<domain>/`) with a **public interface**; other modules
  depend on the interface, never on internals or another module's tables.
- **High cohesion, low coupling, SRP** — cross-module work goes through the interface (in-process call)
  or an **in-process domain event**; never intra-monolith HTTP/queues (that rebuilds the distributed
  monolith inside the app).
- **One Postgres, schema-per-module** — shared runtime, isolated data → the extraction escape-route
  stays open (lift the schema + interface, don't untangle shared tables).

## When a module earns extraction

Only on a **"several yes"** from the decision test: independent deploy · another team owns it · very
different scaling · different tech stack (e.g. Python/ML) · strong data isolation · different SLA ·
consumed by several apps · stable business boundary. One or two yes ≠ a service — it's a
security/architecture-boundary decision, recorded in an ADR.

## Proven in practice — the Complaints slice

The pattern isn't just doctrine: **ktayl-core's Complaints & Disputes module** is the end-to-end proof.
A greenfield vertical slice (register → acknowledge → assign → resolve → close) built as a **module**, not
a service — one deployable, schema-per-module, a CLOSED boundary enforced in CI (`ApplicationModules.verify`),
and **hexagonal internals** (a framework-pure domain, ports & adapters) so the business logic survives the
tech. It layers L1→L3 tests + an ArchUnit purity guard, and the build fails on a cross-module tap or a
framework import in the domain. As-built + ERD + API:
[`ktayl-core/docs/complaints/as-built.md`](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/complaints/as-built.md)
(see also [ADR-013 — hexagonal domain independence](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture/adr/ADR-013-hexagonal-domain-independence.md)).

## Full ADR

Decision, the full ground-truth review, the anti-patterns, and the extraction phases:
[**`docs/modular-monolith-first.md`**](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/modular-monolith-first.md).
