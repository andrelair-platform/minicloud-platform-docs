---
id: phase-8-containers
title: Phase 14 — Container Strategy
sidebar_position: 9
---

# Phase 8 — Container Strategy

Understanding how containers work in a k3s cluster.

---

## Runtime

```text
✔ k3s uses containerd (not Docker)
✔ Docker images still work — OCI-compatible
✔ No Docker daemon required on nodes
```

---

## Building Images

Build on your local machine or in CI:

```bash
docker build -t my-app:v1.0 .
docker tag my-app:v1.0 registry.local/my-app:v1.0
docker push registry.local/my-app:v1.0
```

---

## What You Can Deploy

```text
✔ Node.js apps
✔ Python / FastAPI services
✔ AI/ML inference services
✔ SaaS applications
✔ Databases (PostgreSQL, Redis, etc.)
```

---

## Registry Options

| Option | Use Case |
|---|---|
| Docker Hub | Public images |
| GitLab Registry | Private images + CI integration |
| Harbor | Self-hosted, enterprise features |
| Local registry | Air-gapped / development |

---

## Sample Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
        - name: my-app
          image: registry.local/my-app:v1.0
          ports:
            - containerPort: 3000
```
