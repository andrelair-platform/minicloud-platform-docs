---
id: phase-13-cicd
title: Phase 13 — CI/CD Pipeline (GitHub Actions + ghcr + ArgoCD)
sidebar_position: 8
---

# Phase 13 — CI/CD pipeline

Phase 12 gave us continuous delivery (ArgoCD reconciles the cluster against
git). Phase 13 adds the upstream half: **continuous integration that
produces images and updates git**, closing the loop end-to-end.

The deliverable of this phase is **the pipeline**, not a particular tool.
The pipeline is:

```text
push to andrelair-platform/platform-demo
    │
    ▼
GitHub Actions
    │  go test ./...
    │  buildx → push to ghcr.io/andrelair-platform/platform-demo:<git-sha>
    │  GitHub Contents API → bump image tag in
    │     andrelair-platform/minicloud-gitops/manifests/platform-demo/00-deployment.yaml
    ▼
ArgoCD (Phase 12)
    │  detects gitops change within ~3 min
    │  reconciles: pulls new image from ghcr.io (with imagePullSecret)
    │  rolling restart
    ▼
http://platform-demo.10.0.0.200.nip.io/ returns the new git SHA
```

End-to-end demo verified: a code change pushed to `main` shows up in the
live `/version` response **within ~3 minutes**.

---

## Why GitHub Actions, not GitLab or Gitea

The original 22-phase plan called for installing **GitLab** as a self-hosted
Git+CI host. We **deliberately deferred that** for two reasons:

1. **GitHub already exists and works.** The `andrelair-platform` org hosts
   five repos (docs, ansible, opentofu, gitops, platform-demo). GitHub
   Actions runs free CI on public repos. Adding a second Git host adds
   sync burden and provides nothing GitHub doesn't already do better.
2. **GitLab CE costs ~6 GiB RAM + 30 GiB disk on a 48 GiB cluster.** That's
   real headroom for upcoming phases (Vault, Authentik SSO, data layer).

The senior architectural call: *self-host services that benefit from being
on-prem (registry, monitoring, identity), use SaaS for services where
managed alternatives are mature and free.* Phase 7 already proved we can
self-host a registry (Harbor) — we don't need to also self-host the Git
host.

The portfolio story is **stronger** with this deliberate choice than with
"installed GitLab because the original plan said so."

If a future phase legitimately needs on-prem Git (e.g., a regulated industry
demo where code can't leave premises), revisit then.

---

## Why ghcr.io, not Harbor

Phase 7's documentation already covered this: kubelet can't pull from
`harbor.10.0.0.200.nip.io` due to a known k3s `/v2`-suffix mirror URL
issue. The fix arrives in Phase 15 with TLS. Until then, ArgoCD-deployed
pods need an image source the cluster *can* pull from — which means
public-facing registries.

`ghcr.io` is the natural fit when source code lives in a GitHub org:

* Image namespace mirrors the repo namespace (`ghcr.io/andrelair-platform/platform-demo`)
* The default workflow `GITHUB_TOKEN` can push to ghcr.io for the same
  repo's package — no additional credentials needed for image push
* Free, unlimited public images
* Once Phase 15 unblocks Harbor, we can either continue with ghcr.io or
  configure Harbor as a proxy cache for ghcr.io. Either way, no rework here.

---

## What this phase ships

| Component | Source | Deployed to |
|---|---|---|
| **`platform-demo` Go service** | New repo `andrelair-platform/platform-demo` | `gitops-demo` namespace, hostname `platform-demo.10.0.0.200.nip.io` |
| **CI workflow** | `.github/workflows/ci.yml` in platform-demo repo | runs on every push to `main` |
| **Image** | Built from `Containerfile` (multi-stage, distroless static) | `ghcr.io/andrelair-platform/platform-demo:<sha>` |
| **Bootstrap manifests** | `manifests/platform-demo/` in `minicloud-gitops` | bootstrap with `ghcr.io/stefanprodan/podinfo:6.11.2` until first CI run replaces it |
| **Pull credentials** | `kubernetes.io/dockerconfigjson` Secret named `ghcr-pull` in `gitops-demo` ns | created out-of-band; never lives in git |

---

## The Go service

`main.go` exposes:

| Path | Returns |
|---|---|
| `/`         | JSON: `{app, version, commit, hostname, goVersion, now, message}` |
| `/healthz`  | `200 ok` (liveness) |
| `/readyz`   | `200 ready` (readiness) |

`version` and `commit` are baked in at build time via `-ldflags`:

```go
var (
    version = "dev"
    commit  = "unknown"
)
```

```dockerfile
RUN go build -trimpath \
      -ldflags "-s -w -X main.version=${VERSION} -X main.commit=${COMMIT}" \
      -o /out/platform-demo .
```

The CI workflow passes `${{ steps.meta.outputs.version }}` (short SHA) and
`${{ steps.meta.outputs.commit }}` (full SHA) as build args — so the
deployed pod's `/` response contains the exact git SHA that produced its
image. Instant proof that the pipeline closed.

---

## The CI workflow (`.github/workflows/ci.yml`)

Three jobs, each gating the next:

### `test` — runs on every push and PR

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-go@v5
  with: { go-version: '1.23' }
- run: go test -v ./...
```

### `build-and-push` — runs only on main, after `test` passes

```yaml
needs: test
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
permissions:
  packages: write    # ghcr push via the workflow's built-in GITHUB_TOKEN

steps:
  - uses: actions/checkout@v4
  - uses: docker/setup-buildx-action@v3
  - uses: docker/login-action@v3
    with:
      registry: ghcr.io
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}
  - uses: docker/build-push-action@v6
    with:
      tags: |
        ghcr.io/${{ github.repository }}:${{ steps.meta.outputs.image_tag }}
        ghcr.io/${{ github.repository }}:latest
      build-args: |
        VERSION=${{ steps.meta.outputs.version }}
        COMMIT=${{ steps.meta.outputs.commit }}
      cache-from: type=gha
      cache-to:   type=gha,mode=max
```

### `bump-gitops` — runs after `build-and-push`

This is the cross-repo write — bumps the image tag in `minicloud-gitops`
via the GitHub Contents API:

```yaml
needs: build-and-push
env:
  NEW_IMAGE: ghcr.io/${{ github.repository }}:${{ needs.build-and-push.outputs.image_tag }}
steps:
  - name: Update file via GitHub Contents API
    env:
      GITOPS_TOKEN: ${{ secrets.GITOPS_TOKEN }}
    run: |
      API="https://api.github.com/repos/${GITOPS_REPO}/contents/${GITOPS_PATH}"
      ACCEPT="Accept: application/vnd.github+json"

      # GET current file (need its sha for the update)
      curl --no-netrc -s -H "Authorization: Bearer ${GITOPS_TOKEN}" -H "$ACCEPT" \
        "$API?ref=main" -o /tmp/current.json
      OLD_SHA=$(jq -r .sha /tmp/current.json)

      # Decode → yq edit → re-encode
      jq -r .content /tmp/current.json | base64 -d > /tmp/current.yaml
      yq -i '(.spec.template.spec.containers[] | select(.name == "platform-demo")).image = strenv(NEW_IMAGE)' \
        /tmp/current.yaml
      NEW_B64=$(base64 -w0 /tmp/current.yaml)

      # PUT new content
      jq -n --arg msg "ci(platform-demo): bump image to ${{ needs.build-and-push.outputs.image_tag }}" \
            --arg content "$NEW_B64" --arg sha "$OLD_SHA" --arg branch main \
            '{message:$msg, content:$content, sha:$sha, branch:$branch}' > /tmp/payload.json
      curl --no-netrc -sfX PUT -H "Authorization: Bearer ${GITOPS_TOKEN}" -H "$ACCEPT" \
        -d @/tmp/payload.json "$API"
```

Why the API instead of `git push`: the runner ships with a pre-configured
git credential helper (set up by `actions/checkout`'s previous step) that
intercepts `git push` and provides the workflow's `GITHUB_TOKEN` —
which doesn't have access to the gitops repo. The Contents API takes our
explicit `Authorization` header and does the right thing.

`--no-netrc` on curl forces it to ignore the runner's `~/.netrc`, which
also contains the workflow's GITHUB_TOKEN.

---

## Authentication setup (the painful part)

The `andrelair-platform` org has restrictive defaults that surfaced two
real production-grade problems:

### Problem 1 — Org policy blocks deploy keys, fine-grained PATs, and public ghcr packages

We tried the canonical secure choice first: **a deploy key on the
`minicloud-gitops` repo with write access**, used by the workflow to push
the gitops bump. The org's repository policy disabled deploy keys at the
org level; the toggle to re-enable couldn't be located in the GitHub UI
even by the org owner.

We pivoted to **fine-grained PAT** scoped to `Contents: Read+Write` on the
single gitops repo. Same result: every API call returned `401 Bad
credentials`, with no "pending approval" surface anywhere in the UI.

We finally landed on a **classic PAT with `repo` scope**. Classic PATs
route through different infrastructure that doesn't have the same policy
gating, and this one worked.

The `read:packages` PAT (for kubelet image pulls) is a **second classic
PAT** with the single `read:packages` scope. The image is private at
ghcr.io because the org policy also forbids public packages.

### Problem 2 — `gh secret set --body -` doesn't read stdin

This one was self-inflicted and cost ~30 minutes of debugging. The flag
form `--body -` sets the secret value to the literal string `"-"`. The
correct form is **omit the flag and pipe the value**:

```bash
# WRONG — sets secret value to "-"
echo -n "$TOKEN" | gh secret set GITOPS_TOKEN -R owner/repo --body -

# RIGHT — reads from stdin
printf '%s' "$TOKEN" | gh secret set GITOPS_TOKEN -R owner/repo
```

Detection signal: the workflow's `Token prefix=*** length=1` diagnostic
showed length 1 — every API call was authenticating with the password
`-`.

---

## imagePullSecret for the private ghcr package

Because public packages are blocked at the org level, kubelet has to
authenticate to pull. Standard production pattern:

```bash
kubectl create secret docker-registry ghcr-pull \
  --namespace gitops-demo \
  --docker-server=ghcr.io \
  --docker-username=AndreLiar \
  --docker-password="$READ_PACKAGES_PAT" \
  --docker-email=...
```

And in the Deployment manifest (`minicloud-gitops/manifests/platform-demo/00-deployment.yaml`):

```yaml
spec:
  template:
    spec:
      imagePullSecrets:
        - name: ghcr-pull
      containers:
        - name: platform-demo
          image: ghcr.io/andrelair-platform/platform-demo:<sha>
```

The Secret is created **out-of-band** via `kubectl` and never lives in git.
The Deployment manifest only references it by name. Phase 15 will replace
this with **External Secrets Operator + Vault dynamic credentials** —
eliminating the rotation burden entirely.

---

## End-to-end verification

A push to `main` of platform-demo with a tiny code change (added a
`message` field to the JSON response):

| Time | Event |
|---|---|
| t=0      | `git push` to platform-demo |
| t≈30s    | CI `test` job complete |
| t≈70s    | CI `build-and-push` complete (image at ghcr.io) |
| t≈85s    | CI `bump-gitops` complete (gitops repo updated) |
| t≈3min   | ArgoCD detects gitops change, kicks off rollout |
| t≈3min10s | New pod Running with new image |
| t≈3min20s | Live `/` endpoint returns the new SHA + new field |

Total: **~3 min from push to live**, fully automated.

```bash
$ curl -s http://platform-demo.10.0.0.200.nip.io/ | jq
{
  "app": "platform-demo",
  "version": "77b10fa",
  "commit": "77b10fa9cd12d563820e1230a4fdceccfb199718",
  "hostname": "platform-demo-78cff8c569-p57gk",
  "goVersion": "go1.23.12",
  "now": "2026-05-08T22:08:15Z",
  "message": "deployed end-to-end via GitHub Actions + ghcr.io + ArgoCD GitOps"
}
```

---

## Done When

```text
✔ andrelair-platform/platform-demo repo exists with Go source + Containerfile + workflow
✔ CI green: test → build-and-push → bump-gitops all pass on main
✔ ghcr.io/andrelair-platform/platform-demo:<sha> exists for the latest commit
✔ minicloud-gitops/manifests/platform-demo/00-deployment.yaml shows the latest sha
✔ ArgoCD Application platform-demo is Synced + Healthy
✔ http://platform-demo.10.0.0.200.nip.io/ returns JSON with the same sha
✔ A subsequent push results in a new sha live within ~5 minutes
✔ Homer has a platform-demo tile under Apps
```

---

## Real-world skills demonstrated

| Skill | Where it applies in industry |
|---|---|
| **GitOps image-promotion pattern** (CI writes to gitops repo) | The single most common production CI/CD shape. Real teams at every scale do this. |
| **Multi-stage Containerfile with distroless** | Same security baseline every modern container shop targets — minimal attack surface, no shell, no package manager, runs as non-root |
| **ldflags-injected build metadata** | Standard Go pattern; the same trick works in every language for "what version is deployed?" instrumentation |
| **GitHub Contents API as a fallback for cross-repo writes** | When `git push` is blocked by credential helper or auth policy, the API is the way out. Production CI hits this constantly. |
| **`imagePullSecrets` with private registry** | The default deployment pattern in 80% of enterprise k8s setups. Public registries are the exception, not the rule. |
| **`--no-netrc` to bypass runner credentials** | Saves debug hours when the runner's pre-configured auth fights your explicit auth |
| **Senior-grade scope decisions** | Choosing GitHub Actions over self-hosted GitLab; choosing ghcr.io over Harbor (until Phase 15 fixes it); choosing classic PATs after fine-grained ones hit org policy. Each is a real architectural judgment call. |
| **Documenting "why this is private right now"** | The deferral notes (GitLab, public packages, fine-grained PATs) keep the portfolio honest and signal to readers exactly which trade-offs were intentional |
