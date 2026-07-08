---
id: dependency-auditability
title: Dependency Auditability — Version Pinning, Digest Locking & Renovate
sidebar_label: Dependency Auditability
---

# Dependency Auditability — Version Pinning, Digest Locking & Renovate

Every open-source tool deployed via Helm (Open WebUI, Grafana, Vault, cert-manager, etc.) has no source code in this repository. That creates a silent auditability gap: configuration changes are git-tracked, but the upstream software versions, why they were chosen, and what changed between versions are not.

This runbook documents the three-layer strategy used to close that gap on minicloud.

---

## The Problem: What Was Not Auditable

When a Helm-managed tool is deployed with a wildcard version like `"5.*"` or `"0.10.x"`, the actual version that gets installed depends on what the chart repository serves at sync time. Two syncs of the same ArgoCD app can install different chart versions — and nothing in git records which one ran when.

Similarly, a container image tag like `0.9.4` is **mutable**. An upstream maintainer can push a new build to that same tag. The next pod restart pulls different code with an identical version label, and your git history still says `0.9.4`.

There are three distinct gaps:

| Gap | Symptom | Root cause |
|---|---|---|
| Wildcard chart versions | Two ArgoCD syncs install different versions | `targetRevision: "5.*"` resolves differently over time |
| Mutable image tags | Pod restarts pull different code silently | `image: tool:1.2.3` tag can be overwritten by upstream |
| No upgrade trail | Unknown why a version was chosen or what changed | No link between git commits and upstream changelogs |

---

## Layer 1 — Exact Chart Version Pinning

All ArgoCD Application manifests in `minicloud-gitops/apps/` pin Helm charts to an exact version. No wildcards.

**Before (non-deterministic):**
```yaml
# apps/kured.yaml
targetRevision: "5.*"          # could resolve to 5.10, 5.11, 5.12 on any sync
```

**After (deterministic):**
```yaml
# apps/kured.yaml
targetRevision: "5.12.1"       # always resolves to exactly 5.12.1
```

Charts pinned during the 2026-07-08 hardening pass:

| Chart | Wildcard (before) | Pinned version (after) |
|---|---|---|
| kured | `5.*` | `5.12.1` |
| polaris | `6.*` | `6.0.0` |
| external-secrets | `0.10.x` | `0.10.7` |

All other charts were already on exact versions.

### How to find the running version when pinning

If an app is already deployed with a wildcard and you need to find what's actually running:

```bash
# From the Helm release label on any managed resource
kubectl get daemonset -n <namespace> <name> \
  -o jsonpath='{.metadata.labels.helm\.sh/chart}'
# → kured-5.12.1

# Or from the ArgoCD sync history
kubectl get application -n argocd <name> \
  -o jsonpath='{.status.history[-1].revision}'
# → 0.10.7
```

Pin to that exact version in the ArgoCD Application YAML, commit, and the next sync is a no-op (same version, now declared).

---

## Layer 2 — Image Digest Pinning

Chart version pinning locks the Helm chart. But the chart specifies an image tag, and tags are mutable. To lock the exact bytes of the running container, pin by digest.

A digest (`sha256:...`) is a content hash of the image layers — it is physically impossible for two different images to share the same digest. Unlike a tag, it cannot be overwritten.

### Open WebUI — digest pinned in helm-values

Open WebUI is the only chart where the image configuration is explicitly set in our Helm values (because the init containers reference the same image). The values file at `helm-values/open-webui-values.yaml` pins it:

```yaml
image:
  repository: ghcr.io/open-webui/open-webui
  tag: "0.9.4"
  digest: "sha256:172e1fe0e89af2a07f42f2b1d943f30c8ddd7b9c2e182f3678b4790cdb83abea"
  pullPolicy: IfNotPresent
```

The two init containers (`inject-minicloud-ca`, `patch-bm25-french`) also use the full digest reference:

```yaml
image: ghcr.io/open-webui/open-webui:0.9.4@sha256:172e1fe0e89af2a07f42f2b1d943f30c8ddd7b9c2e182f3678b4790cdb83abea
```

### How to get a digest for any image

```bash
# Using crane (already installed — used for Harbor pushes)
crane digest ghcr.io/open-webui/open-webui:0.9.4
# → sha256:172e1fe0e89af2a07f42f2b1d943f30c8ddd7b9c2e182f3678b4790cdb83abea

# Or via docker
docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/open-webui/open-webui:0.9.4
```

### How to upgrade (tag + digest together)

When a new Open WebUI version is released:

```bash
# 1. Get the new digest
crane digest ghcr.io/open-webui/open-webui:0.10.0

# 2. Update helm-values/open-webui-values.yaml:
#    - tag: "0.9.4"  →  tag: "0.10.0"
#    - digest: "sha256:172e..."  →  digest: "sha256:<new>"
#    - Both init container image lines

# 3. Commit with changelog reference:
git commit -S -m "chore(deps): bump open-webui 0.9.4 → 0.10.0

Changelog: https://github.com/open-webui/open-webui/releases/tag/v0.10.0
Digest: sha256:<new>
Review: checked ENABLE_MEMORY_FEATURE default — unchanged in 0.10.0"
```

The commit message IS the audit record. Reference the upstream changelog URL so future maintainers know what changed and that it was reviewed.

---

## Layer 3 — Renovate Bot (Automated Upgrade PRs)

Renovate Bot runs on `andrelair-platform/minicloud-gitops` via the [Mend Renovate GitHub App](https://developer.mend.io/github/andrelair-platform).

It scans the repository weekly (weekends) and opens pull requests when upstream releases a new version of any tracked chart or image. Each PR includes the upstream changelog — making the upgrade motivation visible without any manual research.

### What Renovate monitors

Configured in `renovate.json` at the repo root:

| Manager | Files watched | What it tracks |
|---|---|---|
| `argocd` | `apps/*.yaml` | `targetRevision` for all Helm chart sources |
| `helm-values` | `helm-values/*.yaml` | Container image tags referenced in values files |

### What a Renovate PR looks like

```
Title: chore(deps): bump open-webui from 14.4.0 to 14.5.0

## Release Notes
open-webui/open-webui (open-webui)
### v0.10.0
- feat: new memory management UI
- fix: ENABLE_MEMORY_FEATURE now defaults to false in fresh installs ← important!
- ...

Changelog: https://github.com/open-webui/open-webui/releases/tag/v0.10.0
```

The changelog is fetched automatically. You read it, decide if it's safe, and merge.

### Labels and review rules

| Chart | Label | Action required |
|---|---|---|
| vault, argo-cd, authentik | `manual-review-required` | Read changelog fully — these can break SSO or GitOps control plane |
| open-webui | `check-default-changes` | Check if any env var defaults changed — may affect feature behavior |
| cert-manager, external-secrets, nginx-ingress | `patch` | Patch updates are lower risk — still review before merging |
| All others | `dependencies`, `renovate` | Standard review |

### Schedule

Renovate runs every weekend. During the week, it queues discovered updates but does not open PRs. This prevents daily noise while ensuring nothing stays unpatched for more than 7 days.

### Dependency Dashboard

Renovate maintains a live **Dependency Dashboard** issue in `minicloud-gitops`. It shows:
- All packages currently tracked
- Which ones have available updates (pending the weekend schedule)
- Any PRs currently open
- Rate-limited or ignored updates

Find it at: `github.com/andrelair-platform/minicloud-gitops/issues` — look for the issue titled "Dependency Dashboard" opened by `renovate[bot]`.

---

## Audit Trail Summary

With all three layers in place, every dependency on the platform has a complete audit trail:

| Question | Where the answer lives |
|---|---|
| What chart version is running? | `apps/<name>.yaml` → exact `targetRevision` |
| What config was applied? | `helm-values/<name>-values.yaml` → git history |
| What exact image bytes are running? | `helm-values/open-webui-values.yaml` → `digest:` field |
| Why was this version chosen? | Renovate PR body → upstream changelog link |
| When was it upgraded? | Git commit timestamp on the merged Renovate PR |
| Who approved the upgrade? | GitHub PR merge — requires PR review |
| What changed upstream? | Renovate PR body embeds release notes |

---

## Operational Reference

### Check if an upgrade is available right now

```bash
# Check Renovate dashboard issue
gh issue list --repo andrelair-platform/minicloud-gitops --label renovate

# Or check latest chart version manually
helm repo add <name> <url>
helm search repo <chart> --versions | head -5
```

### Force Renovate to scan immediately (bypass weekend schedule)

Go to the Dependency Dashboard issue in GitHub and check the box next to any package — Renovate opens a PR immediately regardless of schedule.

Or trigger a full scan at: `https://developer.mend.io/github/andrelair-platform`

### Add digest pinning to a new chart

Only needed when you explicitly configure the image in your values file. For charts where you don't override the image, pinning the chart version (`targetRevision`) is sufficient — the chart pins the image tag internally.

```bash
# 1. Find the image the chart deploys
kubectl get deployment -n <ns> <name> \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# 2. Get its digest
crane digest <image>:<tag>

# 3. Add to helm-values/<name>-values.yaml
image:
  tag: "<tag>"
  digest: "sha256:<hash>"
```
