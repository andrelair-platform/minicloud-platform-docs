---
id: phase-7-cicd
title: Phase 14 — CI/CD Platform
sidebar_position: 8
---

# Phase 7 — CI/CD Platform

Build a pipeline that automatically builds, tests, and deploys code.

---

## Option A — Gitea (Lightweight)

Self-hosted Git platform, minimal resources.

```text
✔ Lightweight (~200MB RAM)
✔ GitHub-like UI
✔ Built-in CI (Gitea Actions, GitHub Actions-compatible)
✔ Good for small teams
```

---

## Option B — GitLab (Full)

Full DevOps platform with integrated CI/CD.

```text
✔ Full CI/CD pipelines
✔ Container registry
✔ Kubernetes integration
✔ Requires more resources (~2-4GB RAM)
```

---

## CI/CD Pipeline Flow

```text
Developer pushes code
        │
        ▼
   GitLab/Gitea
        │
   CI Pipeline runs:
   - Build Docker image
   - Run tests
   - Push to registry
        │
        ▼
   ArgoCD detects new image tag
        │
        ▼
   Deploys to Kubernetes cluster
```

---

## GitLab Runner Setup

```bash
# Install GitLab Runner on a node
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
sudo apt install gitlab-runner

# Register runner
sudo gitlab-runner register
```

---

## GitLab Agent for Kubernetes

Connects GitLab to your cluster for pull-based deployments:

```bash
helm repo add gitlab https://charts.gitlab.io
helm install gitlab-agent gitlab/gitlab-agent \
  --namespace gitlab-agent \
  --create-namespace \
  --set config.token=<AGENT_TOKEN> \
  --set config.kasAddress=wss://kas.gitlab.com
```

---

## Done When

```text
✔ Git push triggers pipeline
✔ Pipeline builds and tests
✔ Auto-deploy to cluster on success
```
