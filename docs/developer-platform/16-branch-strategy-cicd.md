---
id: branch-strategy-cicd
title: Branch Strategy, Repo Structure & CI/CD Flow
sidebar_label: Branch Strategy & CI/CD
---

# Branch Strategy, Repository Structure & CI/CD Flow

:::note Superseded model
This page was rewritten (2026-09-04) for the **trunk-based + Kargo** model. The earlier
`dev`/`staging`/`prod` **branch-per-environment** flow (long-lived branches, `dev-<sha>` /
`staging-<sha>` image tags, CI-driven overlay bumps) is **retired**. Environments are now Kustomize
overlays reconciled from `main`, promoted by Kargo — see
[Kargo — Multi-Stage Promotion](./34-kargo-promotion.md).
:::

All ~26 repositories in `andrelair-platform` follow one **trunk-based** standard: a long-lived `main`,
short-lived feature branches, and **no branch-per-environment**. Environments are *deploy targets*
(namespaces/overlays), not git branches.

---

## Environments are not git branches

The platform runs exactly two **environments** (`dev` + `prod`). Neither is driven by a long-lived
branch — that's the GitOps anti-pattern (Git is the control plane; environments are overlays, not
branches you merge between).

| Thing | What it is | Fed by |
|---|---|---|
| **`dev` environment** | `<svc>-dev` namespace + `minicloud-1/dev` overlay (permanent) | **Kargo** auto-promotes the `main` build into it, then verifies it |
| **`prod` environment** | `<svc>-prod` namespace + `minicloud-1/prod` overlay (permanent) | **Kargo** opens a CODEOWNERS-gated PR promoting the dev-verified Freight |
| **`main` branch** | the trunk — the only deploy trigger | a merge builds `:<sha>` → Kargo takes over |
| **`dev` branch** *(optional)* | a working/integration branch | **nothing** — pushing it no longer builds or deploys |
| **feature branches** | `feat/…` `fix/…` `docs/…` `chore/…` → PR → `main` | short-lived; **auto-deleted on merge** (`delete_branch_on_merge=true` on all 26 repos) |

`staging` was removed platform-wide (environment retired for the 2-env standard; leftover branches
purged 2026-09-04). Do not recreate it.

---

## Repository structure — polyrepo + one GitOps repo

Delivery is **polyrepo**: each service owns its source repo (code + `Dockerfile` + CI); a single
**`minicloud-gitops`** repo holds all deploy configuration (app-of-apps). Source and deploy config
are separated — the opposite of co-locating Helm charts in the manifest repo.

```
<service-repo>/                     # one per microservice (polyrepo)
├── <source>, Dockerfile
├── .github/workflows/ci.yml        # build → test → scan → sign → push (build-only)
└── .github/workflows/release.yml   # release-please + SemVer dual-tag

minicloud-gitops/                   # the single GitOps repo (deploy config only)
├── apps/                           # ArgoCD Application manifests
│   ├── platform/                   # ~43 infra apps
│   └── workloads/                  # <svc>-dev.yaml, <svc>-prod.yaml
├── manifests/argocd-project/       # the AppProject (sourceRepos/destinations/whitelist)
├── services/<svc>/                 # our services — Kustomize, NOT Helm charts
│   ├── base/                       # deployment/service/… (no ns, no image tag)
│   ├── minicloud-1/{dev,prod}/     # env overlays: image tag + patches (≈ per-env values)
│   └── kargo/                      # Kargo Project + Warehouse + Stages + ProjectConfig + verify
├── helm-values/minicloud-1/        # values for THIRD-PARTY charts only
└── manifests/                      # platform infra (network policies, quotas, ai, …)
```

### How this maps to the reference "microservice-helmcharts" layout

A common tutorial layout centralises everything in the manifest repo (`argocd/application/{env}/`,
`env/{env}/<svc>/values.yaml`, `kargo/<svc>-config/`, `service-charts/<svc>/`). We have every one of
those building blocks — organised differently, on purpose:

| Reference layout | Here | Why |
|---|---|---|
| `argocd/application/{dev,staging,prod}/` | `apps/{platform,workloads}/<svc>-{dev,prod}.yaml` | split by type, not env; 2-env |
| `AppProject` (`craftisia-project.yaml`, `destinations: "*"`) | `manifests/argocd-project/00-project.yaml` | explicit allowlist, no `"*"` (hardened) |
| `env/{env}/<svc>/values.yaml` (**Helm values** per env) | `services/<svc>/minicloud-1/{dev,prod}` (**Kustomize** overlays) | Kustomize for our services; Helm reserved for third-party charts |
| `service-charts/<svc>/` (Helm chart **in the manifest repo**) | chart/source **in the service's own polyrepo** | true polyrepo — deploy config ≠ app source |
| `kargo/<svc>-config/` (top-level) | `services/<svc>/kargo/` (**co-located** with the service) | everything for a service in one dir |
| `.github/workflows/docker-ci.yml` (in the manifest repo) | CI **in each service polyrepo** | consistent with polyrepo |
| `projectconfig.yaml` (promotion policies) | `services/<svc>/kargo/projectconfig.yaml` | identical concept |
| `dev` / `staging` / `prod` stages | `dev` + `prod` stages (`sources.stages: [dev]` gate) | 2-env standard |

**Kustomize-vs-Helm is a deliberate tool choice, not a gap:** `minicloud-1/dev/kustomization.yaml`
(image tag + patches) does exactly what the reference's `env/dev/<svc>/values.yaml` does. We do **not**
restructure the working 91-app GitOps repo to match a tutorial's Helm layout — that would be churn for
zero benefit.

---

## Branch protection — enforced via GitHub Rulesets

Enforced through **repository-level rulesets** (works on the free plan). One `main-protection` ruleset
per repo:

| Rule | Value |
|---|---|
| Pull request required | Yes (self-merge allowed; CODEOWNERS review required on protected paths in `minicloud-gitops`) |
| Signed commits required | Yes — GPG key `FD6D39D681DEFA34` (Kargo PRs are squash-merged so GitHub signs the squash commit) |
| Force push | Blocked |
| Auto-delete head branch on merge | **On** (feature branches are short-lived by construction) |

Direct push to `main` without a PR is rejected at the API level; the only exception is admin bypass
(org owner), used only in emergencies, and it leaves a visible audit trail. There is **no**
`staging-protection` ruleset anymore.

**Why per-repo, not org-level:** org-level rulesets need the GitHub Team plan; the org is on free.
Per-repo rulesets carry identical content, applied via the API in batch.

---

## CI/CD flow (per service)

```
feature branch ──PR──► main  (signed, PR-gated)
        │
        ▼  CI (build-only): test → Trivy CRITICAL → build → cosign sign → SBOM (syft)
        │  dual-push:  Harbor :<sha> (dev registry)  +  ghcr :<sha> (prod, durable)
        │  on a release-please release: crane adds the vX.Y.Z SemVer alias to the same digest
        ▼
      Kargo  ──auto-promote──► dev environment ──verify (smoke AnalysisRun)──►
        │
        ▼  dev-verified Freight ──CODEOWNERS PR──► prod environment (Argo CD syncs)
```

- **CI is build-only** (`push: [main]`). It no longer bumps overlays or smokes deploys — Kargo owns
  promotion + dev verification. See [Kargo — Multi-Stage Promotion](./34-kargo-promotion.md).
- **Image tags:** the **git SHA** is the canonical promotion identifier (Warehouses watch it, Freight =
  a commit, overlays pin it). A **SemVer alias** (`vX.Y.Z`) is added to the same digest on a
  release-please release (**dual-tagging** — SHA for machines, SemVer for humans).

### Supply chain (on `main`)

| Control | Applied |
|---|---|
| Trivy CRITICAL scan | Yes |
| Cosign keyless sign (Sigstore/Fulcio) | Yes — Harbor **and** ghcr digests |
| SBOM (CycloneDX via syft) + attached as OCI referrer | Yes |
| GPG-signed GitOps commit | Yes (Kargo squash-merge → signed squash) |

---

## Setting up a new repo (checklist)

```bash
# 1. Create the repo, push initial code to main.
# 2. Enable auto-delete of merged branches:
gh api -X PATCH repos/andrelair-platform/<REPO> -F delete_branch_on_merge=true
# 3. Apply the main-protection ruleset (signed commits + PR + no force-push):
gh api repos/andrelair-platform/<REPO>/rulesets -X POST --input /tmp/main-ruleset.json
# 4. CI trigger = main only:
#      on: { push: { branches: [main] }, pull_request: { branches: [main] } }
# 5. If the service warrants Kargo (build it + dev AND prod + env-agnostic + immutable prod tag),
#    add services/<svc>/kargo/ — see the Kargo guide "new service checklist".
```

No `dev`/`staging` branches to create. An optional `dev` integration branch can exist but deploys
nothing.

---

## ACPR / DORA alignment

- Every merge to `main` produces a `[CHANGE]` issue (`change-record.yml`) — who/when/what/risk —
  satisfying **DORA Art.9 ICT change management**.
- Incident issue template covers **DORA Art.19** major-incident classification.
- Separate `dev` / `prod` **environments** (namespaces/overlays) satisfy **ACPR 2021-R-01 §4.2**
  environment segregation — segregation is by *environment*, not by branch.
- GPG-signed commits + cosign-signed images + SBOM provide non-repudiation and supply-chain provenance
  for every production change.
- Blocked force-push on `main` keeps history immutable.
