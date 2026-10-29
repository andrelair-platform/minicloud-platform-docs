---
id: delivery-board
title: SI Delivery Board — what is live vs missing
sidebar_label: 📊 SI Delivery Board
sidebar_position: 1
---

# ktayl SI — Global Delivery Board

> **One screen: what of the ktayl-solution Information System is actually running, what is in
> flight, and what is still a gap.** This is a *living status board* verified against the live
> cluster — not a plan. Each row is backed by a product board (GitHub Projects) and, where it
> applies, by what ArgoCD is actually running.

**Last verified: 2026-10-29** — derived from the live **ArgoCD** application set (sync + health,
dev vs prod) cross-referenced with the **GitHub org repositories** (real code vs scaffold). It is a
snapshot; re-verify from ArgoCD + the org repos before quoting it.

**Legend:** ✅ deployed & Healthy · 🔶 in progress (repo real, not yet a usable service) ·
❌ scaffold only / not started · ⚠️ running but git-drifted (live, not down).

---

## ✅ Ready / usable — deployed & Healthy

| Domain | Board | Evidence (live) | Env |
|---|---|---|---|
| **Retrieva** — RNCP39583 cert flagship | [#2](https://github.com/orgs/andrelair-platform/projects/2) | `retrieva`, `retrieva-backend`, `retrieva-assessment-crew` all Healthy | **dev + prod** |
| **Policy Service** | [#6](https://github.com/orgs/andrelair-platform/projects/6) | `ktayl-policy-service-dev/prod` Healthy | **dev + prod** |
| **Claims** | [#11](https://github.com/orgs/andrelair-platform/projects/11) | `ktayl-claims-dev/prod` Healthy | **dev + prod** |
| **Underwriting & Pricing** | [#12](https://github.com/orgs/andrelair-platform/projects/12) | `ktayl-underwriting-dev/prod` Healthy | **dev + prod** |
| **Access Governance (IAM/IGA)** | [#17](https://github.com/orgs/andrelair-platform/projects/17) | `ktayl-iam-dev` Healthy | **dev** (prod drifted — see below) |
| **ITSM / GLPI** | [#16](https://github.com/orgs/andrelair-platform/projects/16) | `ktayl-itsm-dev` Healthy | **dev** |
| **Public Web** | [#7](https://github.com/orgs/andrelair-platform/projects/7) | `ktayl-solution-web` (GitHub Pages) | **prod** |
| **ERPNext — HR / Finance** | [#8](https://github.com/orgs/andrelair-platform/projects/8) | `erpnext` Healthy | **prod** |
| **Data Platform** | [#5](https://github.com/orgs/andrelair-platform/projects/5) | `data-platform` Healthy | live |
| **Digital Workplace + Intranet** | [#10](https://github.com/orgs/andrelair-platform/projects/10) | `bookstack` Healthy + platform tools (mail / Nextcloud / Matrix / Jitsi / Docuseal / n8n …) | live |
| **AI Platform** | [#4](https://github.com/orgs/andrelair-platform/projects/4) | LiteLLM, Langfuse, agents | live |
| **GitOps — Platform Engineering** | [#3](https://github.com/orgs/andrelair-platform/projects/3) | ArgoCD, Kargo, Vault, Harbor | live |

The **core insurance value chain is live in production** — Policy, Claims and Underwriting are all
in prod, alongside Retrieva (the certification deliverable). IAM, ITSM, Data Platform and the
Digital Workplace are usable.

---

## 🔶 In progress — repo real, not fully productised

| Domain | Board | Status |
|---|---|---|
| **ktayl-core / Billing** | [#28](https://github.com/orgs/andrelair-platform/projects/28) | `ktayl-core` is real code and `ktayl-core-infra` is deployed Healthy, but only the **infrastructure** — the Billing module (premium → cash → GL) is still being built. Not yet a usable service. |
| **Regulatory & Compliance** | [#15](https://github.com/orgs/andrelair-platform/projects/15) | `ktayl-compliance` is governance / docs; **no runtime service deployed**. Partial. |

---

## ❌ Missing — scaffold only (repo exists, nothing deployed)

| Domain | Board |
|---|---|
| **Distribution & CRM** | [#13](https://github.com/orgs/andrelair-platform/projects/13) |
| **Insurance Finance (LOB)** | [#14](https://github.com/orgs/andrelair-platform/projects/14) |
| **Risk Engineering** | [#21](https://github.com/orgs/andrelair-platform/projects/21) |
| **Reinsurance** | [#22](https://github.com/orgs/andrelair-platform/projects/22) |
| **International Programs** | [#23](https://github.com/orgs/andrelair-platform/projects/23) |
| **Documents & DMS** | [#24](https://github.com/orgs/andrelair-platform/projects/24) |
| **Integration Platform** | [#25](https://github.com/orgs/andrelair-platform/projects/25) |

---

## ❌ Not started / deliberately parked

| Domain | Board | Note |
|---|---|---|
| **Submission Hub** | [#27](https://github.com/orgs/andrelair-platform/projects/27) | No repo exists yet. |
| **Knowledge** | [#18](https://github.com/orgs/andrelair-platform/projects/18) | No repo. |
| **AI Copilot** | [#19](https://github.com/orgs/andrelair-platform/projects/19) | Scaffold repo, **parked** pending real upstream systems. |
| **MDM** | [#20](https://github.com/orgs/andrelair-platform/projects/20) | Scaffold repo, **parked**. |

---

## ⚠️ Running but git-drifted (not down — reconcile when convenient)

These ArgoCD applications are `OutOfSync` yet `Healthy` (live, serving — just drift from Git):

- `ktayl-iam-prod` and `retrieva-dev` — both drift on a **single `ExternalSecret`** resource
  (`ktayl-iam-secret` / `retrieva-secrets`). This is the known **ESO ↔ ArgoCD server-side-apply**
  behaviour: the External Secrets webhook injects default fields (`conversionStrategy`,
  `decodingStrategy`, `metadataPolicy`, `deletionPolicy`) that are not in Git, so the app shows
  permanently `OutOfSync` while pods stay Healthy. The fix is the standard `ignoreDifferences` +
  `RespectIgnoreDifferences=true` block on those two Applications.

Nothing in this section is an outage — it is reconciliation debt.
