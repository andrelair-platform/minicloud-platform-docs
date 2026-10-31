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

**How it is derived (boards-as-target, no cluster access needed):**

1. **Target** = every GitHub **product board** (`gh project list`) — add a board and it appears here on its own.
2. **Code** = each board's **repo size** (`gh repo list`) — real code vs scaffold vs no repo.
3. **Deployed** = the **gitops `apps/**` Application manifests** — which domains have a dev/prod Application
   *defined* (a gh-only proxy for "deployed", with env from the filename).
4. **Maturity** = the committed **capability register** (`data/capability-register.csv` — the single source
   of truth; the B2BAssurance xlsx is a derived view) — each board's `Maturity %` averaged across its
   capabilities. The register is a NOT-ASSESSED *target schema* today, so this honestly shows
   **"not assessed · N caps"** (N = the domain's capability count) and flips to **"~X% · S/N scored"** the
   moment someone fills the `Maturity %` cells in the CSV. No number is invented.

**Legend:** 🟢 a prod deployment is defined · 🔵 on dev only · 🔶 real code, not yet deployed ·
❌ scaffold / no repo yet · ⏸ deliberately parked. **Maturity** = how *complete* a domain is (depth), a
separate axis from deploy status (a domain can be 🟢 *live* yet low-maturity — only a few of its
capabilities built).

> The board↔repo↔app bridge (the one hand-maintained input) lives in the generator (`BRIDGE`). A board
> missing from it still shows (as ❌/🔶 from its repo alone). To track a brand-new domain, just open its
> board — it surfaces here as ❌ until its repo/Application appears.

---

{/* SI-DELIVERY:START */}
_Auto-generated 2026-10-31 by `scripts/gen-si-delivery.py` from the live GitHub product boards + the gitops `apps/**` manifests + repo sizes — do not hand-edit between the markers._

**At a glance:** 🟢 12 · 🔵 1 · 🔶 1 · ❌ 12 · ⏸ 3  (of 29 product boards)

## 🟢 Live — a prod deployment is defined

| Board | Domain | Maturity | Evidence |
|---|---|---|---|
| [#2](https://github.com/orgs/andrelair-platform/projects/2) | Retrieva — RNCP39583 Certification | not assessed · 29 caps | dev+prod · apps: retrieva, retrieva-assessment-crew |
| [#3](https://github.com/orgs/andrelair-platform/projects/3) | GitOps — Platform Engineering | not assessed · 32 caps | prod · apps: argo-cd, backstage, harbor, vault |
| [#4](https://github.com/orgs/andrelair-platform/projects/4) | AI Platform | not assessed · 16 caps | dev+prod · apps: langfuse, litellm, minicloud-agent, minicloud-crew-agent |
| [#5](https://github.com/orgs/andrelair-platform/projects/5) | Data Platform | not assessed · 26 caps | prod · apps: data-platform |
| [#6](https://github.com/orgs/andrelair-platform/projects/6) | ktayl Policy Service | not assessed · 25 caps | dev+prod · apps: ktayl-policy-service |
| [#7](https://github.com/orgs/andrelair-platform/projects/7) | ktayl Public Web | — | live off-cluster (GitHub Pages) |
| [#8](https://github.com/orgs/andrelair-platform/projects/8) | ERPNext (HR-Finance) | not assessed · 53 caps | prod · apps: erpnext |
| [#10](https://github.com/orgs/andrelair-platform/projects/10) | Digital Workplace (M365 Alternative) | not assessed · 33 caps | prod · apps: bookstack, docuseal, jitsi, matrix-synapse |
| [#11](https://github.com/orgs/andrelair-platform/projects/11) | ktayl Claims | not assessed · 40 caps | dev+prod · apps: ktayl-claims |
| [#12](https://github.com/orgs/andrelair-platform/projects/12) | ktayl Underwriting & Pricing | not assessed · 68 caps | dev+prod · apps: ktayl-underwriting |
| [#17](https://github.com/orgs/andrelair-platform/projects/17) | Access Governance (IAM/IGA) | not assessed · 22 caps | dev+prod · apps: ktayl-iam |
| [#28](https://github.com/orgs/andrelair-platform/projects/28) | ktayl-core — Insurance LOB (modular monolith) | — | prod · apps: ktayl-core-infra |

## 🔵 On dev — deployed to dev, not yet promoted to prod

| Board | Domain | Maturity | Evidence |
|---|---|---|---|
| [#16](https://github.com/orgs/andrelair-platform/projects/16) | ktayl ITSM (GLPI) | not assessed · 25 caps | dev · apps: ktayl-itsm |

## 🔶 In progress — real code, not yet deployed

| Board | Domain | Maturity | Evidence |
|---|---|---|---|
| [#9](https://github.com/orgs/andrelair-platform/projects/9) | ktayl Insurance LOB — Product Lines | not assessed · 15 caps | repo has content (261 KB), no Application yet: ktayl-solution-web |

## ❌ Not started — scaffold or no repo yet

| Board | Domain | Maturity | Evidence |
|---|---|---|---|
| [#13](https://github.com/orgs/andrelair-platform/projects/13) | ktayl Distribution & CRM | not assessed · 32 caps | scaffold repo (5 KB): ktayl-distribution |
| [#14](https://github.com/orgs/andrelair-platform/projects/14) | ktayl Insurance Finance & Billing | not assessed · 60 caps | scaffold repo (5 KB): ktayl-finance |
| [#15](https://github.com/orgs/andrelair-platform/projects/15) | Regulatory & Compliance | not assessed · 29 caps | scaffold repo (25 KB): ktayl-compliance |
| [#21](https://github.com/orgs/andrelair-platform/projects/21) | ktayl Risk Engineering | not assessed · 14 caps | scaffold repo (6 KB): ktayl-risk-engineering |
| [#22](https://github.com/orgs/andrelair-platform/projects/22) | ktayl Reinsurance | not assessed · 30 caps | scaffold repo (6 KB): ktayl-reinsurance |
| [#23](https://github.com/orgs/andrelair-platform/projects/23) | ktayl International Programs | not assessed · 29 caps | scaffold repo (6 KB): ktayl-international-programs |
| [#24](https://github.com/orgs/andrelair-platform/projects/24) | ktayl Documents & DMS | not assessed · 16 caps | scaffold repo (6 KB): ktayl-dms |
| [#25](https://github.com/orgs/andrelair-platform/projects/25) | ktayl Integration Platform | not assessed · 24 caps | scaffold repo (31 KB): ktayl-integration |
| [#27](https://github.com/orgs/andrelair-platform/projects/27) | ktayl Submission Hub | not assessed · 20 caps | repo not found / empty: ktayl-submission |
| [#29](https://github.com/orgs/andrelair-platform/projects/29) | ktayl Investment & Treasury (ALM) | not assessed · 18 caps | repo not found / empty: ktayl-investment |
| [#30](https://github.com/orgs/andrelair-platform/projects/30) | ktayl Complaints & Disputes | not assessed · 13 caps | repo not found / empty: ktayl-complaints |
| [#31](https://github.com/orgs/andrelair-platform/projects/31) | ktayl Procurement & Contract Management | not assessed · 35 caps | repo not found / empty: ktayl-procurement |

## ⏸ Parked — deliberate hold

| Board | Domain | Maturity | Evidence |
|---|---|---|---|
| [#18](https://github.com/orgs/andrelair-platform/projects/18) | ktayl Knowledge Assistant | — | parked — needs real upstream systems first |
| [#19](https://github.com/orgs/andrelair-platform/projects/19) | ktayl AI Ops Copilot | — | parked — needs real upstream systems first |
| [#20](https://github.com/orgs/andrelair-platform/projects/20) | ktayl Master Data (MDM) | not assessed · 26 caps | parked — keystone for analytics; deferred |
{/* SI-DELIVERY:END */}

---

## Notes & caveats

- **Deploy status is read from the gitops `apps/**` manifests, not the live cluster** — so it reflects
  what is *declared* (ArgoCD will reconcile it). This is deliberate: the committed board must be
  CI-reproducible (CI has no cluster access), so **live health is never written into this page** (it would
  drift every week). For a **live Synced/Health overlay on demand**, run `python3 scripts/gen-si-delivery.py
  --live` — it prints the board to your terminal with per-domain ArgoCD health (reaching the cluster via
  local kubectl or `ssh controller`), without touching this page. For a dashboard, see Grafana
  *Delivery Portfolio*.
- **🔶 vs ❌ uses a repo-size heuristic** (`SCAFFOLD_KB` in the generator) only to split *no-Application*
  boards into "has real content" vs "scaffold" — it is intentionally approximate.
- **Opening a board ≠ a build commitment.** A board identifies a domain and gives its backlog a home; the
  build-vs-adopt-vs-module decision (per `architecture-strategy.md`) is made at onboarding.
- **Newly identified blind spots (2026-10-30):** Investment & Treasury/ALM (#29), Complaints & Disputes
  (#30), Procurement & Contract Management (#31) — see the gap analysis for *why* they were missing from
  the 19-domain blueprint.
