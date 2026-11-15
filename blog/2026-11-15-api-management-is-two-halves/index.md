---
slug: api-management-is-two-halves
title: "API Management Is Two Halves — and You Already Own the Important One"
authors: [andrelair]
tags: [api-management, backstage, platform-engineering, architecture, api-gateway, governance]
date: 2026-11-15
description: "Someone asks you to 'put API management in place' and the reflex is to go shopping — Kong, Gravitee, WSO2, Apigee. I didn't buy anything. Because 'API management' is actually two different halves, and on a platform that already has an identity provider, a network policy layer and a service catalog, you already own the half that matters for internal APIs. Here's the decision, what I built, the one question that tells me when to buy a gateway, and the two things I got wrong on the way."
---

Someone asks you to *"put API management in place,"* and the reflex is to open a browser and compare products: Kong, Gravitee, WSO2, Apigee, Tyk. Pick one, deploy it, call it done.

I didn't buy anything. Not out of frugality — out of a realisation that saves a lot of footprint and regret: **"API management" is not one thing. It's two halves, and most teams already own the half that actually matters for their internal APIs.**

This is the decision I made for my simulated insurer's platform, what I actually built, the one question that tells me when the *other* half becomes necessary — and, honestly, the two things I got wrong on the way.

{/* truncate */}

## The two halves

When people say "API management," they mean some mix of these, and the two groups behave completely differently:

| Half | What it does | Shape |
|---|---|---|
| **Catalog + governance** (a *portal*) | discovery, ownership, API contracts, who-consumes-what, identity, network policy | control plane |
| **Gateway + runtime** (a *dataplane*) | per-consumer API keys, rate-limiting, quotas, request transformation, per-API usage analytics | data plane |

A monolithic API-management product sells you both in one box. That's the trap. Because the moment you look at what you *already run*, you notice something:

- **Identity / authn-authz?** Already there — a single sign-on provider issuing OIDC tokens for users and client-credentials for service-to-service.
- **Network / L7 policy?** Already there — a default-deny CNI with per-service policy.
- **API catalog / developer portal?** Already there — a service catalog that renders OpenAPI, tracks ownership, and draws the provider↔consumer graph.
- **API contracts?** Already there — a committed `openapi.yaml` per service and contract tests in CI.

That list *is* the first half of API management. For **internal** (service-to-service) APIs, it's the whole job. Buying a monolithic product to get it would mean deploying a **second** identity provider and a **second** portal just to obtain a gateway I didn't yet need — and paying for that in cluster footprint on hardware that doesn't have it to spare.

## The decision: compose now, gate the gateway

So the strategy became one line:

> **API management = provide a catalog + identity + policy now (from what the platform already runs); add a dedicated gateway *only* at the edge, gated behind the first real external consumer.**

No monolithic product. The rejected alternative wasn't rejected on taste — it was rejected because it duplicated two systems I already operate and solved a problem (external, keyed, rate-limited APIs) that I don't have *today*.

## What I actually built (the interim model)

The missing piece wasn't a gateway. It was that the catalog was **empty** — the platform *could* render APIs but nobody had registered them. So I did the cheap, high-value thing: I registered the real APIs as first-class catalog entities — each with its owning component, its provider↔consumer relationship, its rendered OpenAPI, and a link to the authoritative docs.

That turns the catalog from a nice idea into a real map: an engineer can now find an API, see who owns it, read its contract, and know who consumes it — without asking anyone. Combined with the identity provider, the network policy layer and the committed contracts, **that is working API management for internal traffic.** It cost no new infrastructure.

The honest scope matters, though: this is the **catalog + identity + policy** half. It does **not** rate-limit, issue API keys, enforce quotas, transform requests, or produce per-consumer analytics. A catalog is a portal, not a dataplane. Claiming otherwise would be the kind of overstatement that gets found out in an architecture review.

## The one question that tells me when to buy a gateway

The whole point of *gating* the gateway is having a crisp trigger, so the decision isn't vibes. Here it is:

> **Does an API now face a party I don't control, or does money / metering ride on it?**
> **Yes → build the gateway. No → stay interim.**

Concretely, I stand up a real edge gateway the first time any of these is true:

1. **A real external / third-party consumer** calls an API — a broker, a reinsurer, an EDI partner. *(This is the primary trigger.)*
2. **Per-consumer API keys** are needed — a partner expects a key to rotate and revoke, not an OIDC flow.
3. **Rate-limiting or quotas** must protect a partner- or public-facing backend.
4. **Per-consumer usage analytics** — billing, SLA reporting, "who called what, how often."
5. **Monetisation** — a metered API to paying customers.
6. **Edge mediation / transformation** — protocol or format translation for an external consumer.
7. **A regulatory audit requirement** on the external API surface.

And the mirror image — the *non*-triggers, which is where discipline lives: more internal services calling each other, an internal UI hitting an internal API, or simply *wanting a nicer catalog* are **not** reasons to stand up a gateway. The common thread of every real trigger is a consumer outside the trust boundary, or money.

Today the platform is below all seven. So the interim model isn't a stopgap I'm embarrassed about — it's the *correct* state for where the system actually is.

## Two things I got wrong (because pretending otherwise helps no one)

**1. I started inventorying instead of mapping.** My first instinct was to register *every* API-shaped thing. Wrong: a catalog is an **integration map, not an HTTP-surface inventory**. An API entity that nothing consumes teaches a reader nothing. I also managed to register a couple of **duplicates** — because I added entities without first checking that some services already shipped their own catalog entries. The fix was to register only APIs with a real role, and to always check what exists first. (A duplicate even collided on a name; the stale copy quietly self-pruned once I removed the source — but it was avoidable.)

**2. I filed the strategy under the wrong architectural pillar.** I first documented this as an *Information System* concern, because the integration domain it belongs to sits under an "IS Foundations" grouping. But API management is a **platform capability** — it *provides* catalog/identity/policy/gateway to every app and would survive unchanged if the insurance business disappeared tomorrow. The grouping label and the platform-vs-business pillar are **orthogonal axes**, and I'd conflated them. Moved it to the platform pillar, where a shared capability belongs. The *use* of those APIs stays with the business; the *capability* is platform.

## The takeaway

"Put API management in place" almost never means "buy an API-management product." It means: **make your APIs discoverable, owned, contracted, authenticated and policy-governed now** — which, on a mature platform, you can mostly *compose* — and keep the gateway as a deliberate, triggered decision rather than a default purchase. Then write the trigger down, so the day it fires you act on evidence instead of a hunch.

---

*This platform runs a simulated insurer used as an engineering laboratory — no real customers or production traffic. The claim here is engineering judgement and a working interim capability, not commercial scale.*
