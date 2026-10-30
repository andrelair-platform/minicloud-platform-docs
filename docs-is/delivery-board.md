---
id: delivery-board
title: SI Delivery Board — what is live vs missing
sidebar_label: 📊 SI Delivery Board
sidebar_position: 1
---

# ktayl SI — Global Delivery Board

> **One screen: what of the ktayl-solution Information System is actually running, what is in flight, and
> what is still a gap.** This is a **living, auto-generated** status board — it is **not** a hand-made
> snapshot, so it does not go stale. Run `scripts/gen-si-delivery.py` (or let the weekly CI do it)
> **instead of** a manual gap analysis.

**How it is derived (boards-as-target, all from `gh` — no cluster access needed):**

1. **Target** = every GitHub **product board** (`gh project list`) — add a board and it appears here on its own.
2. **Code** = each board's **repo size** (`gh repo list`) — real code vs scaffold vs no repo.
3. **Deployed** = the **gitops `apps/**` Application manifests** — which domains have a dev/prod Application
   *defined* (a gh-only proxy for "deployed", with env from the filename).

**Legend:** 🟢 a prod deployment is defined · 🔵 on dev only · 🔶 real code, not yet deployed ·
❌ scaffold / no repo yet · ⏸ deliberately parked.

> The board↔repo↔app bridge (the one hand-maintained input) lives in the generator (`BRIDGE`). A board
> missing from it still shows (as ❌/🔶 from its repo alone). To track a brand-new domain, just open its
> board — it surfaces here as ❌ until its repo/Application appears.

---

{/* SI-DELIVERY:START */}
_Auto-generated 2026-10-30 by `scripts/gen-si-delivery.py` from the live GitHub product boards + the gitops `apps/**` manifests + repo sizes — do not hand-edit between the markers._

**At a glance:** 🟢 12 · 🔵 1 · 🔶 1 · ❌ 12 · ⏸ 3  (of 29 product boards)

## 🟢 Live — a prod deployment is defined

| Board | Domain | Evidence |
|---|---|---|
| [#2](https://github.com/orgs/andrelair-platform/projects/2) | Retrieva — RNCP39583 Certification | dev+prod · apps: retrieva, retrieva-assessment-crew |
| [#3](https://github.com/orgs/andrelair-platform/projects/3) | GitOps — Platform Engineering | prod · apps: argo-cd, backstage, harbor, vault |
| [#4](https://github.com/orgs/andrelair-platform/projects/4) | AI Platform | dev+prod · apps: langfuse, litellm, minicloud-agent, minicloud-crew-agent |
| [#5](https://github.com/orgs/andrelair-platform/projects/5) | Data Platform | prod · apps: data-platform |
| [#6](https://github.com/orgs/andrelair-platform/projects/6) | ktayl Policy Service | dev+prod · apps: ktayl-policy-service |
| [#7](https://github.com/orgs/andrelair-platform/projects/7) | ktayl Public Web | live off-cluster (GitHub Pages) |
| [#8](https://github.com/orgs/andrelair-platform/projects/8) | ERPNext (HR-Finance) | prod · apps: erpnext |
| [#10](https://github.com/orgs/andrelair-platform/projects/10) | Digital Workplace (M365 Alternative) | prod · apps: bookstack, docuseal, jitsi, matrix-synapse |
| [#11](https://github.com/orgs/andrelair-platform/projects/11) | ktayl Claims | dev+prod · apps: ktayl-claims |
| [#12](https://github.com/orgs/andrelair-platform/projects/12) | ktayl Underwriting & Pricing | dev+prod · apps: ktayl-underwriting |
| [#17](https://github.com/orgs/andrelair-platform/projects/17) | Access Governance (IAM/IGA) | dev+prod · apps: ktayl-iam |
| [#28](https://github.com/orgs/andrelair-platform/projects/28) | ktayl-core — Insurance LOB (modular monolith) | prod · apps: ktayl-core-infra |

## 🔵 On dev — deployed to dev, not yet promoted to prod

| Board | Domain | Evidence |
|---|---|---|
| [#16](https://github.com/orgs/andrelair-platform/projects/16) | ktayl ITSM (GLPI) | dev · apps: ktayl-itsm |

## 🔶 In progress — real code, not yet deployed

| Board | Domain | Evidence |
|---|---|---|
| [#9](https://github.com/orgs/andrelair-platform/projects/9) | ktayl Insurance LOB — Product Lines | repo has content (255 KB), no Application yet: ktayl-solution-web |

## ❌ Not started — scaffold or no repo yet

| Board | Domain | Evidence |
|---|---|---|
| [#13](https://github.com/orgs/andrelair-platform/projects/13) | ktayl Distribution & CRM | scaffold repo (5 KB): ktayl-distribution |
| [#14](https://github.com/orgs/andrelair-platform/projects/14) | ktayl Insurance Finance & Billing | scaffold repo (5 KB): ktayl-finance |
| [#15](https://github.com/orgs/andrelair-platform/projects/15) | Regulatory & Compliance | scaffold repo (25 KB): ktayl-compliance |
| [#21](https://github.com/orgs/andrelair-platform/projects/21) | ktayl Risk Engineering | scaffold repo (6 KB): ktayl-risk-engineering |
| [#22](https://github.com/orgs/andrelair-platform/projects/22) | ktayl Reinsurance | scaffold repo (6 KB): ktayl-reinsurance |
| [#23](https://github.com/orgs/andrelair-platform/projects/23) | ktayl International Programs | scaffold repo (6 KB): ktayl-international-programs |
| [#24](https://github.com/orgs/andrelair-platform/projects/24) | ktayl Documents & DMS | scaffold repo (6 KB): ktayl-dms |
| [#25](https://github.com/orgs/andrelair-platform/projects/25) | ktayl Integration Platform | scaffold repo (31 KB): ktayl-integration |
| [#27](https://github.com/orgs/andrelair-platform/projects/27) | ktayl Submission Hub | repo not found / empty: ktayl-submission |
| [#29](https://github.com/orgs/andrelair-platform/projects/29) | ktayl Investment & Treasury (ALM) | repo not found / empty: ktayl-investment |
| [#30](https://github.com/orgs/andrelair-platform/projects/30) | ktayl Complaints & Disputes | repo not found / empty: ktayl-complaints |
| [#31](https://github.com/orgs/andrelair-platform/projects/31) | ktayl Procurement & Contract Management | repo not found / empty: ktayl-procurement |

## ⏸ Parked — deliberate hold

| Board | Domain | Evidence |
|---|---|---|
| [#18](https://github.com/orgs/andrelair-platform/projects/18) | ktayl Knowledge Assistant | parked — needs real upstream systems first |
| [#19](https://github.com/orgs/andrelair-platform/projects/19) | ktayl AI Ops Copilot | parked — needs real upstream systems first |
| [#20](https://github.com/orgs/andrelair-platform/projects/20) | ktayl Master Data (MDM) | parked — keystone for analytics; deferred |
{/* SI-DELIVERY:END */}

---

## Notes & caveats

- **Deploy status is read from the gitops `apps/**` manifests, not the live cluster** — so it reflects
  what is *declared* (ArgoCD will reconcile it). For live sync/health run `kubectl --context minicloud
  get applications -n argocd`, or see the Grafana *Delivery Portfolio* dashboard.
- **🔶 vs ❌ uses a repo-size heuristic** (`SCAFFOLD_KB` in the generator) only to split *no-Application*
  boards into "has real content" vs "scaffold" — it is intentionally approximate.
- **Opening a board ≠ a build commitment.** A board identifies a domain and gives its backlog a home; the
  build-vs-adopt-vs-module decision (per `architecture-strategy.md`) is made at onboarding.
- **Newly identified blind spots (2026-10-30):** Investment & Treasury/ALM (#29), Complaints & Disputes
  (#30), Procurement & Contract Management (#31) — see the gap analysis for *why* they were missing from
  the 19-domain blueprint.
