---
id: backstage
title: Phase 19 — Backstage
sidebar_position: 1
---

# Backstage — Internal Developer Portal

Backstage is Spotify's open-source internal developer platform. It gives every developer in your team a single place to discover services, browse APIs, read runbooks, trigger pipelines, and check deployment status — all without needing to know where everything lives.

---

## What It Solves

```text
Without Backstage:
  "Where is the API docs for the auth service?"
  "Which team owns the payments service?"
  "How do I deploy a new microservice?"
  "Where is the Grafana dashboard for service X?"

With Backstage:
  → One portal. Everything catalogued. Self-service.
```

---

## Key Features

| Feature | What It Does |
|---|---|
| **Software Catalog** | Browse all services, APIs, libraries with owner + docs |
| **TechDocs** | Auto-generated documentation from Markdown in repos |
| **Software Templates** | "Create a new microservice" button — scaffolds repo, CI, k8s manifest |
| **Kubernetes Plugin** | See pod status, logs, rollouts per service |
| **ArgoCD Plugin** | See GitOps sync status per service |
| **Grafana Plugin** | Embed dashboards per service |
| **Search** | Search across services, docs, APIs |

---

## Architecture on Your Cluster

```text
Developer Browser
      │
      ▼
Backstage Pod (k3s)
  ├── Frontend (React)
  ├── Backend (Node.js)
  └── PostgreSQL (catalog data)
      │
      ├── Reads from: GitLab repos (catalog-info.yaml)
      ├── Connects to: k8s API (pod status)
      ├── Connects to: ArgoCD API
      └── Connects to: Grafana API
```

---

## Deploy Backstage

### Prerequisites

```bash
# Install Node.js 18+ on your local machine
node --version  # v18+
npx @backstage/create-app@latest
# → name: minicloud-portal
```

### Build Docker image

```bash
cd minicloud-portal
yarn install
yarn tsc
yarn build:backend

docker build -t backstage:latest \
  -f packages/backend/Dockerfile .
```

### Push to your Harbor registry (after Harbor is set up)

```bash
docker tag backstage:latest harbor.yourdomain.com/platform/backstage:latest
docker push harbor.yourdomain.com/platform/backstage:latest
```

### Deploy to k3s

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backstage
  namespace: platform
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backstage
  template:
    metadata:
      labels:
        app: backstage
    spec:
      containers:
        - name: backstage
          image: harbor.yourdomain.com/platform/backstage:latest
          ports:
            - containerPort: 7007
          env:
            - name: POSTGRES_HOST
              value: postgres-svc
            - name: POSTGRES_PORT
              value: "5432"
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: backstage-secrets
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: backstage-secrets
                  key: POSTGRES_PASSWORD
---
apiVersion: v1
kind: Service
metadata:
  name: backstage
  namespace: platform
spec:
  type: LoadBalancer
  selector:
    app: backstage
  ports:
    - port: 80
      targetPort: 7007
```

---

## Register Your First Service

In each repo, add `catalog-info.yaml`:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: my-api
  description: The main API service
  tags:
    - nodejs
    - api
  links:
    - url: https://grafana.yourdomain.com/d/xxx
      title: Grafana Dashboard
    - url: https://argocd.yourdomain.com/applications/my-api
      title: ArgoCD
spec:
  type: service
  lifecycle: production
  owner: platform-team
  providesApis:
    - my-api-definition
```

Backstage auto-discovers this file and catalogs the service.

---

## Software Templates (Golden Paths)

Create a "New Microservice" button that:

```text
1. Developer fills form: name, language, team
2. Backstage scaffolds:
   ├── Git repo with code template
   ├── CI/CD pipeline config
   ├── Kubernetes manifests
   ├── Dockerfile
   └── catalog-info.yaml
3. Repo created → pipeline triggers → ArgoCD deploys
```

This is the "golden path" — one click to a fully deployed service.

---

## Done When

```text
✔ Backstage pod Running
✔ Accessible via browser (MetalLB IP or Cloudflare tunnel)
✔ Services from GitLab repos appearing in catalog
✔ Kubernetes plugin showing pod status
```
