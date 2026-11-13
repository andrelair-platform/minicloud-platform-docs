---
id: repo-taxonomy-contract
title: Repository taxonomy contract (minicloud-gitops)
sidebar_label: 🗂️ Repo taxonomy contract
---

# Repository taxonomy contract — where everything lives in `minicloud-gitops`

:::note Map + pointer — the contract of record is in the repo
Summary + pointer page. The authoritative, **enforced** contract is
[`ARCHITECTURE.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/ARCHITECTURE.md) at
the repo root — it stays with the code because the **guard hook + CI reference it by name** as the rule
they enforce. This page is the discoverable map entry. Snapshot: **2026-11-13**.
:::

This is a different altitude from the rest of this Architecture section. The
[C4 system design](./c4-system-design) and [IS application landscape](./is-application-landscape) describe
**how the platform works**; this describes **where files go in the GitOps repo and what is enforced** —
the repo's own "law".

## The two pillars (the one boundary that must never blur)

```
platform/   → technical capabilities the platform PROVIDES   (domain-agnostic)
is/         → the Information System / insurance business      (the CONSUMERS)
services/   → HOW custom apps are packaged (wrapper charts + Kargo — packaging, not taxonomy)
apps/       → WHERE Argo CD classifies + deploys everything    (the taxonomy projection)
```

**Litmus test for any new component:** *if the company stopped selling insurance tomorrow, would this
still have a reason to exist?* **Yes → `platform/<layer>/` · No → `is/<group>/`.** (The enforced decision
rule is `platform-vs-information-system.md`; see also the [Platform ↔ IS dependency matrix](./platform-is-dependency-matrix).)

## The layout (current)

| Path | Holds |
|---|---|
| `bootstrap/` | the app-of-apps **seed** (`root-app.yaml`) — the only thing applied by hand |
| `apps/` | ArgoCD **Application** manifests (taxonomy): `platform/<layer>/` · `is/<group>/` · `retrieva/` · `previews/` |
| `platform/<layer>/` | platform capabilities by layer — `foundation · storage · networking · secrets · delivery · security · observability · data · automation · ai · shared-services · _demos`. Also holds cluster-scoped resources within a layer (quotas → `security/quotas`, netpols → `security/network-policies`, SCs → `storage/`). |
| `is/<group>/` | raw/vendor IS manifests — `workplace · erp · insurance` (custom IS **services** like `ktayl-iam`/`ktayl-itsm` live in `services/`, deployed via `apps/is/{iam,itsm}`) |
| `services/<svc>/` | per-custom-app packaging: `helm/` (wrapper chart) + `kargo/` (promotion) — Helm-only, zero kustomize |
| `charts/` · `helm-values/` | the shared `minicloud-app-deployment` **library chart** · values for third-party charts |
| `docs/` · `.claude/` | in-repo ADRs (design coupled to code) · the agent guardrails + rules constitution |

> **History:** the former flat `manifests/` dir was fully migrated into `platform/<layer>/` (LOT E, 2026-10),
> and the `environments/` team-namespace model was retired (2026-11) — both reflected above.

## What's enforced (the FREEZE)

Two layers keep the taxonomy from rotting — both cite `ARCHITECTURE.md` as the contract:

- **Keystroke:** the `guard-write.py` hook refuses a new `manifests/<subdir>` (now gone — belt-and-braces)
  and application source code outside the sanctioned dirs.
- **Pre-merge CI:** `architecture-guard.yml` fails any PR that **adds** an Application outside
  `apps/platform/<layer>/` or `apps/is/<group>/`, a new top-level dir without an ADR, or app source code.

Both inspect only *newly added* files, so pre-existing legacy state is grandfathered — the FREEZE blocks
adding to the entropy, not the existing state.

## Full contract

The canonical tree, the per-directory contract table, the FREEZE details, and the (completed) migration
playbook are all in the repo:
[**`ARCHITECTURE.md`**](https://github.com/andrelair-platform/minicloud-gitops/blob/main/ARCHITECTURE.md).
