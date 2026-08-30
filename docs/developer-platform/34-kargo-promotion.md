---
title: Kargo — Multi-Stage Promotion
sidebar_label: Kargo Promotion
---

# Kargo — Multi-Stage Promotion

> **What:** Kargo automates moving a verified container image from `dev` to `prod`
> across the GitOps overlays — the one thing Argo CD does *not* do.
> **Detail lives with the code:** [`manifests/kargo/README.md`](https://github.com/andrelair-platform/minicloud-gitops/tree/main/manifests/kargo)
> and the `.claude/rules/gitops.md` *Multi-stage promotion — Kargo* section.

## Why

Argo CD (and Flux) excel at one job: **synchronise one environment from Git to the
cluster.** They deliberately do **not** manage *how a change moves between stages*.
Historically that gap gets filled with fragile glue — `sed`/`git commit` in CI,
bespoke release scripts, or PR-based copy/paste between overlays. On this platform
that glue was CI's `bump-gitops` job plus a hand-written prod PR.

**Kargo** fills the gap the GitOps-native way: it watches the built image and
**writes the Git change** (opens PRs) that Argo CD then reconciles. It never touches
the cluster directly, so the GitOps model — and the CODEOWNERS prod gate — stay
fully intact.

## Division of labour

```
 CI  ──build & prove──►  ghcr image (signed, SBOM, immutable SHA)
                              │
 Kargo ──promote──►  opens PR bumping the overlay tag   (dev → prod)
                              │
 Argo CD ──deploy──►  reconciles the merged overlay to the cluster
```

**CI builds & proves the artifact. Kargo promotes it. Argo CD deploys it.** Kargo
replaces only CI's image-bump step — all testing, build, scan, sign and SBOM stay
in CI, and post-deploy verification (smoke + k6) stays in CI too.

## The promotion pipeline (per service)

Each Kargo-promotable service has a `services/<svc>/kargo/` directory:

| Resource | Role |
|---|---|
| `Project` | a Kargo tenant = one namespace |
| `Warehouse` | watches the prod ghcr image (`NewestBuild`, SHA-tag regex) → produces **Freight** (an immutable artifact set) |
| `Stage: dev` | pulls Freight directly; opens an auto-mergeable PR bumping the **dev** overlay |
| `Stage: prod` | accepts Freight **only after it is live in dev**; opens a **CODEOWNERS-gated PR** bumping the **prod** overlay |

The prod Stage's `sources.stages: [dev]` is the **multi-stage gate** — nothing
reaches prod that has not already run in dev. The prod PR lands on the CODEOWNERS
gate (the human approval), and the live canary Rollout + its AnalysisTemplate remain
the runtime safety brake.

## Two environments only

Kargo's arrival came with a standard cleanup: **staging was removed** platform-wide
(overlays, the `_staging-optional` template, `environments.yaml`, the CI
`promote-staging` job). The standard is now exactly **`dev` + `prod`**; Kargo's
governed dev→prod promotion makes a third gate unnecessary.

## Which services are wired

| Service | Status | Reason |
|---|---|---|
| platform-demo, minicloud-plane, minicloud-agent, minicloud-crew-agent | **Wired** | single ghcr image, *same immutable artifact* runs in dev and prod |
| retrieva | **Parked** | frontend bakes `NEXT_PUBLIC_API_URL` at build → dev and prod are *different* artifacts (nothing to promote) |
| ktayl-policy-service | **Parked** | prod still Harbor `:latest` (mutable) — not on the ghcr/SHA pattern |

The litmus test: **Kargo can only promote one immutable artifact across stages.** A
service that bakes environment config into its image, or isn't on the ghcr/SHA prod
pattern, is parked with a `kargo/README.md` explaining the prerequisite.

## Safe-by-default posture

The initial rollout configures **no auto-promotion** — Freight is discovered
automatically but a promotion only runs when triggered in the Kargo UI. So Kargo
cannot fight CI's existing dev image-bump and cannot open a prod PR on its own.
Full cutover per service is opt-in: enable a `dev` auto-promotion policy and delete
that service's CI `bump-gitops` step. The `automerge` auto-merge is already wired
(`.github/workflows/kargo-automerge.yml`), and it refuses any PR that touches more
than dev overlays.

- **UI:** [kargo.10.0.0.200.nip.io](https://kargo.10.0.0.200.nip.io) (Tailscale + minicloud CA)
- **Install:** `apps/platform/kargo.yaml` (Helm chart) + `apps/platform/kargo-projects.yaml` (ApplicationSet over `services/*/kargo/`)
