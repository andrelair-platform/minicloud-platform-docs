---
slug: container-registry-architecture-harbor-k3s-proxy-cache
title: "One Registry to Rule Them All: Harbor as the Single Image Entry Point for a Bare-Metal k3s Cluster"
authors: [andrelair]
tags: [harbor, kubernetes, docker, registry, k3s, self-hosted, devops, supply-chain, rate-limiting, containerd]
date: 2026-08-16
description: "How a self-hosted Harbor instance, configured as a pull-through proxy for docker.io, ghcr.io, quay.io, and registry.k8s.io, becomes the single entry point for all image traffic on a bare-metal k3s cluster — eliminating Docker Hub rate limits, centralizing vulnerability scanning, and keeping air-gap capability without any code changes in your manifests."
---

If you run a Kubernetes cluster seriously, you eventually hit the Docker Hub wall. One morning your CI pipeline starts failing with `toomanyrequests: You have reached your pull rate limit`. Or worse — it fails during a cluster recovery at 2 AM, when your nodes are pulling images to restart critical workloads and Docker Hub decides you've exceeded your 100-pulls-per-6-hours anonymous quota.

The standard advice is to add authentication. But that only raises the limit — it doesn't eliminate the dependency on an external service during your most vulnerable moments. The production answer is a pull-through proxy cache, and on a self-hosted k3s cluster, Harbor + k3s mirrors makes every node behave as if Docker Hub were local.

{/* truncate */}

## The Full Picture: Five Registries, One Entry Point

On the minicloud platform — a 5-node bare-metal k3s cluster running 70+ workloads — image traffic involves five distinct registries:

| Registry | Type | What it serves |
|---|---|---|
| `harbor.10.0.0.200.nip.io` | Self-hosted (Harbor 2.14) | **Everything** — CI-built images + proxy cache for all public registries |
| `docker.io` | Upstream public | Default Docker Hub — nginx, postgres, redis, alpine, ubuntu... |
| `ghcr.io` | Upstream public | GitHub Container Registry — Authentik, Longhorn, Velero, most CNCF tooling |
| `quay.io` | Upstream public | Red Hat quay — Prometheus, AlertManager, Grafana, OPA |
| `registry.k8s.io` | Upstream public | Kubernetes project images — pause, kube-proxy, CoreDNS, metrics-server |

But "five registries" is only true from the perspective of pull origin. From the perspective of every node in the cluster, there is exactly **one** registry: Harbor.

---

## How k3s Makes Harbor Transparent

The key is `registries.yaml` — a containerd mirror configuration file that k3s reads on startup. It tells the container runtime: "when a pod asks for an image from X, try Y first, fall back to X."

```yaml
# /etc/rancher/k3s/registries.yaml (on every k3s node)
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

When a pod spec says `image: nginx:alpine`, containerd does not contact `docker.io`. It tries `harbor.10.0.0.200.nip.io/v2/docker-hub` first. If Harbor has the image cached, it returns it immediately. If not, Harbor fetches it from `registry-1.docker.io`, caches it, and serves it — the node only ever communicates with Harbor.

The fallback endpoint (`"https://registry-1.docker.io"`) is there as a resilience mechanism: if Harbor itself is down, containerd can still pull directly. In practice this fallback fires only during Harbor restarts or maintenance windows.

**Nothing in your Kubernetes manifests changes.** A Deployment that says `image: ghcr.io/goauthentik/server:2024.12.0` keeps saying exactly that. The mirror intercepts the pull at the containerd level, before any manifest parsing.

---

## Harbor Proxy Cache Projects

On the Harbor side, each upstream registry becomes a **proxy cache project**. A proxy cache project has no images stored in git or pushed by anyone — it is purely a pull-through cache. When Harbor receives a request for `docker-hub/nginx:alpine`, it:

1. Checks its local storage for `nginx:alpine` (same digest as Docker Hub's)
2. If found and the manifest hasn't expired: serves from local storage
3. If not found: pulls from the configured upstream registry, stores it, serves it

The four proxy cache projects on minicloud:

| Harbor project name | Upstream registry | Registry type in Harbor |
|---|---|---|
| `docker-hub` | `https://registry-1.docker.io` | Docker Hub |
| `ghcr` | `https://ghcr.io` | Docker Registry (OCI-compatible) |
| `quay` | `https://quay.io` | Docker Registry (OCI-compatible) |
| `k8s-registry` | `https://registry.k8s.io` | Docker Registry (OCI-compatible) |

The project name in Harbor **must exactly match** the path segment in `registries.yaml`. The mirror endpoint `harbor.10.0.0.200.nip.io/v2/docker-hub` routes to the Harbor project named `docker-hub`. If you create the project as `proxy-docker` but the mirror path says `docker-hub`, every pull misses cache and goes to the fallback — you get no rate limit protection and no vulnerability scanning.

One gotcha worth documenting: Harbor lists `quay` as a supported registry type, but when you try to create a proxy cache project against a `quay`-type registry, the API returns `400: unsupported registry type quay`. The fix is to register the Quay upstream as `docker-registry` (generic OCI) instead of `quay` — Quay's V2 API is fully OCI-compatible and Harbor's generic OCI proxy works correctly against it.

---

## Why This Matters Beyond Rate Limits

Docker Hub rate limits are the obvious motivation, but the architecture delivers several other properties that matter in production:

**Vulnerability scanning at the chokepoint.** Harbor runs Trivy. Every image that passes through the proxy cache is scanned. If you enable "Prevent vulnerable images" at project level, no image with a Critical CVE can be pulled into the cluster — even if it is a publicly published upstream image that a manifest references directly. The Kubernetes scheduler sees a 403 from Harbor and the pod stays Pending instead of running vulnerable code.

**Reproducibility under network partition.** A bare-metal cluster in a home lab or office does not have enterprise internet SLAs. If your cluster can survive a 4-hour internet outage, it is because every image your workloads need is already in Harbor's cache from the last pull. During a power failure recovery on minicloud — where all 5 nodes restart simultaneously and try to pull images at once — Harbor serves everything from local storage. No image pull failures, no pods stuck in `ImagePullBackOff`.

**Audit trail for all image pulls.** Harbor logs every pull request: which image, which tag, which digest, at what time, authenticated as which user or service account. On a cluster with 70 running workloads, knowing that `set-hog` pulled `quay.io/prometheus/prometheus:v2.54.0` at 03:47 on 2026-08-02 is occasionally useful for incident investigation.

**Supply chain integrity for CI-built images.** The fifth entry in the `registries.yaml` mirror list — `harbor.10.0.0.200.nip.io` pointing to itself — ensures that CI-built images (your own services, custom Backstage image, custom Open WebUI) are also served through Harbor with no special treatment. cosign signatures are stored as Harbor artifacts alongside the image. Trivy scans your own images with the same policy as upstream images. The entire fleet's image provenance flows through one system.

---

## The Pull Flow, Step by Step

Here is exactly what happens when k3s schedules `harbor-core` onto a node after a fresh Harbor database wipe (which requires Harbor to re-pull its own images):

```
1. Scheduler assigns pod to node fast-skunk
2. kubelet asks containerd: pull goharbor/harbor-core:v2.14.0
3. containerd checks registries.yaml: "docker.io" → mirror harbor.10.0.0.200.nip.io/v2/docker-hub
4. containerd sends: GET harbor.10.0.0.200.nip.io/v2/docker-hub/goharbor/harbor-core/manifests/v2.14.0
5. Harbor: checks docker-hub project cache → cache miss (fresh DB)
6. Harbor: authenticates to registry-1.docker.io (with stored credentials if configured)
7. Harbor: pulls manifest + layers from Docker Hub
8. Harbor: stores layers in harbor-registry PVC (20Gi Longhorn)
9. Harbor: returns manifest to containerd
10. containerd: pulls layers from Harbor (same request, now cache hit)
11. Node: image unpacked, pod starts
```

On subsequent pulls of the same image (same digest), step 6–8 are skipped entirely. Harbor answers from its own storage. Docker Hub is never contacted.

---

## What Breaks When Harbor Goes Down

This architecture creates a single point of failure: if Harbor is down and an image is not already on the node, the pod cannot start. The fallback endpoints in `registries.yaml` mitigate this, but they expose you to rate limits again and require outbound internet access that may not always be available.

The operational answer is to treat Harbor with the same reliability posture as your ingress controller or DNS: keep it on a stable node (`fast-skunk`, pinned via nodeSelector), use Longhorn with 3 replicas for its PVCs, and alert on Harbor pod restarts. During planned Harbor maintenance, pre-pull any images you know will be needed.

On minicloud, this played out once when harbor-database's Longhorn PVC faulted and Harbor was unavailable for ~40 minutes. During that window, nodes that already had images cached locally were unaffected. Pods that needed image pulls were stuck in `ImagePullBackOff` — they fell back to Docker Hub and hit rate limits because the anonymous pull quota was already consumed from earlier in the day. The lesson: a pull-through cache is not the same as a local registry. Containerd does not pre-populate nodes; it only caches after the first pull. For critical workloads, `imagePullPolicy: IfNotPresent` with pre-pulled images on each node is the only true offline guarantee.

---

## Configuration Reference

**Creating a proxy cache registry in Harbor (API):**

```bash
HARBOR_PASS=$(ssh controller "cat ~/.harbor-admin")

# Register the upstream (example: ghcr.io)
curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:${HARBOR_PASS}" \
  -X POST "https://harbor.10.0.0.200.nip.io/api/v2.0/registries" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "ghcr-upstream",
    "type": "docker-registry",
    "url": "https://ghcr.io",
    "insecure": false
  }'

# Get the registry ID from the response, then create the proxy project
curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:${HARBOR_PASS}" \
  -X POST "https://harbor.10.0.0.200.nip.io/api/v2.0/projects" \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name": "ghcr",
    "registry_id": <ID_FROM_ABOVE>,
    "public": true
  }'
```

**Verifying the mirror is working:**

```bash
# On any node, watch containerd pull through Harbor:
ssh controller "journalctl -u k3s -f | grep 'pulling from'"

# Or check Harbor's pull count via API:
curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:${HARBOR_PASS}" \
  "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/ghcr" \
  | python3 -c "import sys,json; p=json.load(sys.stdin); print('pulls:', p['metadata'].get('pull_count', 0))"
```

**Critical: project names must match mirror paths.** The mirror config `harbor.10.0.0.200.nip.io/v2/docker-hub` requires a Harbor project named exactly `docker-hub`. The `/v2/` prefix and the project name form the containerd pull URL.

---

## Summary

The minicloud registry architecture is deliberately simple: one Harbor instance, four proxy cache projects, one `registries.yaml` on every node. No image pull authentication secrets in namespaces. No special handling in Helm values or Kustomize overlays. Every node pulls every image from Harbor, Harbor fetches from upstream when needed, and Docker Hub rate limits are a problem that no longer exists in day-to-day operations.

The more interesting property is the supply chain consolidation: every image, whether it was built by CI and pushed to `library/my-service`, or pulled through the cache from `ghcr.io/someproject/tool`, passes through the same Harbor instance, gets scanned by the same Trivy policy, and appears in the same audit log. For a platform that runs insurance workloads where image provenance matters for regulatory compliance, that single chokepoint is worth more than the Docker Hub rate limit fix.
