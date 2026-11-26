---
id: how-sso-works
title: How SSO & login work
sidebar_label: How SSO works (start here)
tags: [explanation]
---

# How SSO & login work

> **Explanation.** One login (**Authentik** + MFA) for everything — apps, `kubectl`, even email. This page
> is the map of *how* that works; each row links to the detail.

**Who this is for:** anyone who wants the "how does login work here?" picture before diving into the
per-topic pages.

## One identity provider, three ways in

All access flows through **Authentik** (the identity provider). How an app plugs in depends on whether it
speaks OIDC itself:

| You access… | How it authenticates | Detail |
|---|---|---|
| **An app that speaks OIDC** (ArgoCD, Grafana, Backstage…) | the app redirects you to Authentik → you log in (+MFA) → it gets a token back | [SSO with Authentik](/platform/security-enterprise/sso-authentik) |
| **An app with no login of its own** | the **ingress** checks with Authentik *before* the app sees the request (forward-auth) | [SSO with Authentik](/platform/security-enterprise/sso-authentik) · [Public access](/platform/security-enterprise/phase25-public-access) |
| **`kubectl`** (the cluster API) | `kubelogin` gets an OIDC token from Authentik; the k3s API server validates it (JWKS) | [kubectl OIDC access](/platform/security-enterprise/kubectl-oidc-access) |
| **Email** (Stalwart) | the **same credential**, federated via an Authentik LDAP outpost | [Mail ↔ Authentik LDAP](/platform/security-enterprise/mail-authentik-ldap) |

> Whatever the path, it's **one credential + MFA**. Identity *is* the perimeter — the platform is
> BYOD / zero-trust, so every app is SSO-gated rather than trusting the network.

## Who decides what you can do

Two distinct roles — don't conflate them:

- **System of Record** (who *may* access what) = the **ktayl-iam** catalog — the authoritative `role → group` model.
- **Policy Enforcement Point** (who *enforces* it) = **Authentik** — it checks your groups at login via the OIDC `groups` claim / forward-auth.

The per-tool map of *who can reach and do what* is the
[Platform Access Matrix](/platform/security-enterprise/platform-access-matrix).

## Two identity layers

**Workforce** identity (staff → Authentik) and **customer** identity (end-users → a separate IdP) are
different problems, solved separately — see the
[two-layer identity model](/platform/security-enterprise/identity-two-layer).

## Kubernetes specifics

How the OIDC token reaches the k3s API, MFA enforcement, and human-vs-workload identity:
[IAM hardening](/platform/security-enterprise/iam-hardening) ·
[RBAC audit](/platform/security-enterprise/rbac-audit).

## Related

- [SSO with Authentik](/platform/security-enterprise/sso-authentik) — the foundational "how it works"
- [Platform Access Matrix](/platform/security-enterprise/platform-access-matrix) — who may reach what
- [Glossary: IdP · OIDC · forward-auth · PEP · SoR](/glossary)
