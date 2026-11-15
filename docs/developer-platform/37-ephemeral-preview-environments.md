---
title: Ephemeral Preview Environments (per-PR)
sidebar_label: Preview Environments
---

# Ephemeral Preview Environments

> **What:** opt-in, per-PR preview environments — label a pull request `preview` and an isolated,
> throwaway copy of the app is built and deployed at its own URL; unlabel or close the PR and it is
> automatically destroyed. This is the platform's **Environment Management** capability (the IDP
> "spin up an environment on demand" building block).
> **Why it's opt-in + cheap:** this is a resource-constrained 5-node cluster, so a full stack per
> *every* PR would be wasteful. Previews are **label-gated** (nothing happens unless you ask), run a
> **simplified, minimal** variant of the app (~1 small pod), and **cost nothing when none exist.**
> **Pilot / reference:** `platform-demo`. **Verified end-to-end** 2026-11-15.

---

## When to use it

Open a preview when you want to validate a **risky or boundary-crossing change on real infra without
polluting the shared `dev` environment** — a migration, a new network policy, an auth change, a UI you
want to click through. The shared `dev` environment stays clean; the preview is isolated and disposable.

It is **not** on by default and **not** per-every-PR — add the `preview` label only when a change warrants it.

## How to use it (the whole workflow)

1. Open a PR on the app repo (`platform-demo`).
2. Add the **`preview`** label.
3. CI builds a `pr-<n>-<sha>` image and the environment comes up within a couple of minutes at:
   **`https://demo-pr-<n>.10-0-0-200.nip.io`** (Tailscale + the minicloud CA; no SSO on previews).
4. Push more commits → the preview rebuilds and redeploys automatically (the `synchronize` event).
5. **Remove the `preview` label** (or merge/close the PR) → the environment is **destroyed** (the
   ArgoCD `resources-finalizer` prunes the app's resources).

## Architecture — how it works

```
 PR labelled `preview`  (andrelair-platform/platform-demo)
        │
        ▼  .github/workflows/preview.yml  (deploy-preview job)
   build pr-<n>-<sha> image  ──►  Harbor (dev registry)
        │
        ▼  writes a Helm ArgoCD Application + opens a PR on minicloud-gitops
   apps/previews/preview-pd-<n>.yaml
        │   (path: services/platform-demo/helm · valueFiles: [values-preview.yaml]
        │    · per-PR helm.valuesObject: image.tag + host + TLS cert)
        ▼  merged to main
   ArgoCD root-app (recurse) discovers it  ──►  syncs into ns preview-pd-<n>
        │
        ▼
   Deployment + Service + Ingress + Certificate   →   https://demo-pr-<n>.10-0-0-200.nip.io
        │
   unlabel / close PR  ──►  teardown-preview removes the Application
        ▼
   resources-finalizer.argocd.argoproj.io  prunes everything
```

| Piece | Where | Role |
|---|---|---|
| `preview.yml` | `platform-demo/.github/workflows/` | build the PR image + generate/remove the ArgoCD Application (label-gated) |
| `values-preview.yaml` | `minicloud-gitops/services/platform-demo/helm/` | the **simplified** preview overlay of the wrapper chart |
| `apps/previews/preview-pd-<n>.yaml` | `minicloud-gitops/apps/previews/` | the generated ArgoCD Application (one per live preview; auto-discovered) |

### A preview is a deliberately *simplified* app

The preview overlay (`values-preview.yaml`) renders a **cheap, minimal** variant so it proves the PR's
**code**, not the platform scaffolding (which `dev`/`prod` already demonstrate). Versus `dev`/`prod` it drops:

| Dropped | Why it's safe for a preview |
|---|---|
| **Vault agent injection** | the preview namespace isn't in the Vault k8s-auth role → the agent-init would block the pod; the demo app only needs `PORT`, never the injected secret |
| **SSO forward-auth** | previews are Tailscale-gated already — a plain ingress is enough |
| **KEDA scale-to-zero** | ingress backends straight onto the app Service; 1 tiny replica instead |
| **canary Rollout / ServiceMonitor / PDB** | a throwaway env needs none of them |

Result: ~1 pod at `100m/64Mi` when a preview exists, **zero footprint when none do**.

## Operate / verify

```bash
# the live previews (one Application per open, labelled PR):
kubectl --context minicloud get applications -n argocd | grep '^preview-pd-'
kubectl --context minicloud get ns | grep '^preview-pd-'

# a specific preview's resources:
kubectl --context minicloud -n preview-pd-<n> get deploy,pod,ingress,certificate

# reach it (Tailscale + minicloud CA; no SSO):
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://demo-pr-<n>.10-0-0-200.nip.io/healthz   # HTTP 200
```

**Teardown leaves an empty namespace.** ArgoCD's `CreateNamespace=true` auto-creates the preview namespace
but does **not** own its deletion, so after the Application is pruned the (empty) `preview-pd-<n>` namespace
lingers harmlessly. Remove it with `kubectl delete namespace preview-pd-<n>` when convenient.

## Gotchas (all proven in the 2026-11-15 end-to-end run)

- **nip.io host MUST use dash form for the IP.** `demo-pr-<n>.10.0.0.200.nip.io` resolves to garbage
  (`49.10.0.0`) — the `-<n>` numeric label suffix collides with nip.io's dotted-octet IP parsing. Use the
  **dash form `10-0-0-200.nip.io`** → `10.0.0.200`.
- **Neutralise overridden ingress annotations with `""`, not `null`.** Helm's **subchart** value-coalescing
  does not delete `null` keys (only top-level merging does), so a `null` SSO snippet leaves a `<nil>` value
  → ArgoCD's Ingress annotation accessor rejects it (*"contains non-string value"*). Empty string is a valid no-op.
- **Connect to Tailscale once per job.** Re-running `tailscale/github-action` in the same job fails with
  `cannot create /usr/local/bin/tailscaled: Text file busy`. The gitops steps talk to GitHub.com (public) —
  they need no Tailscale.
- **The image must build for the PR.** `platform-demo` CI builds on `pull_request`, so a preview has a real
  `pr-<n>-<sha>` image to deploy; a repo whose CI is `push:[main]`-only would have nothing to show.

## Relationship to the other environments

Previews are **ephemeral and isolated** — they do **not** replace the two standing environments. The
`dev` → `prod` promotion path (CI builds → [Kargo](./kargo-promotion) promotes → ArgoCD deploys, see
[Delivery Workflow](./delivery-workflow)) is unchanged. A preview is a throwaway sandbox *alongside* `dev`,
not a third promotion stage.
