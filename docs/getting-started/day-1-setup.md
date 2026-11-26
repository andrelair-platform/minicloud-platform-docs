---
id: day-1-setup
title: Day 1 — access & local setup
sidebar_label: Day 1 — access & setup
tags: [how-to]
---

# Day 1 — access & local setup

> **How-to.** Everything you need **before** you can build: accounts, the tools on your laptop, cluster
> access, and a quick "am I ready?" check. ~30–45 minutes.

## 1. Accounts & access

| What | How to get it |
|---|---|
| **GitHub org** (`andrelair-platform`) | Ask the platform owner to add you to the **`andrelair-platform`** GitHub org. Repos are **public**, so you can clone immediately; org membership is what lets you open PRs. Then run `gh auth login`. *(Who grants this + the exact request path is owner-specific — ask André.)* |
| **SSO account** (Authentik) | You log into every internal app through **Authentik** (one login + MFA). Ask the owner to create your Authentik account, then **enrol MFA (TOTP)** on first login. → [How SSO & login work](/platform/security-enterprise/how-sso-works) |
| **Private mesh** (Tailscale) — only for internal tools | Internal tools (ArgoCD, Grafana, Backstage…) are reached over **Tailscale** + the **minicloud CA cert**. Business apps are public (SSO only). Follow the 3-tier model: → [Onboarding a colleague](/platform/remote-access/onboarding-a-colleague) |
| **Backstage** (developer portal) | No separate account — log in with **SSO**. It's your **catalog · scaffolder · TechDocs · New BMAD Sprint**. → [Backstage](/platform/developer-platform/backstage) |

## 2. Install the tools (local)

**Always needed**
```bash
# macOS (Homebrew)
brew install git gh            # Git + GitHub CLI
# Docker Desktop (or Colima/Podman) — to build & run images
```
Plus **your service's language toolchain**: Python 3.11+, Go 1.22+, Java 21, or Node 20 — whichever your
reference service uses (see step 4).

**For cluster access / debugging (optional on day 1)**
```bash
brew install kubectl helm
brew install int128/kubelogin/kubelogin   # OIDC login plugin for kubectl
```

**Verify**
```bash
git --version && gh --version && docker version
# and, if installed: kubectl version --client && helm version
```

## 3. Cluster access — read/debug only (you deploy via Git, not kubectl)

You **do not** deploy by running `kubectl apply`. Deployment is **GitOps** (a PR to `minicloud-gitops`,
then Kargo/Argo CD). Cluster access is only for **reading/debugging** the dev environment.

- **kubectl via OIDC** — a browser login through Authentik gives you a scoped `minicloud-oidc` context.
  Full setup + troubleshooting: → [kubectl OIDC access](/platform/security-enterprise/kubectl-oidc-access).
- **curl to internal HTTPS** — pass the minicloud CA cert (don't use an OpenSSL curl that ignores the
  system keychain): `/usr/bin/curl --cacert <minicloud-ca.crt> -sI https://<app>.10.0.0.200.nip.io`.
- Get the **minicloud CA cert** from the onboarding pack / the platform owner.

## 4. Pick your stack & clone a reference service

**You almost never start from a blank repo** — scaffold from a **Backstage** [software template](/platform/developer-platform/backstage-software-templates), or clone the closest reference below and find-replace.

| Your stack | Reference service to clone |
|---|---|
| Python / FastAPI | `ktayl-underwriting` |
| Java / Spring (a module in the monolith) | `ktayl-core` |
| TypeScript / NestJS | `retrieva-backend` |
| Go | `platform-demo` |

The step-by-step (clone → standardise → CI → Helm → Argo CD → Kargo → secrets) is the golden path:
→ [New business service — zero → prod](/platform/app-deployment/new-business-service).

## 5. "Am I ready?" checklist

- [ ] Added to the `andrelair-platform` GitHub org; `gh auth status` is green.
- [ ] Logged into an internal app via Authentik (SSO) with MFA enrolled.
- [ ] `git`, `gh`, `docker` installed and verified.
- [ ] Cloned your stack's **reference service** and it builds locally.
- [ ] Ran the reference service's **L0–L1 tests** locally (`make test` / the per-language command in [Testing strategy](/platform/engineering-standards/testing-strategy)).
- [ ] *(Optional)* `kubectl --context minicloud-oidc get pods -A` returns the dev namespaces.

When these are green, continue with the main thread → [Getting Started (A→Z)](/platform/getting-started).

## Related

- [Getting Started (A→Z)](/platform/getting-started) — the full developer thread
- [Onboarding a colleague](/platform/remote-access/onboarding-a-colleague) — the access tiers in detail
- [How SSO & login work](/platform/security-enterprise/how-sso-works)
