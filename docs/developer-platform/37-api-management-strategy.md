---
id: api-management-strategy
title: API Management Strategy — interim catalog + gated gateway
sidebar_label: 🔌 API Management
sidebar_position: 37
---

# API Management Strategy

:::note Status
✅ **Interim model LIVE (2026-11-15).** API management is a **Platform capability composed from the
platform**, not bought as a product. The **catalog + identity + policy** layer runs today; the dedicated
**external API gateway** (runtime tier) is **designed and deliberately deferred** behind a real external
consumer.
:::

:::info Pillar
This is a **Platform** capability (it *provides* API discovery / identity / policy / gateway to every
app — it survives unchanged regardless of the insurance business). The *business use* — which specific
broker / claims / policy APIs flow through it — is **IS**, covered by the business-application pages. See
the [Platform ↔ IS dependency matrix](../architecture/platform-is-dependency-matrix.md) for the pillar axis.
:::

This page is a **pointer** (map, not library). The authoritative decision, the as-built detail and the
switch-trigger checklist live in the ADR:

> **ADR-0001 — API Management Strategy**
> [`ktayl-integration/docs/architecture/adr/ADR-0001-api-management-strategy.md`](https://github.com/andrelair-platform/ktayl-integration/blob/main/docs/architecture/adr/ADR-0001-api-management-strategy.md)
> (the founding ADR of the Integration domain, board **#25 / INT-01**, which owns the gateway *build*).

## The decision in one line

> **API management = PROVIDE a catalog + identity + policy now (Backstage · Authentik · Cilium ·
> OpenAPI/L3 contracts); add a dedicated gateway ONLY at the edge, gated behind the first external
> consumer.** We do **not** run a monolithic APIM product.

## What is live today (the interim model)

| Capability | Provided by |
|---|---|
| API **catalog / developer portal** — discovery, ownership, OpenAPI/Swagger rendering, provider↔consumer graph | **Backstage** (11 API entities registered + served) |
| **AuthN / AuthZ** — SSO + service-to-service | **Authentik** (OIDC + M2M client-credentials) |
| **Network / L7 policy** | **Cilium + Hubble** (default-deny) |
| **API contracts** | committed `api/openapi.yaml` + **L3 contract tests** |

**Scope (precise):** this is the catalog + identity + policy half, for **internal (east-west)** APIs. It
does **NOT** include the runtime gateway half — **no per-consumer API keys, rate-limiting, quotas,
request transformation, or per-API usage analytics**. Backstage is a *portal*, not a *dataplane*.

## When we switch to "real" API management (the gateway tier)

**The one-line test:** *does an API now face a party we don't control, or does money / metering ride on
it?* → **yes** = build the gateway · **no** = stay interim.

Stand up the **Kong OSS (DB-less)** edge gateway the first time **any** of these is true:

1. **First external / third-party consumer** (the primary trigger — a broker, reinsurer, EDI/coverholder).
2. **Per-consumer API keys** needed (not an Authentik OIDC flow).
3. **Rate-limiting / quotas** to protect a partner- or public-facing backend.
4. **Per-consumer / per-API usage analytics** (billing, SLA, "who called what").
5. **Monetization** — a metered API to paying customers.
6. **Edge mediation / transformation** (EDI / legacy / versioning facade for an external consumer).
7. **A regulatory / audit requirement** on the external API surface (DORA / ACPR per-consumer audit).

**Not triggers (stay interim):** more internal services calling each other · an internal UI/BFF hitting
an internal API · wanting a nicer catalog · adding more internal specs.

See the ADR for the full rationale, the rejected alternatives (monolithic APIM, fabricated partner), and
the gateway-build step.
