---
id: architecture-at-a-glance
title: Architecture at a Glance — read this first
sidebar_label: 🗺 Architecture at a Glance (start here)
sidebar_position: 0
---

# ktayl IS — Architecture at a Glance

> **If you read one page to understand ktayl, read this.** It is the whole business-application
> architecture on a single screen: who uses it, the insurance value chain, the legacy core it wraps,
> the shared platforms (Data · AI · **Documents**), and the foundations everything runs on — plus a
> **reading path** into the detailed docs. Depth lives elsewhere; this is the mental model.

:::note One insurer, one IS — and a separate product
**ktayl-solution** is a fictional commercial-lines (**IARD / large-risk**) insurer; everything here is
**its** information system. **Retrieva** is a *separate* product (RNCP cert / DORA) that only *runs on*
this platform — it is not a ktayl business app and appears nowhere below.
:::

## The one picture

Read it **top-down**: people → the apps they touch → the insurance value chain (the business) → the
legacy core that one domain wraps → the shared Data/AI/**Document** platforms → the foundations.

```
                           ┌─────────────────────────────────────────┐
   PEOPLE                  │ Underwriters · Claims handlers · Brokers  │
                           │ Finance · Compliance · Ops                │
                           └─────────────────────┬─────────────────────┘
                                                 │  browser-first, SSO (Authentik + MFA)
   CHANNELS / APPS         ┌─────────────────────▼─────────────────────┐
   (how work gets done)    │  Web apps · Underwriter/Claims workbench   │
                           │  Broker portal · Digital workplace (M365-alt)│
                           └─────────────────────┬─────────────────────┘
                                                 │  every call: OIDC · RBAC · audit
   ══════════════ BUSINESS VALUE CHAIN (the insurer itself — Track A) ══════════════
        DISTRIBUTION ─► UNDERWRITING ─► POLICY ADMIN ─► CLAIMS ─► BILLING ─► REINSURANCE
           #13             #12          #6 (LIVE)        #11        #14         #22
        broker/CRM      workbench      contracts       FNOL→      premium     treaty/
        submissions     rating/quote   endorsements    settle     finance     cessions
                                          │                │
                                          │                │  (Claims is delivered by wrapping a legacy)
   ══════════════ LEGACY SPINE — one deliberate initiative (Track C) ══════════════
                          ┌──────────────▼───────────────┐
                          │ GlobalCore (System of Record) │  Oracle · Java 8 · SOAP · batch
                          │ FROZEN · OUTSIDE k8s          │  holds the CLAIMS domain
                          └──────────────┬───────────────┘
                          ACL wraps it:  │  SOAP→JSON (writes) · Debezium→NATS (events)
                          ┌──────────────▼───────────────┐
                          │ ktayl-claims (#11) = the ACL  │  modern Claims, built AS the wrap
                          └──────────────┬───────────────┘
                                         │  clean domain events on NATS (never raw legacy access)
   ══════════════ SHARED PLATFORMS (serve every domain — transversal) ══════════════
        ┌───────────────────┬────────────────────────┬───────────────────────────┐
        │ DATA / ACTUARIAL  │ AI / AUTOMATION         │ ENTERPRISE DOCUMENT PLATFORM│
        │ #5                │ #4 · #18 · #19          │ #24                        │
        │ warehouse · BI    │ RAG (docs) + SQL-tools  │ parse→chunk→metadata→embed │
        │ semantic/metrics  │ (data) · Copilot (last) │ →vector DB · GED · e-sign  │
        └───────────────────┴────────────────────────┴───────────────────────────┘
        also transversal: INTEGRATION (#25 · API-GW/events/ETL) · MDM (#20 · golden records)
   ══════════════ FOUNDATIONS (live) + GOVERNANCE (continuous — Track B) ══════════════
     k3s · GitOps (ArgoCD/Kargo) · IaC (OpenTofu) · Observability (OTel/Prom/Grafana/Tempo)
     Identity (Authentik) · Secrets (Vault/ESO) · Supply-chain (cosign/SBOM/Trivy)
     GOVERNANCE gate every domain clears: regulatory impact · AI-Act tier · NFR + security + resilience
```

## The three tracks (why nothing is scattered)

Every item on the roadmap is in exactly one of three parallel tracks — this is the organising idea:

| Track | What it is | Contains |
|---|---|---|
| **A — Business build** | the insurance value chain, built domain by domain | Distribution #13 → Underwriting #12 → **Policy Admin #6 (live)** → Claims #11 → Billing #14 → Reinsurance #22 |
| **B — Governance** | the gate *every* Track-A build clears (not a phase) | regulatory impact · AI-Act tier · NFR/security/resilience by design |
| **C — Modernization lab** | the legacy-wrap muscle, feeding real integration skill into A | **GlobalCore** (legacy core) + the **ktayl-claims** ACL + GenApp M1–M4 |

Foundations (platform #3, AI #4, digital workplace #10) are **live** and underpin all three.

## How every domain is built (one repeatable recipe)

```
1. FDE playbook   → understand the domain (process, users, pain, data, KPIs)
2. BMAD spec+stories → the implementation contract
3. Thin end-to-end slice → (uses Track-C wrap patterns when it touches the legacy)
4. Governance gate → Track-B: regulatory impact + AI-Act tier + NFR/security/resilience
5. Deploy (GAP wrapper chart) → iterate
```

So the docs aren't a pile of apps — they're **one architecture, three tracks, one recipe per domain.**

## Reading path (where to go next)

| You want to understand… | Read |
|---|---|
| **What to build next / the tracks** | [🧭 IS Build Roadmap](../product-roadmap/is-build-roadmap) |
| **The functional target (12 domains + 4 layers) + the legacy spine** | [🏛 EA Blueprint](./enterprise-architecture-blueprint) |
| **Every app, its stack + status** | [Business Applications Catalog](./business-applications-catalog) |
| **The legacy-core wrap (GlobalCore + Oracle + Claims)** | [Legacy-Core Modernization](./legacy-core-modernization) |
| **How AI is applied (RAG vs SQL-tools, the copilot)** | [AI-First Operating Model](./ai-first-operating-model) |
| **Regulation & compliance-by-design** | [Regulatory Operating Model](./regulatory-operating-model) |
| **A worked domain (deep-dive)** | [Underwriting FDE Playbook](./underwriting-fde-playbook) · [Policy Service](./ktayl-policy-service) |

**One-line takeaway:** ktayl is a **greenfield-modern insurer** whose value chain is built domain-by-domain
on a mature k8s platform, with **one deliberate legacy spine** (Claims via GlobalCore/Oracle) to prove
real enterprise modernization — all clearing a continuous governance gate.
