---
id: platform-is-dependency-matrix
title: Platform ↔ IS Dependency Matrix
sidebar_label: Platform ↔ IS Dependency Matrix
---

# Platform ↔ IS Dependency Matrix

> The explicit **consumption contract** between the two pillars: which Information-System application
> consumes which **platform capability**, through what **interface**, and who **owns** each side. This is
> the precise form of the "consumes" arrow in the [L1 Landscape](./index.md). It captures *ownership and
> interfaces*, not just arrows.

## How to read it

- **Consumer** = the IS application (business-owned). **Provided capability** = the platform service
  (platform-owned). **Ownership ≠ deployment** — both may run on the same cluster; the boundary is
  logical.
- **Maturity** — 🟩 Implemented · 🟨 Scaffold · ⬜ Planned (does the code exist?).
- **Runtime** — **Verified** / **Unverified** (is it actually running?). The last audit could **not reach
  the cluster**, so every row here is **Unverified** and the dependencies are **inferred** from GitOps
  manifests + repo code + the `.claude/rules` constitution. Re-verify against the live cluster before
  claiming operational reality.
- **Evidence** = where the dependency is grounded (a repo, a rule, a manifest).

## The provider side — platform capabilities (who owns them)

| Capability | Provided as | Platform owner |
|---|---|---|
| **Authentik SSO** | OIDC / forward-auth identity-as-a-service | Platform (Security) |
| **PostgreSQL / CNPG** | managed Postgres clusters (HA, PITR) | Platform (Data) |
| **NATS JetStream** | durable eventing | Platform (Data/Messaging) |
| **LiteLLM gateway** | governed LLM inference (keys, routing, PII) | Platform (AI Runtime) |
| **Qdrant** | vector store for RAG | Platform (AI Runtime) |
| **Object storage (MinIO / R2)** | S3-compatible buckets, backup targets | Platform (Storage) |
| **Observability** | Prometheus / Grafana / Loki / Tempo | Platform (Observability) |
| **GitOps + Kargo** | delivery (promote one artifact dev→prod) | Platform (Delivery) |
| **ERPNext GL** | double-entry general ledger (adopted) | *(IS-owned app, listed as a downstream the way Billing consumes it)* |

> The IS **owns** the business meaning on top of each capability: the *data model* on Postgres, the
> *business authorization* on Authentik, the *domain events* on NATS, the *AI use case* on the gateway,
> the *business KPIs* on the telemetry. The platform owns the *capability*; the IS owns the *use*.

## The consumption matrix (inferred · Unverified)

| Consumer (IS app) | Provided platform capability | Interface / contract | Maturity | Runtime | Evidence / reference |
|---|---|---|---|:--:|:--:|---|
| **Underwriting** (ktayl-underwriting) | PostgreSQL/CNPG · NATS · LiteLLM · Authentik | SQLAlchemy JDBC · JetStream subject · OpenAI-compat HTTP · OIDC | 🟩 | Unverified | `ktayl-underwriting` repo; `datastore-selection.md` (CNPG) |
| **Policy Admin / PAS** (ktayl-policy-service) | PostgreSQL/CNPG · Authentik | golang-migrate JDBC · gRPC/REST + OIDC | 🟩 | Unverified | `ktayl-policy-service`; `datastore-selection.md` (CNPG migrated) |
| **Claims** (ktayl-claims) | PostgreSQL/CNPG · NATS · (legacy globalcore SOAP via ACL) | Flyway JDBC · JetStream CDC · SOAP strangler | 🟩 | Unverified | `ktayl-claims`; `reference_debezium_server_nats_cdc` |
| **Billing** (ktayl-core) | PostgreSQL/CNPG · NATS · Stripe (ext) · ERPNext GL | Flyway JDBC · JetStream `insurance.underwriting.bound-risk` · Stripe API · ERPNext Journal Entry | 🟨 | Unverified | `ktayl-core`; project memory `ktayl_core_billing` |
| **IAM / IGA** (ktayl-iam) | PostgreSQL/CNPG · Authentik | TypeORM JDBC · OIDC (governs Authentik groups) | 🟩 | Unverified | `ktayl-iam`; `datastore-selection.md` (CNPG migrated) |
| **Data products** (ktayl-data-platform) | PostgreSQL (source) · ClickHouse · object storage | dbt models · JDBC · S3 | 🟩 | Unverified | `ktayl-data-platform`; `reference_data_platform_slice1` |
| **Retrieva** (cert product, separate) | LiteLLM · Qdrant · Langfuse · PostgreSQL/CNPG · object storage | OpenAI-compat HTTP · Qdrant HTTP · Langfuse SDK · JDBC · S3 | 🟩 | Unverified | `retrieva` docs; `llmops.md` |
| **Digital Workplace** (ERPNext, Nextcloud, Matrix, Jitsi, Plane, n8n, Stalwart, Docuseal) | PostgreSQL/MariaDB · Authentik · object storage | per-app DB · OIDC/forward-auth · S3 | 🟩 | Unverified | `is/` docs; `workplace-architecture.md` |
| **Scaffold domains** (Distribution, Finance, Reinsurance, Risk-Eng, International, Compliance, DMS, Integration, MDM) | *(to be assigned when built — modular-monolith-first)* | — | 🟨 | — | empty `ktayl-*` repos; `architecture-strategy.md` |
| **Submission Hub** (#27) | *(planned)* | — | ⬜ | — | board #27 — no repo |

## Cross-cutting consumption (every IS app)

- **Delivery** — built + promoted dev→prod via GitOps (ArgoCD) + Kargo; no app owns its own pipeline.
- **Observability** — emits metrics/logs/traces to the platform stack (Prometheus/Loki/Tempo); the app
  defines its *business* KPIs on top.
- **Secrets** — config via ESO→Vault; no app stores its own credentials.
- **Networking/Security** — default-deny egress + Cilium NetworkPolicies; Gatekeeper admission.

See the [L1 Landscape](./index.md) for the high-level picture and the
[IS Application Landscape](./is-application-landscape.md) for the domains. The provider-side detail lives
in the platform topology ([L2 Platform](../developer-platform/29-production-stack-architecture.md)).
