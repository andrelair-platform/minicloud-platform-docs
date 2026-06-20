---
id: cosign-sbom
title: Cosign + SBOM (Supply Chain Security)
sidebar_position: 5
---

:::caution Not deployed on this cluster
Cosign image signing and SBOM enforcement have **not been deployed**. There is no Gatekeeper policy enforcing signatures. Harbor Trivy scanning (Phase 7) is the only active supply-chain control.
:::


# Cosign + SBOM — Supply Chain Security

Supply chain attacks compromise software before it reaches your cluster — a malicious dependency, a tampered image, or a compromised registry. This layer signs every image with Cosign, generates a Software Bill of Materials (SBOM), and enforces that only signed images from your Harbor registry can be deployed.

---

## Supply Chain Attack Surface

```text
ATTACK VECTOR                    CONTROL
─────────────────────────────────────────────────────────────────────
Malicious base image             Trivy scan in CI (blocks CRITICAL CVEs)
Tampered image in registry       Cosign signature (immutable proof)
Unknown dependencies             SBOM (full dependency inventory)
Unsigned image deployed          Gatekeeper + Sigstore Policy Controller
Compromised CI pipeline          Keyless signing (OIDC + Sigstore)
Registry impersonation           Harbor TLS + image digest pinning
```

---

## Install Cosign

```bash
# macOS
brew install cosign

# Linux
curl -sLO https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64
chmod +x cosign-linux-amd64
sudo mv cosign-linux-amd64 /usr/local/bin/cosign

cosign version
```

---

## Generate a Signing Key Pair

```bash
# Generate key pair — store private key in Vault
cosign generate-key-pair

# This creates:
#   cosign.key   ← PRIVATE KEY (store in Vault / GitLab CI variable)
#   cosign.pub   ← PUBLIC KEY  (store in git, distribute to Gatekeeper policy)

# Store in Vault
vault kv put secret/platform/cosign \
  private_key=@cosign.key \
  password="$COSIGN_PASSWORD"

# Store public key in GitOps repo
cp cosign.pub gitops-repo/security/cosign.pub
```

---

## Sign Images in CI Pipeline

Add signing to the GitLab CI pipeline (after the push stage):

```yaml
# .gitlab-ci.yml — add sign stage after build
stages:
  - build
  - test
  - scan
  - sign        # ← NEW
  - package
  - promote

sign-image:
  stage: sign
  image: gcr.io/projectsigstore/cosign:v2.2.3
  script:
    # Get signing key from Vault
    - vault kv get -field=private_key secret/platform/cosign > /tmp/cosign.key
    # Sign the image
    - |
      cosign sign \
        --key /tmp/cosign.key \
        --yes \
        $IMAGE:$CI_COMMIT_SHORT_SHA
    # Clean up key
    - rm /tmp/cosign.key
  only:
    - main
    - /^release\/.*/
```

---

## Generate SBOM with Syft

SBOM (Software Bill of Materials) is a complete inventory of every package inside an image:

```yaml
# In .gitlab-ci.yml sign stage
generate-sbom:
  stage: sign
  image: anchore/syft:latest
  script:
    # Generate SBOM in SPDX format
    - |
      syft $IMAGE:$CI_COMMIT_SHORT_SHA \
        -o spdx-json=/tmp/sbom.spdx.json

    # Attach SBOM as a Cosign attestation
    - |
      cosign attest \
        --key /tmp/cosign.key \
        --type spdxjson \
        --predicate /tmp/sbom.spdx.json \
        $IMAGE:$CI_COMMIT_SHORT_SHA

  artifacts:
    paths:
      - /tmp/sbom.spdx.json
    reports:
      sbom: /tmp/sbom.spdx.json
```

The SBOM is stored in Harbor alongside the image and can be queried at any time.

---

## Verify an Image Signature

```bash
# Verify signature (returns 0 if valid, non-zero if invalid)
cosign verify \
  --key cosign.pub \
  harbor.local/myteam/myapp:$SHA

# Verify and show details
cosign verify \
  --key cosign.pub \
  --output text \
  harbor.local/myteam/myapp:$SHA | jq .

# Verify SBOM attestation
cosign verify-attestation \
  --key cosign.pub \
  --type spdxjson \
  harbor.local/myteam/myapp:$SHA | jq '.payload | @base64d | fromjson'
```

---

## Enforce Signing via Sigstore Policy Controller

The Policy Controller is a Kubernetes admission webhook that blocks unsigned images:

```bash
helm repo add sigstore https://sigstore.github.io/helm-charts
helm repo update

helm upgrade --install policy-controller sigstore/policy-controller \
  --namespace cosign-system \
  --create-namespace \
  --set config.no-match-policy=deny
```

### ClusterImagePolicy

```yaml
# cluster-image-policy.yaml
apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
metadata:
  name: require-signed-harbor-images
spec:
  images:
    - glob: "harbor.local/**"        # all images from Harbor
    - glob: "harbor.yourdomain.com/**"

  authorities:
    - key:
        data: |
          -----BEGIN PUBLIC KEY-----
          <contents of cosign.pub>
          -----END PUBLIC KEY-----
      ctlog:
        url: https://rekor.sigstore.dev   # transparency log
```

```bash
kubectl apply -f cluster-image-policy.yaml

# Test: try to deploy an unsigned image
kubectl run unsigned-test \
  --image=harbor.local/myteam/myapp:unsigned-tag \
  --namespace default
# Expected: admission webhook blocked the request
```

---

## Scan SBOM for Known Vulnerabilities

```bash
# Scan SBOM file directly (no need to pull image)
grype sbom:/tmp/sbom.spdx.json --fail-on critical

# Or via Trivy
trivy sbom /tmp/sbom.spdx.json --severity CRITICAL,HIGH

# Query Harbor for stored SBOM
cosign download sbom harbor.local/myteam/myapp:$SHA
```

---

## Image Digest Pinning

Never use `:latest` in production — pin to digest:

```yaml
# Bad (tag can be replaced)
image: harbor.local/myteam/myapp:latest

# Good (digest is immutable)
image: harbor.local/myteam/myapp@sha256:abc123def456...
```

```bash
# Get digest for a tag
docker pull harbor.local/myteam/myapp:1.3.0
docker inspect harbor.local/myteam/myapp:1.3.0 \
  --format='{{index .RepoDigests 0}}'
# harbor.local/myteam/myapp@sha256:...

# Or via Helm values
helm upgrade --install myapp-prod oci://harbor.local/charts/myapp \
  --set image.digest=sha256:abc123def456
```

---

## Harbor — View Signatures and SBOM

```text
Harbor UI → myteam → myapp → Tags → <tag>
  → Signature: ✅ Cosign signed
  → SBOM: ✅ SPDX attached
  → Vulnerabilities: Trivy scan report
```

---

## Keyless Signing (OIDC — No Keys to Manage)

For GitLab CI with OIDC support, sign without a private key:

```yaml
sign-image-keyless:
  stage: sign
  image: gcr.io/projectsigstore/cosign:v2.2.3
  id_tokens:
    SIGSTORE_ID_TOKEN:
      aud: sigstore
  script:
    - |
      cosign sign \
        --yes \
        --oidc-issuer https://gitlab.local \
        --identity-token $SIGSTORE_ID_TOKEN \
        $IMAGE:$CI_COMMIT_SHORT_SHA
```

Identity is bound to the GitLab CI job identity — no long-lived key material.

---

## Done When

```text
✔ Cosign key pair generated, private key stored in Vault
✔ All images signed in CI after successful Trivy scan
✔ SBOM generated and attached as attestation for every build
✔ Sigstore Policy Controller blocking unsigned images cluster-wide
✔ Harbor shows signature + SBOM for all production images
✔ Image digest pinning enforced in production Helm values
```
