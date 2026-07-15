---
id: backstage-software-templates
title: Phase 70 — Backstage Software Templates (Golden Path)
sidebar_label: Phase 70 — Software Templates
---

# Phase 70 — Backstage Software Templates (Golden Path)

Every new service on the platform used to require the same manual work: create the GitHub repo, configure three branches, write the CI workflow from scratch, create Kustomize overlays in minicloud-gitops, open an ArgoCD Application, and register the component in Backstage. None of it was hard, but none of it was standardised either — each repo had slight differences in action versions, GPG setup, or Trivy config.

Phase 70 replaces all of that with a **Backstage Software Template** (the scaffolder plugin). A developer fills in a name and description in the Backstage UI, clicks "Create", and gets back a fully wired service.

---

## What the Golden Path Produces

One template run creates everything needed to ship:

| Artifact | Location | Notes |
|---|---|---|
| GitHub repo | `andrelair-platform/<name>` | `main`, `dev`, `staging` branches |
| CI workflow | `.github/workflows/ci.yml` | Canonical golden path — Tailscale OAuth, Trivy, Cosign, SBOM, crazy-max GPG |
| Go HTTP server | `main.go` + `Containerfile` | Distroless image, `/healthz` + `/readyz` endpoints |
| Kustomize base | `services/<name>/base/` in minicloud-gitops | Deployment + ServiceAccount + Service |
| Three overlays | `overlays/dev` / `staging` / `prod` | Different resource limits; prod adds Ingress + Certificate |
| ArgoCD Application | `apps/<name>-dev.yaml` in minicloud-gitops | Auto-sync on dev overlay |
| Backstage entity | `catalog-info.yaml` in the new repo | Component with `kubernetes-id` + `argocd/app-name` annotations |

---

## Architecture

```
Developer fills Backstage form
          │
          ▼
  Backstage Scaffolder
  (scaffolder plugin — already in the backend)
          │
          ├─ 1. fetch:template  ──► render service skeleton
          │                         (Containerfile, main.go, ci.yml, mkdocs.yml, catalog-info.yaml)
          │
          ├─ 2. fetch:template  ──► render gitops skeleton
          │                         (Kustomize base+overlays, ArgoCD app, VPA object)
          │
          ├─ 3. publish:github  ──► create repo + push to main
          │
          ├─ 4. github:branch:create × 2 ──► dev + staging branches
          │
          ├─ 5. publish:github:pull-request ──► PR on minicloud-gitops
          │                                     adds services/<name>/ + apps/<name>-dev.yaml
          │
          ├─ 6. vault:policy:create  ──► Vault policy + seed secrets + K8s auth role
          │                              (custom backend action, runs server-side)
          │
          └─ 7. catalog:register ──► auto-register in Backstage
```

The GitHub token (steps 3–5) is stored in Vault at `secret/platform/backstage` (key: `github-token`) and mounted as the `backstage-github-secret` Secret in the `backstage` namespace. The Vault provisioning token (step 6) is stored at `secret/platform/backstage` (key: `vault-scaffolder-token`) and mounted as `backstage-vault-secret`.

---

## Template Structure

All template files live in `minicloud-backstage`:

```
templates/go-service/
├── template.yaml                    ← Template entity (parameters + steps + output)
└── skeleton/
    ├── service/                     ← goes into the new GitHub repo
    │   ├── .github/workflows/ci.yml
    │   ├── Containerfile
    │   ├── main.go
    │   ├── go.mod
    │   └── catalog-info.yaml
    └── gitops/                      ← goes into minicloud-gitops via PR
        ├── apps/
        │   └── ${{ values.name }}-dev.yaml
        └── services/
            └── ${{ values.name }}/
                ├── base/
                │   ├── kustomization.yaml
                │   ├── deployment.yaml
                │   └── service.yaml
                └── overlays/
                    ├── dev/   (kustomization.yaml + patch-resources.yaml)
                    ├── staging/ (kustomization.yaml + patch-resources.yaml)
                    └── prod/  (kustomization.yaml + patch-resources.yaml
                                + ingress.yaml + certificate.yaml)
```

Directory names containing `${{ values.name }}` are Nunjucks-rendered at scaffold time — a skeleton path of `services/${{ values.name }}/base/` becomes `services/my-api/base/` in the output.

---

## Key Implementation Decision — Avoiding `${{ }}` Conflicts

The Backstage scaffolder uses Nunjucks with `${{ }}` as its template delimiter. GitHub Actions also uses `${{ }}`. A CI workflow skeleton file would be a mess of escaping if you tried to mix them.

The solution: the entire `ci.yml` skeleton is wrapped in a single Nunjucks `{% raw %}...{% endraw %}` block, and the service name is never injected via Nunjucks — instead the workflow uses `${{ github.event.repository.name }}` (a GitHub Actions context variable) to derive the image name at runtime:

```yaml
# skeleton/service/.github/workflows/ci.yml
{% raw %}
env:
  REGISTRY: harbor.10.0.0.200.nip.io
  IMAGE_NAME: library/${{ github.event.repository.name }}   ← GHA resolves this, not Nunjucks
{% endraw %}
```

The gitops overlay path is also derived from `github.event.repository.name` in the bump-gitops job:

```yaml
case "${{ needs.build-and-push.outputs.branch }}" in
  main)    echo "path=services/${{ github.event.repository.name }}/overlays/prod" >> $GITHUB_OUTPUT ;;
  staging) echo "path=services/${{ github.event.repository.name }}/overlays/staging" >> $GITHUB_OUTPUT ;;
  dev)     echo "path=services/${{ github.event.repository.name }}/overlays/dev"     >> $GITHUB_OUTPUT ;;
esac
```

This means `ci.yml` is 100% static — no Nunjucks substitutions needed inside it at all. Only `catalog-info.yaml`, `go.mod`, `main.go`, and the gitops manifests use Nunjucks `${{ values.* }}` substitution.

---

## Generated CI Workflow

The scaffolded `ci.yml` is the canonical golden path, identical in structure to all other minicloud repos:

```
push to dev/staging/main
         │
         ▼
  build-and-push job
    checkout → compute SHA → Tailscale OAuth → Trust CA
    → Login Harbor → Buildx → Build+Push (linux/amd64)
    → Trivy (CRITICAL, exit-code 1)
    → Cosign sign (staging + main only)
    → syft SBOM generate + attach (main only)
         │
         ▼ (separate job)
  bump-gitops job
    Tailscale → Trust CA → checkout minicloud-gitops
    → crazy-max GPG import → kustomize
    → Harbor pre-flight check (verify image exists before bump)
    → kustomize edit set image → GPG-signed commit → push
```

The generated repo gets all 7 required secrets automatically when you add them via the organization secrets or repo-level secrets:
`TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `MINICLOUD_CA_CERT`, `HARBOR_USER`, `HARBOR_PASSWORD`, `GITOPS_TOKEN`, `GPG_PRIVATE_KEY`

:::tip Organization secrets
Consider adding these as organization-level secrets in the `andrelair-platform` GitHub org so every new repo inherits them automatically — no per-repo setup required.
:::

---

## Generated Kubernetes Manifests

The base `deployment.yaml` includes all security standards enforced by Gatekeeper from day one:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  seccompProfile:
    type: RuntimeDefault
containers:
  - name: <service>
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop:
          - ALL
```

The pod template also includes the `backstage.io/kubernetes-id: <name>` label so the Kubernetes tab in Backstage shows the service's pods immediately after deployment.

---

## Backstage Configuration

Two sections were added to `minicloud-gitops/helm-values/backstage-values.yaml` (commit `ac45267`):

```yaml
integrations:
  github:
    - host: github.com
      token: ${GITHUB_TOKEN}    # from backstage-github-secret k8s Secret

scaffolder:
  defaultAuthor:
    name: AndreLiar
    email: andrelaurelyvan.kanmegnetabouguie@ynov.com
  defaultCommitMessage: "feat: scaffold initial service structure"
```

And `Template` was added to the catalog rules:

```yaml
catalog:
  rules:
    - allow: [Component, System, API, Resource, Location, User, Group, Template]
  locations:
    ...
    - type: url
      target: https://raw.githubusercontent.com/andrelair-platform/minicloud-backstage/main/templates/go-service/template.yaml
```

The `backstage-github-secret` Kubernetes Secret was created in the `backstage` namespace with the GITOPS_TOKEN value (stored in Vault at `secret/platform/ci-secrets.gitops-token` and patched into `secret/platform/backstage.github-token`):

```bash
kubectl create secret generic backstage-github-secret -n backstage \
  --from-literal=github-token=<GITOPS_TOKEN>
```

---

## How to Use the Template

1. Open Backstage → **Create** (top nav)
2. Select **"Go Service (Golden Path)"**
3. Fill in:
   - **Name** — slug format, e.g. `my-api` (becomes repo name, image name, namespace prefix)
   - **Description** — one-line description
   - **Owner** — `group:default/platform`
   - **Port** — defaults to `8080`
4. Click **Review** → **Create**

The scaffolder runs 6 steps. When complete, the output panel shows:
- Link to the new GitHub repo
- Link to the minicloud-gitops PR
- Link to the component in Backstage catalog

---

## Post-Scaffold Manual Steps

After merging the GitOps PR one step remains manual:

### Add namespace to AppProject

Edit `manifests/argocd-project/00-project.yaml` and add the new namespace to the destinations list:

```yaml
destinations:
  ...
  - namespace: my-api-dev
    server: https://kubernetes.default.svc
```

That's it — Vault policy, initial secrets, and the Kubernetes auth role are all created automatically by the `vault:policy:create` scaffolder action (step 6).

---

## Gotcha — minicloud-backstage Missing CI Secrets

When Phase 70 was implemented, the `minicloud-backstage` repo was still using the old `TAILSCALE_AUTH_KEY` pattern (from Phase 24 setup) instead of `TS_OAUTH_CLIENT_ID` + `TS_OAUTH_SECRET`. It was also missing `HARBOR_USER` and `HARBOR_PASSWORD`. All four were added during Phase 70.

Any repo set up before the OAuth migration will have the same gap — audit your repo secrets and replace `TAILSCALE_AUTH_KEY` with the two OAuth secrets.

---

## Phase 70b — Custom Image Template

Phase 70b added a second template: **`custom-image`**. It targets services that wrap an existing upstream image (like `minicloud-open-webui` wrapping `ghcr.io/open-webui/open-webui:latest`) — where there are no Kustomize overlays, just a Helm values file that pins the image tag.

The template lives at `minicloud-backstage/templates/custom-image/`.

### What it produces

| Artifact | Notes |
|---|---|
| GitHub repo with `Containerfile` | Extends upstream image; injects minicloud CA cert via `ARG CA_CERT` (never committed) |
| `catalog-info.yaml` | Component entity with `kubernetes-id`, `argocd/app-name`, TechDocs ref |
| `mkdocs.yml` + `docs/` | TechDocs documentation scaffold |
| `ci.yml` | Canonical golden path — same as go-service but image bump uses `sed` on a Helm values file |
| `manifests/<name>/00-deployment.yaml` in minicloud-gitops | Plain Deployment (not Kustomize) via GitOps PR |
| Vault policy + initial secrets | Created automatically (same vault:policy:create step) |

### Parameters

| Parameter | What it controls |
|---|---|
| `name` | Kebab-case slug → repo name, image name, Harbor path |
| `description` | Shown in catalog and GitHub repo |
| `upstreamImage` | e.g. `ghcr.io/open-webui/open-webui:latest` |
| `gitopsFile` | Path in minicloud-gitops to the file that holds the image tag (e.g. `helm-values/open-webui-values.yaml`) |
| `owner` | Backstage entity ref |

### Key implementation decision — Nunjucks at top level, `{% raw %}` for the rest

The custom-image CI workflow has a different challenge from go-service. The go-service uses `${{ github.event.repository.name }}` as a GHA runtime expression, so the whole CI file can be wrapped in `{% raw %}`. For custom-image, the service name IS known at scaffold time (`${{ values.name }}`), but `gitopsFile` also needs to be injected at scaffold time.

The solution: only the `env:` block at the top of `ci.yml` uses Nunjucks expressions. Everything else is inside `{% raw %}...{% endraw %}`. The `bump-gitops` job reads from bash env vars (`$GITOPS_FILE`, `$IMAGE_NAME`) — not GHA `${{ }}` expressions — so there's no conflict inside the `{% raw %}` block.

```yaml
# Top of ci.yml — Nunjucks resolves these at scaffold time:
env:
  REGISTRY: harbor.10.0.0.200.nip.io
  IMAGE_NAME: library/${{ values.name }}
  GITOPS_FILE: "${{ values.gitopsFile }}"

{% raw %}
jobs:
  bump-gitops:
    steps:
      - run: |
          # bash env vars from the workflow-level env: block above
          sed -i "s|${REGISTRY}/${IMAGE_NAME}:.*|${REGISTRY}/${IMAGE_NAME}:${NEW_TAG}|" "$GITOPS_FILE"
{% endraw %}
```

---

## Phase 70c — `vault:policy:create` Backend Action

Phase 70c implemented the `vault:policy:create` custom scaffolder action, eliminating the only remaining manual step after a template run.

### What it provisions

When the scaffolder runs step 6 (`vault:policy:create`), it performs three Vault API calls server-side from within the Backstage pod:

1. **Creates a read-only policy** at `sys/policy/<name>`:
   ```hcl
   path "secret/data/platform/<name>/*" { capabilities = ["read"] }
   path "secret/metadata/platform/<name>/*" { capabilities = ["list"] }
   ```

2. **Seeds initial KV secrets** at `secret/data/platform/<name>/config` with `environment: dev` and `log_level: info` so the service starts without a 404 on first Vault Agent inject.

3. **Creates a Kubernetes auth role** at `auth/kubernetes/role/<name>` bound to the service's three namespaces (`<name>-dev`, `<name>-staging`, `<name>-prod`) with the new policy and 1h TTL.

### Setup

The action uses two environment variables:
- `VAULT_ADDR: https://vault.10.0.0.200.nip.io` — set as an `extraEnvVar` in `backstage-values.yaml`
- `VAULT_SCAFFOLDER_TOKEN` — from the `backstage-vault-secret` k8s Secret

The Vault token has the `scaffolder-provisioner` policy, which grants:
- `create/update` on `secret/data/platform/*` (seed secrets)
- `create/update/read` on `sys/policy/*` (create service policies)
- `create/update/read` on `auth/kubernetes/role/*` (create K8s auth roles)

```bash
# How the token was created (controller):
vault token create \
  -policy=scaffolder-provisioner \
  -ttl=0 \
  -period=720h \
  -display-name=backstage-scaffolder
```

The token is stored in Vault at `secret/platform/backstage.vault-scaffolder-token` and in the cluster as:

```bash
kubectl create secret generic backstage-vault-secret -n backstage \
  --from-literal=vault-scaffolder-token=<TOKEN>
```

### Source

`minicloud-backstage/packages/backend/src/actions/vault.ts` — registered via `createBackendModule` and the `scaffolderActionsExtensionPoint`. Added to `packages/backend/src/index.ts` as:

```typescript
backend.add(import('./actions/vault'));
```
