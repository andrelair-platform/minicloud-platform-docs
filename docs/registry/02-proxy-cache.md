---
id: harbor-proxy-cache
title: Phase 16 — Harbor as Sovereign Registry (Proxy Cache)
sidebar_position: 2
---

# Phase 16 — Harbor as Sovereign Registry

Phase 7 installed Harbor and pushed a few test images to its `library`
project. After Phase 13 shipped `platform-demo` to ghcr.io and Phase 15
fixed Harbor's TLS, **Harbor wasn't actually serving any production
traffic**. It was running, healthy, eating ~1.5 GiB RAM — but no
workload pulled from it.

Phase 16 fixes that. Harbor becomes the **single chokepoint for every
image pull on the cluster**. Public images (Docker Hub, ghcr.io,
Quay.io, registry.k8s.io) are routed through Harbor's proxy-cache
projects, cached on Longhorn-backed storage, and served back to kubelet.
The cluster's external image-pull traffic drops to zero on cache hits.

This is the canonical "production registry" pattern — same shape every
on-prem and air-gapped platform team uses. The skill demonstrated
isn't "Harbor exists in the cluster"; it's **"Harbor mediates the supply
chain."**

---

## Why this pattern matters

| Problem this solves | Real-world payoff |
|---|---|
| **Docker Hub rate limits** (anonymous: 100 pulls/6h) | Hit upstream once per image; thereafter every pull is a cache hit |
| **WAN saturation on home WiFi** | 20 MB image pulled 3× now lives on the cluster's internal 1 Gbps net |
| **Image disappears upstream** | Cached layers stay on Longhorn; surviving image, even if upstream pulls it |
| **Supply-chain inspection point** | One place to scan, sign, audit, control-list every image |
| **"What if docker.io changes their TOS"** | Sovereign infrastructure: your cluster keeps working |

---

## Architecture

```text
                          ┌───────────────────────────────────────────────────┐
   Cluster pod            │  Harbor (in-cluster, harbor.10.0.0.200.nip.io)    │
       │                  │   ┌─────────────────────────────────────────────┐ │
       │ "I need          │   │ Project: library    (our own pushed images) │ │
       │  nginx:alpine"   │   │ Project: docker-hub  → docker.io            │ │
       │                  │   │ Project: ghcr        → ghcr.io (PAT auth)   │ │
       ▼                  │   │ Project: quay        → quay.io              │ │
  containerd ───┐         │   │ Project: k8s-registry→ registry.k8s.io      │ │
                │         │   └─────────────────────────────────────────────┘ │
   k3s mirrors  │         │       │                                           │
   in           │         │       │ on cache miss                             │
   registries   │         │       ▼                                           │
   .yaml ───────┼────────▶│  fetch from upstream, cache on Longhorn           │──▶ docker.io
                          │  (Trivy auto-scan: pushed-only, see limitation)  │──▶ ghcr.io  (with read:packages PAT)
   ↓ on Harbor             │                                                   │──▶ quay.io
   unreachable             │                                                   │──▶ registry.k8s.io
   ──fallback──────────────┴───────────────────────────────────────────────────┘──▶ direct upstream
```

The mirror config in `/etc/rancher/k3s/registries.yaml` lists Harbor
**first** and the upstream registry **second**. If Harbor is down (during
upgrades, pod restarts, or PVC issues), containerd transparently falls
through to direct upstream pulls. **Harbor is a performance + supply-
chain layer, never a single point of failure.**

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Proxy-cache targets | `docker.io`, `ghcr.io`, `quay.io`, `registry.k8s.io` | Covers every upstream our cluster currently pulls from |
| Project names | `docker-hub`, `ghcr`, `quay`, `k8s-registry` | Short, clear; matches Harbor convention |
| Endpoint type for Quay | `docker-registry` (not `quay`) | Harbor 2.14's `quay` registry type isn't supported as a proxy-cache target; Quay.io is a standard OCI registry, so the generic `docker-registry` type works |
| Authentication for upstream | Anonymous for public; **read:packages PAT** for ghcr.io | Reuse the same PAT we already use for the (now-decommissioned) `ghcr-pull` Secret |
| Mirror configuration | Per-registry mirrors with **Harbor first + upstream fallback** | Avoids the "Harbor restart breaks the cluster" trap; canonical resilience pattern |
| Bootstrap exclusion | Don't proxy `goharbor/*` images | Harbor's own image pulls go direct (or use containerd's local cache); avoids the chicken-and-egg cycle |
| Existing `library` project | Untouched | Stays as the destination for our own pushed images (e.g., the test artifacts from Phases 7 + 15). Historical record. |
| Trivy auto-scan on cached images | **Limitation: not supported in Harbor 2.14** | Auto-scan applies to pushed artifacts, not proxy-cached. Documented honestly here; Phase 17+ will add CI-side Trivy + Cosign + Kyverno admission policies. |

---

## Setup

### 1. Configure 4 Registry Endpoints in Harbor (via API)

```bash
HARBOR="https://harbor.10.0.0.200.nip.io"
HARBOR_PW=$(cat ~/.harbor-admin)
GHCR_PAT=$(kubectl get secret ghcr-pull -n gitops-demo \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d \
  | jq -r '.auths."ghcr.io".password')

curl --cacert ~/minicloud-ca.crt -u "admin:${HARBOR_PW}" \
  -H "Content-Type: application/json" \
  -X POST "${HARBOR}/api/v2.0/registries" \
  -d '{"name":"docker-hub-upstream","type":"docker-hub","url":"https://hub.docker.com"}'

curl --cacert ~/minicloud-ca.crt -u "admin:${HARBOR_PW}" \
  -H "Content-Type: application/json" \
  -X POST "${HARBOR}/api/v2.0/registries" \
  -d "{
    \"name\":\"ghcr-upstream\",
    \"type\":\"github-ghcr\",
    \"url\":\"https://ghcr.io\",
    \"credential\":{\"type\":\"basic\",\"access_key\":\"AndreLiar\",\"access_secret\":\"${GHCR_PAT}\"}
  }"

curl --cacert ~/minicloud-ca.crt -u "admin:${HARBOR_PW}" \
  -H "Content-Type: application/json" \
  -X POST "${HARBOR}/api/v2.0/registries" \
  -d '{"name":"quay-upstream","type":"docker-registry","url":"https://quay.io"}'

curl --cacert ~/minicloud-ca.crt -u "admin:${HARBOR_PW}" \
  -H "Content-Type: application/json" \
  -X POST "${HARBOR}/api/v2.0/registries" \
  -d '{"name":"k8s-registry-upstream","type":"docker-registry","url":"https://registry.k8s.io"}'
```

All four return `HTTP 201` and show `"status": "healthy"` on
`GET /api/v2.0/registries`.

### 2. Create 4 Proxy-Cache Projects

```bash
for pair in "docker-hub:1" "ghcr:2" "quay:5" "k8s-registry:4"; do
  NAME="${pair%:*}"
  EID="${pair##*:}"
  curl --cacert ~/minicloud-ca.crt -u "admin:${HARBOR_PW}" \
    -H "Content-Type: application/json" \
    -X POST "${HARBOR}/api/v2.0/projects" \
    -d "{
      \"project_name\":\"${NAME}\",
      \"public\":true,
      \"registry_id\":${EID},
      \"metadata\":{\"public\":\"true\",\"auto_scan\":\"true\"}
    }"
done
```

### 3. Verify the cache works (crane test, before touching cluster)

```bash
crane auth login harbor.10.0.0.200.nip.io --username admin --password "$HARBOR_PW"

# Cold pull (cache miss) — Harbor pulls from docker.io and caches
crane pull --insecure harbor.10.0.0.200.nip.io/docker-hub/library/alpine:3.20 /tmp/alpine.tar
# real    0m3.7s

# Warm pull (cache hit) — served from Harbor's Longhorn-backed cache
crane pull --insecure harbor.10.0.0.200.nip.io/docker-hub/library/alpine:3.20 /tmp/alpine.tar
# real    0m2.1s
```

### 4. Update the Phase 10 Ansible role

`roles/k3s-registries/files/registries.yaml`:

```yaml
mirrors:
  "docker.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/docker-hub"
      - "https://registry-1.docker.io"
  "ghcr.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/ghcr"
      - "https://ghcr.io"
  "quay.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/quay"
      - "https://quay.io"
  "registry.k8s.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/k8s-registry"
      - "https://registry.k8s.io"
  "harbor.10.0.0.200.nip.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io"

configs:
  "harbor.10.0.0.200.nip.io":
    tls:
      ca_file: /etc/rancher/k3s/minicloud-ca.crt
```

Apply:

```bash
cd ansible/
ansible-playbook playbooks/site.yml --check --diff   # preview
ansible-playbook playbooks/site.yml                  # apply, restarts k3s on each node
```

### 5. End-to-end benchmark from cluster

```bash
TEST_IMG=docker.io/library/nginx:1.27.4-alpine

# Verify not yet cached on any node
for n in 10.0.0.2 10.0.0.4 10.0.0.7; do
  ssh ubuntu@$n "sudo k3s ctr images list | grep -c $TEST_IMG"
done

# COLD pull on fast-skunk
kubectl run nginx-cold --image=$TEST_IMG --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"fast-skunk"}}}'
# kubelet event:  "Successfully pulled in 5.446s"  (cache miss in Harbor + fetch from docker.io)

# WARM pull on fast-heron
kubectl run nginx-warm --image=$TEST_IMG --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"fast-heron"}}}'
# kubelet event:  "Successfully pulled in 2.887s"  (cache HIT in Harbor)
```

**Cold vs. warm: 5.446s → 2.887s for a 20.8 MB image. ~47% reduction.**
The savings scale with image size — for typical 100-300 MB workload
images, the absolute time savings are much larger.

---

## platform-demo migration

After Phase 16, platform-demo's CI pipeline writes the **Harbor URL**
(not the ghcr.io URL) into the gitops repo. Cluster pods pull through
Harbor's `ghcr` proxy cache; the `ghcr-pull` imagePullSecret in the
`gitops-demo` namespace was deleted.

### CI workflow change (`andrelair-platform/platform-demo/.github/workflows/ci.yml`):

```yaml
bump-gitops:
  env:
    # Phase 16: cluster pulls go through Harbor's ghcr proxy cache,
    # not directly from ghcr.io.
    NEW_IMAGE: harbor.10.0.0.200.nip.io/ghcr/${{ github.repository }}:${{ needs.build-and-push.outputs.image_tag }}
```

### gitops manifest change:

```diff
       containers:
         - name: platform-demo
-          image: ghcr.io/andrelair-platform/platform-demo:c2dd9cd
+          image: harbor.10.0.0.200.nip.io/ghcr/andrelair-platform/platform-demo:c2dd9cd
-      imagePullSecrets:
-        - name: ghcr-pull
```

### Decommission the now-unused Secret:

```bash
kubectl delete secret ghcr-pull -n gitops-demo
```

After the next CI run (or the immediate ArgoCD sync from the manifest
change), pods pull from Harbor. Verified end-to-end with the new SHA
landing in `harbor.../ghcr/andrelair-platform/platform-demo` repository
inside Harbor's UI.

---

## Trivy on cached images: the honest limitation

Harbor 2.14's auto-scan setting only applies to **pushed** artifacts,
not proxy-cached ones. Cached images don't get scanned automatically.
The scan-API endpoint accepts manual triggers but in practice doesn't
populate scan_overview for proxy-cache projects.

**This is a real production gap.** The canonical fix is **CI-side
scanning** of dependencies before they reach the cluster — which is
Phase 17+ work (Cosign + Kyverno admission control). Phase 16's value
is the cache + control-point shape, not the auto-scan story.

If proxy-cache image scanning is critical, the workarounds are:

1. **Schedule Harbor's "Scan All" policy** (settings → System → Schedule)
2. **Pull images via Trivy directly** in CI (`trivy image harbor.../docker-hub/library/nginx:alpine`)
3. **Use an admission policy** to reject pods running un-scanned images

All three pair naturally with Phase 17's planned Kyverno work.

---

## Done When

```text
✔ 4 Registry Endpoints in Harbor, all "healthy"
✔ 4 proxy-cache Projects created: docker-hub, ghcr, quay, k8s-registry
✔ crane test: cold + warm pulls of alpine via Harbor work
✔ Phase 10 Ansible k3s-registries role updated, all 3 nodes have new mirrors
✔ Cluster cold/warm pull benchmark documented (47% reduction on 20 MB image)
✔ platform-demo CI writes harbor.../ghcr/... URLs; gitops manifest matches
✔ ghcr-pull Secret deleted from gitops-demo namespace
✔ Pipeline still works end-to-end: push → CI → ghcr.io push → bump → Harbor pulls → kubelet pulls via Harbor → live
✔ Homer's Harbor tile subtitle reflects the proxy-cache role
```

---

## Acceptance test — verify all 4 proxy caches end-to-end

The "Done When" checklist above describes the install. This section is the **operational test that proves all 4 proxies are actually caching**, runnable any time against the live system. Discovered and documented during the 2026-06-15 health-check pass.

### The one-liner

```bash
# 1) Force-pull one image through each proxy (manifest + blobs)
for proj in docker-hub ghcr quay k8s-registry; do
  case "$proj" in
    docker-hub)   IMG="library/alpine:3.20" ;;
    ghcr)         IMG="andrelair-platform/platform-demo:latest" ;;
    quay)         IMG="jetstack/cert-manager-controller:v1.20.2" ;;
    k8s-registry) IMG="pause:3.10" ;;
  esac
  crane pull --insecure "harbor.10.0.0.200.nip.io/${proj}/${IMG}" "/tmp/${proj}-test.tar"
  rm -f "/tmp/${proj}-test.tar"
done

# 2) Confirm each project now reports a non-zero cached-repo count
HARBOR_PW=$(cat ~/.harbor-admin)
for proj in docker-hub ghcr quay k8s-registry; do
  COUNT=$(curl -s --cacert ~/minicloud-ca.crt -u "admin:${HARBOR_PW}" \
    "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/${proj}/repositories" \
    | jq 'length')
  echo "${proj}: ${COUNT} repos cached"
done
```

Expected output (numbers grow over time as more workloads pull):

```
docker-hub: 10 repos cached
ghcr: 10 repos cached
quay: 1 repos cached
k8s-registry: 1 repos cached
```

### Two gotchas discovered while building this test

1. **A manifest-only fetch does NOT populate Harbor's proxy-cache repository listing.** A `curl` against `/v2/<proj>/<image>/manifests/<tag>` returns `HTTP/1.1 200 OK` and proxies the manifest from upstream, but Harbor only formally registers the repository when the actual image *layer blobs* are pulled. Use `crane pull` (which fetches manifest + all blobs) — not just `crane manifest` or curl-against-manifest — when validating cache fill.

2. **Do NOT pass `?page_size=100` to `GET /api/v2.0/projects/{name}/repositories`.** It returns an inflated repo count vs. the un-parameterized call. Observed: docker-hub returned 16 with `?page_size=100` but 10 without. The naked endpoint is the source of truth.

### Why this test matters

The original Phase 16 plan ended with cluster-level cold/warm benchmarks (Section 5) for the `docker-hub` proxy only. That proved one proxy worked; this test proves **all four** are caching, which is the actual definition of "sovereign supply chain." Without it, the 0-count behavior on `quay` and `k8s-registry` (caused by containerd's per-node image cache short-circuiting kubelet's pull when images predate Phase 16) looks like a broken proxy. With this test, we confirm the proxies are fully functional — the empty initial state is just an artifact of timing, not configuration.

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Sovereign / proxy-cache registry pattern** | The default architecture for any on-prem or air-gapped Kubernetes platform. Same shape as JFrog Artifactory, Sonatype Nexus, AWS ECR Pull-Through Cache, GitLab Dependency Proxy. |
| **Harbor proxy-cache project + Endpoint configuration** | Harbor-specific knowledge that's directly applicable in any shop running Harbor (Goldman Sachs, Capital One, every regulated-industry k8s platform) |
| **k3s/containerd `mirrors` with fallback endpoints** | The "Harbor first + upstream fallback" pattern is the production-grade availability shape. Same idea in containerd's `hosts.toml` system on full-fat k8s. |
| **Authenticated upstream proxying** (read:packages PAT for ghcr.io) | Real production: pulling private base images through a registry mirror requires upstream auth, stored once on the proxy rather than fanned out as imagePullSecrets across every namespace |
| **Decommissioning workflow** | Removing the now-redundant `ghcr-pull` Secret is the cleanup discipline that distinguishes "ships features" engineers from "owns the platform" engineers |
| **Honest documentation of limitations** | The Trivy auto-scan gap on proxy-cached images is real. Naming it (and pointing at Phase 17 as the path to closing it) is more credible than hand-waving. |
| **Senior-grade scope reframing** | Recognizing that the original Phase 16 plan (n8n + Temporal + Airflow) was three heavy tools compressed into one phase, and replacing it with a coherent architectural improvement to existing infrastructure, is the same skill as the GitLab and Crossplane deferrals. |
