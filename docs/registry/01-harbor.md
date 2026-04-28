---
id: harbor
title: Phase 7 — Harbor + Trivy
sidebar_position: 1
---

# Harbor — Self-Hosted Container Registry with Trivy Scanning

Harbor is an enterprise-grade private container registry. It stores OCI images in the cluster, scans every push for CVEs via **Trivy**, and serves pulls back to Kubernetes nodes. After this phase, every image used by the platform can live entirely inside the cluster — no Docker Hub dependency, no rate limits, no leak of internal artifact names to the public.

This phase composes the previous five: Harbor's containers run on **k3s**, store image blobs and metadata on **Longhorn** PVCs (5 of them), are exposed as a single **Ingress** through the **F5 NGINX Ingress Controller** that **MetalLB** assigned `10.0.0.200` to, and are reachable from anywhere via **Tailscale's** subnet route to that IP. Phase 5–6 layers all paying off at once.

---

## Architecture

```text
docker push / crane / kubelet pull
       │
       ▼
DNS: harbor.10.0.0.200.nip.io  → 10.0.0.200
       ▼
MetalLB-advertised ARP for 10.0.0.200 (port 80)
       ▼
F5 NGINX Ingress Controller
       │  Host header → harbor-portal (UI) or harbor-core (API + registry)
       ▼
Harbor Core ──► Harbor Registry ──► Longhorn PVC (20 GiB, image blobs)
   │                │
   │                └──► Trivy ──► Longhorn PVC (5 GiB, vuln DB cache)
   │
   ├──► Harbor Database (PostgreSQL on Longhorn PVC)
   ├──► Harbor Redis (Longhorn PVC)
   └──► Harbor Jobservice (Longhorn PVC, async work queue)
```

---

## Decisions Made for This Cluster

| | Decision | Reasoning |
|---|---|---|
| Exposure | `expose.type=ingress` | Use the existing Phase 6 NGINX Ingress; one IP fronts everything. Doesn't burn a second MetalLB IP. |
| TLS | HTTP-only (`expose.tls.enabled=false`) | TLS is Phase 15 (cert-manager + Let's Encrypt). Self-signed certs would need to be propagated to every containerd trust store on every node. |
| Storage | Longhorn for all 5 PVCs | RWO is fine for Harbor; replication gives node-failure tolerance. `registry` 20 GiB (resizable later via Longhorn `allowVolumeExpansion`); others at chart defaults. |
| Trivy | enabled | Half the value of running Harbor instead of a plain registry is automatic CVE scanning. |
| k3s registries.yaml mirror | added (with caveats — see "Pull-side limitation" below) | Tells containerd to use HTTP for `harbor.10.0.0.200.nip.io`. |

---

## Step 1 — Generate an Admin Password

Don't hardcode `Admin12345` like the upstream docs suggest — generate a random one and store it locally with `0600` permissions.

```bash
openssl rand -base64 24 > ~/.harbor-admin
chmod 600 ~/.harbor-admin
```

---

## Step 2 — Install Harbor via Helm

```bash
helm repo add harbor https://helm.goharbor.io
helm repo update

helm install harbor harbor/harbor \
  --namespace harbor --create-namespace \
  --set expose.type=ingress \
  --set expose.ingress.hosts.core=harbor.10.0.0.200.nip.io \
  --set expose.ingress.className=nginx \
  --set expose.ingress.controller=default \
  --set expose.tls.enabled=false \
  --set-string "expose.ingress.annotations.nginx\.org/client-max-body-size=0" \
  --set externalURL=http://harbor.10.0.0.200.nip.io \
  --set persistence.persistentVolumeClaim.registry.storageClass=longhorn \
  --set persistence.persistentVolumeClaim.registry.size=20Gi \
  --set persistence.persistentVolumeClaim.database.storageClass=longhorn \
  --set persistence.persistentVolumeClaim.redis.storageClass=longhorn \
  --set persistence.persistentVolumeClaim.jobservice.storageClass=longhorn \
  --set persistence.persistentVolumeClaim.trivy.storageClass=longhorn \
  --set "harborAdminPassword=$(cat ~/.harbor-admin)" \
  --set trivy.enabled=true
```

**Two flags worth knowing:**

- `--set-string "expose.ingress.annotations.nginx\.org/client-max-body-size=0"` — F5 NGINX defaults to 1 MiB request bodies. Image layer pushes can be hundreds of megabytes; without this the very first `docker push` of any non-trivial image returns `413 Request Entity Too Large`. The value `0` means "unlimited." The `--set-string` (not `--set`) is required because `0` is otherwise parsed as an integer and Kubernetes annotation values must be strings.
- `expose.ingress.controller=default` — Harbor's chart needs to know which ingress flavor it's targeting; `default` is the right value for F5 NGINX (and for community ingress-nginx).

Wait for all 7 Harbor pods to reach Ready:

```bash
kubectl get pods -n harbor --watch
```

Expect:
- `harbor-portal` (UI) — Ready first
- `harbor-redis-0` — Ready
- `harbor-database-0` — Ready (~30 s for postgres init)
- `harbor-trivy-0` — Ready
- `harbor-registry` (2/2 — registry + registryctl sidecar) — Ready
- `harbor-core` — Ready (after database + redis)
- `harbor-jobservice` — Ready last; **expect 2–3 restarts here** while it waits for core/db. Normal.

Total time-to-ready: ~2–3 minutes.

---

## Step 3 — Verify the Install

```bash
# API ping (no auth)
curl -s http://harbor.10.0.0.200.nip.io/api/v2.0/ping
# Pong

# Trivy scanner registered as default
curl -s -u admin:$(cat ~/.harbor-admin) \
  http://harbor.10.0.0.200.nip.io/api/v2.0/scanners | python3 -m json.tool
# [{ "name": "Trivy", "is_default": true, ... }]
```

Browse the UI: `http://harbor.10.0.0.200.nip.io` — login with `admin` + the password from `~/.harbor-admin`.

---

## Step 4 — Push an Image (Push-Side Workflow)

### Why `docker push` doesn't work cleanly with HTTP-only Harbor

Docker 25+ (we're on 29) defaults to HTTPS for any registry, and `insecure-registries` only weakens TLS verification — it doesn't make Docker fall back to HTTP cleanly when HTTPS fails. With Harbor on HTTP-only behind a port-80-only Ingress, `docker push` fails with one of these:

```text
remote error: tls: unrecognized name
http: server gave HTTP response to HTTPS client
dial tcp 10.0.0.200:443: connect: no route to host
```

This isn't a Harbor problem; it's a Docker-on-modern-Linux problem. Two ways forward:

- **Now (Phase 7):** use [`crane`](https://github.com/google/go-containerregistry) — Google's standalone OCI tool that talks plain HTTP correctly when told `--insecure`.
- **Later (Phase 15):** put real TLS on the Ingress with cert-manager + Let's Encrypt (or an internal CA) and `docker push` works without any flags.

### Push with `crane`

Install crane (no sudo, no Docker daemon):

```bash
CRANE_VER=v0.20.6
curl -sL https://github.com/google/go-containerregistry/releases/download/${CRANE_VER}/go-containerregistry_Linux_x86_64.tar.gz \
  | tar -xz -C ~/.local/bin/ crane
chmod +x ~/.local/bin/crane
```

Login + copy:

```bash
crane auth login harbor.10.0.0.200.nip.io \
  -u admin -p "$(cat ~/.harbor-admin)"

crane copy busybox:1.36 \
  harbor.10.0.0.200.nip.io/library/busybox:1.36 \
  --insecure
```

`crane copy` is faster than `docker pull && docker tag && docker push` because crane streams blobs directly from one registry to another without ever materializing them on local disk.

---

## Step 5 — Trivy Scan on Push

Harbor auto-scans every artifact on push. Check the scan result via API:

```bash
curl -s -u admin:$(cat ~/.harbor-admin) \
  "http://harbor.10.0.0.200.nip.io/api/v2.0/projects/library/repositories/busybox/artifacts/sha256:<digest>?with_scan_overview=true"
```

For our `busybox:1.36` push (per-architecture amd64 image):

| Field | Value |
|---|---|
| Status | `Success` |
| Scan duration | 33 s |
| **Total CVEs** | **0** |
| Severity | None (clean) |

`busybox:1.36` is a clean upstream image — no CVEs at all. Try this same scan on something heavier (e.g. `nginx:1.20-alpine`) and you'll see a realistic distribution of LOW/MEDIUM/HIGH/CRITICAL findings.

### Multi-arch image gotcha

When pushing a multi-arch manifest (busybox ships ~8 platform images), Trivy spawns one scan job per platform in parallel. On a fresh install with cold Trivy DB, this can hit a Redis connection-pool exhaustion in the harbor-redis pod, leaving 1–2 sub-image scans stuck in `Running` while the rest succeed. Symptom in logs:

```text
Error while enqueuing scan job: redis: connection pool exhausted
```

The per-platform results are still reachable — query the child digest directly. The parent index status will eventually rectify (or you can re-trigger with `POST /api/v2.0/.../scan`).

---

## Step 6 — Pull from k3s (Pull-Side Workflow)

### k3s registries.yaml — the mirror config

To make k3s/containerd pull from Harbor over HTTP, write `/etc/rancher/k3s/registries.yaml` on **every node**:

```yaml
configs:
  "harbor.10.0.0.200.nip.io":
    tls:
      insecure_skip_verify: true
mirrors:
  "harbor.10.0.0.200.nip.io":
    endpoint:
      - "http://harbor.10.0.0.200.nip.io"
```

Then restart k3s on each node:

```bash
sudo systemctl restart k3s         # control plane
sudo systemctl restart k3s-agent   # workers
```

K3s renders this into containerd's `hosts.toml` at `/var/lib/rancher/k3s/agent/etc/containerd/certs.d/harbor.10.0.0.200.nip.io/hosts.toml`.

### Pull-side limitation (deferred to Phase 15)

In our testing, even with the mirror config above, kubelet pulls of `harbor.10.0.0.200.nip.io/library/busybox:1.36` failed with:

```text
dial tcp 10.0.0.200:443: connect: no route to host
```

The cause: k3s's registries.yaml renderer appends `/v2` to the mirror URL, producing `[host."http://harbor.10.0.0.200.nip.io/v2"]` in the rendered hosts.toml. Some containerd builds don't match that URL pattern correctly when the mirror hostname equals the target hostname, falling through to the `server = "https://..."` fallback line. Manually editing the generated hosts.toml works briefly but k3s overwrites it on every restart.

**This is fully solved by Phase 15** — once cert-manager issues a real cert and Harbor moves to HTTPS, the entire HTTP/HTTPS fallback dance disappears: kubelet talks HTTPS to a real cert and pulls succeed without any registries.yaml gymnastics.

For Phase 7's purposes:
- ✅ **Push works** (via crane)
- ✅ **Trivy scans work** (auto-scan on push, 0 CVEs in busybox 1.36)
- ✅ **UI + API reachable** through the Ingress
- ⚠️ **Pull from k3s deferred** to Phase 15 (TLS fix)

---

## Robot Accounts for CI/CD

Once CI/CD is in (Phase 13), every pipeline gets a robot account instead of using the admin password:

```text
Harbor UI → Projects → library → Robot Accounts
→ + NEW ROBOT ACCOUNT
   Name:        ci-builder
   Permissions: push + pull (for the project only)
→ Save → copy the generated token (only shown once)
```

In CI:

```bash
crane auth login harbor.10.0.0.200.nip.io \
  -u 'robot$ci-builder' -p "$HARBOR_TOKEN"
crane copy myapp:$CI_COMMIT_SHA \
  harbor.10.0.0.200.nip.io/library/myapp:$CI_COMMIT_SHA --insecure
```

---

## Result on This Cluster

Installed and verified on 2026-04-28:

| | |
|---|---|
| Harbor chart version | `harbor/harbor` (latest, app `2.14.3`) |
| Pods Running | 7 (core, jobservice, portal, registry [2/2], database, redis, trivy) |
| PVCs (Longhorn) | 5 — registry 20 GiB, others 1–5 GiB |
| Ingress hostname | `harbor.10.0.0.200.nip.io` (HTTP-only) |
| Default scanner | Trivy (via Harbor scanner-adapter) |
| First image pushed | `library/busybox:1.36` (multi-arch via `crane copy`) |
| First Trivy result | amd64 image — 0 CVEs, scan duration 33 s |
| Admin password | random, in `~/.harbor-admin` (mode 600) |

---

## Done When

```text
✔ All 7 Harbor pods Ready
✔ 5 PVCs Bound on Longhorn
✔ UI reachable at http://harbor.10.0.0.200.nip.io
✔ Trivy registered as the default scanner
✔ At least one image pushed (via crane)
✔ At least one Trivy scan completed Successfully
```
