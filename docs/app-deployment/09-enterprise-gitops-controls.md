---
id: enterprise-gitops-controls
title: Enterprise GitOps Controls
sidebar_position: 9
---

# Enterprise GitOps Controls

Five controls turn a working GitOps repo into an auditable, production-safe one. Each addresses a concrete failure mode: unreviewed production changes, invisible diffs, noisy audit trails, implicit cluster coupling, and a flat directory that gives no signal about blast radius.

---

## 1. CODEOWNERS — Mandatory Review for Production Paths

**File:** `.github/CODEOWNERS`

GitHub automatically requests a review from `@AndreLair` when any PR touches the following paths:

| Path | Why it's gated |
|------|----------------|
| `services/*/minicloud-1/prod/` | Production overlay — any change here deploys to prod |
| `helm-values/minicloud-1/` | All Helm values for running platform tools |
| `manifests/rbac/` | Cluster-wide role bindings — security-sensitive |
| `manifests/network-policies/*-prod.yaml` | Production network isolation |
| `bootstrap/` | Root ArgoCD app — affects the entire cluster if misconfigured |

Dev and staging paths have no CODEOWNERS entry. A developer can freely open a PR against `services/platform-demo/minicloud-1/dev/` without blocking on a review, but touching `prod/` requires explicit approval.

The CODEOWNERS rule is enforced at the GitHub branch protection level — if the required reviewer has not approved, the PR cannot be merged regardless of other status checks passing.

---

## 2. PR Manifest Diff — Rendered Output on Every PR

**File:** `.github/workflows/pr-manifest-diff.yml`

Triggered by: any PR touching `services/**/minicloud-1/**`, `helm-values/**`, `manifests/**`, or `environments/**`.

What it does:

1. For each changed Kustomize overlay, runs `kustomize build` on the base branch and on the PR head, then diffs the rendered YAML.
2. For each changed `helm-values/minicloud-1/*.yaml`, shows a plain unified diff of the values file.
3. Posts the result as a collapsible comment on the PR. If you push another commit, the comment is updated — no duplicate spam.

What reviewers see:

```diff
- replicas: 1
+ replicas: 3

- memory: "256Mi"
+ memory: "512Mi"
```

Rather than: "kustomization.yaml changed line 4: `newTag: abc123` → `newTag: def456`".

The rendered diff shows exactly which Kubernetes resources change, including resources that inherit values from the base. A reviewer can approve a production overlay change knowing precisely what will land in the cluster.

Diffs longer than 400 lines are truncated with a notice.

---

## 3. Scoped Change Records — Audit Trail for Production Only

**File:** `.github/workflows/change-record.yml`

A change record (GitHub Issue) is created automatically when a PR merges **and** at least one of these conditions is true:

- The PR touches a production overlay (`*/minicloud-1/prod/**`)
- The PR touches `helm-values/minicloud-1/`
- The PR touches `manifests/rbac/`, `manifests/network-policies/`, or `bootstrap/`
- The PR is classified as `risk: medium` or `risk: high` in the PR template

Change records for a production merge look like this:

```
Title: [CHANGE] 2026-08-02 [PROD] — feat: increase platform-demo memory limits

Merged by: @AndreLair
Date: 2026-08-02 at 14:30 UTC
Change type: normal
Risk level: medium
Affected services: platform-demo (Helm: harbor)
Files changed: 3 | Commits: 1
Labels: change-record, change-type: normal, risk: medium, scope: production
```

The issue carries a post-change verification checklist:
- ArgoCD app(s) Synced + Healthy
- No new Gatekeeper violations
- Relevant pods Running / Ready

**What does not create a change record:** dev image-tag bumps, staging config changes with `risk: low`. These were creating noise before — every CI-automated tag bump to dev produced an issue, making the audit trail useless.

### Classifying a change

Use the PR template checkboxes (already in `.github/PULL_REQUEST_TEMPLATE.md`):

```markdown
- [x] `normal`   ← ticked
- [ ] `emergency`
- [ ] `standard`

- [x] `medium`   ← ticked
- [ ] `high`
- [ ] `low`
```

---

## 4. Cluster Dimension in Paths

The directory hierarchy includes the cluster name as an explicit level:

```
services/platform-demo/minicloud-1/dev/
                        ──────────
                        cluster name
```

Before this change, the path was `services/platform-demo/overlays/dev/`. The word `overlays` carries no information — every Kustomize repo uses it. `minicloud-1` names the cluster.

If a second cluster (`minicloud-2`) were added, the overlay for its dev environment would live at `services/platform-demo/minicloud-2/dev/`. The ArgoCD Application pointing to it would be:

```yaml
path: services/platform-demo/minicloud-2/dev
```

No other structural change is needed. The cluster dimension is built into the tree from day one rather than discovered as a requirement when the second cluster arrives.

The same convention applies to Helm values:

```
helm-values/minicloud-1/argocd-values.yaml
            ──────────
            cluster name
```

A second cluster would add `helm-values/minicloud-2/argocd-values.yaml` with different resource limits, replica counts, or endpoint URLs — the per-cluster override is an isolated file, not a merged section.

### Note on `../../base`

Because `minicloud-1/dev/` sits at the same depth as the old `overlays/dev/`, the relative path `../../base` in every `kustomization.yaml` file still resolves to `services/<app>/base/`. No kustomization.yaml file required changes during the rename.

---

## 5. apps/ Split — Platform vs Workloads

The ArgoCD Application directory is split into two subdirectories:

```
apps/
├── platform/    ← 43 infrastructure apps
│   ├── argo-cd.yaml
│   ├── vault.yaml
│   ├── cilium.yaml
│   ├── harbor.yaml
│   └── …
└── workloads/   ← 28 application services
    ├── platform-demo.yaml
    ├── minicloud-plane.yaml
    ├── backstage.yaml
    └── …
```

**Platform** apps are infrastructure tooling owned by the platform operator: ArgoCD itself, Vault, cert-manager, Cilium, Harbor, Prometheus, Grafana, Loki, Gatekeeper, Falco, NATS, KEDA, Velero, and similar. Changing a platform app is a platform-level event.

**Workloads** are business services: platform-demo, minicloud-plane, Backstage, Plane CE, ERPNext, Jitsi, Matrix, LiteLLM, Open WebUI, and similar. Changing a workload app affects a service, not the cluster itself.

This split makes it immediately clear what kind of change is being made. A PR touching only `apps/workloads/platform-demo.yaml` carries no platform risk. A PR touching `apps/platform/cilium.yaml` touches the CNI and needs more scrutiny.

The root Application (`bootstrap/root-app.yaml`) uses `recurse: true` to scan both subdirectories:

```yaml
source:
  path: apps
  directory:
    recurse: true
```

Without `recurse: true`, ArgoCD would scan only `apps/` root and find nothing. This was applied to the cluster before the file move to avoid any gap.

---

## Applying These Controls to a New Service

When adding a service via `services/_template/`:

1. **CODEOWNERS** — no action needed; `services/*/minicloud-1/prod/` is already gated.
2. **PR diff** — no action needed; the workflow triggers on `services/**/minicloud-1/**` automatically.
3. **Change record** — no action needed; any prod overlay PR will produce a record.
4. **Cluster dimension** — use `minicloud-1/{dev,staging,prod}` (the template already has this structure).
5. **apps/ split** — add your Application YAML to `apps/workloads/<name>.yaml`; infrastructure goes to `apps/platform/`.
