---
id: new-business-service
title: Deploy a new business service — zero → prod
sidebar_position: 2
---

# Deploy a new business service — from zero to production

:::note Who this is for
A developer building a **new business (IS) service** — an insurance domain app — who does **not** yet
know the platform deeply. Follow the steps in order; each links the authoritative detail. The golden
rule: **you almost never hand-write the plumbing — you copy a reference service in the same stack and
change the names.** This page is the on-ramp; [End-to-End Delivery Workflow](/platform/developer-platform/delivery-workflow)
is the deeper runbook for *promoting* an artifact once the service exists.
:::

:::tip New to GitOps / Kubernetes? Read these two first (20 min), then come back
This page assumes the vocabulary below. If any term is new, skim
[Application Delivery Overview](/platform/app-deployment/deploy-overview) and
[the Helm wrapper chart](/platform/app-deployment/helm-chart) first — they explain *why* the pieces exist.
:::

### Mini-glossary (the words this page uses)

| Term | In one line |
|---|---|
| **GitOps** | The cluster's desired state is **Git**; a controller makes the cluster match Git. You never `kubectl apply` by hand. |
| **ArgoCD** | The controller that reads Git and **reconciles** the cluster to match it. |
| **ArgoCD `Application`** | A small YAML that says "deploy *this* chart from *this* Git path into *this* namespace." |
| **AppProject** | ArgoCD's allow-list of which namespaces/repos Applications may touch. |
| **Helm chart** | A templated package of Kubernetes YAML. |
| **wrapper chart / library chart** | Your thin chart (`wrapper`) `depends on` a shared `minicloud-app-deployment` chart (`library`) that renders the common workload; your chart adds the service-specific extras. |
| **Kargo** | Promotes one built image **dev → prod** by opening Git PRs (it never touches the cluster). |
| **Freight / Warehouse** | Kargo's unit of "a thing to promote" (`Freight`) and the thing that detects new images/commits (`Warehouse`). |
| **ESO / ExternalSecret** | External-Secrets Operator: a CR that pulls a secret from **Vault** and renders it as a Kubernetes `Secret`. |
| **CNPG** | CloudNativePG — runs Postgres as a managed, backed-up cluster. |
| **netpol** | `NetworkPolicy` — a firewall rule for pods. The platform is **default-deny**; you allow only what you need. |
| **SSA** | ArgoCD Server-Side-Apply (how it writes objects). Relevant only for the ESO quirk in Step 4. |
| **CODEOWNERS** | Ownership map that records owners and can suggest reviewers for sensitive paths. |

## The model in one sentence

Two repositories: **your app repo** builds + proves the image; **`minicloud-gitops`** declares *how and
where* it runs. CI builds the image, **Kargo** promotes it `dev → prod`, **ArgoCD** reconciles Git to the
cluster. You will touch **both** repos — the app code in yours, the deployment config in `minicloud-gitops`.

```text
your-repo (code)                    minicloud-gitops (deployment)
  push → CI builds+signs image  ─────►  services/<svc>/helm  (wrapper chart = how it runs)
                                        services/<svc>/kargo  (dev→prod promotion)
                                        apps/is/<group>/<svc>-{dev,prod}.yaml  (ArgoCD Applications)
```

> **Naming convention used throughout** — pick a short domain name, e.g. `billing`. Your repo is then
> `ktayl-billing`, your namespace is `billing`, your hosts are `billing.10.0.0.200.nip.io`. Because the
> whole stack follows this pattern, **a single find-replace of the reference's name does almost all the
> renaming** (Step 3).

## Prerequisites (access) — do these once

You cannot deploy or verify without platform access. Get these first (see
[Onboarding a colleague](/platform/remote-access/onboarding-a-colleague)):

- **Tailscale** on your machine + the **minicloud CA** trusted (so `*.10.0.0.200.nip.io` + Harbor resolve).
- **kubectl** with the `minicloud-oidc` context (daily use) — login via Authentik. Confirm it works:
  `kubectl --context minicloud get ns` returns the namespace list.
- **`gh`** (GitHub CLI) authenticated; **`helm`** installed.
- Your **app repo created `public`** in the `andrelair-platform` org. *(This matters: the 7 org-level CI
  secrets reach **public** repos only — a private repo's CI silently no-ops with empty tokens. Make it public.)*

## Step 0 — pick your stack, then clone a reference service

**Do not start from an empty repo.** Choose the stack that fits the work (numeric/actuarial → Python,
heavy transactional → Java, high-throughput/glue → Go, one-language-full-stack → NestJS), then **clone the
closest reference** that already has every platform wire done, and reuse its structure:

| Your stack | Reference service (clone its shape) |
|---|---|
| **Python / FastAPI** | [`ktayl-underwriting`](https://github.com/andrelair-platform/ktayl-underwriting) (backend + a Next.js workbench — dual-workload) |
| **Go** | [`ktayl-policy-service`](https://github.com/andrelair-platform/ktayl-policy-service) |
| **Java / Spring** | [`ktayl-core`](https://github.com/andrelair-platform/ktayl-core) |
| **Express / NestJS (TS)** | [`retrieva-backend`](https://github.com/andrelair-platform/retrieva-backend) |

Create your repo and seed it from the reference (you want its *structure*, not its git history):

```bash
# example: a new Python/FastAPI service called "billing"
gh repo create andrelair-platform/ktayl-billing --public
git clone https://github.com/andrelair-platform/ktayl-underwriting ktayl-billing-seed
cd ktayl-billing-seed && rm -rf .git          # drop the reference's history
# rename the reference's name everywhere in the CODE repo, then push to your new repo:
grep -rl 'underwriting' . | xargs sed -i '' 's/underwriting/billing/g'   # macOS sed; Linux: sed -i '...'
git init && git add -A && git commit -m "chore: seed from ktayl-underwriting" && git branch -M main
git remote add origin https://github.com/andrelair-platform/ktayl-billing && git push -u origin main
```

The reference gives you: a working CI pipeline, the Dockerfile with the CA-trust pattern, the test layout,
release-please, and — most importantly — a **matching deployment folder in `minicloud-gitops`** you clone
the same way in Step 3.

## Step 1 — standardise the app repo

Bring the repo to the house standard **before** merging its first story (reference: `ktayl-policy-service`):

- Root files: `README.md` (with CI/CD + architecture sections), `LICENSE` (MIT), `CONTRIBUTING.md`.
- **GitHub About** — run the real commands (replace `<repo>`):
  ```bash
  gh api repos/andrelair-platform/<repo> --method PATCH \
    -f description="<one sentence, mentions the stack>" \
    -f homepage="https://andrelair-platform.github.io/<repo>/"
  gh api repos/andrelair-platform/<repo>/topics --method PUT \
    -f 'names[]=python' -f 'names[]=kubernetes' -f 'names[]=microservice' -f 'names[]=insurance'
  ```
- **release-please** — these **5 files** (copy them from the reference, change `package-name`):
  `.github/workflows/release.yml`, `release-please-config.json`, `.release-please-manifest.json`,
  `version.txt`, `CHANGELOG.md`.
- If the repo owns a relational schema: a committed `docs/data-model/` ERD baseline + the
  `schema-erd-drift` CI job → it then auto-appears on the [🧬 Schema diagrams index](/is/insurance-platform/schema-erd-autogenerated).
- Any ADR/design doc you write under `docs/` auto-appears on the
  [📜 Decision records index](/platform/engineering-standards/decision-records) — no manual pointer needed.

## Step 2 — the CI pipeline (build + prove the image)

Your `.github/workflows/` came with the clone in Step 0 (already renamed by the `sed`). What to know:

- **Secrets** are the 7 **org-level** secrets (inherited automatically by a *public* repo — you add nothing):
  `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `MINICLOUD_CA_CERT`, `HARBOR_USER`, `HARBOR_PASSWORD`,
  `GITOPS_TOKEN`, `GPG_PRIVATE_KEY`.
- **Dual-push:** `dev` branch → Harbor only; `main` → **both** Harbor (dev tag) **and**
  `ghcr.io/andrelair-platform/<repo>:<sha>` (prod), with keyless **cosign** signature + **SBOM** on the
  ghcr image.
- **CA-in-image:** never commit the CA — inject it at build time (`ARG CA_CERT` + `--build-arg`). The
  `MINICLOUD_CA_CERT` secret is **raw PEM — never `base64 -d` it**.
- **Trap:** a stale **repo-level** `HARBOR_*` secret shadows the org one → 401 at `docker login`. If build
  fails at registry login, check both `gh secret list --repo` and `--org`.
- **Tests must match the repo tier** ([testing strategy](/platform/engineering-standards/testing-strategy)):
  a Tier-A business service is **not** done on L0+L1 — it needs L2 (real DB), L3 (contract against the
  collaborator's real API), L4 (smoke). Unit-with-mocks that are never backed by a contract test are
  untested, not tested.

## Step 3 — the deployment: a wrapper Helm chart in `minicloud-gitops`

This is where deployment lives — **not** in your app repo. Clone `minicloud-gitops`, copy the reference's
folder, and do the **same single find-replace**:

```bash
cd minicloud-gitops
cp -r services/ktayl-underwriting services/ktayl-billing
cp apps/is/insurance/ktayl-underwriting-dev.yaml  apps/is/insurance/ktayl-billing-dev.yaml
cp apps/is/insurance/ktayl-underwriting-prod.yaml apps/is/insurance/ktayl-billing-prod.yaml
# one rename does repo/image/releaseName/namespace/hosts/DB-secret/OIDC-secret (whole-word, safe):
grep -rl 'underwriting' services/ktayl-billing apps/is/insurance/ktayl-billing-*.yaml \
  | xargs sed -i '' 's/underwriting/billing/g'       # macOS sed; Linux: sed -i '...'
rm -rf services/ktayl-billing/helm/charts            # let helm re-fetch the library dep
```

The **real** shape you just copied (from `ktayl-underwriting`):

```text
services/ktayl-billing/helm/
  Chart.yaml        # dependencies: minicloud-app-deployment (the shared library chart, OCI)
  Chart.lock        # COMMIT it (ArgoCD runs `helm dependency build`)
  .helmignore       # must NOT list charts/  (charts/ is gitignored instead)
  values.yaml       # common: `minicloud-app-deployment: {…}` (the workload) + wrapper-local keys
  values-dev.yaml   # dev overlay (image.tag, hosts, replicas:1)
  values-prod.yaml  # prod overlay (image.tag, replicas:2–3, prod-only gates)
  templates/        # service-specific EXTRAS, rendered alongside the library workload:
    postgres.yaml            # the dedicated CNPG Postgres cluster
    network-policies.yaml    # DB-namespace NetworkPolicies
    certificate.yaml         # TLS cert (ClusterIssuer minicloud-ca)
    externalsecret-*.yaml    # ESO ExternalSecrets (ghcr pull, OIDC creds)
```

Non-negotiables (each has bitten someone — see [Enterprise GitOps controls](/platform/app-deployment/enterprise-gitops-controls)):

- **`helm.releaseName` is mandatory** = your service name (else the library objects take the ArgoCD *app*
  name). The `sed` already set it.
- **The image tag MUST be block-style YAML** in `values-dev.yaml` and `values-prod.yaml` — `image:` then
  an indented `tag: "<sha>"`. **Never** flow style `image: { tag: … }` — Kargo's promotion mutator can't
  parse it and every promotion errors. (The whole-word `sed` above doesn't touch tag structure — safe.)
- **`charts/` is gitignored, `Chart.lock` is committed.**

Render it locally before committing (this both fetches the library dep and proves the YAML is valid):

```bash
cd services/ktayl-billing/helm
helm registry login ghcr.io -u <your-gh-user>   # only if `dependency update` says "unauthorized"
helm dependency update .
helm template ktayl-billing . -f values-dev.yaml | head -40   # eyeball: no errors, names are yours
```

## Step 4 — the ArgoCD Applications (dev + prod)

The two Applications are the files you copied in Step 3 (`apps/is/insurance/ktayl-billing-{dev,prod}.yaml`).
Business services live under `apps/is/…`, not `apps/platform/…`. The **real** dev source block:

```yaml
spec:
  project: minicloud-platform
  source:
    repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    path: services/ktayl-billing/helm
    helm:
      releaseName: ktayl-billing               # MANDATORY (set by the sed)
      valueFiles: [values-dev.yaml]            # the prod file uses values-prod.yaml
  destination: { namespace: billing }          # prod file uses: billing-prod
  # If the chart has an ExternalSecret, KEEP this block (it came with the copy):
  ignoreDifferences:                            # ESO injects 4 defaults at admission (never in Git)…
    - group: external-secrets.io
      kind: ExternalSecret
      jqPathExpressions:
        - .spec.data[].remoteRef.conversionStrategy
        - .spec.data[].remoteRef.decodingStrategy
        - .spec.data[].remoteRef.metadataPolicy
        - .spec.target.deletionPolicy
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: [CreateNamespace=true, ServerSideApply=true, RespectIgnoreDifferences=true]
```

The **prod** file (`…-prod.yaml`) is identical except `name: ktayl-billing-prod`, `valueFiles:
[values-prod.yaml]`, and `namespace: billing-prod`.

**Register your namespaces** in the AppProject allow-list —
`minicloud-gitops/platform/delivery/argocd-project/00-project.yaml`, under `spec.destinations`, add (keep
it alphabetical):

```yaml
    - namespace: billing
      server: https://kubernetes.default.svc
    - namespace: billing-prod
      server: https://kubernetes.default.svc
```

The root app-of-apps discovers the Application wherever it sits under `apps/`, so the folder is pure taxonomy.

## Step 5 — Kargo promotion (dev → prod gate)

`services/ktayl-billing/kargo/` came with the Step-3 copy. Kargo watches your prod ghcr image and **opens
the Git PRs** ArgoCD then reconciles — it never touches the cluster, so the protected-PR prod gate stays
intact. Two models, **pick correctly** — this is the one place to think, not copy blindly:

- **image model** (`NewestBuild`) — only if the image's build timestamp is **monotonic per build**. A plain
  **Go or Python** single image is fine here.
- **git model** (Freight = a commit) — **required** for multi-image services (e.g. backend + frontend) *and*
  for **Java/temurin or reproducible-build images** (their timestamps tie → `NewestBuild` silently stalls).

Rule of thumb: **Python/Go single image → image model; Java/Spring or multi-workload → git model.** The
reference you cloned already uses the right one for *its* stack — if your stack differs, switch per
[Kargo promotion](/platform/developer-platform/kargo-promotion). Mechanics (promote, roll back, approve the
prod PR with `--squash`) are in the [End-to-End Delivery Workflow](/platform/developer-platform/delivery-workflow).

## Step 6 — secrets, networking, SSO

- **Secrets** never go in Git. They live in **Vault** and reach the pod via an **ESO ExternalSecret**
  (you copied `externalsecret-*.yaml`). ⚠️ **Writing a new secret into Vault `secret/platform/*` needs the
  break-glass root token — that is the owner's step, not self-serve.** Give the owner the list of keys your
  ExternalSecret references (DB creds are auto-created by CNPG; you typically only need OIDC creds + any
  third-party API keys). Coordinate this *before* you expect the pod to start.
- **NetworkPolicy** is **default-deny** — a pod can reach *nothing* until you allow it. The `network-policies.yaml`
  you copied already allows the usual set; adjust the egress allows to what *your* app actually calls:
  | Allow | Why |
  |---|---|
  | DNS (`kube-dns`/CoreDNS :53) | every app resolves names |
  | your CNPG Postgres (same ns, :5432) | the app's database |
  | ingress-nginx (ingress) | so users can reach you |
  | Authentik (egress :80/443) | OIDC / JWKS validation if SSO-gated |
  | LiteLLM / Qdrant (egress) | **only if** it calls the AI gateway / vector DB |
  | NATS (egress :4222) | **only if** it publishes/consumes events |

  Delete the allows you don't use; add none you don't need.
- **SSO:** a user-facing app is gated by **Authentik** (OIDC natively, or forward-auth) and bound to the
  right **group** — never "any authenticated user". See [SSO with Authentik](/platform/security-enterprise/sso-authentik)
  for how to create the OIDC provider + group; the reference's `externalsecret-oidc.yaml` shows the creds wiring.

## Step 7 — the QA gate (MANDATORY before prod)

Green CI is **not** enough to promote. After the service is live on **dev**, run an **adversarial QA pass
against the running dev deployment**, covering: auth (is the API actually authenticated?), input validation
(bad input → 4xx, never 5xx), state guards, idempotency, money/units, and observability (does it actually
emit logs in the pod?). **Blockers gate the prod PR.** This catches integration/deploy/runtime/config bugs
that mocked CI structurally cannot. The full scope + severities are in the
[testing strategy](/platform/engineering-standards/testing-strategy); the `ktayl-underwriting` story is the
worked reference (48 checks + a severity report).

## Verify it's actually live (do this after dev sync)

Don't guess — check these three, in order:

```bash
# 1) ArgoCD thinks it's deployed (the authoritative signal): both should say Synced / Healthy
kubectl --context minicloud get application ktayl-billing-dev -n argocd \
  -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status
#   …or open the UI: https://argocd.10.0.0.200.nip.io  → app ktayl-billing-dev

# 2) the pods are actually Running (not Pending/CrashLoop/ImagePull):
kubectl --context minicloud get pods -n billing

# 3) the app answers: port-forward past the SSO ingress and hit its health endpoint
kubectl --context minicloud -n billing port-forward svc/ktayl-billing 8080:80 &
/usr/bin/curl -s http://localhost:8080/health ; kill %1
#   (or, if dev isn't SSO-gated, curl the ingress directly:)
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://billing.10.0.0.200.nip.io
```

Green on all three = it's live on dev → run the QA gate → promote.

## Troubleshooting — the three first-deploy failures

| Symptom (`kubectl get pods`) | Most likely cause | What to do |
|---|---|---|
| **`ImagePullBackOff`** | image name/tag in `values-*.yaml` wrong, or (Internal ghcr) the `ghcr-pull` ExternalSecret hasn't synced | `kubectl describe pod …` → read the pull error; check the image repo path matches what CI pushed; confirm the `ghcr-pull` Secret exists in the ns |
| **`CrashLoopBackOff`** | the app's *own* startup — missing env, DB not reachable, a failing boot migration | `kubectl logs <pod> -n billing --previous` → read the stack trace; usually a wrong DB secret/host or an env the ExternalSecret didn't provide yet |
| app stuck **`OutOfSync`** in ArgoCD (pods Healthy) | the ESO `ignoreDifferences` block / `RespectIgnoreDifferences` is missing, **or** you *added keys to an existing* ExternalSecret (SSA no-ops) | confirm the block in Step 4 is present; if you edited an existing ES, **delete the ExternalSecret** so ESO re-renders it fresh |
| pods **`Pending`** / `FailedScheduling` | the namespace `ResourceQuota` is too small, or node capacity | `kubectl describe pod …` → read the reason; lower requests or raise the quota (`manifests/quotas/`) |

## You're done when

- [ ] App repo standardised (README/LICENSE/CONTRIBUTING, About via `gh api`, the 5 release-please files).
- [ ] CI green on `main`: image dual-pushed (Harbor + ghcr `:sha`), cosign-signed, SBOM.
- [ ] Tier-A tests actually run L0–L4 (not unit-only).
- [ ] `services/<svc>/helm` renders locally; tag is block-style; `Chart.lock` committed.
- [ ] Two ArgoCD apps (`…-dev`, `…-prod`) under `apps/is/<group>/`; **namespaces added to the AppProject**.
- [ ] `services/<svc>/kargo` with the **correct** Warehouse model.
- [ ] Secrets in Vault→ESO (owner did the Vault write); default-deny netpol trimmed to real allows; SSO-gated if user-facing.
- [ ] **Verified live on dev** (ArgoCD Synced/Healthy + pods Running + health 200) → **QA gate clean** →
      Kargo dev-verified Freight → **protected production PR** (maintainer merge after checks).
- [ ] As-built doc updated (this is a Definition-of-Done gate, not a follow-up).

## What still needs a human / deeper knowledge (be honest)

- **The Vault secret write** (`secret/platform/*`) needs the break-glass **root** token → the **owner**
  does it. Coordinate before you deploy.
- **The prod PR** uses the protected `main` ruleset. The solo maintainer reviews and merges after required checks pass; this is self-review and release confirmation, not an independent human approval. No `--admin` is used in the normal path.
- **There is no non-Go scaffolder yet** — Backstage's one-click golden path is Go-only, so for Python/Java/TS
  you clone a reference repo (Step 0) rather than generate one. (Tracked improvement.)
- **The Kargo model choice** (Step 5) genuinely requires understanding your image's build-timestamp
  behaviour — the one step where copying blindly can stall promotion.

## Related

- [Application Delivery Overview](/platform/app-deployment/deploy-overview) · [End-to-End Delivery Workflow](/platform/developer-platform/delivery-workflow)
- [Helm wrapper chart](/platform/app-deployment/helm-chart) · [Enterprise GitOps controls](/platform/app-deployment/enterprise-gitops-controls) · [Kargo promotion](/platform/developer-platform/kargo-promotion)
- [Per-environment isolation](/platform/app-deployment/per-env-isolation) · [Testing strategy](/platform/engineering-standards/testing-strategy) · [SSO with Authentik](/platform/security-enterprise/sso-authentik)
- [Schema ERD index](/is/insurance-platform/schema-erd-autogenerated) · [Decision records](/platform/engineering-standards/decision-records)
