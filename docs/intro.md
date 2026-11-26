---
id: intro
title: minicloud
sidebar_position: 1
slug: /
---

# minicloud — a self-hosted enterprise information system

> Built from scratch on bare metal: a **platform** (MAAS, k3s, GitOps, observability, AI) **and the applications running on it** (a simulated insurer's information system).

**minicloud is a hybrid platform I build and operate.** I run most of it on my own hardware using
open-source software and use managed cloud services for specific operational needs. Its internal developer
platform helps me deliver and operate applications, including those that make up Ktayl Solution's insurance
information system. See the reasoning behind these choices under **[System Design](/system-design)**.

---

## In 20 seconds

> **minicloud** is a sovereign **private cloud *and* Internal Developer Platform** (IDP), built from open-source tools on **6 second-hand laptops** — and **ktayl-solution**, a simulated insurer's **information system**, runs on top of it. A third thing, **Retrieva** (RNCP39583 / DORA third-party-risk), is a *separate product* that also runs on it.
>
> *The Platform **provides** the capabilities; the IS **consumes** them to do insurance. Litmus test — "if ktayl stopped selling insurance tomorrow, would this survive?" → **Yes = Platform · No = IS**.*

---

## Two pillars — pick your layer

This documentation is organised in **two layers** that mirror how the system really works: an application layer running **on top of** an infrastructure layer. Use the top navigation.

- **🏗 Platform** — *minicloud*: a sovereign **private cloud** *and* an **Internal Developer Platform (IDP)** — i.e. two hats on one stack. The **cloud** half *provides* the capabilities a public cloud sells (MAAS bare-metal, k3s, networking, storage, registry, secrets, identity-as-a-service, observability, the AI & data platforms) — all FOSS, self-hosted, EU-sovereign; the **IDP** half is the **golden paths developers self-serve on** so they don't hand-roll infra (Backstage portal + scaffolders, GitOps/ArgoCD, Kargo dev→prod promotion, the wrapper-chart standard, CI guardrails). → Start at **[Production Stack Architecture](/platform/developer-platform/production-stack-architecture)**.
  > *("IDP" here = **Internal Developer Platform**, the paved-road layer — not to be confused with **IdP**, an **Identity Provider**; that's Authentik, one of the capabilities the platform provides.)*
- **🏢 Information System** — *ktayl-solution*: the business system that runs **on** the platform — a simulated commercial-lines (IARD) insurer's IS (business applications, insurance domains, data platform, governance). → Start at **[Insurance Platform → Architecture at a Glance](/is/insurance-platform/architecture-at-a-glance)**.

*(This page is the neutral home — reach it any time via the minicloud logo.)*

> **See how the two pillars fit together → the [🧭 Architecture Hub](/platform/architecture)** — the
> pillar-neutral entry point: the L1 enterprise landscape, the L2 Platform topology + IS application
> landscape, and the Platform ↔ IS dependency matrix.

:::note Keep the two layers distinct
The **platform** (minicloud) and the **information system** (ktayl-solution) are deliberately separate: the IS *runs on and benefits from* the platform, but they are not the same thing — that separation is the point. Also distinct: **Retrieva** — a *separate* product (RNCP39583 certification / DORA third-party-risk) that merely *runs on* this infrastructure; it is **not** part of the ktayl IS.
:::

```text
The platform alone is equivalent to: AWS EC2 + VPC + auto-provisioning — but local, on owned hardware.
```

---

## Infrastructure at a Glance

| Node | IP | Role | Hardware |
|---|---|---|---|
| set-hog | 10.0.0.2 | Control Plane | ThinkPad T15 Gen 1 (8-core / 16 GiB) |
| fast-skunk | 10.0.0.4 | Worker | ThinkPad T490 (8-core / 16 GiB) |
| fast-heron | 10.0.0.7 | Worker · storage | ThinkPad T490 (8-core / 16 GiB) |
| star-kitten | 10.0.0.8 | Worker · AI | ThinkPad T490 (8-core / 16 GiB) |
| loving-gannet | 10.0.0.9 | Worker · storage | ThinkPad T490 (20N4000BFR) (8-core / 16 GiB) |
| swift-mac | 10.0.0.10 | Worker · storage | MacBook Pro 13" 2012 (4-core / 8 GiB) |

> **Node roles** (live labels): `set-hog` = control-plane; `fast-skunk` = plain worker;
> `fast-heron`/`loving-gannet`/`swift-mac` = **storage** (Longhorn replica-holding);
> `star-kitten` = **AI** (LLM/GPU-class workloads).

**MAAS Controller:** Ubuntu + dual NIC (WiFi → internet, Ethernet → 10.0.0.1)
**Cluster totals:** 6 nodes · 44 cores · ~84 GiB RAM · k3s v1.36.3+k3s1 (1 control-plane + 5 workers).

---

## Start here — pick your path

New here? Use the **search** (top-right) to jump straight to a topic — or follow one of these short reading paths:

- **🏗 Understand the platform** (≈15 min) → [Architecture Hub](/platform/architecture) (how it fits together) → [Production Stack Architecture](/platform/developer-platform/production-stack-architecture) (what's actually running) → [System Design](/system-design) (*why* it's built this way).
- **🏢 Understand the insurance system** → [Architecture at a Glance](/is/insurance-platform/architecture-at-a-glance) (the whole IS on one screen) → [Business Journey: contract → ledger](/is/insurance-platform/business-journey) (the end-to-end flow, no assembly required).
- **🧭 Follow the reasoning** → [System Design](/system-design) (case studies by question) → the **Blog** / [Carnets](/carnets) (write-ups & decisions).

<details>
<summary>Dig deeper (all entry points)</summary>

- **The current live stack & topology** → [Production Stack Architecture](/platform/developer-platform/production-stack-architecture)
- **How the two pillars fit together** → [Architecture Hub](/platform/architecture)
- **The insurance information system** → [Insurance Platform → Architecture at a Glance](/is/insurance-platform/architecture-at-a-glance)
- **Write-ups & decisions** → the **Blog** in the top navigation.

</details>

## Common questions

Jump straight to the answer — or use the **search** box (top-right):

- **How was the cluster built?** → [bare metal → Kubernetes, step by step](/platform/build-the-cluster)
- **How do I deploy an app?** → [Application delivery — zero → prod](/platform/app-deployment/deploy-overview)
- **How does SSO / login work?** → [How SSO & login work](/platform/security-enterprise/how-sso-works)
- **Where are the backups?** → [Backups & recovery — where everything lives](/platform/backup-dr/backups-overview)

