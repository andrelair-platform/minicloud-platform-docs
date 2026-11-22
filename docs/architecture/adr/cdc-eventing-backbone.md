---
title: "ADR: CDC & the Eventing Backbone"
sidebar_label: "🔄 CDC & Eventing Backbone"
---

# ADR: CDC scope & the eventing backbone — Debezium is a scoped legacy-strangler bridge, not the universal "capture-once" backbone

**Status:** Accepted (2026-11-21) · **Owner:** SA/TL (AndreLiar) · **Scope:** platform-wide integration/eventing strategy across the ktayl-solution IS (ktayl-core, ktayl-claims, Data Platform #5). Cross-references ktayl-core **ADR-007** (internal events vs NATS), **ADR-003** (Billing ingest via JetStream), and `modular-monolith-first.md`.

## Context — the question this ADR answers

A reasonable architecture proposal keeps recurring: use **Debezium as the single backbone** — "capture
once, distribute everywhere". One CDC capture off every operational database, fanned out two ways: a
real-time stream to applications **and** a sink connector to the data warehouse. The pitch is that it
avoids two tools on the primary DB, and that Airbyte/dlt alone can't do application-grade real-time.

The pattern is sound in the abstract. This ADR records **why we deliberately did *not* make Debezium the
universal backbone**, and what we built instead — so the decision is evidence, not tribal knowledge, and
so the revisit trigger is explicit.

**Ground truth (what actually runs today):**

- The standard async bus is **NATS / JetStream** — *not* Kafka. There is no Kafka cluster, no Kafka
  Connect, no schema registry in the stack.
- **Debezium *is* deployed** — but as **Debezium Server (standalone, file-based offsets, no Kafka) →
  NATS JetStream**, scoped to **one** source: the `ktayl-claims` legacy `globalcore` MySQL binlog
  (`services/ktayl-claims/helm/templates/debezium.yaml`; tables `gc_claim`, `gc_policy`,
  `gc_policy_peril`; subject `claims-cdc.globalcore.<table>` → a JetStream stream → CDC read models).
- Greenfield module→module interaction inside `ktayl-core` is **in-process Spring application events**
  (ADR-007). Cross-deployment interaction is a **versioned NATS integration event** (e.g. Underwriting
  `insurance.underwriting.bound-risk` → Billing, ADR-003).
- The **DB → warehouse** leg is served by the **Data Platform (#5): scheduled dbt ELT** (read-only
  `analytics_ro` → CNPG `analytics` medallion → Metabase), *not* a CDC sink.

So the choice was never "CDC or nothing". It was: **where does CDC belong, and what is the bus.**

## Decision

**CDC (Debezium) is a scoped tool for crossing a boundary we do not own; it is not the universal
eventing backbone. The backbone is NATS/JetStream carrying intentional events: in-process domain events
inside a deployment, versioned integration events across one. Reporting is served by dbt ELT.**

Concretely:

1. **Own the source → publish a domain/integration event, never CDC your own tables.** A module you own
   emits a business event at the point the business fact occurs (`PolicyBound`, `ClaimSettled`). That
   event is part of the *published contract* — intentional, versioned, documented (we literally publish
   named interfaces: `submission.api`, `screening.api`). CDC captures *row changes*, which leak the
   physical schema and rebuild a distributed monolith across tables you control — the exact trap ADR-005/
   006/007 exist to prevent.

2. **Don't own the source (frozen legacy / black-box) → CDC is correct, and that is where Debezium runs.**
   GlobalCore is a frozen COBOL/CICS-style core we cannot change; CDC off its binlog is the only
   *non-invasive* read path and is precisely the Strangler-fig "don't let the legacy core become a
   bottleneck" pattern. This is the *only* sanctioned CDC source today.

3. **The bus is NATS/JetStream, reached via Debezium *Server*, not Kafka + Kafka Connect.** We do not
   introduce Kafka. Debezium Server sinks CDC straight to JetStream; JetStream also carries every
   greenfield integration event. One bus, two producer styles (CDC for legacy, domain events for owned).

4. **Reporting / DWH = dbt ELT, not a CDC sink.** Insurance/DORA reporting is not a sub-second
   requirement; micro-batch ELT into the medallion warehouse is adequate and far cheaper to operate than
   a CDC→DWH sink per source. The Data Platform reads sources read-only (ADR "no shared operational DB").

5. **Reliable externalization of an owned event = transactional outbox, not CDC-on-business-tables.** When
   an in-process domain event must also become a NATS integration event, use the **outbox** (Spring
   Modulith's event publication registry) — write the outbox row in the same transaction, relay to NATS
   (ADR-007). This gives the at-least-once guarantee people often reach for Debezium to get, without
   coupling consumers to the producer's schema.

## Why this over "Debezium as the single backbone"

| Force | Why it rules out universal CDC |
|---|---|
| **Encapsulation** | `ktayl-core` is a modular monolith with Spring Modulith enforcing module boundaries. CDC on another module's tables smashes straight through them — an anti-pattern *against* the chosen architecture, not a missing feature. |
| **Contract quality** | A domain event is a versioned, documented contract; a CDC row-change is the producer's internal schema leaking to every consumer. Insurance semantics (`PremiumCalculated`, not "row in `quote` changed") matter. |
| **Topology** | Debezium's canonical form is Kafka + Kafka Connect + schema registry + sink connectors — none of which we run. Standing up Kafka purely for CDC is a major new stateful component to operate/back up/secure on a resource-constrained 6-node cluster. Fails the **need-first gate** (`cloud-adoption.md`). |
| **Reporting freshness** | The DB→DWH need is already met by dbt ELT. A CDC→DWH sink adds operational burden for freshness nobody has asked for. |
| **Dual-write reliability** | Already solved for owned events by the Modulith outbox/event-publication-registry — CDC-on-outbox would be the heavyweight alternative to a mechanism we already have in-process. |

**Where the proposal is right (and we agree):** external **SaaS** sources (Stripe, Salesforce, HubSpot)
into the DWH are **not** a Debezium job — that is the Airbyte/dlt leg. If/when BI needs Stripe data, use
dlt/Airbyte, independent of any CDC decision. The proposal's own table says exactly this; we concur.

## Consequences

- **Positive:** no accidental distributed monolith; internal refactors don't break external contracts;
  one bus (NATS/JetStream) with two clear producer styles; CDC confined to the one place it is genuinely
  the only option (frozen legacy); the warehouse leg stays cheap (ELT) and sovereign.
- **Negative / accepted:** two producer mechanisms to understand (CDC for legacy, domain events for
  owned) plus an outbox+relay to operate — justified, because collapsing them into "CDC everything" is
  exactly the mistake this ADR prevents. Reporting is micro-batch, not real-time — accepted until a
  freshness requirement proves otherwise (below).
- **Rule of thumb:** *CDC only what you cannot change; publish events for what you own; ELT for reporting.*

## Revisit triggers (when Debezium's footprint *should* grow)

Reopen this decision if **any** become true — each is a concrete, testable signal:

1. **A module graduates to its own service with its own DB** (per `modular-monolith-first.md` /
   ADR-008 extraction criteria) and needs guaranteed at-least-once event emission beyond the in-process
   registry → **Debezium-on-outbox** (tail a dedicated `outbox` table, *never* business tables) becomes
   the clean, non-leaky option. This is the single most likely future expansion.
2. **A near-real-time reporting requirement** appears (live fraud/SIU exposure, real-time regulatory
   dashboards) where micro-batch dbt ELT is demonstrably too stale → evaluate a CDC→warehouse sink *for
   that data product only*.
3. **A second frozen/black-box source** (another acquired legacy system) needs non-invasive capture →
   extend the existing Debezium-Server→JetStream pattern (as with `globalcore`), still *not* Kafka,
   unless the connector count makes Kafka Connect's operational model pay for itself.
4. **External SaaS → DWH** need → adopt **Airbyte/dlt** (not Debezium) for that leg.

Until one of these is real, the scope stays: **Debezium = the GlobalCore strangler bridge; NATS/JetStream
= the backbone; dbt ELT = reporting.**

## References

- ktayl-core **ADR-007** — internal domain events vs NATS integration events (+ transactional outbox)
- ktayl-core **ADR-003** — Billing ingest via the Underwriting `bound-risk` JetStream event
- ktayl-core **ADR-005/006** — bounded contexts, schema ownership, no shared operational DB
- `modular-monolith-first.md` — service granularity; the "async-first (NATS events, Debezium CDC)" posture
- `ktayl-integration/docs/legacy-wrapper-initiative-spec.md` — the ACL + CDC-fed read-model strangler design
- `ktayl-data-platform/docs/architecture.md` — the dbt ELT medallion (the DB→DWH leg)
- Live config: `minicloud-gitops/services/ktayl-claims/helm/templates/debezium.yaml`
