---
id: harbor
title: Phase 7 — Harbor Registry
sidebar_position: 1
---

# Harbor — Self-Hosted Container Registry

Harbor is an enterprise-grade private container registry. It stores your Docker images inside your cluster, scans them for vulnerabilities, enforces access control, and integrates with your CI/CD pipelines — no Docker Hub dependency, no image leak risk.

---

## Why a Private Registry

```text
Without Harbor:
  CI builds image → pushes to Docker Hub (public or private)
  k3s pulls from Docker Hub → needs internet, rate-limited, slow

With Harbor:
  CI builds image → pushes to harbor.yourdomain.com (internal)
  k3s pulls from harbor.yourdomain.com → fast, no internet needed
  Images never leave your network
```

---

## Key Features

| Feature | What It Does |
|---|---|
| **Multi-project registry** | Separate registries per team/project |
| **RBAC** | Push/pull permissions per user or robot account |
| **Vulnerability scanning** | Trivy integration — scans every pushed image |
| **Image signing** | Cosign/Notary support |
| **Replication** | Mirror images to/from other registries |
| **Garbage collection** | Automatically clean untagged images |
| **Web UI** | Browse images, tags, scan reports |

---

## Install Harbor via Helm

```bash
helm repo add harbor https://helm.goharbor.io

helm install harbor harbor/harbor \
  --namespace harbor \
  --create-namespace \
  --set expose.type=loadBalancer \
  --set expose.loadBalancer.IP=10.0.0.210 \
  --set expose.tls.enabled=false \
  --set externalURL=http://10.0.0.210 \
  --set persistence.persistentVolumeClaim.registry.storageClass=longhorn \
  --set persistence.persistentVolumeClaim.registry.size=100Gi \
  --set persistence.persistentVolumeClaim.database.storageClass=longhorn \
  --set persistence.persistentVolumeClaim.redis.storageClass=longhorn \
  --set harborAdminPassword=Admin12345
```

Wait for all pods:

```bash
kubectl get pods -n harbor --watch
```

---

## Access Harbor UI

Open: `http://10.0.0.210`

Login: `admin / Admin12345`

Via Tailscale: `http://10.0.0.210` (after subnet route)
Via Cloudflare: `https://registry.yourdomain.com`

---

## Configure k3s to Use Harbor

Tell k3s to use Harbor as a registry mirror:

```bash
sudo nano /etc/rancher/k3s/registries.yaml
```

```yaml
mirrors:
  "harbor.local":
    endpoint:
      - "http://10.0.0.210"

configs:
  "10.0.0.210":
    auth:
      username: admin
      password: Admin12345
```

```bash
sudo systemctl restart k3s
```

---

## Push an Image to Harbor

```bash
# Create project in Harbor UI first: "platform"

# Tag and push
docker tag my-app:latest 10.0.0.210/platform/my-app:latest
docker push 10.0.0.210/platform/my-app:latest
```

---

## Configure Docker Daemon (local machine)

Add Harbor as an insecure registry (if using HTTP):

```json
// /etc/docker/daemon.json
{
  "insecure-registries": ["10.0.0.210"]
}
```

```bash
sudo systemctl restart docker
docker login 10.0.0.210
```

---

## Robot Accounts for CI/CD

Create robot accounts in Harbor UI for CI pipelines:

```text
Harbor UI → Projects → platform → Robot Accounts
→ New Robot Account
   Name: gitlab-ci
   Permissions: push + pull
→ Copy generated token
```

In GitLab CI:

```yaml
variables:
  HARBOR_URL: "10.0.0.210"
  HARBOR_PROJECT: "platform"

build:
  script:
    - docker login $HARBOR_URL -u robot\$gitlab-ci -p $HARBOR_TOKEN
    - docker build -t $HARBOR_URL/$HARBOR_PROJECT/my-app:$CI_COMMIT_SHA .
    - docker push $HARBOR_URL/$HARBOR_PROJECT/my-app:$CI_COMMIT_SHA
```

---

## Vulnerability Scanning

Harbor integrates **Trivy** — every pushed image is automatically scanned:

```text
Harbor UI → Projects → platform → Repositories → my-app
→ Artifacts → sha256:abc...
→ Vulnerabilities tab:
   CRITICAL: 0
   HIGH: 2
   MEDIUM: 5
   LOW: 12
```

Set a policy to block deployments if CRITICAL vulnerabilities are found:

```text
Harbor UI → Projects → platform → Configuration
→ Automatically scan images on push: ✔
→ Prevent vulnerable images from running: CRITICAL
```

ArgoCD will refuse to sync any image that fails the scan policy.

---

## Done When

```text
✔ Harbor pods Running with Longhorn storage
✔ UI accessible at 10.0.0.210
✔ k3s configured to pull from Harbor
✔ First image pushed and scannable
✔ Robot account created for CI/CD
✔ Vulnerability scanning active
```
