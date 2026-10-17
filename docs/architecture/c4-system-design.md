---
id: c4-system-design
title: C4 System Design — the Platform
sidebar_label: C4 System Design (Platform)
---

# C4 System Design — the minicloud Platform

> The platform's **solution-architecture model** — *the platform is made of **these** components, working
> together like **this***. Modelled once as a [Structurizr](https://structurizr.com) DSL
> ([`workspace.dsl`](https://github.com/andrelair-platform/minicloud-platform-docs/blob/main/diagrams/structurizr/workspace.dsl))
> and rendered to [C4-model](https://c4model.com) diagrams — diagram-as-code, so it never drifts.
> **Every relationship is verified against the GitOps manifests** (no invented edges).

**Boundary:** this models **the Platform** — the shared technical capabilities (the *internal cloud
provider*). The **Information System** (the insurer's business apps) appears as a single external
**consumer** and gets its own C4 model later. See the [Architecture Hub](./index.md) for how the two pillars relate.

**Two lenses, same facts.** Each view is shown as the **icon-rich** visual (brand logos + verb-labelled
edges, mingrammer `diagrams`); the equivalent **formal C4 notation** (Structurizr, standard boxes) is
linked beside it. **Click any diagram to open it full-screen.** The complementary capability map,
technology topology and physical view live on
**[Platform Architecture](../developer-platform/29-production-stack-architecture.md)**.

**Jump to** · [① Context](#-system-context--who-the-platform-talks-to) · [② Container](#-container--the-complete-platform-all-capabilities) · [③ Deployment](#-deployment--where-it-physically-runs) · [④ Subsystem deep-dives](#subsystem-deep-dives-c4-component--flow)

## ① System Context — who the platform talks to

The platform as one system, its users, the external systems it depends on, and **the Information System as
its consumer**.

[![C4 System Context — minicloud Platform](/img/architecture/platform-c4-context.svg)](/img/architecture/platform-c4-context.svg)

*Formal C4 notation (Structurizr): [Context diagram →](/img/c4/structurizr-Context.svg).*

---

## ② Container — the complete platform (all capabilities)

The whole platform in one view: every capability as a **container**, grouped (Access & Networking ·
Delivery/GitOps · Security & Secrets · Data & Messaging · Storage & Backup · Observability · AI Runtime ·
Runtime & Tooling), with the relationships that make it work — code→production (Delivery), request→app
(Access), secrets, telemetry, backup, and what the IS consumes. It's detailed — **click to open full-screen and zoom**.

[![C4 Container view — the complete minicloud Platform](/img/architecture/platform-c4-container.svg)](/img/architecture/platform-c4-container.svg)

*Formal C4 notation (Structurizr): [Container diagram →](/img/c4/structurizr-Containers.svg).*

**Drill into a subsystem →** [GitOps / ArgoCD](#gitops-delivery--inside-argocd) · [Secrets / Vault+ESO](#secrets-delivery--inside-vault--eso) · [AI / LiteLLM](#ai-gateway--inside-litellm) — or follow a flow: [delivery](#how-code-reaches-production--the-delivery-flow) · [request](#how-a-request-reaches-an-app-networking-flow) · [observability](#telemetry--alerting-observability-flow).

---

## ③ Deployment — where it physically runs

The same model, deployed: the **6-node k3s cluster** + the **off-cluster MAAS controller**, with placement
(Vault → fast-heron, vLLM → star-kitten, control-plane → set-hog) and **Longhorn replicated across the
storage nodes**.

[![C4 Deployment view — 6-node k3s + controller](/img/c4/structurizr-Deployment.svg)](/img/c4/structurizr-Deployment.svg)

---

## Subsystem deep-dives (C4 Component + flow)

Zooming **inside** the key containers — *"the GitOps platform in detail"*, and the same for secrets and
the AI gateway. All grounded in the GitOps manifests + the platform rules. (Click any diagram to enlarge.)

↑ [Back to the Container view](#-container--the-complete-platform-all-capabilities)

### How code reaches production — the delivery flow

A `git push` to a running production workload (CI → registries → Kargo → ArgoCD → cluster), showing the
**continuous-delivery vs continuous-deployment split**: the same artifact is built+proved once, Kargo
**auto-deploys it to dev (continuous *deployment* — no human)**, then a **CODEOWNERS-gated PR promotes it
to prod (continuous *delivery* — a human decides when)**. The full narrative is on the
**[Delivery Workflow](../developer-platform/35-delivery-workflow.md#continuous-delivery-vs-continuous-deployment)** page.

**System-design view** — icon-rich, the four stages colour-coded (grey build · cyan promote · **green =
automatic dev** · **amber = human-gated prod**). [Open full SVG →](/img/architecture/platform-delivery-pipeline.svg)

[![Delivery pipeline — continuous delivery (prod) + continuous deployment (dev)](/img/architecture/platform-delivery-pipeline.svg)](/img/architecture/platform-delivery-pipeline.svg)

**Formal C4 dynamic view** — the same sequence in standard C4 notation (Structurizr).
[Open full SVG →](/img/c4/structurizr-DeliveryFlow.svg)

[![Delivery flow — how code reaches production](/img/c4/structurizr-DeliveryFlow.svg)](/img/c4/structurizr-DeliveryFlow.svg)

### GitOps delivery — inside ArgoCD

The app-of-apps engine: Root App-of-Apps → ApplicationSets / AppProjects → Sync+Health controller →
the cluster; Kargo opens the CODEOWNERS-gated PR.

[![C4 Component — inside ArgoCD](/img/c4/structurizr-GitOpsComponents.svg)](/img/c4/structurizr-GitOpsComponents.svg)

### Secrets delivery — inside Vault + ESO

Vault KV/PKI (KMS auto-unseal) → ESO ClusterSecretStore reads Vault → ExternalSecret renders the k8s
Secrets workloads consume.

[![C4 Component — inside Vault + ESO](/img/c4/structurizr-SecretsComponents.svg)](/img/c4/structurizr-SecretsComponents.svg)

### AI gateway — inside LiteLLM

Virtual keys/budgets → model router → PII guardrail (Presidio) + cache + provider connectors
(vLLM / Groq / cloud).

[![C4 Component — inside the LiteLLM gateway](/img/c4/structurizr-AIComponents.svg)](/img/c4/structurizr-AIComponents.svg)

### How a request reaches an app (networking flow)

User → Cloudflare → tunnel → ingress → Authentik (forward-auth) → the workload.

[![Request flow — how a user request reaches an app](/img/c4/structurizr-RequestFlow.svg)](/img/c4/structurizr-RequestFlow.svg)

### Telemetry + alerting (observability flow)

Prometheus scrapes the cluster · OTel ships logs→Loki / traces→Tempo · alerts →
Alertmanager → SES email.

[![Observability flow — telemetry + alerting](/img/c4/structurizr-ObservabilityFlow.svg)](/img/c4/structurizr-ObservabilityFlow.svg)

> Further subsystem views are cheap to add — the model already holds the elements; just add a
> `component`/`dynamic` view to [`workspace.dsl`](https://github.com/andrelair-platform/minicloud-platform-docs/blob/main/diagrams/structurizr/workspace.dsl).

---

## Legend

- **Shapes (C4):** rounded person = a **Person**; blue box = the **Platform** (software system); grey box =
  an **external system**; **purple box = the Information System** (the platform's consumer); teal/coloured
  boxes = **containers** (platform capabilities, tinted by group).
- **Arrows:** every arrow is a **relationship with a verb** (*builds · pushes · promotes · reconciles ·
  supplies-secrets · issues-certs · authenticates · scrapes · ships-logs · backs-up · routes-to · consumes*).
- Each formal view also has a C4 **key** (auto-generated): `structurizr-<view>-key.svg`.

## Maintaining it

Edit [`diagrams/structurizr/workspace.dsl`](https://github.com/andrelair-platform/minicloud-platform-docs/blob/main/diagrams/structurizr/workspace.dsl),
run `make c4` (Structurizr CLI → PlantUML → SVG, via Docker), commit the refreshed SVGs — a CI workflow
also regenerates on change. This is the single source of truth for the platform's C4 views; the
[capability map / technology topology / physical view](../developer-platform/29-production-stack-architecture.md)
remain the complementary stylistic references.
