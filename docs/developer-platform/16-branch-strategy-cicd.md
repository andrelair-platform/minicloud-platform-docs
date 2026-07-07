---
id: branch-strategy-cicd
title: Branch Strategy & CI/CD Flow
sidebar_label: Branch Strategy & CI/CD
---

# Branch Strategy & CI/CD Flow

Every custom application repo follows a **3-branch GitFlow** aligned with the Kustomize overlay structure in `minicloud-gitops`. Changes move from `dev` → `staging` → `main` via pull requests, each PR triggering the automated change-record workflow for ACPR audit trail.

## Branch Map

| Branch | Environment | ArgoCD overlay | CI behaviour |
|---|---|---|---|
| `dev` | Development | `overlays/dev` (auto-sync) | Build + push `dev-<sha>` tag, no sign, gitops update |
| `staging` | Staging | `overlays/staging` (manual sync) | Build + push `staging-<sha>` tag, cosign, no gitops update¹ |
| `main` | Production | `overlays/prod` (manual sync) | Build + push `<sha>` tag, cosign + SBOM, gitops update |
| PR | — | — | Build + test only, no push |

¹ For `platform-demo` the gitops overlay is updated on all 3 branches. For flat-manifest repos (`ktayl-solution-web`, custom image repos), gitops is only updated on `main`.

## Repos covered

| Repo | CI file | GitOps target |
|---|---|---|
| `platform-demo` | `ci.yml` | `services/platform-demo/overlays/{dev,staging,prod}` |
| `ktayl-solution-web` | `build-push.yml` | `manifests/ktayl-solution-web/00-deployment.yaml` (main only) |
| `minicloud-markitdown-proxy` | `ci.yml` | `manifests/ai/10-markitdown-proxy.yaml` (main only) |
| `minicloud-rag-ingest` | `ci.yml` | `manifests/ai/11-rag-ingest.yaml` (main only) |
| `minicloud-litellm-custom` | `ci.yml` | `manifests/ai/01-litellm-deployment.yaml` (main only) |
| `minicloud-postgresql-noavx512` | `ci.yml` | None (version-tagged base image) |

## Promotion flow

```
dev branch
  │  push → CI builds dev-<sha>, pushes to Harbor, updates overlays/dev
  │  ArgoCD auto-syncs dev namespace
  │
  ▼ open PR: dev → staging
     PR template filled (change type, risk, ACPR ref)
     build-only CI runs (tests pass, image not pushed again)
     self-merge (0 approvals required, admin bypass available)
     │
     ▼ staging branch
          push → CI builds staging-<sha>, cosign-signs, pushes to Harbor
          ArgoCD manual sync of staging overlay
          │
          ▼ open PR: staging → main
               PR merged → change-record GHA creates [CHANGE] issue automatically
               │
               ▼ main branch
                    push → CI builds <sha>, cosign + SBOM, pushes to Harbor
                    gitops overlay updated with signed commit
                    ArgoCD manual sync of prod overlay
```

## Branch protection rules

| Branch | PR required | Signed commits | Admin bypass | Force push |
|---|---|---|---|---|
| `main` | Yes (0 approvals) | Yes (GPG FD6D39D681DEFA34) | Yes | Blocked |
| `staging` | Yes (0 approvals) | No | Yes | Blocked |
| `dev` | No | No | — | Allowed |

Admin bypass allows the sole engineer to push directly to `main` or `staging` in an emergency without opening a PR. Use sparingly — direct pushes bypass the change-record workflow.

## Supply chain per branch

| Control | `dev` | `staging` | `main` |
|---|---|---|---|
| Trivy CRITICAL scan | Yes | Yes | Yes |
| Cosign keyless sign | No | Yes | Yes |
| SBOM (CycloneDX) | No | No | Yes |
| GitOps signed commit | Yes¹ | Yes¹ | Yes |

¹ For `platform-demo` only (uses Kustomize overlays on all 3 branches).

## Image tag format

```
dev push   →  harbor.../image:dev-a1b2c3d
staging push → harbor.../image:staging-a1b2c3d
main push  →  harbor.../image:a1b2c3d
```

The gitops manifests always reference the internal Harbor URL (`harbor.10.0.0.200.nip.io`) so kubelet pulls are cluster-internal. CI authenticates to Harbor via the public Cloudflare Tunnel URL (`harbor.devandre.sbs`).

## Typical dev workflow

```bash
# Start feature on dev branch
git checkout dev
git pull origin dev

# ... make changes ...

git add -p
git commit -S -m "feat: describe what changed"
git push origin dev
# CI runs automatically — image built and deployed to dev namespace

# Promote to staging
gh pr create --base staging --head dev --title "feat: describe what changed"
# Self-merge the PR (0 approvals required)
# CI runs on staging — image signed and pushed

# Promote to production
gh pr create --base main --head staging --title "feat: describe what changed"
# Fill in PR template (change type, risk level, ACPR ref)
# Self-merge → change-record issue auto-created for audit trail
```

## ACPR / DORA alignment

- Every merge to `main` produces a `[CHANGE]` issue with metadata (who, when, what, risk) — satisfies **DORA Art.9 ICT change management**
- Incident issue template covers **DORA Art.19** major incident classification
- Separate `dev` / `staging` / `prod` environments satisfy the **ACPR 2021-R-01 §4.2** requirement for environment segregation
- GPG-signed commits on `main` provide non-repudiation of all production changes
