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
          │                         (Containerfile, main.go, ci.yml, catalog-info.yaml)
          │
          ├─ 2. fetch:template  ──► render gitops skeleton
          │                         (Kustomize base+overlays, ArgoCD app)
          │
          ├─ 3. publish:github  ──► create repo + push to main
          │
          ├─ 4. github:branch:create × 2 ──► dev + staging branches
          │
          ├─ 5. publish:github:pull-request ──► PR on minicloud-gitops
          │                                     adds services/<name>/ + apps/<name>-dev.yaml
          │
          └─ 6. catalog:register ──► auto-register in Backstage
```

The GitHub token used for steps 3–5 is stored in Vault at `secret/platform/backstage` (key: `github-token`) and mounted as the `backstage-github-secret` Kubernetes Secret in the `backstage` namespace.

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

After merging the GitOps PR two steps remain manual:

### 1. Add namespace to AppProject

Edit `manifests/argocd-project/00-project.yaml` and add the new namespace to the destinations list:

```yaml
destinations:
  ...
  - namespace: my-api-dev
    server: https://kubernetes.default.svc
```

### 2. Create Vault policy and seed secrets

```bash
# On the controller, authenticated against Vault:
vault policy write my-api - <<EOF
path "secret/data/platform/my-api/*" { capabilities = ["read"] }
EOF

vault kv put secret/platform/my-api/config \
  environment=dev \
  log_level=info
```

Then create the ExternalSecret or bind the Vault role to the service's ServiceAccount (matching the existing pattern from platform-demo or minicloud-plane).

---

## Gotcha — minicloud-backstage Missing CI Secrets

When Phase 70 was implemented, the `minicloud-backstage` repo was still using the old `TAILSCALE_AUTH_KEY` pattern (from Phase 24 setup) instead of `TS_OAUTH_CLIENT_ID` + `TS_OAUTH_SECRET`. It was also missing `HARBOR_USER` and `HARBOR_PASSWORD`. All four were added during Phase 70.

Any repo set up before the OAuth migration will have the same gap — audit your repo secrets and replace `TAILSCALE_AUTH_KEY` with the two OAuth secrets.

---

## What's Next

Phase 70 delivered the `go-service` template. Two follow-up templates are planned:

| Phase | Template | For |
|---|---|---|
| 70b | `custom-image` | Services that wrap an upstream image (like open-webui, onlyoffice) — helm-values sed bump instead of Kustomize overlays |
| 70c | Vault policy step | Add a `vault:write` (or equivalent) step to auto-create the Vault policy inside the template, removing manual step 2 entirely |

For 70c, the scaffolder would need a Vault token with policy-write permissions, stored as a separate Backstage secret.
