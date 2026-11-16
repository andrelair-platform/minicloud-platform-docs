---
slug: crossplane-without-a-cloud
title: "Crossplane Without a Cloud — Why I Deferred It for a Year, and What Finally Earned Its Place"
authors: [andrelair]
tags: [crossplane, platform-engineering, idp, self-service, backstage, architecture]
date: 2026-11-16
description: "The reflex is that Crossplane is for provisioning cloud resources — RDS, GKE, S3 — so on a bare-metal cluster with no cloud account, it has nothing to do. I believed that and deferred it for a year. I was wrong about what Crossplane is for. Its value isn't a cloud account; it's a self-service infrastructure API, and the thing that makes that worth building is a developer portal. Here's the decision, what I built (including the composite-of-composites that genuinely impressed me), the boundary that keeps it from duplicating Helm, and the lesson about timing."
---

For about a year, my platform's architecture doc had a page titled **"Phase 11 — Crossplane (Deferred)."** The reasoning on it was, I thought, sound: Crossplane provisions external infrastructure as Kubernetes resources — AWS RDS instances, GKE clusters, Azure subscriptions — and my cluster is six laptops in a cupboard. No cloud account, no cloud resources, nothing to provision. So Crossplane had no job to do. Defer it.

That page even predicted its own ending: *"the most likely home for Crossplane is the Backstage / developer portal, where Compositions are the templates a developer clicks create on."*

Last week I deleted the word "Deferred" from the title. Here's what I'd gotten wrong, and what finally made Crossplane earn its weight.

{/* truncate */}

## The thing I was wrong about

I was defining Crossplane by its **providers** — provider-aws, provider-gcp — and concluding that without a cloud, there's nothing to orchestrate. That's looking at the plumbing and missing the point.

Crossplane's actual job is to be a **self-service infrastructure API**. A platform team defines a new Kubernetes resource type — say `PostgresInstance` — and a *Composition* that turns one short claim into all the real objects a database needs. A developer then writes six lines of YAML (or clicks a button) and gets a database. No Helm, no `kubectl`, no PR into the platform's internals.

Seen that way, the trigger for adopting Crossplane was never *"do I have a cloud account."* It was ***"do I have someone who wants to self-serve infrastructure."*** And the moment that became true was the moment a developer portal (Backstage) went up with golden-path templates. The deferral note had the right answer written on it the whole time.

This is the generalisable lesson, so let me pull it out of the Crossplane-specific story:

> **The right time to adopt a tool is not when the tool is interesting. It's when a real consumer for it exists.** Crossplane without a self-service consumer is a control plane managing nothing — impressive and pointless. With a portal in front of it, it's the engine of the whole IDP. Same software, a year apart, completely different value.

## What I built

Two self-service APIs, each a Crossplane *Composite Resource Definition* (the new type) plus a *Composition* (what it renders), both consumed from Backstage.

**`PostgresInstance`** — a developer asks for a database by size, and gets a CloudNativePG cluster (one instance for `small`, a two-instance HA pair for `medium`), a NetworkPolicy that locks it to the namespace, and a connection secret. One claim, three real objects.

**`AppBundle`** — this is the one that made me grin. It's an app's *whole infrastructure baseline* in a single claim, and the way it's built is the advanced Crossplane move: a composite that **composes another composite**.

```
AppBundle/orders            (one claim)
├─ PostgresInstance/orders   ← a NESTED composite, reconciled by its OWN Composition
│   ├─ Cluster/orders-cnpg        (the database)
│   └─ NetworkPolicy/orders-db-netpol
└─ NetworkPolicy/orders-baseline  (the app's default-deny network baseline)
```

`AppBundle` doesn't re-implement the database — it *claims a `PostgresInstance`*, which Crossplane then expands via its own Composition. Delete the one `AppBundle` and the entire tree garbage-collects. A high-level request assembling lower-level requests: that's the pattern that turns a pile of primitives into a real platform.

## The boundary that stops it duplicating Helm

The obvious trap with `AppBundle` is that it starts to look like "deploy my app," which the platform already does with a Helm golden path. So I drew a hard line:

- **Crossplane (`AppBundle`) owns the app's *infrastructure*** — its database, its network baseline.
- **Helm (`wrapper-service`) owns the app's *deployment*** — the Deployment/Rollout, Service, Ingress, TLS cert.

They **compose** instead of overlapping: the Deployment mounts the secret the bundle created, and its pods are selected by the baseline NetworkPolicy. Infra vs runtime. If you don't draw this line explicitly, a "bundle" abstraction will slowly eat the deployment path and you'll have two tools fighting over the same objects.

## The honest parts

A few things that weren't free:

- **Installing on a hardened cluster is a cascade, not a `helm install`.** Gatekeeper, a locked-down ArgoCD AppProject and a scoped-RBAC model each had to be taught about Crossplane's provider pods before anything ran. Worth writing down once; painful to rediscover.
- **Composing a nested composite bit me.** My first `AppBundle` tried to write a status field *onto the composed `PostgresInstance`* — a field that isn't in that resource's schema — and the whole nesting silently failed to materialise. To surface a value you read *from* the child, not patch *into* it. The live test caught it; a unit test would not have.
- **It's still bare metal.** The provider I use is `provider-kubernetes`, which composes in-cluster resources. The day I want self-service *cloud* buckets, I add `provider-aws` pointed at an always-free tier — but I'm applying the same rule: only when a real consumer asks.

## So: was deferring it a mistake?

No — and that's the point. Building Crossplane a year ago, with no portal and no one to self-serve, would have been a control plane orchestrating nothing: maintenance cost, zero value. Building it the week the portal needed "click → database" was exactly right. The tool didn't change. The *consumer* arrived. That's the signal to watch — not the tool's reputation, and not a 22-phase plan that happened to pencil it in for last spring.

*The full as-built — the XRDs, the Compositions, the install cascade — lives on the [Crossplane page](/platform/iac/crossplane) in the platform docs.*
