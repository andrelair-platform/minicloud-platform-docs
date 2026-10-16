---
id: identity-two-layer
title: Two-layer identity — workforce + customer IdP
sidebar_label: 🪪 Two-layer identity
---

# Two-layer identity — self-hosted workforce IdP + managed customer IdP

:::note Summary + pointer
This page is the discoverable map entry. The decision of record — alternatives weighed, the
federation-spike evidence, compliance mapping — is the ADR in the GitOps repo (linked below).
Status: **Accepted** (federation spike verified 2026-09-12).
:::

The platform authenticates ~30 internal tools (ArgoCD, Grafana, Vault, Harbor, Backstage, Plane,
ERPNext, Open WebUI, …) through **Authentik**, self-hosted on the cluster. The recurring question —
*"should we replace Authentik with Microsoft Entra ID, since that's what enterprises use?"* — is
answered here once, deliberately.

> **Adopt a two-layer identity model; do not replace Authentik.** Workforce SSO and customer identity
> are two different problems with different constraints.

1. **Workforce / platform IdP = Authentik (self-hosted).** All staff + internal-tool SSO stays on
   Authentik. **Hard rule: the control plane (ArgoCD, Vault, Grafana, Harbor, Backstage) must never
   depend on an external cloud IdP for login** — availability + bootstrap (you can't log in to Vault
   to fix an outage *caused by* losing external connectivity).
2. **Customer / external IdP = Microsoft Entra External ID** (free ≤50k MAU), introduced **only when a
   customer-facing product needs it** (Retrieva SaaS users, a broker portal) — never for staff SSO.
3. **Enterprise-SSO credibility = federation, not migration.** Authentik may federate *to* Entra as an
   upstream source ("Login with Microsoft") to demonstrate enterprise SSO **without** making the
   platform depend on Entra — it adds a *source*, not a dependency.

## Why not Entra as the primary IdP

Moving the platform's most foundational service into a US-jurisdiction managed SaaS means sovereignty
loss + residency/CLOUD-Act exposure, a **bootstrap circular dependency**, and cost (workforce SSO +
Conditional Access needs paid P1/P2, breaching the €10/mo/provider cap). It also contradicts the
platform's own thesis — a sovereign, DORA-compliant IS. The two-layer model keeps the sovereign core
and *demonstrates* concentration-risk discipline (DORA Art. 28–29) instead of violating it.

## Federation spike (verified 2026-09-12)

Proved the Authentik ← Entra mechanism end-to-end: an Entra app registration + an Authentik
`OAuthSource` (created via the `ak shell` ORM — Authentik's REST API 403s on this version, so the
config is ORM/UI-only), the "Microsoft Entra" button renders, and clicking it completes the OIDC
round-trip to Entra's own MFA gate. Conclusion: federation *works*, but it's **not** a workforce IdP
here (a 2-user personal tenant has no population to federate) — Entra's real value is customer identity.

## Full ADR

Decision, alternatives, the full spike write-up + teardown, and compliance mapping:
[**`docs/identity-two-layer.md`**](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/identity-two-layer.md).
Related: [SSO via Authentik](./sso-authentik).
