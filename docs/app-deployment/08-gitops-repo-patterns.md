---
id: gitops-repo-patterns
title: GitOps Repository Patterns
sidebar_position: 8
---

# GitOps Repository Patterns

Every GitOps project requires a strict separation between two concerns: **application source code** and **deployment configuration**. These never live in the same repository. Beyond that split, teams must decide whether deployment config lives in one shared repository for all services or in a dedicated repository per service.

---

## The Two-Repo Split (Universal Rule)

Every service, regardless of team size or company, follows the same split:

```
application-my-service/          ← source code repo
│  src/
│  Dockerfile
│  .github/workflows/ci.yml      ← builds image, pushes to registry, bumps tag in deployment repo

deployment config                ← deployment repo (no source code ever)
│  values.yaml / kustomization.yaml
│  resource limits, env vars, ingress hostnames, image tag
```

**The deployment repo contains zero application code.** Its only job is to describe the desired state of the cluster: which image to run, with what resources, on what hostname. A Kubernetes operator could change a memory limit or promote to production without ever opening the source code repo.

The two repos only connect at one point: the CI pipeline in the source repo automatically opens a pull request in the deployment repo to bump the image tag after a successful build.

```
Developer pushes code
        │
        ▼
CI builds image → pushes to registry
        │
        ▼
CI opens PR: bump tag in deployment repo overlays/dev/
        │
        ▼
PR merged → ArgoCD picks up change → deploys to dev
```

### What goes where

| Change | Repo |
|--------|------|
| Fix a bug in the application | Source code repo |
| Add a new API endpoint | Source code repo |
| Increase memory limit | Deployment repo |
| Add an environment variable | Deployment repo |
| Change the ingress hostname | Deployment repo |
| Promote image tag to staging | Deployment repo |
| Update a Helm chart dependency version | Deployment repo |

---

## Pattern A — Deployment Monorepo

One deployment repository holds the config for **all services**.

```
minicloud-gitops/                         ← single deployment repo
├── services/
│   ├── platform-demo/
│   │   ├── base/
│   │   └── overlays/{dev,staging,prod}/
│   ├── minicloud-plane/
│   │   ├── base/
│   │   └── overlays/{dev,staging,prod}/
│   └── minicloud-backstage/
├── manifests/
│   ├── network-policies/
│   ├── quotas/
│   └── rbac/
└── apps/                                 ← ArgoCD Application CRs
```

Source repos are separate:
```
platform-demo/        ← source
minicloud-plane/      ← source
minicloud-backstage/  ← source
minicloud-gitops/     ← deployment for all of the above
```

### When to use

- One team or one person owns all services
- You want a single place to see the entire cluster state
- Platform-wide changes are frequent (add NetworkPolicies to all services, bump a shared quota, update RBAC across envs) — one PR covers everything
- You are simultaneously the platform team and the application team

### Tradeoffs

| | Advantage | Disadvantage |
|--|-----------|--------------|
| **Visibility** | One repo = complete picture of the cluster | A single bad merge can affect every service at once |
| **Cross-cutting changes** | Update a policy for all services in one commit | Merge conflicts increase as more contributors push simultaneously |
| **Onboarding** | Clone one repo to understand the full system | Git log becomes noisy — a platform-demo deploy appears next to a minicloud-plane change |
| **Access control** | Simple — one repo, one set of permissions | Everyone with write access can touch every service's production config |
| **Audit** | Full platform history in one place | Compliance tools cannot scope audit trails per application |

---

## Pattern B — Per-Project Deployment Repo

Each service has its **own dedicated deployment repository**, independent of all others.

```
application-claims-api/           ← source (team A)
deployment-claims-api/            ← deployment (team A only)
│  dev/{cluster}/def/claims-api/
│  uat/{cluster}/def/claims-api/
│  prod/{cluster}/def/claims-api/

application-fraud-detection/      ← source (team B)
deployment-fraud-detection/       ← deployment (team B only)
│  dev/{cluster}/def/fraud-detection/
│  uat/{cluster}/def/fraud-detection/
│  prod/{cluster}/def/fraud-detection/
```

The folder axis flips: **environment is the top level**, service name is nested inside.

```
deployment-claims-api/
├── dev/
│   └── cluster-west/
│       └── def/
│           └── claims-api/
│               ├── Chart.yaml
│               └── values.yaml
├── uat/
│   └── cluster-west/
│       └── def/
│           └── claims-api/
│               └── (empty until promoted)
└── prod/
    └── cluster-west/
        └── def/
            └── claims-api/
                └── (empty until promoted)
```

`uat/` and `prod/` folders start as empty placeholders. Promoting to UAT means creating the `values.yaml` file there via a pull request — the act of creating the file is the promotion.

### When to use

- Multiple independent teams, each owning one or a few services
- Teams should not have write access to each other's production config
- Compliance requires audit trails scoped per application (regulated industries — insurance, banking, healthcare)
- Different release cadences: one team deploys ten times a day, another deploys once a month — they must not block each other's PR reviews
- The platform team is a separate group from the application teams

### Tradeoffs

| | Advantage | Disadvantage |
|--|-----------|--------------|
| **Access control** | Team A cannot accidentally affect Team B's production | 50 services = 50 deployment repos to manage |
| **Blast radius** | A bad merge only affects one service | No single place to see the state of the whole platform |
| **Audit** | One repo history = one application's change history | Cross-service changes (e.g. update a shared library chart version) require opening PRs in every repo |
| **Autonomy** | Teams ship completely independently | Platform-wide policies are harder to enforce consistently across all repos |
| **CI/CD** | Each repo has its own pipeline, independently configurable | Pipeline definitions are duplicated across repos |

---

## Choosing Between the Two

**Start with a monorepo. Split when access control becomes a concrete problem.**

Most teams start with a monorepo because it is simpler to set up, simpler to onboard new members, and simpler to make platform-wide changes. The cost of splitting — maintaining dozens of repos, duplicating pipeline config, losing the single-pane-of-glass view — is only worth paying when a specific pain appears.

Split per project when:
- A team complains they cannot ship because another team's PR is blocking the deployment repo
- A security or compliance audit requires per-application change logs
- A team needs production write access to their service but must not have it for other services

The threshold in practice is roughly **5–10 teams** each owning distinct services. Below that, the monorepo overhead is lower than the split overhead.

---

## How minicloud Uses This

minicloud follows the **monorepo** pattern for deployment config:

```
Source repos (one per service):
  platform-demo/          → GitHub Actions builds image → Harbor
  minicloud-plane/        → GitHub Actions builds image → Harbor
  minicloud-backstage/    → GitHub Actions builds image → Harbor

Deployment repo (shared):
  minicloud-gitops/
    services/platform-demo/overlays/{dev,staging,prod}/
    services/minicloud-plane/overlays/{dev,staging,prod}/
    helm-values/backstage-values.yaml
```

This is the correct choice for a single-operator platform. If minicloud grew to multiple independent teams each owning a service, the deployment repo would be split per team — each team's service would move into its own `deployment-<service>/` repository with the environment-first folder structure, and that team would own the CI pipeline that bumps their image tag there.

The two-repo split between source and deployment is **non-negotiable** in both patterns. Only the scope of the deployment repo changes.
