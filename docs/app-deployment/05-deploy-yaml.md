---
id: deploy-yaml
title: Deploy with Raw YAML
sidebar_position: 5
---

# Deploy with Raw YAML (Alternative)

Raw Kubernetes YAML is the alternative to Helm for cases where a full chart is overkill — one-off jobs, quick debugging, simple internal tools, or when learning the platform. For persistent production workloads, [Helm + ArgoCD](./deploy-argocd) is always preferred.

---

## When to Use Raw YAML vs Helm

| Use Case | Raw YAML | Helm |
|---|---|---|
| Production app, multiple envs | ❌ | ✅ |
| One-off batch job | ✅ | ❌ |
| Quick debug pod | ✅ | ❌ |
| Simple internal tool (1 env) | ✅ | optional |
| App with DB + cache dependencies | ❌ | ✅ |
| Needs rollback history | ❌ | ✅ |
| Managed by ArgoCD | ✅ (possible) | ✅ (preferred) |

---

## Complete Deployment Manifest

A single file covering all standard resources:

```yaml
# myapp.yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: myteam-staging
  labels:
    team: myteam
    environment: staging

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: myteam-staging
  labels:
    app: myapp
    version: "1.3.0"
spec:
  replicas: 2
  selector:
    matchLabels:
      app: myapp
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0         # zero-downtime deploy
  template:
    metadata:
      labels:
        app: myapp
        version: "1.3.0"
    spec:
      imagePullSecrets:
        - name: harbor-registry-secret
      containers:
        - name: myapp
          image: harbor.local/myteam/myapp:1.3.0
          ports:
            - containerPort: 3000
          env:
            - name: NODE_ENV
              value: staging
            - name: LOG_LEVEL
              value: debug
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: 3000
            initialDelaySeconds: 15
            periodSeconds: 20

---
apiVersion: v1
kind: Service
metadata:
  name: myapp
  namespace: myteam-staging
spec:
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 3000
  type: ClusterIP

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: myteam-staging
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: myapp.staging.yourdomain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp
                port:
                  number: 80

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp
  namespace: myteam-staging
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

---

## Apply

```bash
kubectl apply -f myapp.yaml

# Watch rollout
kubectl rollout status deployment/myapp -n myteam-staging

# Verify
kubectl get all -n myteam-staging
```

---

## Update Image Tag

```bash
kubectl set image deployment/myapp \
  myapp=harbor.local/myteam/myapp:1.3.1 \
  -n myteam-staging

kubectl rollout status deployment/myapp -n myteam-staging
```

---

## Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/myapp -n myteam-staging

# Rollback to a specific revision
kubectl rollout history deployment/myapp -n myteam-staging
kubectl rollout undo deployment/myapp --to-revision=3 -n myteam-staging
```

---

## Kustomize — Environment Overrides Without Helm

Kustomize is built into `kubectl` and allows YAML overlays per environment without a template engine:

```text
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
└── overlays/
    ├── staging/
    │   ├── kustomization.yaml
    │   └── patch-replicas.yaml
    └── prod/
        ├── kustomization.yaml
        └── patch-replicas.yaml
```

**base/kustomization.yaml:**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - ingress.yaml
```

**overlays/staging/kustomization.yaml:**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
  - ../../base
namespace: myteam-staging
images:
  - name: harbor.local/myteam/myapp
    newTag: "1.3.0"
patches:
  - path: patch-replicas.yaml
```

**overlays/staging/patch-replicas.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 1
```

Deploy:

```bash
# Staging
kubectl apply -k k8s/overlays/staging

# Production
kubectl apply -k k8s/overlays/prod
```

---

## Raw YAML Limitations vs Helm

```text
❌ No release history (no helm history)
❌ No atomic rollback (manual undo)
❌ No dependency management (DB, Redis)
❌ No values templating for multiple envs
❌ No chart versioning in Harbor

✔ Simpler to understand
✔ No templating syntax to learn
✔ Good for one-off resources
✔ ArgoCD can manage raw YAML too (just point to the folder)
```

---

## Harbor Registry Secret (required for both paths)

Before pulling from Harbor, create the pull secret in each namespace:

```bash
kubectl create secret docker-registry harbor-registry-secret \
  --docker-server=harbor.local \
  --docker-username=myteam-robot \
  --docker-password=<robot-token> \
  --namespace myteam-staging

kubectl create secret docker-registry harbor-registry-secret \
  --docker-server=harbor.local \
  --docker-username=myteam-robot \
  --docker-password=<robot-token> \
  --namespace myteam-prod
```
