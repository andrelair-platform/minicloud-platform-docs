---
id: cosign-sbom
title: Phase 30 — Cosign + SBOM (Supply Chain Security)
sidebar_position: 5
---

# Phase 30 — Cosign + SBOM — Supply Chain Image Signing

Supply chain attacks target software before it reaches your cluster — a tampered image pushed to a registry, a compromised CI runner, or a registry impersonation. Cosign signs every image with a cryptographic certificate proving *which CI run built it*, and syft generates a Software Bill of Materials (SBOM) — a complete dependency inventory attached to the image digest.

---

## Architecture

```text
GitHub Actions CI                    ghcr.io                       Cluster
─────────────────          ──────────────────────────────     ─────────────────────
1. Build image             platform-demo:<sha>               harbor.10.0.0.200.nip.io
2. Push to ghcr.io    ──▶  platform-demo:<sha>-cosign   ──▶  ghcr proxy cache
3. syft SBOM               platform-demo:<sha>-sbom           kubelet pulls
4. cosign sign                    │                            Gatekeeper warns
5. cosign attach sbom   ──────────┘                           on non-Harbor images
   (OCI referrer)
```

### Why keyless signing?

Traditional key-pair signing creates a long-lived private key — a secret that must be rotated, stored securely, and is valuable to attackers. **Keyless signing** uses the GitHub Actions OIDC token as the signer identity:

```text
GitHub Actions job
  → requests OIDC token (audience: sigstore)
  → presents token to Sigstore Fulcio CA
  → Fulcio issues a short-lived (10-minute) certificate
  → cosign signs the image with that certificate
  → certificate + signature written to Sigstore Rekor transparency log
```

The resulting identity is:
```
Subject:   https://github.com/andrelair-platform/platform-demo/.github/workflows/ci.yml@refs/heads/main
Issuer:    https://token.actions.githubusercontent.com
```

No private key to rotate. No secret to leak. Provenance is bound to the exact workflow file + branch.

---

## CI Pipeline Changes

Three steps added to the `build-and-push` job in `.github/workflows/ci.yml` after the `Build and push` step:

```yaml
permissions:
  contents: read
  packages: write
  id-token: write   # request GitHub OIDC token for Cosign

# After Build and push:

- name: Install Cosign
  uses: sigstore/cosign-installer@v3

- name: Install syft
  uses: anchore/sbom-action/download-syft@v0

- name: Generate SBOM (CycloneDX JSON)
  run: |
    syft ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }} \
      -o cyclonedx-json=sbom.json

- name: Sign image (keyless — GitHub OIDC → Sigstore Fulcio)
  run: |
    cosign sign --yes \
      ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}

- name: Attach SBOM to image as OCI referrer
  run: |
    cosign attach sbom \
      --sbom sbom.json \
      --type cyclonedx \
      ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
```

Signing and SBOM generation happen **by digest**, not by tag. Digests are immutable — a tag can be overwritten, a `sha256:...` cannot.

---

## Verify a Signature

After the CI run completes, the signature is in the Sigstore Rekor transparency log:

```
tlog entry created with index: 1900056177
Pushing signature to: ghcr.io/andrelair-platform/platform-demo
```

Verify from any machine with cosign installed (requires `read:packages` on the GHCR token):

```bash
# Authenticate cosign to ghcr.io
echo $GHCR_PAT | cosign login ghcr.io --username AndreLiar --password-stdin

# Verify the signed image
cosign verify \
  --certificate-identity-regexp="https://github.com/andrelair-platform/platform-demo" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/andrelair-platform/platform-demo:dc9b66b

# Expected output:
# Verification for ghcr.io/andrelair-platform/platform-demo:dc9b66b --
# The following checks were performed on each of these signatures:
#   - The cosign claims were validated
#   - Existence of the claims in the transparency log was verified offline
#   - The code-signing certificate claims were validated
#
# [{"critical":{"identity":{"docker-reference":"ghcr.io/andrelair-platform/platform-demo"},
#   "image":{"docker-manifest-digest":"sha256:535cfe2434b13c1659187252039432b701dd4b83a9301b7a28624b9d5a10ee92"},
#   "type":"cosign container image signature"},
#   "optional":{"1.3.6.1.4.1.57264.1.1":"https://token.actions.githubusercontent.com",
#   "1.3.6.1.4.1.57264.1.2":"push",
#   "1.3.6.1.4.1.57264.1.3":"dc9b66be821792b064597ad9d7c1845b5d2571aa",
#   "1.3.6.1.4.1.57264.1.4":"CI",
#   "1.3.6.1.4.1.57264.1.5":"andrelair-platform/platform-demo",
#   "1.3.6.1.4.1.57264.1.6":"refs/heads/main"}}]
```

`1.3.6.1.4.1.57264.1.*` are the Sigstore Fulcio OID extensions — they embed the GitHub Actions context (workflow, run, repo, ref) into the certificate.

### Search Rekor transparency log directly

The signature is in the public Rekor log regardless of registry visibility:

```bash
# Search by image digest (no registry auth needed)
rekor-cli search --sha sha256:535cfe2434b13c1659187252039432b701dd4b83a9301b7a28624b9d5a10ee92

# Or view the entry directly
rekor-cli get --log-index 1900056177
```

### Verify SBOM attachment

```bash
cosign download sbom \
  ghcr.io/andrelair-platform/platform-demo:dc9b66b \
  | jq '{bomFormat, specVersion, metadata: .metadata.component}'
```

---

## SBOM — What It Contains

A CycloneDX SBOM generated by syft for the `platform-demo` Go binary lists every dependency by name, version, type, and PURL:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "metadata": {
    "component": {
      "name": "ghcr.io/andrelair-platform/platform-demo",
      "type": "container"
    }
  },
  "components": [
    {
      "name": "github.com/gofiber/fiber/v2",
      "version": "v2.52.6",
      "purl": "pkg:golang/github.com/gofiber/fiber/v2@v2.52.6",
      "type": "library"
    },
    {
      "name": "github.com/prometheus/client_golang",
      "version": "v1.22.0",
      "purl": "pkg:golang/github.com/prometheus/client_golang@v1.22.0",
      "type": "library"
    }
    // ... all transitive Go module dependencies
  ]
}
```

The SBOM is stored in the registry alongside the image. Any future vulnerability scanner can query it without re-pulling the full image layers.

---

## Gatekeeper — Allowed Registries Policy

A fourth Gatekeeper constraint was added: `K8sAllowedRegistries`. It requires all pod images to use the `harbor.10.0.0.200.nip.io/` prefix — enforcing that every workload goes through Harbor's proxy cache (the Trivy scanning chokepoint).

### ConstraintTemplate

```yaml
# manifests/gatekeeper-policies/03-ct-allowed-registries.yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sallowedregistries
spec:
  crd:
    spec:
      names:
        kind: K8sAllowedRegistries
      validation:
        openAPIV3Schema:
          type: object
          properties:
            registries:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sallowedregistries

        containers[c] {
          c := input.review.object.spec.containers[_]
        }
        containers[c] {
          c := input.review.object.spec.template.spec.containers[_]
        }
        containers[c] {
          c := input.review.object.spec.initContainers[_]
        }
        containers[c] {
          c := input.review.object.spec.template.spec.initContainers[_]
        }

        violation[{"msg": msg}] {
          container := containers[_]
          not startswith_allowed(container.image)
          msg := sprintf("Container '%v' uses image '%v' from a disallowed registry. Allowed prefixes: %v",
            [container.name, container.image, input.parameters.registries])
        }

        startswith_allowed(image) {
          registry := input.parameters.registries[_]
          startswith(image, registry)
        }
```

### Constraint (warn mode)

```yaml
# manifests/gatekeeper-policies/13-constraint-allowed-registries.yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sAllowedRegistries
metadata:
  name: allowed-registries
spec:
  enforcementAction: warn
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values:
            - kube-system
            - kube-public
            - kube-node-lease
            - gatekeeper-system
            - metallb-system
            - longhorn-system
            - nfs-provisioner
            - cert-manager
            - ingress-nginx
            - chaos-mesh
            - velero
            - falco
  parameters:
    registries:
      - "harbor.10.0.0.200.nip.io/"
      - "harbor.devandre.sbs/"
```

### Audit results

```bash
kubectl --context minicloud get k8sallowedregistries allowed-registries \
  -o jsonpath='{.status.totalViolations}'
# 116
```

116 violations — all in warn mode. The violations are expected: Helm-installed workloads use their upstream registry URLs (quay.io, ghcr.io, docker.io, etc.) by default rather than Harbor proxy-cache prefixes.

**Compliant workloads (0 violations):**
- `gitops-demo/platform-demo` — uses `harbor.10.0.0.200.nip.io/ghcr/andrelair-platform/platform-demo:...` ✅

**Violation examples:**
```
argocd/         quay.io/argoproj/argocd:v3.4.1
monitoring/     docker.io/grafana/grafana:13.0.1
monitoring/     quay.io/prometheus-operator/prometheus-operator:v0.90.1
keda/           ghcr.io/kedacore/keda:2.19.0
vault/          hashicorp/vault:2.0.2        ← Vault Agent sidecar (injected)
backstage/      docker.io/bitnamilegacy/postgresql:15.4.0-debian-11-r10
```

:::note Vault Agent sidecar
The `hashicorp/vault:2.0.2` violation comes from the Vault Agent Injector — it mutates pods to inject a sidecar using its own configured image, bypassing our GitOps manifests. Fixing this requires overriding the sidecar image in the Vault Helm values:
```yaml
injector:
  agentImage:
    repository: harbor.10.0.0.200.nip.io/docker-hub/hashicorp/vault
    tag: "2.0.2"
```
:::

### Path to zero violations

Migrate each namespace's Helm values to use Harbor proxy-cache URLs:
```bash
# docker.io images → harbor.10.0.0.200.nip.io/docker-hub/<image>
# ghcr.io images  → harbor.10.0.0.200.nip.io/ghcr/<image>
# quay.io images  → harbor.10.0.0.200.nip.io/quay/<image>
# k8s registry   → harbor.10.0.0.200.nip.io/k8s-registry/<image>
```

Once all workloads use Harbor, flip `enforcementAction: deny`.

---

## Full Supply Chain Security Chain

```text
Source code
  │
  ▼
GHAS (Phase 13)
  ├── CodeQL SAST — finds injection, RCE, SQL injection
  ├── Dependabot SCA — CVEs in Go modules
  └── Secret scanning — blocks committed credentials
  │
  ▼
GitHub Actions CI
  ├── go test ./... — unit tests
  ├── docker build — reproducible Containerfile build
  ├── docker push → ghcr.io
  ├── syft SBOM — CycloneDX dependency inventory
  ├── cosign sign — GitHub OIDC → Sigstore Fulcio (this phase)
  └── cosign attach sbom — OCI referrer artifact
  │
  ▼
Harbor (Phases 7, 16)
  ├── Trivy scan on push — blocks CRITICAL CVEs
  ├── Proxy cache — mirrors ghcr.io, docker.io, quay.io
  ├── Cosign signature stored alongside image
  └── SBOM accessible via cosign download sbom
  │
  ▼
Cluster admission (Phase 27 + this phase)
  ├── K8sBlockLatestTag — blocks :latest images
  ├── K8sNoPrivilegedContainers — blocks privileged pods
  ├── K8sRequireResourceLimits — blocks uncapped containers
  └── K8sAllowedRegistries (warn) — flags non-Harbor images
  │
  ▼
Runtime (Phase 28)
  └── Falco — detects unexpected syscalls, privilege escalation
```

---

## Verification Commands

```bash
# List all 4 Gatekeeper constraints
kubectl --context minicloud get constraints

# Check AllowedRegistries violation count
kubectl --context minicloud get k8sallowedregistries allowed-registries \
  -o jsonpath='{.status.totalViolations}'

# Verify cosign signature (run after the CI push completes)
cosign verify \
  --certificate-identity-regexp="https://github.com/andrelair-platform/platform-demo" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/andrelair-platform/platform-demo:latest

# Download and inspect SBOM
cosign download sbom ghcr.io/andrelair-platform/platform-demo:latest \
  | jq '.components | length'   # total dependencies
```

---

## Done When

```text
✔ CI workflow: cosign-installer@v3 + syft installed in build-and-push job
✔ syft generates CycloneDX JSON SBOM from image digest
✔ cosign signs image by digest (keyless — GitHub OIDC → Sigstore Fulcio)
✔ cosign attach sbom attaches SBOM as OCI referrer on ghcr.io
✔ K8sAllowedRegistries ConstraintTemplate deployed (k8sallowedregistries)
✔ allowed-registries Constraint active (enforcementAction: warn, 116 violations audited)
✔ platform-demo in gitops-demo namespace: 0 AllowedRegistries violations (compliant)
✔ Full supply chain documented: GHAS → Cosign/SBOM → Harbor Trivy → Gatekeeper → Falco
```
