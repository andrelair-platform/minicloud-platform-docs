---
id: cicd-pipeline
title: Full CI/CD Pipeline
sidebar_position: 6
---

# Full CI/CD Pipeline - GitHub Actions -> Kargo -> ArgoCD

The live minicloud flow uses **GitHub Actions**, **Kargo**, and **ArgoCD**. GitLab was evaluated in
the original roadmap and deferred; it is not part of the running platform.

For the current custom-service path, CI does not deploy and does not edit GitOps state directly:

```text
application repo
  -> GitHub Actions: test, build, scan, sign, SBOM
  -> registry artifact: Harbor for dev, ghcr SHA for prod
  -> Kargo: promote artifact by opening PRs in minicloud-gitops
  -> ArgoCD: reconcile merged desired state to the cluster
```

Start with [End-to-End Delivery Workflow](../developer-platform/delivery-workflow) for the full
two-repo model.

---

## Responsibilities

| Layer | Owns | Does not do |
|---|---|---|
| Application repo | source code, tests, Dockerfile, GitHub Actions workflow | Kubernetes runtime configuration |
| GitHub Actions | build, unit tests, vulnerability scan, Cosign signing, SBOM generation, image push | environment promotion or cluster writes |
| `minicloud-gitops` | ArgoCD apps, wrapper Helm charts, values, Kargo configs, shared controls | application source code |
| Kargo | detects immutable artifacts, promotes Freight, opens GitOps PRs | direct Kubernetes deployment |
| ArgoCD | renders Helm and reconciles the desired state | artifact selection or promotion policy |

---

## Application CI Workflow

Each custom service keeps a workflow similar to this in its own repository:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  packages: write
  id-token: write
  security-events: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: npm test

      - name: Build image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: ${{ github.event_name == 'push' }}
          tags: |
            ghcr.io/andrelair-platform/myapp:${{ github.sha }}

      - name: Scan image
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/andrelair-platform/myapp:${{ github.sha }}
          severity: CRITICAL,HIGH

      - name: Sign image
        if: github.event_name == 'push'
        run: cosign sign --yes ghcr.io/andrelair-platform/myapp:${{ github.sha }}

      - name: Generate SBOM
        if: github.event_name == 'push'
        run: syft ghcr.io/andrelair-platform/myapp:${{ github.sha }} -o spdx-json=sbom.spdx.json
```

Adapt the test command to the service stack (`npm test`, `pytest`, `go test ./...`, etc.). Keep the
workflow build-only: no `kubectl`, no `helm upgrade`, and no direct commit to `minicloud-gitops`.

---

## GitOps Promotion

Kargo watches the built artifact and creates **Freight**. For services using the GAP wrapper chart,
promotion updates the image tag in:

```text
minicloud-gitops/services/<svc>/helm/values-dev.yaml
minicloud-gitops/services/<svc>/helm/values-prod.yaml
```

The normal promotion sequence is:

```text
1. Developer merges application code to main.
2. GitHub Actions publishes a signed image and SBOM.
3. Kargo Warehouse detects the new image or git commit.
4. Kargo auto-promotes to dev and opens a dev PR.
5. Dev-only PR auto-merges when path guards pass.
6. ArgoCD syncs dev.
7. Kargo runs dev verification.
8. A verified Freight can be promoted to prod.
9. Kargo opens a CODEOWNERS-gated prod PR.
10. ArgoCD reconciles prod after the PR merges.
```

See [Kargo Promotion](../developer-platform/kargo-promotion) for Warehouse models, verification
variants, and service-specific promotion behavior.

---

## GitOps Repository Layout

The deployment repository is the source of truth for how services run:

```text
minicloud-gitops/
|-- apps/                         # ArgoCD Applications
|-- helm-values/                  # third-party chart values
|-- manifests/                    # shared platform controls
`-- services/
    `-- <svc>/
        |-- helm/                 # GAP wrapper chart + values
        `-- kargo/                # Warehouse, Stages, ProjectConfig, verification
```

For custom services, edit the wrapper chart values or templates under `services/<svc>/helm/`. For
platform tools such as Vault, Grafana, Harbor, and Authentik, edit `helm-values/`.

---

## Release Checks

Before considering a deployment complete, verify:

```text
GitHub Actions workflow is green
image exists in the expected registry with an immutable SHA tag
Cosign signature and SBOM were produced
Kargo Freight exists for the new artifact
Kargo dev verification passed before prod promotion
ArgoCD application is Synced and Healthy
prod promotion PR passed CODEOWNERS review
```

---

## Break-Glass Boundary

Direct `kubectl apply`, `helm upgrade`, or manual cluster patching is reserved for bootstrap,
recovery, or documented break-glass work. After any emergency change, reconcile the final desired
state back into `minicloud-gitops` so ArgoCD remains authoritative.
