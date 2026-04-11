---
id: homer-dashboard
title: Homer Dashboard
sidebar_position: 4
---

# Homer — Self-Hosted Web Dashboard

Homer is a lightweight static dashboard that runs as a pod in your k3s cluster. It gives you a single browser page with tiles linking to every service in your infrastructure — accessible via Tailscale or Cloudflare Tunnel.

---

## What It Looks Like

```text
┌──────────────────────────────────────────────────────┐
│              Mini Cloud Platform                     │
│         Private Bare-Metal Infrastructure            │
├──────────────┬──────────────┬──────────────┬─────────┤
│  MAAS        │  Grafana     │  ArgoCD      │ GitLab  │
│  Bare-metal  │  Monitoring  │  GitOps      │  CI/CD  │
│  provisioner │  dashboards  │  sync        │         │
├──────────────┴──────────────┴──────────────┴─────────┤
│  Kubernetes                                          │
│  set-hog (CP) · fast-skunk · fast-heron             │
│  ● ● ●  All nodes Ready                             │
└──────────────────────────────────────────────────────┘
```

---

## Deploy Homer in k3s

### Create the namespace and config

```bash
kubectl create namespace homer
```

Create the Homer config file (you'll mount it as a ConfigMap):

```bash
cat <<'EOF' > homer-config.yml
title: "Mini Cloud Platform"
subtitle: "Private Bare-Metal Infrastructure"
logo: "logo.png"

header: true
footer: false

colors:
  light:
    highlight-primary: "#3367d6"
    highlight-secondary: "#4285f4"
    highlight-hover: "#5a95f5"
    background: "#f2f4f8"
    card-background: "#ffffff"
    text: "#363636"
    text-header: "#ffffff"
    text-title: "#303030"
    text-subtitle: "#424242"
    card-shadow: rgba(0, 0, 0, 0.1)
    link: "#3273dc"
    link-hover: "#363636"
  dark:
    highlight-primary: "#3367d6"
    highlight-secondary: "#4285f4"
    highlight-hover: "#5a95f5"
    background: "#131313"
    card-background: "#2b2b2b"
    text: "#eaeaea"
    text-header: "#ffffff"
    text-title: "#fafafa"
    text-subtitle: "#f5f5f5"
    card-shadow: rgba(0, 0, 0, 0.4)
    link: "#3273dc"
    link-hover: "#ffdd57"

services:
  - name: "Infrastructure"
    icon: "fas fa-server"
    items:
      - name: "MAAS"
        logo: "https://assets.ubuntu.com/v1/0b5f1b3e-maas-logo.svg"
        subtitle: "Bare-metal provisioning"
        tag: "infra"
        url: "http://10.0.0.1:5240/MAAS"
        target: "_blank"

      - name: "set-hog"
        icon: "fas fa-microchip"
        subtitle: "Control plane — 10.0.0.2"
        tag: "k8s"
        url: "http://10.0.0.1:5240/MAAS/r/machines"
        target: "_blank"

      - name: "fast-skunk"
        icon: "fas fa-microchip"
        subtitle: "Worker — 10.0.0.4"
        tag: "k8s"
        url: "http://10.0.0.1:5240/MAAS/r/machines"
        target: "_blank"

      - name: "fast-heron"
        icon: "fas fa-microchip"
        subtitle: "Worker — 10.0.0.7"
        tag: "k8s"
        url: "http://10.0.0.1:5240/MAAS/r/machines"
        target: "_blank"

  - name: "Observability"
    icon: "fas fa-chart-line"
    items:
      - name: "Grafana"
        logo: "https://grafana.com/static/assets/img/fav32.png"
        subtitle: "Metrics & dashboards"
        tag: "monitoring"
        url: "http://10.0.0.2:3000"
        target: "_blank"

      - name: "Prometheus"
        icon: "fas fa-fire"
        subtitle: "Metrics storage"
        tag: "monitoring"
        url: "http://10.0.0.2:9090"
        target: "_blank"

  - name: "DevOps"
    icon: "fas fa-code-branch"
    items:
      - name: "ArgoCD"
        icon: "fas fa-sync"
        subtitle: "GitOps — continuous deployment"
        tag: "gitops"
        url: "http://10.0.0.2:8080"
        target: "_blank"

      - name: "GitLab / Gitea"
        icon: "fas fa-code"
        subtitle: "Git platform & CI/CD"
        tag: "cicd"
        url: "http://10.0.0.2:80"
        target: "_blank"
EOF
```

---

### Create Kubernetes manifests

```bash
cat <<'EOF' > homer-deployment.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: homer-config
  namespace: homer
data:
  config.yml: |
    # paste the contents of homer-config.yml here
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: homer
  namespace: homer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: homer
  template:
    metadata:
      labels:
        app: homer
    spec:
      containers:
        - name: homer
          image: b4bz/homer:latest
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: config
              mountPath: /www/assets/config.yml
              subPath: config.yml
      volumes:
        - name: config
          configMap:
            name: homer-config
---
apiVersion: v1
kind: Service
metadata:
  name: homer
  namespace: homer
spec:
  type: NodePort
  selector:
    app: homer
  ports:
    - port: 8080
      targetPort: 8080
      nodePort: 30902
EOF

kubectl apply -f homer-deployment.yaml
```

---

### Verify

```bash
kubectl get pods -n homer
kubectl get svc -n homer
```

Homer is now running at:

```text
http://10.0.0.2:30902        ← from inside the network
http://100.x.x.x:30902      ← via Tailscale
https://dashboard.yourdomain.com  ← via Cloudflare Tunnel
```

---

## Connect to Cloudflare Tunnel

Update your `~/.cloudflared/config.yml` on the MAAS controller:

```yaml
- hostname: dashboard.yourdomain.com
  service: http://10.0.0.2:30902
```

Then reload:

```bash
sudo systemctl restart cloudflared
```

---

## Connect to Tailscale

No extra config needed. If the MAAS controller has the `10.0.0.0/24` route advertised via Tailscale, Homer is automatically reachable at:

```text
http://10.0.0.2:30902
```

from any Tailscale-connected machine.

---

## Customize Homer

Edit `homer-config.yml` and update the ConfigMap:

```bash
kubectl create configmap homer-config \
  --from-file=config.yml=homer-config.yml \
  -n homer \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/homer -n homer
```

---

## Alternative Dashboards

| Tool | Docker image | Features |
|---|---|---|
| **Homer** | `b4bz/homer` | Lightweight, YAML config, no DB |
| **Dashy** | `lissy93/dashy` | Rich UI, status checks, widgets |
| **Heimdall** | `linuxserver/heimdall` | App launcher, search bar |
| **Flame** | `pawelmalak/flame` | Bookmarks + weather widgets |

Homer is recommended for simplicity — no database, purely static, minimal resources (~10MB RAM).

---

## Done When

```text
✔ Homer pod Running in homer namespace
✔ Dashboard accessible at NodePort :30902
✔ All service tiles open correct URLs
✔ Accessible via Tailscale AND/OR Cloudflare Tunnel
```
