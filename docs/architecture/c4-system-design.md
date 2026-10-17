---
id: c4-system-design
title: C4 System Design — the Platform
sidebar_label: C4 System Design (Platform)
---

# C4 System Design — the minicloud Platform

> The **complete solution-architecture artefact** of the platform: *the platform is made of **these**
> components, working together like **this***. Modelled once as a [Structurizr](https://structurizr.com)
> DSL ([`workspace.dsl`](https://github.com/andrelair-platform/minicloud-platform-docs/blob/main/diagrams/structurizr/workspace.dsl))
> and rendered to clean [C4-model](https://c4model.com) diagrams — diagram-as-code, so it never drifts.
> **Every relationship is verified against the GitOps manifests** (no invented edges).

**Boundary:** this models **the Platform** — the shared technical capabilities (the *internal cloud
provider*). The **Information System** (the insurer's business apps) appears as a single external
**consumer**; it gets its own C4 model later. See the [Architecture Hub](./index.md) for how the two
pillars relate.

**How to read C4** — three zoom levels: **① System Context** (the platform + who it talks to) → **②
Container** (its internal capabilities) → **③ Deployment** (where it runs). Boxes = people / systems /
containers; **every arrow is a labelled relationship** (a verb). Below the three top-level views are the
**Component** deep-dives (④ — *the GitOps pipeline, secrets, and the AI gateway in detail*). *(An
interactive Structurizr Lite is the remaining follow-up; the model already holds the elements.)*

:::tip Two complementary approaches — pick the right lens
This page is the **formal, standard-notation C4 model** (Structurizr, as code). For the **icon-rich
visual** views of the same platform — capability map, technology topology, physical/deployment — see
**[Platform Architecture](../developer-platform/29-production-stack-architecture.md)** (mingrammer
`diagrams`). This is the rigorous *model*; that is the *visual* reference. Same facts, different lens.
:::

---

## ① System Context — who the platform talks to

The platform as one system, its users, the external systems it depends on, and **the Information System as
its consumer**. [Open full SVG →](pathname:///img/c4/structurizr-Context.svg)

[![C4 System Context — minicloud Platform](pathname:///img/c4/structurizr-Context.svg)](pathname:///img/c4/structurizr-Context.svg)

---

## ② Container — the complete platform (all capabilities)

The whole platform in one view: every capability as a **container**, grouped (Access & Networking ·
Delivery/GitOps · Security & Secrets · Data & Messaging · Storage & Backup · Observability · AI Runtime ·
Runtime & Tooling), with the relationships that make it work — code→production (Delivery), request→app
(Access), secrets, telemetry, backup, and what the IS consumes. It's detailed — **open it full-screen and
zoom**. [Open full SVG →](pathname:///img/c4/structurizr-Containers.svg)

[![C4 Container view — the complete minicloud Platform](pathname:///img/c4/structurizr-Containers.svg)](pathname:///img/c4/structurizr-Containers.svg)

---

## ③ Deployment — where it physically runs

The same model, deployed: the **6-node k3s cluster** + the **off-cluster MAAS controller**, with placement
(Vault → fast-heron, vLLM → star-kitten, control-plane → set-hog) and **Longhorn replicated across the
storage nodes**. [Open full SVG →](pathname:///img/c4/structurizr-Deployment.svg)

[![C4 Deployment view — 6-node k3s + controller](pathname:///img/c4/structurizr-Deployment.svg)](pathname:///img/c4/structurizr-Deployment.svg)

---

## Subsystem deep-dives (C4 Component + flow)

Zooming **inside** the key containers — *"the GitOps platform in detail"*, and the same for secrets and
the AI gateway. All grounded in the GitOps manifests + the platform rules.

### How code reaches production — the delivery flow

A **numbered** sequence from a `git push` to a running production workload (CI → registries → Kargo →
ArgoCD → cluster). [Open full SVG →](pathname:///img/c4/structurizr-DeliveryFlow.svg)

[![Delivery flow — how code reaches production](pathname:///img/c4/structurizr-DeliveryFlow.svg)](pathname:///img/c4/structurizr-DeliveryFlow.svg)

### GitOps delivery — inside ArgoCD

The app-of-apps engine: Root App-of-Apps → ApplicationSets / AppProjects → Sync+Health controller →
the cluster; Kargo opens the CODEOWNERS-gated PR. [Open full SVG →](pathname:///img/c4/structurizr-GitOpsComponents.svg)

[![C4 Component — inside ArgoCD](pathname:///img/c4/structurizr-GitOpsComponents.svg)](pathname:///img/c4/structurizr-GitOpsComponents.svg)

### Secrets delivery — inside Vault + ESO

Vault KV/PKI (KMS auto-unseal) → ESO ClusterSecretStore reads Vault → ExternalSecret renders the k8s
Secrets workloads consume. [Open full SVG →](pathname:///img/c4/structurizr-SecretsComponents.svg)

[![C4 Component — inside Vault + ESO](pathname:///img/c4/structurizr-SecretsComponents.svg)](pathname:///img/c4/structurizr-SecretsComponents.svg)

### AI gateway — inside LiteLLM

Virtual keys/budgets → model router → PII guardrail (Presidio) + cache + provider connectors
(vLLM / Groq / cloud). [Open full SVG →](pathname:///img/c4/structurizr-AIComponents.svg)

[![C4 Component — inside the LiteLLM gateway](pathname:///img/c4/structurizr-AIComponents.svg)](pathname:///img/c4/structurizr-AIComponents.svg)

> More subsystem views (Observability, Networking…) are cheap to add — the model already holds the
> elements; just add a `component`/`dynamic` view to [`workspace.dsl`](https://github.com/andrelair-platform/minicloud-platform-docs/blob/main/diagrams/structurizr/workspace.dsl).

---

## Legend

- **Shapes (C4):** rounded person = a **Person**; blue box = the **Platform** (software system); grey box =
  an **external system**; **purple box = the Information System** (the platform's consumer); teal/coloured
  boxes = **containers** (platform capabilities, tinted by group).
- **Arrows:** every arrow is a **relationship with a verb** (*builds · pushes · promotes · reconciles ·
  supplies-secrets · issues-certs · authenticates · scrapes · ships-logs · backs-up · routes-to · consumes*).
- Each view also has a C4 **key** (auto-generated): `structurizr-<view>-key.svg`.

## Maintaining it

Edit [`diagrams/structurizr/workspace.dsl`](https://github.com/andrelair-platform/minicloud-platform-docs/blob/main/diagrams/structurizr/workspace.dsl),
run `make c4` (Structurizr CLI → PlantUML → SVG, via Docker), commit the refreshed SVGs — a CI workflow
also regenerates on change. This is the single source of truth for the platform's C4 views; the
[capability map / technology topology / physical view](../developer-platform/29-production-stack-architecture.md)
remain the complementary stylistic references.
