---
title: "ADR: Modular-Monolith-First"
sidebar_label: "🧱 Modular-Monolith-First"
---

# ADR: Modular-monolith-first — service granularity for the ktayl-solution IS

**Status:** Accepted (2026-09-30) · **Owner:** SA/TL (AndreLiar) · **Scope:** ktayl-solution insurance IS (business domains). Does not govern platform infra or the AI/data products.

## Context

The ktayl-solution IS is a **solo-developer**, portfolio + RNCP-certification build of a
simulated insurer's information system. Early domains were built **service-per-domain**
(own repo + CI + Kargo + isolated Postgres + board). A ground-truth review (2026-09-30) found:

- **4 domains are real, live services** — `ktayl-policy-service` (Go/gRPC PAS),
  `ktayl-claims` (Java/Spring, the ACL over the frozen `globalcore` legacy),
  `ktayl-underwriting` (Python/FastAPI), `ktayl-iam` (NestJS).
- **12 domains are scaffolds** — `distribution, finance, compliance, dms, integration,
  reinsurance, risk-engineering, international-programs, mdm, ai-copilot, itsm, workplace` —
  each already carries a **separate repo + board + empty CI**, but **no code and no deployment.**
- **Coupling is low-moderate, not a distributed-monolith mess:** every service owns its own DB
  (no shared tables), integration is async-first (NATS bound-risk events, Debezium CDC), and
  there are only **two synchronous chains — both deliberate:** `claims → globalcore` (SOAP, the
  Strangler ACL) and **`underwriting → policy-service`** (a 3-call blocking bind: create → submit
  → activate — the classic early "distributed-monolith seam").

Two forces make service-per-domain the wrong **default** going forward:

1. **Solo-dev tax.** Every new service = repo + BMAD + CI + Kargo + CNPG + Helm wrapper chart +
   NetworkPolicies + QA gate + docs site + board **+ the full AI-native SDLC harness**. That cost
   multiplies by service count and is paid by one person; a modular monolith pays it **once**.
2. **The 12 scaffold repos are a loaded gun** pointed at "12 more services" — the exact
   `30-microservices-from-day-one` anti-pattern, for domains with **no team boundary and no scale
   pressure** (the two things that actually justify a service).

The senior signal in a portfolio/interview/cert is **not** "I ran 20 microservices" — it is
"I size architecture to the problem, and I know when microservices are the wrong call."

## What a modular monolith is (and the discipline that makes it work)

Three points on the spectrum:

- **Monolith** — one deployable, but UI / business logic / data are *tightly coupled*; a change
  touches the whole. Simple to start, hard to maintain as it grows.
- **Modular monolith** — one deployable, but the code is organised into **loosely-coupled modules**
  around business capabilities (DDD). You get most of the design benefits of services — clear
  boundaries, separation of concerns, independent evolution of a module — **without** the
  distributed-systems tax (network calls, eventual consistency, service discovery, distributed
  transactions, per-service ops).
- **Microservices** — those modules deployed as independent networked services. Real
  scaling/ownership/resilience wins, large operational tax — worth it only when the boundary is an
  *organisational or scaling* boundary (the decision test below).

`ktayl-core` is the **modular monolith**, and it delivers its benefits *only* if these principles
are enforced — they are what separate it from a big ball of mud:

- **Modularity + clear boundaries** — one module per business domain (`src/<domain>/`), each with a
  **well-defined public interface**; other modules depend on the *interface*, never on internals.
- **High cohesion, low coupling** — a module owns one business capability end-to-end; cross-module
  work goes through the interface (an in-process call) or an **in-process domain event**, never by
  reaching into another module's code.
- **Single Responsibility** — each module has one reason to change; a change in `claims` must not
  ripple into `billing`.
- **Shared runtime + one database, but ISOLATED data** — one deployable, one Postgres (the
  simplicity of "shared data storage"), **but schema-per-module and a hard rule that a module never
  queries another module's tables.** This precision is what keeps coupling low *and* keeps the
  extraction escape-route open: pulling a module into a service later = lifting its schema + its
  interface, not untangling shared tables.
- **In-process, NOT intra-monolith HTTP** — modules call each other in-process (a function call),
  not over the network. Putting HTTP/queues *between modules of the same app* rebuilds the
  distributed monolith inside the monolith — don't. Real NATS events appear only on extraction.

Internally each module is free to use a **layered** structure (API → domain → persistence) and
**component**-based reuse — those patterns compose *inside* the modular monolith. What we buy:
**simplicity** (one artifact, one pipeline, one DB), **maintainability** (SRP + boundaries), **ease
of deployment**, and enough **scalability** (scale the whole app horizontally; extract the one hot
module if a real bottleneck ever appears) for the tens-to-thousands-of-users reality — where the
first bottleneck is **business-process complexity, not throughput.**

## Decision

**Modular-monolith-first.** *Design service boundaries from the beginning; do not deploy them as
separate services from the beginning.* Concretely:

1. **New insurance business domains become MODULES in a single app — `ktayl-core` — not new
   services.** Clean internal boundaries (`src/<domain>/` with its own API/interface and its own
   logical data boundary), one deployable, one Postgres (schema-per-domain), one CI/Kargo/board.
   The 12 scaffold domains land here as they are built (need-first), not as 12 services.
2. **Extract a module into its own service ONLY when the decision test below turns several
   "yes".** Extraction is a later, justified step (the thesis's Phase 3), recorded in an ADR.
3. **The 4 existing services stay** — they are treated as *deliberate, justified extractions*, not
   the default (see the test applied below). Do not tear down working, live services to prove a point.
4. **`ktayl-core`'s stack is NOT pre-locked here — it is chosen fit-for-purpose WHEN the first
   domain is built.** The modular-monolith *pattern* + the module discipline above are
   **framework-agnostic**; the only hard requirement is a framework that supports **clean module
   boundaries + DI + in-process domain events** (ideally one that *verifies* boundaries). Decide
   against the **actual solution's** needs at build time (transactional weight · team/skills ·
   performance/footprint · existing integrations) — the `tech-stack-selection.md` mindset, not a
   default. Strong candidates, by fit — **not a ranking, a shortlist to evaluate then**:
   - **NestJS** — the `@Module` system is modular-monolith-native; matches `ktayl-iam`; fast solo velocity.
   - **Java / Spring Boot + Spring Modulith** — heaviest-transactional home turf; Modulith
     *machine-verifies* boundaries + gives per-module test slices; matches `ktayl-claims`.
   - **.NET / ASP.NET Core** — strong modular DI (adds a new ecosystem to run solo, though).
   - Express / others — possible, but need discipline (no built-in boundary enforcement).
5. **`ktayl-core` is created NEED-FIRST — NOT scaffolded ahead of a domain (decided 2026-09-30).**
   See *When `ktayl-core` is created* below. An empty modular monolith is not a reference; it is
   structure-ahead-of-need — the same anti-pattern this ADR warns against.

### The extraction decision test (extract when several become true)

| Question | Extract? |
|---|---|
| Does this domain need **independent deployment**? | ✅ |
| Does **another team** own it? (N/A while solo) | ✅ |
| Very different **scaling** profile? | ✅ |
| Different **technology stack** (e.g. Python/ML)? | ✅ |
| Needs strong **data isolation**? | ✅ |
| Different **availability/SLA**? | ✅ |
| Consumed by **several applications**? | ✅ |
| A clear, stable **business boundary**? | ✅ |

### The test applied to today's 4 services (the story to tell)

- **`ktayl-iam`** — consumed by *every* app; company-wide identity → **justified service.** ✅
- **`ktayl-claims`** — an ACL over a frozen, different-stack (Java 8/SOAP) legacy; the Strangler
  pattern *needs* the boundary → **justified service.** ✅
- **`ktayl-underwriting`** — Python/FastAPI because pricing/rating math is Python-native →
  "different tech stack" → **borderline-justified.** ~✅
- **`ktayl-policy-service`** — the *core transactional* domain, synchronously called 3× by
  underwriting. This is the one a modular-monolith purist folds in; kept (live, demonstrates
  Go/gRPC) but it is **the coupling seam to watch.** ⚠️

## When `ktayl-core` is created — need-first (decided 2026-09-30)

`ktayl-core` **does not exist and is not scaffolded empty.** Verified 2026-09-30: no `ktayl-core`
among the 45 org repos; the candidate domains (`ktayl-finance`, `ktayl-distribution`,
`ktayl-compliance`, …) are **designed but not built** — a README + a full BMAD backlog (boundaries +
scope already worked out), **0 code**. So the boundaries the modular monolith needs are already
designed; only the code is absent, and no active sprint is demanding it.

**Decision: create `ktayl-core` the day the FIRST genuinely-custom, greenfield insurance domain is
actively prioritized for build — born WITH that first module (boundaries enforced from commit one by
the fit-for-purpose framework chosen then) — never before.** Realistic first trigger: **Distribution / CRM** (broker
portal, CRM, commissions, co-insurance) — genuinely custom insurance LOB with **no off-the-shelf
substitute**. Rationale: an empty reference monolith rots and is a liability; a monolith is a
reference only when it carries a real domain. Choosing *not* to build ahead of need is the senior
call and costs nothing — the strategy + boundaries + stack are recorded here, so first-module
bring-up is ~an afternoon.

### Adopt-vs-build — `ktayl-core` hosts only the genuinely-custom LOB
Not every "domain" is a module to build. Much is already covered by **adopted tools**; `ktayl-core`
**integrates with** them rather than rebuilding them:

| Capability | Already provided by | `ktayl-core`'s part |
|---|---|---|
| GL / financial close / HR | **ERPNext** (live) | the insurance-finance **LOB** only (premium billing, IFRS 17, reserving, bordereaux) → integrates to ERPNext GL |
| ITSM / helpdesk / CMDB | **GLPI** (`ktayl-itsm`) | — (adopt) |
| Reporting / BI | **data-platform / Metabase** (live) | — (adopt; emit data/events) |
| Documents / GED / OCR | **Paperless / DMS** | — (adopt) |
| Identity | **`ktayl-iam`** (service) | consume it |
| Policy · Claims · Underwriting (core value chain) | **already live as 3 services** | integrate at the boundary (the UW→policy seam) |

The genuinely-custom, `ktayl-core`-bound surface is the **insurance LOB logic no tool does**:
Distribution/CRM, the finance-LOB layer, compliance-workflow, MDM. The platform is therefore a
deliberate **hybrid** — adopted tools + a few justified services + one `ktayl-core` modular monolith
for the custom LOB — not "everything in one monolith," not "everything a microservice."

## Consequences

**Positive:** ~10× less per-domain toil for a solo dev; enforced DDD module boundaries with a
clean extraction escape-route; the portfolio now demonstrates **both** patterns **and** the
judgment to choose between them (the more senior signal); one harness, one pipeline, one DB to run.

**Trade-offs / negative:** fewer discrete "services" on the portfolio surface (mitigated — the
judgment outweighs the count); `ktayl-core` is a larger single deployable (mitigated by schema
isolation + module ownership); a future extraction is real work (mitigated by designing the
boundaries up front — which is the whole point).

**Implications (staged, need-first — NOT an immediate teardown):**
- The 12 scaffold **repos/boards** are the wrong structure under this ADR. When a scaffold domain
  gets real work, its code goes into `ktayl-core` as a module and its backlog consolidates onto the
  `ktayl-core` board. Idle scaffolds stay untouched until then (harmless briefs).
- Board model (`github-projects.md`): `ktayl-core` is **one product board**, not 12. Revisit the
  per-domain boards for the unbuilt domains at consolidation time.
- The `underwriting → policy` sync bind seam: keep (justified) but ensure a **timeout + circuit
  breaker** on the policy client; if the chain grows, prefer an **async saga** over deeper sync calls.

## Phased path (from the thesis)
```
Phase 1  ktayl-core modular monolith (domains = modules)
Phase 2  + async domain events (NATS) between modules where useful
Phase 3  extract a module to a service when the decision test justifies it
Phase 4  a service-oriented platform only where scale/stack/ownership justify it
```

## References
- `.claude/rules/architecture-strategy.md` (the auto-loaded principle derived from this ADR)
- `.claude/rules/tech-stack-selection.md` (per-domain language choice)
- `.claude/rules/conventions.md` (deployment-repo vs code-repo)
- `.claude/rules/github-projects.md` (product-board model — revisit for ktayl-core)
- Ground-truth review 2026-09-30 (4 live services + 12 scaffolds; UW→PAS + Claims→legacy seams).
