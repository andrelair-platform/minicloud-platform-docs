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

## Which deployments need Kargo? (why only 6 of ~91 apps)

A common confusion: the cluster runs **~91 Argo CD Applications, 127 Deployments,
34 StatefulSets, ~369 pods** — yet only **6 services** are on Kargo. That is not an
oversight. **Kargo promotes *one immutable artifact that you build* across *multiple
stages*.** It only earns its place when **all four** conditions hold at once:

1. **You build the image** (your source → CI → image — not a vendor's chart).
2. **Two environments** run the *same* artifact (a `dev` **and** a `prod`).
3. The image is **env-agnostic** (config read at **runtime**, so the identical binary is promotable).
4. The prod tag is **immutable** (ghcr / SHA, never a moving `:latest`).

Everything else on the platform falls into three buckets that **do not** need Kargo —
they update by a plain **version bump in Git → Argo CD sync**, with nothing to move
between stages:

| Bucket | Examples | Why not Kargo |
|---|---|---|
| **① Third-party / off-the-shelf** (the majority) | Grafana, Vault, Harbor, Argo CD, Authentik, Prometheus, Loki, Nextcloud, Matrix, ERPNext & Plane charts | You don't build their image and there's no `dev` copy — *conditions 1 & 2 fail*. "Promote" = bump the chart/image version in `helm-values/`. |
| **② Platform infra** | cert-manager, ESO, Cilium, Longhorn, KEDA, Tempo, cloudflared | Cluster plumbing, single instance, no application lifecycle — *condition 2 fails*. |
| **③ Your custom images, but single-environment** | minicloud-backstage, minicloud-open-webui, minicloud-onlyoffice, minicloud-erpnext, ktayl-solution-web | You *do* build them (✓ condition 1) but there's **one prod instance**, no `dev→prod` — *condition 2 fails*. They're tools deployed once; update = bump the tag → Argo CD deploys. |

**The mental test:** *"Do I have a `dev` **and** a `prod` running the same artifact I
build, and do I want to move a validated version from one to the other?"*
**Yes → Kargo** (the 6). **No** (third-party / single instance / infra) **→ just Argo CD
+ Helm version-pinning.**

:::note Why 91 ≠ 91 candidates
One Kargo service is itself **~3 Argo CD Applications** (`<svc>-dev` + `<svc>-prod` +
`kargo-<svc>`). The 91 count also includes every separate dev/prod app, all third-party
apps and all infra. **91 apps is not 91 promotion candidates** — the vast majority
self-update by a Git version bump, not a multi-stage promotion.
:::

## Which services are wired (all 6 custom services — fully on Option 2)

**All 6 are cut over to the target model** (below): Kargo is the sole dev promoter (auto-promotion),
Kargo owns the dev→prod verification gate, and each CI is build-only. The dev **smoke variant**
depends on the service's dev topology (see the variants table further down).

| Service | Warehouse | Smoke variant | Notes |
|---|---|---|---|
| platform-demo | image (public ghcr) | **A** — KEDA interceptor + netpol | reference; full canary promo demonstrated |
| ktayl-policy-service | image (Internal ghcr + cred) | **B** — via ingress-nginx | ghcr/SHA; own prod Postgres |
| minicloud-agent / -crew | image (Internal ghcr + cred) | **C** — dev Service cross-ns | internal, no ingress |
| minicloud-plane | image (Internal ghcr + cred) | **D** — cron scale-aware | pauses the KEDA cron scaler, smokes, resumes |
| **retrieva** | **git** (2 images) | **C** — both dev Services cross-ns | runtime-config frontend; builds on `main` only; smoke verifies both images |

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

## Auto-promotion & Kargo-owned dev verification (the live model on all 6 services)

This is the model **now live on all 6 custom services** (piloted on platform-demo, then rolled out).
It makes Kargo the **sole promoter of dev** and moves **dev verification off the CI** into Kargo.
(The earlier "safe posture" — manual promotions — is superseded for these services; only prod
promotion stays manual, behind the CODEOWNERS PR gate.) Rationale: once Kargo owns promotion, having CI drive the dev deploy and
then smoke it *synchronously in the same run* is a **sync-over-async anti-pattern**. CI should
only **build & prove the artifact**; *"what qualifies a Freight for prod?"* → *"it was verified
in dev"*, and that verification belongs to the deploy orchestrator.

Three pieces in `services/<svc>/kargo/`:

1. **`ProjectConfig`** — `spec.promotionPolicies: [{stage: dev, autoPromotionEnabled: true}]`.
   New Freight is auto-promoted to the dev Stage (which subscribes to the Warehouse). Prod is
   omitted → stays manual (the CODEOWNERS PR gate).
2. **Stage `dev.spec.verification.analysisTemplates`** — references an AnalysisTemplate. After
   promoting to dev, Kargo runs it as an `AnalysisRun`; the Freight becomes `verifiedIn:[dev]`
   **only if it passes**. The prod Stage (`sources.stages: [dev]`) accepts **only verified
   Freight** — that is the dev→prod gate.
3. **`AnalysisTemplate`** — a `job`-provider **smoke** (curl the app's health endpoint). A failed
   verification does **not** roll back dev (promotion already happened); it just blocks
   prod-promotability. Prod still has its canary Rollout metric brake.

The CI then loses `bump-gitops`/`smoke`/`canary` and builds **main-only**.

```
git push main → CI (build+sign+SBOM only) → ghcr:<sha>
   → Warehouse → Freight → auto-promote dev (PR, auto-merged) → Argo CD sync
   → Kargo verification (smoke AnalysisRun) → Freight verifiedIn:[dev] → promotable to prod
```

### The smoke must reach a real, deployed app — the variant depends on dev topology

The probe is **service-specific** — this is the main thing a rollout must get right, and the
biggest lesson of the rollout: *the "same recipe" doesn't exist; each service's dev topology
decides how the smoke reaches it.* All variants use a Gatekeeper-compliant pod (`runAsNonRoot`,
`allowPrivilegeEscalation: false`, drop all caps, resource limits, seccomp `RuntimeDefault`) and a
**fully-qualified image** (`docker.io/curlimages/curl:…` — a bare name is denied by the
allowed-registries policy).

| Variant | Dev topology | How the smoke reaches the app | Extra infra |
|---|---|---|---|
| **A** | **HTTP scale-to-zero (KEDA) + SSO** — platform-demo | curl the **KEDA interceptor directly** (`…interceptor-proxy.keda.svc:8080` + `Host: <dev-host>`) → wakes dev 0→1 **and** bypasses the ingress SSO (you test the app, not the identity chain) | one label-scoped `NetworkPolicy` in the `keda` ns allowing `kargo.akuity.io/project=true` namespaces → interceptor:8080 (covers all Kargo services) |
| **B** | **always-on + ingress, no SSO** — ktayl | curl the app **via ingress-nginx** (`--connect-to <dev-host>:443:<nginx-svc>:443` for correct SNI, `-k`) | **none** — ingress-nginx accepts from all namespaces and the dev ns already allows ingress-nginx |
| **C** | **always-on, internal (no ingress)** — agent, crew | curl the **dev Service directly cross-namespace** (`http://<svc>.<svc>-dev.svc:<port>/health`) from the Kargo project ns | a label-scoped `allow-kargo-verification` `NetworkPolicy` **in each dev ns** allowing ingress from `kargo.akuity.io/project=true` → the app port |
| **D** | **cron scale-to-zero (KEDA), internal** — plane | **scale-aware**: the Job pauses the KEDA ScaledObject at 1 replica (`autoscaling.keda.sh/paused-replicas`), waits for Ready, smokes cross-ns, then removes the annotation so cron control resumes | the Variant-C netpol **+** a ServiceAccount/Role (patch scaledobjects, get rollouts/pods in the dev ns) bound to the AnalysisRun Job |

An **HTTP** scale-to-zero app (Variant A) wakes on the probe itself; a **cron** scale-to-zero app
(Variant D) does **not** — it's up only on a schedule, so an on-demand smoke must *make* it up
first, then hand control back. Don't confuse the two KEDA modes.

**Rollout checklist per service:** confirm its dev topology (autoscaler kind? ingress? SSO?) →
pick the variant → add `projectconfig.yaml` + `analysis-dev-smoke.yaml` (+ any variant netpol/RBAC)
+ Stage `verification` → **prove live** (create an AnalysisRun from the deployed template →
`Successful`) → only then strip the CI (remove the dev bump-gitops, `push` on `main` only). Prove
*before* stripping so dev keeps being fed if anything is wrong.

## Gotchas worth knowing

- **Mixed Freight** (multi-image, one unchanged) → use a **git Warehouse** (above).
- **No-delta promotion** (overlay already at the Freight SHA) → the Stage `if`-gates the
  PR steps on `commit != clone HEAD` so it succeeds without opening an empty PR.
- **All-numeric image tag** (a git short-SHA that is all digits, e.g. `4846055` — ~3.7% of
  them) → Kargo coerces the expression result to a **number**, so `kustomize-set-image` rejects
  it (`images.0.tag: Invalid type`) and the promotion **Errors**. Wrap the tag expression in
  **`quote()`**: `tag: '${{ quote(imageFrom(...).Tag) }}'`. Diagnose an Errored promotion via
  `kubectl get promotion <name> -o json` → `.status.stepExecutionMetadata[]` (the first *failed*
  step is the real cause; downstream `cannot fetch commit from <nil>` guard errors are secondary).
- **Unsigned Kargo commits** vs `main`'s verified-signatures rule → **squash-merge** Kargo
  PRs (GitHub signs the squash commit); the dev auto-merge workflow already uses `--squash`.
- **Gatekeeper** requires container `securityContext` (runAsNonRoot, no-priv-esc) + resource
  limits — set them in Helm values / manifests or the Deployment is denied.
- **Env-baked images** (or mutable `:latest` prod) can't be promoted — fix first.

## SemVer alias (dual-tagging) — SHA for machines, SemVer for humans

The **git SHA is the canonical promotion identifier**: Warehouses watch SHA tags, Freight = a
commit, prod overlays pin the SHA. That is correct for continuous promotion — every commit is
immutable, exactly traceable, and promotable with no release step. The trade-off is readability:
`4846055` doesn't tell an operator *what* is in prod or whether prod is behind dev.

**Dual-tagging** adds the human layer without touching the machine layer. When **release-please**
cuts a release, the `release.yml` `dual-tag-semver` job uses `crane` to add the SemVer alias
(`vX.Y.Z`) to the **same ghcr digest** that ci.yml already built for that commit — no rebuild, the
SHA tag stays. One digest then carries both `<sha>` (what Kargo promotes) and `vX.Y.Z` (what a
changelog / audit / on-call dashboard reads). The deploy pipeline keeps manipulating the SHA; only
humans read the SemVer.

- This is **not** SemVer-as-promotion-key: forcing a SemVer per commit would either bump patches
  artificially on every merge or block auto-promotion waiting for a tag — friction the SHA avoids.
- **Never back-fill** an old digest with a version it wasn't released as (false mapping) — the alias
  only goes forward, on the fresh image a release builds.
- **Wired on all 5 release-please services** (platform-demo, ktayl-policy-service, minicloud-plane,
  minicloud-agent, minicloud-crew-agent) in each `.github/workflows/release.yml`; the job is skipped
  when `release_created=false`. **Verified live on platform-demo**: cutting `v0.1.2` added the
  `v0.1.2` tag to the **same digest** as the release commit's SHA image (`sha256:59ff60…`) — one
  digest, two tags, no rebuild. (retrieva has no release-please → no SemVer source → not applicable;
  a multi-image service would alias each image.)

## Two environments only

Kargo's arrival removed **staging** platform-wide (overlays, `_staging-optional`,
`environments.yaml`, the CI `promote-staging` job). Standard = **`dev` + `prod`**.

- **UI:** [kargo.10.0.0.200.nip.io](https://kargo.10.0.0.200.nip.io) (Tailscale + minicloud CA)
- **Install:** `apps/platform/kargo.yaml` (Helm) + `apps/platform/kargo-projects.yaml` (ApplicationSet) + `apps/platform/kargo-retrieva.yaml` (dedicated).
