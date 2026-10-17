---
id: is-application-landscape
title: IS Application Landscape (L2)
sidebar_label: L2 · IS Application Landscape
---

# Information System — Application Landscape (L2)

> A **navigation map** of the ktayl-solution business applications, grouped by insurance domain and
> coloured by **implementation maturity**. It is not a new source of truth — the authoritative docs are
> the **[Enterprise Architecture Blueprint](/is/insurance-platform/enterprise-architecture-blueprint)**
> (functional target + gap analysis) and the **[Business Capability Map](/is/insurance-platform/capability-map)**
> (~150 capabilities × criticality). This map helps you *find* them. Platform dependencies are in the
> **[Platform ↔ IS Dependency Matrix](./platform-is-dependency-matrix.md)**.

**Maturity legend** — 🟩 **Implemented** (real code + substantial functionality) · 🟨 **Scaffold**
(repo/skeleton, little business logic) · ⬜ **Planned** (no implementation yet).

:::caution These are maturity statuses, not runtime verification
Colours assert whether the **code** exists, **not** that the app is running. The last audit could not
reach the cluster → **runtime is Unverified** (see the [Hub vocabulary](./index.md#reading-vocabulary-two-independent-axes)).
ktayl is a **synthetic enterprise** — "implemented" never implies real production usage.
:::

```mermaid
flowchart TB
  subgraph FO["Front office &amp; distribution"]
    direction LR
    DIST["Distribution &amp; CRM<br/>ktayl-distribution"]:::scaffold
    SUB["Submission Hub<br/>#27 · no repo"]:::planned
    WEB["Public Web (7 LOB)<br/>ktayl-solution-web · Astro"]:::impl
  end

  subgraph VC["Core insurance value chain"]
    direction LR
    UW["Underwriting &amp; Pricing<br/>ktayl-underwriting · Python/FastAPI"]:::impl
    POL["Policy Administration (PAS)<br/>ktayl-policy-service · Go"]:::impl
    CLM["Claims<br/>ktayl-claims · Java/Spring (ACL strangler)"]:::impl
    BILL["Billing<br/>ktayl-core · Spring Modulith"]:::scaffold
  end

  subgraph RR["Risk &amp; reinsurance"]
    direction LR
    RISK["Risk Engineering<br/>ktayl-risk-engineering"]:::scaffold
    RE["Reinsurance<br/>ktayl-reinsurance"]:::scaffold
    INTL["International Programs<br/>ktayl-international-programs"]:::scaffold
  end

  subgraph GOV["Governance, finance &amp; compliance"]
    direction LR
    IAM["IAM / IGA governance<br/>ktayl-iam · NestJS"]:::impl
    FIN["Insurance Finance<br/>ktayl-finance (→ Billing in ktayl-core)"]:::scaffold
    CMP["Regulatory &amp; Compliance<br/>ktayl-compliance"]:::scaffold
    ITSM["ITSM<br/>ktayl-itsm · GLPI (vendor)"]:::scaffold
  end

  subgraph SH["Shared IS layers"]
    direction LR
    DMS["Documents / DMS<br/>ktayl-dms"]:::scaffold
    INTG["Integration Platform<br/>ktayl-integration"]:::scaffold
    MDM["MDM<br/>ktayl-mdm"]:::scaffold
    DATA["Data products / BI<br/>ktayl-data-platform · dbt+Metabase"]:::impl
  end

  subgraph DW["Digital Workplace (M365 alternative)"]
    direction LR
    ERP["ERPNext<br/>HR · finance · GL"]:::impl
    COLLAB["Nextcloud · Matrix · Jitsi<br/>files · chat · meetings"]:::impl
    OFFICE["Plane · n8n · Stalwart · Docuseal<br/>projects · workflow · mail · e-sign"]:::impl
  end

  classDef impl fill:#064e3b,stroke:#34d399,color:#ffffff;
  classDef scaffold fill:#78350f,stroke:#f59e0b,color:#ffffff;
  classDef planned fill:#1f2937,stroke:#9ca3af,color:#e5e7eb;
```

## Where to go deeper (authoritative docs)

- **IS target + gaps:** [Enterprise Architecture Blueprint](/is/insurance-platform/enterprise-architecture-blueprint)
- **Capabilities × status:** [Business Capability Map](/is/insurance-platform/capability-map)
- **IS one-screen view:** [Architecture at a Glance](/is/insurance-platform/architecture-at-a-glance)
- **App catalogue:** [Business Applications Catalog](/is/insurance-platform/business-applications-catalog)
- **Digital Workplace:** [Digital Workplace Architecture](/is/is/digital-workplace-architecture)
- **Per-product boards/repos:** the `ktayl-*` repos on [github.com/andrelair-platform](https://github.com/andrelair-platform)
  (one GitHub Project per product — see the product-boards table in the governance rules).

## Why so many "Scaffold" domains?

Deliberate **modular-monolith-first + need-first** design: a business domain gets built as a **module in
`ktayl-core`** (or earns its own service only on a justified extraction), **the day its work actually
starts** — not pre-scaffolded. The empty `ktayl-*` repos define the board/boundary structure so a domain
can be built in without rework; they are *architectural stubs*, honestly marked 🟨, not abandoned code.
