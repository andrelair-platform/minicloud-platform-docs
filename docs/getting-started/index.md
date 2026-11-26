---
id: index
title: "Getting Started — build & ship an app for ktayl (A→Z)"
sidebar_label: Getting Started (A→Z)
slug: /getting-started
tags: [how-to]
---

# Getting Started — from new developer to running in prod

> **How-to.** The **single thread** for a developer joining to build applications for the ktayl insurance
> IS. Each stage is one or two lines + a link to the detailed doc — follow it top to bottom.

**Who this is for:** a developer (any stack) who will build and ship a service for ktayl-solution and does
**not** yet know this platform. By the end you'll have an app running on **dev** and know how it reaches
**prod**.

## The one rule to internalise first

**Two repos, never `kubectl apply` to prod.** Your **code** lives in your service's own repo (CI builds &
proves the image). The **deployment config** lives in `minicloud-gitops`. You change the cluster by
**merging Git** — CI builds the image, **Kargo** promotes it, **Argo CD** reconciles it. You never deploy
by hand. (Full model: [Application delivery overview](/platform/app-deployment/deploy-overview).)

## The path

| # | Stage | What you do | Start here |
|---|-------|-------------|-----------|
| **1** | **Day 1 — access & setup** | Accounts (GitHub org · SSO · Tailscale), install your tools, get cluster access, pick your stack | **[Day 1 — access & local setup](/platform/getting-started/day-1-setup)** |
| **2** | **Understand where your app fits** | The insurer on one screen, the money path, who owns which data | [Architecture at a Glance](/is/insurance-platform/architecture-at-a-glance) · [Business Journey](/is/insurance-platform/business-journey) · [System of Record](/is/insurance-platform/system-of-record) |
| **3** | **Develop** | Clone the closest **reference service**, write it with tests (L0–L4), author stories (BMAD) | [New business service — zero → prod](/platform/app-deployment/new-business-service) · [Testing strategy](/platform/engineering-standards/testing-strategy) · [BMAD workflow](/platform/engineering-standards/bmad-workflow) |
| **4** | **Deploy to dev** | Push to `main` → CI builds/signs the image → wrapper Helm chart + Argo CD apps → Kargo auto-promotes to **dev** | [CI/CD pipeline](/platform/app-deployment/cicd-pipeline) · [Delivery workflow](/platform/developer-platform/delivery-workflow) · [Kargo promotion](/platform/developer-platform/kargo-promotion) |
| **5** | **Promote to prod** | Pass the **QA gate** on live dev → the CODEOWNERS-gated prod PR → Argo CD reconciles | [New business service](/platform/app-deployment/new-business-service) (Step 7) · [Delivery workflow](/platform/developer-platform/delivery-workflow) |
| **6** | **Operate** | Secrets (Vault→ESO), networking (default-deny netpol), SSO, metrics/alerts | [Vault](/platform/developer-platform/vault) · [ESO](/platform/developer-platform/eso-vault) · [Network isolation](/platform/security-enterprise/namespace-isolation) · [How SSO works](/platform/security-enterprise/how-sso-works) · [App monitoring](/platform/observability/application-monitoring) |

## What "done" looks like

Your service is **live on dev** (auto-promoted by Kargo), passes its tests + the QA gate, has its secrets
coming from Vault via ESO, a default-deny NetworkPolicy, SSO where it's user-facing, and RED metrics
scraped by Prometheus — and the path to **prod** is a reviewed PR, not a manual step.

## Related

- [Day 1 — access & local setup](/platform/getting-started/day-1-setup) — the prerequisites checklist
- [How the cluster was built](/platform/build-the-cluster) — the infra underneath (context, not required)
- [Architecture Hub](/platform/architecture) — how the whole platform fits together
