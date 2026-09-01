---
title: Kargo — Multi-Stage Promotion
sidebar_label: Kargo Promotion
---

# Kargo — Multi-Stage Promotion (developer guide)

> **What:** Kargo automates moving a verified container artifact from `dev` to `prod`
> across the GitOps overlays — the one thing Argo CD does *not* do.
> **Detail with the code:** [`manifests/kargo/README.md`](https://github.com/andrelair-platform/minicloud-gitops/tree/main/manifests/kargo)
> + the `.claude/rules/gitops.md` *Multi-stage promotion — Kargo* section.

## Why

Argo CD synchronises **one** environment from Git to the cluster. It deliberately does
**not** manage *how a change moves between stages*. That gap used to be filled with
fragile glue (CI `sed`/`git commit`, hand-written prod PRs). **Kargo** fills it the
GitOps-native way: it watches the built artifact and **writes the Git change** (opens
PRs) that Argo CD reconciles. It never touches the cluster, so the GitOps model — and
the CODEOWNERS prod gate — stay intact.

## Division of labour (the mental model)

```
 CI  ──build & prove──►  ghcr artifact (signed, SBOM, immutable SHA)
                              │
 Kargo ──promote──►  opens a PR bumping the overlay tag   (dev → prod)
                              │
 Argo CD ──deploy──►  reconciles the merged overlay to the cluster
```

**CI builds & proves the artifact. Kargo promotes it. Argo CD deploys it.** Kargo
replaces only the image-bump/promotion step — testing, build, scan, sign, SBOM and
post-deploy verification all stay in CI.

## The pipeline (per service)

Each service has a `services/<svc>/kargo/` directory: a `Project` (= a Kargo namespace),
a `Warehouse` (produces **Freight** = an immutable artifact set), and one or two `Stage`s
whose `promotionTemplate` runs `git-clone → kustomize-set-image → git-commit → git-push →
git-open-pr → git-wait-for-pr`. The **prod** PR lands on the **CODEOWNERS gate**; the live
canary Rollout + its AnalysisTemplate are the runtime safety brake.

## Two Warehouse models (choose per service)

| Model | Freight = | Use when | Reference |
|---|---|---|---|
| **Image Warehouse** (`NewestBuild`, SHA-tag regex) | the newest image build | a **single-image** service (or images that always change together) | platform-demo, plane, agent, crew, ktayl |
| **Git Warehouse** (`git` subscription on `main`) | one **git commit** → all images pinned to that commit's `${{ commitFrom(...).ID[0:7] }}` | a **multi-image** service where one image can be unchanged | **retrieva** (backend + frontend) |

**Why the git model exists (a real lesson):** with two `NewestBuild` image subscriptions,
if one image is *unchanged* between releases, its rebuild is a byte-identical cached image
with no newer timestamp — so `NewestBuild` can't rank the new SHA as "newest", and Kargo
produces a **mixed Freight** (e.g. `backend@old + frontend@new`). A **git** Warehouse keys
Freight on the commit, so every image is promoted at the **same SHA** — consistent and
auditable. (retrieva is a public repo, so its git subscription needs no credential.)

## Which services are wired (all 6 custom services)

| Service | Warehouse | Stages | Notes |
|---|---|---|---|
| platform-demo | image (public ghcr) | dev + prod | reference; full canary promo demonstrated |
| minicloud-plane / -agent / -crew | image (Internal ghcr + cred) | dev + prod | dev PRs squash-auto-merge |
| ktayl-policy-service | image (Internal ghcr + cred) | dev + prod | migrated to ghcr/SHA; own prod Postgres |
| **retrieva** | **git** (2 images) | **prod-only** | frontend made **runtime-config** so one image serves all envs; dev stays on its dev-branch track |

## For developers — how you work with it

- **Trigger a promotion:** in the [Kargo UI](https://kargo.10.0.0.200.nip.io) open your
  service's Project, pick a Freight, and promote to a Stage. Or by kubectl:
  ```bash
  kubectl create -n <svc> -f - <<EOF
  apiVersion: kargo.akuity.io/v1alpha1
  kind: Promotion
  metadata: { generateName: prod-, namespace: <svc> }
  spec: { stage: prod, freight: <freight-name> }
  EOF
  ```
  Kargo runs the template and **opens the PR** — dev PRs auto-merge (dev overlays aren't
  CODEOWNERS-gated); the **prod PR waits for your CODEOWNERS review**, then Argo CD syncs.
- **You never hand-edit overlay image tags.** Kargo writes them.
- **Runtime config, not baked config:** an image must be **env-agnostic** to be promotable
  (the same artifact runs in dev and prod). Read environment values at **runtime**, not at
  build. Reference: retrieva's frontend uses a server-injected `window.__ENV__` +
  `getApiUrl()` instead of baking `NEXT_PUBLIC_API_URL` (see
  `retrieva/docs/kargo-runtime-config-migration.md`).
- **Add a new service:** copy `services/platform-demo/kargo/`, point the Warehouse at your
  ghcr image (or use the git model for multi-image), add the namespace to the AppProject,
  and un-exclude it in `apps/platform/kargo-projects.yaml` (or add a dedicated app if its
  prod namespace collides — see retrieva). The litmus test: **Kargo promotes one immutable
  artifact across stages.**

## Gotchas worth knowing

- **Mixed Freight** (multi-image, one unchanged) → use a **git Warehouse** (above).
- **No-delta promotion** (overlay already at the Freight SHA) → the Stage `if`-gates the
  PR steps on `commit != clone HEAD` so it succeeds without opening an empty PR.
- **Unsigned Kargo commits** vs `main`'s verified-signatures rule → **squash-merge** Kargo
  PRs (GitHub signs the squash commit); the dev auto-merge workflow already uses `--squash`.
- **Gatekeeper** requires container `securityContext` (runAsNonRoot, no-priv-esc) + resource
  limits — set them in Helm values / manifests or the Deployment is denied.
- **Env-baked images** (or mutable `:latest` prod) can't be promoted — fix first.

## Two environments only

Kargo's arrival removed **staging** platform-wide (overlays, `_staging-optional`,
`environments.yaml`, the CI `promote-staging` job). Standard = **`dev` + `prod`**.

- **UI:** [kargo.10.0.0.200.nip.io](https://kargo.10.0.0.200.nip.io) (Tailscale + minicloud CA)
- **Install:** `apps/platform/kargo.yaml` (Helm) + `apps/platform/kargo-projects.yaml` (ApplicationSet) + `apps/platform/kargo-retrieva.yaml` (dedicated).
