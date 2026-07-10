---
id: ci-registry-migration
title: CI Registry Migration — Tailscale + Harbor Direct
sidebar_label: CI Registry Migration
---

# CI Registry Migration — Tailscale + Harbor Direct

## Why We Migrated

All 6 custom image repos previously used one of two registry paths:

| Old path | Repos | Problem |
|---|---|---|
| `harbor.devandre.sbs` (Cloudflare tunnel) | platform-demo, ktayl-solution-web, markitdown-proxy, rag-ingest | **~100 MB Cloudflare body-size limit** — any push above that got `413 Payload Too Large` |
| `ghcr.io` + `crane copy` to Harbor | litellm-custom | Two-step push; GHCR token management; extra CI step |

The fix: join the minicloud Tailscale tailnet from the GitHub Actions runner, then push directly to `harbor.10.0.0.200.nip.io` (MetalLB IP) over the LAN. No Cloudflare in the path, no size limit, no secondary crane copy.

---

## Architecture After Migration

```
GitHub Actions runner
       │
       │  tailscale/github-action@v3 (TAILSCALE_AUTH_KEY secret)
       ▼
 Tailscale tailnet
       │
       │  direct LAN (MetalLB)
       ▼
harbor.10.0.0.200.nip.io  ──►  kubelet pulls same IP in-cluster
```

All 6 repos now use a single registry path: `harbor.10.0.0.200.nip.io/library/<name>`.

---

## CI Workflow Pattern

Every migrated repo follows the same steps in its CI workflow:

### 1. Connect to Tailscale

```yaml
- name: Connect to Tailscale
  uses: tailscale/github-action@v3
  with:
    authkey: ${{ secrets.TAILSCALE_AUTH_KEY }}
    version: latest
```

The auth key is a reusable ephemeral key from the Tailscale admin console (Settings → Keys). Each runner joins the tailnet for the duration of the job and is automatically removed.

### 2. Trust the minicloud CA

```yaml
- name: Trust minicloud CA
  run: |
    sudo mkdir -p /etc/docker/certs.d/harbor.10.0.0.200.nip.io
    echo "${{ secrets.MINICLOUD_CA_CERT }}" \
      | sudo tee /etc/docker/certs.d/harbor.10.0.0.200.nip.io/ca.crt
    echo "${{ secrets.MINICLOUD_CA_CERT }}" \
      | sudo tee /usr/local/share/ca-certificates/minicloud-ca.crt
    sudo update-ca-certificates
```

Two locations are required:
- `/etc/docker/certs.d/…/ca.crt` — Docker daemon (image pulls/pushes)
- `/usr/local/share/ca-certificates/` + `update-ca-certificates` — cosign and crane (Go TLS)

### 3. Set up BuildKit with insecure registry

```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3
  with:
    buildkitd-config-inline: |
      [registry."harbor.10.0.0.200.nip.io"]
        insecure = true
```

The BuildKit **container** driver runs in its own network namespace and does **not** inherit `/etc/docker/certs.d/` from the host. The `insecure = true` flag tells BuildKit to skip TLS verification for this registry when pushing layers.

### 4. Build and push

```yaml
- name: Build and push
  uses: docker/build-push-action@v6
  with:
    push: true
    tags: harbor.10.0.0.200.nip.io/library/<name>:<sha>
    platforms: linux/amd64
    cache-from: type=gha
    cache-to:   type=gha,mode=max
```

---

## Required Repository Secrets

| Secret | Value source |
|---|---|
| `TAILSCALE_AUTH_KEY` | Tailscale admin console → Settings → Auth Keys (reusable, ephemeral) |
| `MINICLOUD_CA_CERT` | Contents of `~/minicloud-ca.crt` on Mac |
| `HARBOR_USER` | `admin` |
| `HARBOR_PASSWORD` | `ssh controller 'cat ~/.harbor-admin'` |
| `GITOPS_TOKEN` | GitHub PAT with `repo` scope on `andrelair-platform/minicloud-gitops` |
| `GPG_PRIVATE_KEY` | `gpg --armor --export-secret-keys FD6D39D681DEFA34` |

---

## Repos Migrated

| Repo | Image | GitOps auto-bump |
|---|---|---|
| `platform-demo` | `library/platform-demo` | ✅ `services/platform-demo/overlays/<branch>/kustomization.yaml` |
| `ktayl-solution-web` | `library/ktayl-solution-web` | ✅ `manifests/ktayl-solution-web/00-deployment.yaml` |
| `minicloud-markitdown-proxy` | `library/markitdown-proxy` | ✅ `manifests/ai/…` |
| `minicloud-rag-ingest` | `library/rag-ingest` | ✅ `manifests/ai/…` |
| `minicloud-litellm-custom` | `library/litellm-custom` | ✅ `manifests/ai/01-litellm-deployment.yaml` |
| `minicloud-postgresql-noavx512` | `library/postgresql` | ❌ version-tagged manually |
| `minicloud-backstage` | `library/backstage` | ❌ bumped via release workflow |

---

## Harbor Disk Management

Harbor registry PVC (`pvc-46beb573`, Longhorn RWO, 20 Gi) fills up as old image layers accumulate.

**Trigger GC manually when disk approaches 80%:**

```bash
HARBOR_PASS=$(ssh controller "cat ~/.harbor-admin")
ssh controller "/usr/bin/curl -sk -u admin:${HARBOR_PASS} \
  -X POST 'https://harbor.10.0.0.200.nip.io/api/v2.0/system/gc/schedule' \
  -H 'Content-Type: application/json' \
  -d '{\"schedule\":{\"type\":\"Manual\"}}'"

# Check GC result
ssh controller "/usr/bin/curl -sk -u admin:${HARBOR_PASS} \
  'https://harbor.10.0.0.200.nip.io/api/v2.0/system/gc' | python3 -m json.tool | head -20"
```

**Check disk after GC:**

```bash
ssh controller "kubectl exec -n harbor \
  \$(kubectl get pod -n harbor -l component=registry -o jsonpath='{.items[0].metadata.name}') \
  -- df -h /storage"
```

The GC that triggered this runbook freed **11 GB** (303 blobs + 62 manifests purged), dropping the PVC from 100% to 47%.

### Harbor registry Longhorn Multi-Attach deadlock

If a rolling update stalls with one old and one new registry pod stuck, the Longhorn RWO PVC can't attach to both simultaneously. Fix:

```bash
kubectl patch deployment harbor-registry -n harbor \
  -p '{"spec":{"strategy":{"rollingUpdate":{"maxUnavailable":1}}}}'
```

This lets the old pod terminate first, releasing the PVC before the new pod starts.

---

## Gotchas

### BuildKit `insecure = true` is mandatory

`docker/build-push-action@v6` uses the `docker-container` BuildKit driver by default. This driver runs BuildKit in a separate container that **does not inherit** the Docker daemon's `/etc/docker/certs.d/` directory. Without `insecure = true` in `buildkitd-config-inline`, layer pushes to Harbor fail with TLS errors even though `docker login` succeeds on the host.

### `apk upgrade` in `nginx-unprivileged` images

`nginxinc/nginx-unprivileged` sets `USER nginx` in the image. Running `apk upgrade` as a non-root user fails with:

```
ERROR: Unable to open log: Permission denied
exit code: 99
```

The fix:

```dockerfile
FROM nginxinc/nginx-unprivileged:1.28-alpine
USER root
RUN --network=host apk update && apk upgrade --no-cache
USER nginx
```

Two additional requirements:
- `buildkitd-flags: --allow-insecure-entitlement network.host` on `docker/setup-buildx-action`
- `allow: network.host` on `docker/build-push-action`

Without both, `RUN --network=host` is rejected with `network.host is not allowed`.

### `apk upgrade` needs `apk update` first (apk-tools 3.x)

Alpine 3.22 ships `apk-tools` 3.x. Without a preceding `apk update`, `apk upgrade --no-cache` exits 99 because there is no local package index to compare against and `--no-cache` prevents downloading one implicitly.

### cosign and crane require system CA trust

Both tools use Go's native TLS, which reads from the system certificate store (`update-ca-certificates`), not from `/etc/docker/certs.d/`. Always run both the docker certs step and the system CA step.

### Tailscale auth key rotation

The auth key `TAILSCALE_AUTH_KEY` is a shared secret across all 6 repos. If it expires or is revoked, all CI pipelines break simultaneously. Rotate it in all 6 repos' GitHub secrets at the same time. Generate a new key from the Tailscale admin console (reusable, ephemeral, no expiry or set a long one).
