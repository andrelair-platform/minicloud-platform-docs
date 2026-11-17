---
id: glossary
title: Glossary
sidebar_label: 📖 Glossary
---

# Glossary

> One place for the recurring terms across the platform's themes — access/identity, the two-layer models,
> delivery, security, reliability. Definitions are **one line + how it applies here**, and link the
> authoritative page. A living doc: add a term the moment it starts recurring in the docs.

## Access & Identity

| Term | Meaning (as used here) |
|---|---|
| **SoR — System of Record** | The *one* authoritative place a fact officially lives; if two systems disagree, the SoR wins. For access, the **ktayl-iam catalog** (`application → role → group`) is the SoR for *who may access what*. |
| **IdP — Identity Provider** | The system that authenticates users and issues identity tokens. Here = **Authentik** (SSO for every app). |
| **PEP — Policy Enforcement Point** | The thing that *enforces* an access decision at runtime but doesn't *own* it. Here = **Authentik** (checks the group at login). |
| **PDP / PAP** | **PDP** = Policy *Decision* Point (evaluates the rule); **PAP** = Policy *Administration* Point (where rules are authored). In our model ktayl-iam is the PAP/decision source; Authentik enforces. |
| **RBAC** | Role-Based Access Control — access granted via *roles* (groups), not per-user. The platform tools map the OIDC `groups` claim → a role. |
| **ABAC** | Attribute-Based Access Control — access from *attributes* (country, line-of-business), layered on RBAC for cross-border cases. |
| **IGA** | Identity Governance & Administration — the lifecycle of *who should have what* (request, approval, provision, recertify). The **ktayl-iam** product. |
| **JML — Joiner/Mover/Leaver** | The identity lifecycle events IGA governs (onboard → role change → offboard). |
| **SSO** | Single Sign-On — one login (Authentik) for all apps. |
| **OIDC** | OpenID Connect — the SSO protocol; carries identity + a **`groups` claim** the tools read for RBAC. |
| **forward-auth** | An ingress-level auth check for apps that can't speak OIDC — Authentik authorizes the request before it reaches the app. |
| **claim** | A field inside the OIDC token (e.g. `email`, `groups`) the app trusts. |
| **Segregation of privilege** (least privilege) | A lower tier **cannot** perform a higher tier's action (Developer → Viewer, not Admin). A *read-vs-write* control. **Proven live.** |
| **SoD — Segregation of Duties** | No *one person* holds two **conflicting** duties — e.g. **request** AND **approve** their own access (maker ≠ checker). An *anti-fraud* control, distinct from least-privilege; a planned **ktayl-iam** governance control (request → dual-approval → provision). |
| **break-glass** | An emergency credential/path used only when normal SSO is down (e.g. Vaultwarden master login, a `user:default/` admin fallback). |

See: [Platform Access Matrix](../security-enterprise/18-platform-access-matrix.md) · [SSO (Authentik)](../security-enterprise/02-sso-authentik.md) · [ktayl-iam access-role-model](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/access-role-model.md).

## The two-layer models (don't conflate)

| Term | Meaning |
|---|---|
| **Platform (minicloud)** | The shared **technical capabilities** (compute, delivery, identity, data, observability) — the internal cloud *provider*. Agnostic to the business. |
| **Information System (IS, ktayl-solution)** | The **business apps, data and processes** of the insurer — the *consumer* of the platform. |
| **Provider ↔ consumer** | The relationship between them: IS *consumes* Platform capabilities. Litmus: *"if ktayl stopped selling insurance, would this survive?"* Yes → Platform, No → IS. |
| **Retrieva** | The RNCP39583 **certification product** (DORA third-party-ICT) that *runs on* the IS — a *separate* axis from Platform↔IS. |

See: [Architecture Hub](./index.md) · [Platform ↔ IS Dependency Matrix](./platform-is-dependency-matrix.md).

## Delivery & GitOps

| Term | Meaning |
|---|---|
| **GitOps** | Git is the single source of truth for the cluster; a controller continuously reconciles live state to match it. |
| **ArgoCD** | The GitOps reconciler — syncs each environment from `main`. |
| **Kargo** | The **promoter** — moves one immutable image `dev → prod` by opening the Git PRs ArgoCD then reconciles (CI builds, Kargo promotes, ArgoCD deploys). |
| **Promotion** | Advancing one **immutable artifact** across environments (never rebuilt per-env) — a dev-overlay PR then a CODEOWNERS-gated prod PR. |
| **CODEOWNERS** | The GitHub gate requiring owner review on protected paths (prod overlays, security, `apps/`) — the prod approval lives in Git. |
| **Trunk-based** | `main` is the only deploy branch + source of truth for **both** environments; environments ≠ branches. |
| **SHA tag** | An immutable image tag (the commit SHA); prod pins these, never `:latest`. |

See: [GitOps & delivery](../developer-platform/35-delivery-workflow.md) · [C4 System Design](./c4-system-design.md).

## Security & supply chain

| Term | Meaning |
|---|---|
| **Vault / ESO** | **Vault** = the secrets store; **ESO** (External Secrets Operator) delivers secrets from Vault into pods. Secrets never live in Git. |
| **CNPG** | CloudNativePG — the Postgres operator; the DB standard (HA + PITR backups). |
| **Gatekeeper / OPA** | Admission policy — denies non-compliant manifests at the API server (e.g. no node-pins, non-root only). |
| **Falco** | Runtime security — detects anomalous syscalls in running containers. |
| **cosign / SBOM / Trivy** | Supply-chain: **cosign** signs images, **SBOM** lists their contents, **Trivy** scans for CVEs. |

## Reliability

| Term | Meaning |
|---|---|
| **SLO / SLI** | **SLI** = a measured indicator (p95 latency, availability); **SLO** = the target for it. |
| **Error budget** | `1 − SLO` — how much failure is tolerable before risky changes freeze. |
| **RTO / RPO** | **RTO** = how fast you must recover; **RPO** = how much data loss is acceptable. Proven by DR drills. |
| **Game Day** | A deliberately-induced failure to measure recovery (→ a postmortem + KPI update). |
| **MTTR** | Mean Time To Recovery — average time to restore after an incident. |

Related: [Architecture Hub](./index.md) · [Platform-vs-IS boundary](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/platform-vs-information-system.md).
