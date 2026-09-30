---
slug: modular-monolith-first
title: "Modular-Monolith-First: Sizing Architecture to the Problem, Not the Fashion"
authors: [andrelair]
tags: [architecture, modular-monolith, microservices, domain-driven-design, platform-engineering, insurance, decision-records]
date: 2026-09-30
description: "I run a simulated insurer's IS on Kubernetes, built as separate services per domain. Then I stopped and asked the uncomfortable question: is that the right architecture, or just the fashionable one? This is the decision I made — modular-monolith-first — and, more usefully, the decision I deliberately did NOT make: building the thing at all, yet."
---

There's a reflex in our industry, and I had it too: a new business domain shows up, and the hand reaches for *"…so that's a new microservice."* It feels modern. It feels scalable. It feels like what serious engineers do.

On the ktayl-solution information system — a six-node Kubernetes platform running a simulated insurer's entire IS — I'd built four domains exactly that way: policy, claims, underwriting, identity, each its own repo, CI pipeline, database, promotion track. Then I stopped and asked the question that matters more than any framework choice: **is this the right architecture, or just the fashionable one?**

This post is the answer I arrived at — **modular-monolith-first** — and, honestly, the more valuable half: the decision I deliberately *didn't* make.

{/* truncate */}

## Architecture follows the problem, not the fashion

The uncomfortable truth is that **microservices are a solution to an organisational problem, not a technical one.** They pay for themselves when *teams* need to deploy independently, when *scaling* profiles genuinely diverge, when a domain needs a *different stack*. They cost a fortune — service discovery, retries, circuit breakers, distributed tracing, eventual consistency, distributed transactions, N pipelines, N databases, N on-call surfaces — when you adopt them for a domain that has *none* of those pressures.

For an internal business platform — an insurer's IS, tens to a few thousand users — the first bottleneck is almost never throughput. It's **business-process complexity and maintainability.** And a modular monolith addresses exactly that while skipping the distributed-systems tax entirely.

So the default flipped. Not "a service per domain," but:

> **Start with a well-structured modular monolith. Move a part to its own service only when a concrete operational or organisational reason makes it true.**

I made that decision test explicit — extract when *several* of these turn yes: independent deployment · another team owns it · very different scaling · different tech stack · strong data isolation · different SLA · consumed by several apps · a clear, stable business boundary. **One or two yeses is not a service.** It's a module.

## What a modular monolith actually is (and the discipline that saves it)

A modular monolith is one deployable whose code is organised into **loosely-coupled modules** around business capabilities — you get the design benefits of services (clear boundaries, separation of concerns, independent evolution) without the network in between. But it only works if you enforce the discipline that separates it from a big ball of mud:

- **Modules talk through a public interface, in-process** — a function call or an in-process domain event, never another module's internals. Putting HTTP or a queue *between modules of the same app* rebuilds the distributed monolith *inside* the monolith. Don't.
- **One database, but isolated data** — one Postgres for simplicity, **schema-per-module, and a hard rule that a module never reads another module's tables.** That single constraint is what keeps coupling low *and* keeps the escape-route open: extracting a module later means lifting its schema and its interface, not untangling shared tables.
- **High cohesion, low coupling, single responsibility** — a change in `claims` must not ripple into `billing`.

Get that right and you have designed the service boundaries *without deploying them as services* — which is the whole game, because it makes the later extraction cheap instead of catastrophic.

## The honest audit of my own platform

Applying this to my own IS was uncomfortable, which is how I knew it was worth doing. The ground truth:

- **Four domains are real services** — and, tested against my own decision test, three are *justified*: `iam` (company-wide identity, consumed by everything), `claims` (an anti-corruption layer over a frozen, different-stack legacy — the boundary is the point), `underwriting` (Python, because pricing math is Python-native). The fourth, `policy-service`, is the core transactional domain that `underwriting` calls **synchronously three times at bind** — the textbook early tell of a distributed monolith. Justified today, but the seam to watch.
- **Twelve more domains were *designed but not built*** — a README and a full backlog each, and **zero lines of code.** The boundaries exist; the services don't. That turned out to be the best possible position: the design is done, and I hadn't yet committed the mistake of deploying twelve more services.

So the correction was narrow and clear: the four stay (they earned it); the twelve become **modules in a single app** as they're built, not twelve more services.

## Adopt before you build

Here's the part the microservices reflex hides completely: **most "domains" aren't yours to build.** My finance domain isn't a service to write — ERPNext already runs the general ledger and financial close. ITSM is GLPI. Reporting is a data platform and Metabase. Documents are Paperless. Identity is its own service already.

The genuinely custom surface — the code no off-the-shelf tool will ever write for you — is small and specific: the insurance line-of-business logic. Broker portal and CRM. Premium billing rules and IFRS 17. Commissions, co-insurance, compliance workflow. *That* is what a modular monolith should host; everything else, it should **integrate with, not reinvent.** The platform that results is a deliberate **hybrid** — adopted tools, a few justified services, and one modular monolith for the custom logic. Not everything-in-one; not everything-a-service.

## The two senior moves nobody puts on a slide

**1. The stack is a *late* decision.** I nearly fell into a second version of the same trap — pre-committing the monolith to a framework ("it'll be Spring Boot") before a single domain existed to build. That's the stack-fashion mistake wearing the modular-monolith outfit. The honest position is: the modular-monolith *pattern* is framework-agnostic; the *stack* is chosen **when the first real domain is defined, against what that solution actually needs** — could be NestJS, Spring Boot with Spring Modulith, .NET, whatever fits. Right tool for the task, decided at the moment you know the task. Not before.

**2. The most senior thing I did was not build it.** There is no modular monolith on my platform. I checked — zero of forty-five repositories. And I'm not going to create it now, because **an empty reference architecture is a liability, not a reference.** A modular monolith is only worth anything when it carries a real domain doing real work. So it gets born the day I actually prioritise building the first genuinely-custom greenfield domain — realistically the broker/CRM distribution layer — *with* that first module, and not one commit sooner. Choosing *not* to build, when everything in you wants to scaffold the clever thing, is a discipline. It's also almost always the right call.

## The signal is judgment, not service count

If there's a single thing to take from this, it's that the impressive artifact was never "I ran twenty microservices." Anyone can multiply services. The senior signal — the thing an architect, an interviewer, a certification jury actually reads — is the *judgment*: **a modular-monolith default, services only where a real boundary justifies one, adoption where a tool already exists, and the restraint to not build ahead of need.**

The whole decision cost nothing to *not* execute. It's written down as an architecture decision record; the boundaries are designed; the day a real domain needs a home, it's an afternoon's work. Until then, the most valuable line of code in this system is the one I chose not to write.
