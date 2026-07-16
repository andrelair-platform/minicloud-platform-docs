---
id: branch-strategy-cicd
title: Branch Strategy & CI/CD Flow
sidebar_label: Branch Strategy & CI/CD
---

# Branch Strategy & CI/CD Flow

All 14 repositories in `andrelair-platform` follow a single, enforced branching standard. The standard splits repos into two categories based on whether they build and push a Docker image.

---

## Two-Category System

### Category A — Image repos (9 repos)

Repos that have a `Dockerfile` and a CI pipeline pushing to Harbor. These use three branches:

| Branch | Environment | CI behaviour | GitOps bump |
|---|---|---|---|
| `dev` | Development | Build + push `dev-<sha>` tag. No cosign. | Yes (dev overlay / dev manifest) |
| `staging` | Staging | Build + push `staging-<sha>` tag. Cosign-signed. | No |
| `main` | Production | Build + push `<sha>` tag. Cosign + SBOM. | Yes (prod manifest) |

**Repos in Category A:**

| Repo | GitOps target |
|---|---|
| `minicloud-backstage` | `helm-values/backstage-values.yaml` (main only) |
| `minicloud-rag-ingest` | `manifests/ai/11-rag-ingest.yaml` (main only) |
| `minicloud-markitdown-proxy` | `manifests/ai/10-markitdown-proxy.yaml` (main only) |
| `minicloud-litellm-custom` | `manifests/ai/01-litellm-deployment.yaml` (main only) |
| `minicloud-open-webui` | `helm-values/open-webui-values.yaml` (main only) |
| `minicloud-onlyoffice` | `manifests/productivity/` (main only) |
| `minicloud-plane` | `manifests/` (main only) |
| `platform-demo` | `services/platform-demo/overlays/{dev,staging,prod}` (all 3 branches) |
| `ktayl-solution-web` | `manifests/ktayl-solution-web/00-deployment.yaml` (main only) |

### Category B — Config / docs / IaC repos (5 repos)

Repos with no Docker image. These use `main` only — `dev` and `staging` branches add no value when there is no artifact to promote.

| Repo | Purpose |
|---|---|
| `minicloud-gitops` | ArgoCD app-of-apps + all Helm values — source of truth for the cluster |
| `minicloud-ansible` | Post-MAAS node bootstrap + Day-2 rolling upgrade playbooks |
| `minicloud-opentofu` | MAAS infrastructure as code (subnet, DHCP, machines) |
| `minicloud-platform-docs` | Docusaurus docs site → GitHub Pages |
| `phi3-financial` | LLM prompt-engineering evaluation pipeline |

---

## Branch Protection — Enforced via GitHub Rulesets

Branch protection is enforced through **repository-level rulesets** (GitHub's ruleset feature, available on the free plan). Two rulesets exist per image repo; one per config repo.

### `main-protection` ruleset (all 14 repos)

| Rule | Value |
|---|---|
| Pull request required | Yes — 0 approvals needed (self-merge allowed) |
| Signed commits required | Yes — GPG key `FD6D39D681DEFA34` |
| Force push | Blocked |

Direct push to `main` without a PR is rejected at the API level. The only exception is admin bypass (org owner), which should be used only in emergencies and leaves a visible audit trail.

### `staging-protection` ruleset (Category A repos only)

| Rule | Value |
|---|---|
| Pull request required | Yes — 0 approvals needed |
| Required status check | `build-and-push` must pass |
| Force push | Blocked |

This gates promotion from `dev` to `staging` on CI passing — a broken image cannot reach the staging environment. The `dev` branch has no protection: direct push is allowed for fast iteration.

### Summary table

| Branch | Exists on | PR required | CI gate | Signed commits | Force push |
|---|---|---|---|---|---|
| `main` | All 14 repos | Yes | No¹ | Yes (GPG) | Blocked |
| `staging` | Category A (9 repos) | Yes | `build-and-push` | No | Blocked |
| `dev` | Category A (9 repos) | No | No | No | Allowed |

¹ CI runs on PRs to `main` via `pull_request:` trigger, but it is not a hard merge gate on `main` itself — only on `staging`.

---

## Promotion Flow

```
dev branch
  │  git push origin dev
  │  → CI: build + push harbor.../image:dev-<sha>
  │  → GitOps bump (platform-demo only)
  │  → ArgoCD auto-syncs dev namespace
  │
  ▼  gh pr create --base staging --head dev
     PR opened → CI runs (build-and-push must pass)
     Self-merge once CI is green
     │
     ▼ staging branch
          → CI: build + push harbor.../image:staging-<sha>  (cosign-signed)
          → ArgoCD manual sync of staging overlay
          │
          ▼  gh pr create --base main --head staging
               PR opened → CI runs
               Fill PR template (change type, risk, ACPR ref)
               Self-merge → change-record GHA creates [CHANGE] issue
               │
               ▼ main branch
                    → CI: build + push harbor.../image:<sha>  (cosign + SBOM)
                    → GitOps bump with GPG-signed commit
                    → ArgoCD syncs prod overlay
```

---

## Supply Chain per Branch

| Control | `dev` | `staging` | `main` |
|---|---|---|---|
| Trivy CRITICAL scan | Yes | Yes | Yes |
| Cosign keyless sign | No | Yes | Yes |
| SBOM (CycloneDX via syft) | No | No | Yes |
| SBOM attached as OCI referrer | No | No | Yes |
| GitOps signed commit (GPG) | Yes¹ | No | Yes |

¹ `platform-demo` only — it uses Kustomize overlays on all 3 branches.

---

## Image Tag Format

```
dev push     →  harbor.10.0.0.200.nip.io/library/<name>:dev-a1b2c3d
staging push →  harbor.10.0.0.200.nip.io/library/<name>:staging-a1b2c3d
main push    →  harbor.10.0.0.200.nip.io/library/<name>:a1b2c3d
```

The GitOps manifests always reference the internal Harbor URL so kubelet pulls are cluster-local. CI authenticates to Harbor over the Cloudflare Tunnel (`harbor.devandre.sbs`).

---

## Typical Dev Workflow

```bash
# 1. Start work on dev
git checkout dev
git pull origin dev

# 2. Make changes, commit (no GPG signing required on dev)
git add -p
git commit -m "feat: describe what changed"
git push origin dev
# CI builds dev-<sha> and deploys to dev namespace automatically

# 3. Promote to staging (when dev looks good)
gh pr create --base staging --head dev --title "feat: describe what changed"
# Wait for build-and-push CI check to pass, then self-merge
gh pr merge <N> --merge

# 4. Verify in staging namespace, then promote to production
gh pr create --base main --head staging --title "feat: describe what changed"
# Fill in PR body: change type checkbox, risk level, ACPR reference
# Self-merge → change-record issue created automatically
gh pr merge <N> --merge
```

---

## Setting Up a New Repo (Checklist)

When creating a new image repo under `andrelair-platform`:

```bash
# 1. Create the repo and push initial code to main

# 2. Create the dev and staging branches
sha=$(gh api repos/andrelair-platform/<REPO>/git/ref/heads/main --jq '.object.sha')
gh api repos/andrelair-platform/<REPO>/git/refs -X POST \
  -f ref="refs/heads/dev" -f sha="$sha"
gh api repos/andrelair-platform/<REPO>/git/refs -X POST \
  -f ref="refs/heads/staging" -f sha="$sha"

# 3. Apply main-protection ruleset
gh api repos/andrelair-platform/<REPO>/rulesets -X POST --input /tmp/main-ruleset.json

# 4. Apply staging-protection ruleset
gh api repos/andrelair-platform/<REPO>/rulesets -X POST --input /tmp/staging-ruleset.json
```

The ruleset JSON files are defined in the [Branch Protection Rulesets](#branch-protection--enforced-via-github-rulesets) section above. Save them to `/tmp/` from the values documented there before running.

**CI workflow trigger block** — every image repo must declare:

```yaml
on:
  push:
    branches: [main, staging, dev]
  pull_request:
    branches: [main, staging]
```

This ensures:
- Every push to any branch builds an image (enables Trivy + Harbor cache warming)
- PRs to `staging` and `main` trigger CI so the `staging-protection` gate can evaluate `build-and-push`

For **config/docs repos** (no Dockerfile): keep `main` only. Apply only the `main-protection` ruleset. No `dev`/`staging` branches needed.

---

## Why Not Org-Level Rulesets?

GitHub org-level rulesets (which would let you define one ruleset applied to all repos at once) require the **GitHub Team plan**. The `andrelair-platform` org is on the free plan. Per-repo rulesets are used instead — identical content on each repo, applied via the API in batch. If the org upgrades to Team in the future, the per-repo rulesets can be deleted and replaced with a single org-level ruleset.

---

## ACPR / DORA Alignment

- Every merge to `main` produces a `[CHANGE]` issue (via `change-record.yml`) with metadata: who merged, when, what changed, risk level — satisfies **DORA Art.9 ICT change management**
- Incident issue template covers **DORA Art.19** major incident classification
- Separate `dev` / `staging` / `prod` environments satisfy **ACPR 2021-R-01 §4.2** environment segregation
- GPG-signed commits on `main` provide non-repudiation of all production changes
- Blocked force push on `main` and `staging` ensures commit history is immutable
