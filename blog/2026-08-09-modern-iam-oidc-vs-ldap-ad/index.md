---
slug: modern-iam-oidc-vs-ldap-ad
title: "Why We Skipped LDAP, Active Directory, and Entra ID — And What We Built Instead"
authors: [andrelair]
tags: [iam, sso, oidc, oauth2, authentik, kubernetes, enterprise, security, identity, ldap, active-directory, self-hosted]
date: 2026-08-09
description: "Most enterprises carry 25 years of identity debt — AD on-prem, LDAP connectors, Entra sync agents. We built a Kubernetes platform from scratch and landed directly at the modern end of that arc. This post explains the difference and why it matters."
---

Most enterprise identity architectures did not start as what they are today. They started in 1999 with Active Directory, accumulated LDAP integrations over the following decade, and are now partway through a migration toward cloud-based identity via Microsoft Entra ID — carrying the weight of every layer that came before.

We built our platform from scratch. We never had an on-premises domain. We never configured LDAP. We skipped directly to the protocol stack that enterprises are spending years and significant money trying to reach. This post explains what we chose, why, and how the resulting identity architecture compares to the enterprise standard.

{/* truncate */}

## What Most Enterprises Actually Run

Before comparing, it is worth understanding what the enterprise identity stack looks like in practice, because the gap between what organisations have and what they are targeting is significant.

A typical large organisation has three layers coexisting simultaneously:

```
┌───────────────────────────────────────────────────────────────┐
│  Microsoft Entra ID                                           │
│  (cloud identity, modern apps, Microsoft 365)                 │
└────────────────────────┬──────────────────────────────────────┘
                         │ Entra Connect sync (bidirectional)
┌────────────────────────▼──────────────────────────────────────┐
│  Active Directory Domain Services (on-premises)               │
│  (Windows machines, Kerberos, Group Policy, legacy apps)      │
└────────────────────────┬──────────────────────────────────────┘
                         │ LDAP / LDAPS queries
┌────────────────────────▼──────────────────────────────────────┐
│  Legacy application layer                                     │
│  (VPNs, file servers, printers, older web apps)               │
└───────────────────────────────────────────────────────────────┘
```

Each layer was added because the previous one could not handle the new requirement. Each layer is still running because the applications depending on it cannot be migrated quickly enough. The organisation is paying the operational cost of all three simultaneously.

This is not a criticism — it is the reality of any system that has evolved over 25 years under real business constraints. But it does mean that what enterprises call "modern identity" is often Entra ID sitting on top of Active Directory sitting on top of LDAP, with sync agents managing consistency between all three.

---

## The Protocol Stack Underneath Each Layer

The three technologies are not equivalent in kind, which makes direct comparison misleading.

**LDAP** is a protocol — specifically, a wire format and query language for asking questions of a directory service. It does not store users itself. It defines how an application asks *"does this user exist?"* or *"what groups does this user belong to?"*

```
Application
     │
     │  LDAP query  (port 389 / 636)
     ▼
Directory service
     ├── uid=andre,ou=users,dc=company,dc=com
     ├── memberOf: cn=developers,ou=groups,...
     └── userPassword: {SSHA}...
```

**Active Directory** is a product that implements LDAP alongside Kerberos for authentication, DNS for service discovery, and Group Policy for Windows machine configuration. It is the dominant on-premises directory service because it shipped with Windows Server and became the default for Windows-centric enterprises.

**Microsoft Entra ID** is a cloud identity platform. Despite retaining "Active Directory" in its legacy name, it does not speak LDAP or Kerberos natively toward cloud applications. It speaks OAuth 2.0, OpenID Connect, and SAML — the same protocols used by every modern web service. The mental model shift is significant:

```
LDAP model                    OIDC model
──────────────────────        ──────────────────────
App queries directory         App delegates auth
App checks password           User authenticates at IDP
App manages session           IDP issues JWT token
App decides access            App trusts token claims
```

Under LDAP, the application is in control of authentication. Under OIDC, the identity provider is. This is a fundamentally better security boundary: the application never touches credentials, never stores password hashes, and never has to implement MFA itself.

---

## What We Built

Our platform runs on five bare-metal nodes — four ThinkPads and a MacBook Pro — with k3s as the Kubernetes distribution. From the first workload, we chose a single identity approach: **Authentik** as a self-hosted identity provider, with every application configured to use OIDC.

```
                    ┌──────────────────────────┐
                    │         Authentik         │
                    │   auth.devandre.sbs       │
                    │                           │
                    │  Users  Groups  Flows      │
                    │  TOTP   Sessions  Policies │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
           OAuth2             OpenID Connect      Proxy
              │                  │                  │
   ┌──────────▼─────┐  ┌────────▼──────┐  ┌───────▼──────┐
   │ ArgoCD         │  │ Open WebUI    │  │ Jitsi Meet   │
   │ Harbor         │  │ Grafana       │  │ (forward auth)│
   │ Plane          │  │ Backstage     │  └──────────────┘
   │ Vaultwarden    │  │ n8n           │
   │ ERPNext        │  │ Temporal      │
   └────────────────┘  └───────────────┘
```

Every application in the platform — more than fifteen — authenticates through a single login page with TOTP. There are no per-application password databases. No application stores credentials. There is no LDAP connector, no sync agent, no on-premises component of any kind.

The flow for a user accessing any protected resource is identical regardless of which application they are opening:

```
User opens ArgoCD / Grafana / Harbor / any app
              │
              │  302 redirect to Authentik
              ▼
      Authentik login page
              │
              │  password + TOTP
              ▼
      JWT issued with claims:
        sub: andre
        groups: ["authentik Admins"]
        email: kanmegnea@...
              │
              │  redirect back with code
              ▼
      Application exchanges code for token
              │
              │  reads groups claim
              ▼
      Access granted (admin or user tier)
```

---

## Feature-for-Feature Comparison

| Capability | Enterprise LDAP/AD | Microsoft Entra ID | Our Authentik stack |
|---|---|---|---|
| User store | AD DS | Entra ID | Authentik (PostgreSQL-backed) |
| Auth protocol | Kerberos / LDAP | OAuth2 / OIDC / SAML | OAuth2 / OIDC |
| MFA | Separate product (Duo, ADFS) | Entra MFA | Authentik TOTP (built-in) |
| SSO | Federated / complex | Native | Native |
| Group-based access | AD groups → app RBAC | Entra groups → app RBAC | Authentik groups → app RBAC |
| Windows domain | Required | Optional | Not applicable |
| App password storage | Per-app | Per-app (legacy) | Never — IDP only |
| Self-hosted | Yes (AD DS) | No | Yes |
| Cloud-native design | No | Yes | Yes |
| Conditional Access policies | No | Yes (premium) | Basic (Authentik policy engine) |
| Operational overhead | High (AD DCs, GPO, replication) | Low (managed) | Medium (self-operated) |
| Vendor lock-in | Microsoft | Microsoft | None |
| GDPR / data residency | Complex | Data in Microsoft DCs | Full control (on-prem) |

The protocol column is where the real difference sits. Kerberos and LDAP were designed for a world where every application lived inside a network perimeter and could reach a domain controller directly. OIDC was designed for a world where applications are distributed, may run in the cloud, and cannot assume network adjacency to an identity provider. Our stack was built for the second world from day one.

---

## The One Thing LDAP Still Does That OIDC Does Not

There is an honest reason LDAP has not simply disappeared: some applications do not speak OIDC and never will. Network switches, storage appliances, older VPN concentrators, legacy ERP modules, printers with access controls — many of these devices speak LDAP and nothing else.

Authentik handles this case with an optional **LDAP outpost**: a sidecar component that translates LDAP queries against the Authentik user store. If we ever need to authenticate a device that only understands LDAP, we do not need to run a separate directory. Authentik surfaces its users and groups over LDAP while the real store remains OIDC-native.

We have not needed this feature yet. Every application we deployed — including ERPNext (HR), Matrix Synapse (chat), Jitsi Meet (video), Plane (project management), and Vaultwarden (passwords) — has native OIDC support. The LDAP outpost exists as a fallback for the legacy integration case, not as a primary path.

---

## The Operational Tradeoff We Accept

Running a self-hosted identity provider is not free. The honest tradeoffs compared to a managed service like Entra ID are:

**Single point of failure.** Authentik is a single pod in our cluster. If the `auth` namespace goes down — during a Kubernetes upgrade, a storage rebuild, a node failure — every SSO-protected application becomes unreachable until it recovers. This is why every critical application has a break-glass local admin account (`~/.argocd-admin`, `~/.grafana-admin`, etc.) stored on the controller for emergencies.

**We operate the upgrades.** Entra ID upgrades itself. We schedule Authentik upgrades, test them in staging, and roll them out manually. This is a few hours of work per major version, not a continuous burden, but it is work that Entra ID customers do not do.

**No Conditional Access equivalent.** Entra ID's Conditional Access lets you say *"require MFA only when the user is outside the corporate network"* or *"block login from specific countries."* Authentik has a policy engine that can express similar rules, but the tooling is less mature and requires more manual configuration.

For a homelab-grade cluster serving a team of one, these tradeoffs are entirely reasonable. For an organisation with compliance requirements and an IT operations team, the managed alternative earns its cost.

---

## Why This Architecture Matters for Kubernetes Specifically

Kubernetes has its own authentication model, and it aligns naturally with OIDC rather than LDAP. The API server can be configured to accept OIDC tokens directly — meaning the same JWT that grants access to Grafana or ArgoCD can also be used to run `kubectl` commands. The user's group membership, issued by Authentik at login time, flows into Kubernetes RBAC without any synchronisation job.

```
User logs in via Authentik
         │
         │  JWT with groups claim
         ▼
kubectl --token=<jwt> get pods
         │
         │  API server validates token against
         │  Authentik OIDC discovery endpoint
         ▼
RBAC: group "authentik Admins" → ClusterRole cluster-admin
```

Under LDAP or Active Directory, achieving the same result requires a bridge: either an LDAP-to-Kubernetes RBAC sync daemon, or Entra ID integration via a Microsoft-specific plugin. With OIDC native to both Authentik and Kubernetes, there is no bridge to maintain.

---

## Summary

Most enterprises are modernising *toward* what we have. They are running Entra ID on top of Active Directory on top of LDAP, progressively lifting applications from the older layers to the newer one, spending engineering effort at each step on migration, compatibility shims, and sync agents.

We started at the top. Every application speaks OIDC. Every user authenticates once through Authentik and receives a token that works everywhere. There is no on-premises directory, no Kerberos, no LDAP connector, no vendor dependency.

The tradeoff is that we operate the identity platform ourselves rather than paying for it as a service. For a self-hosted Kubernetes platform, that is a straightforward and conscious choice — not a constraint.

The protocol stack that enterprises are converging on after 25 years of evolution is the only one we have ever run.
