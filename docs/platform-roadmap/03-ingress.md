---
id: phase-6-ingress
title: Phase 6 — Ingress Controller
sidebar_position: 4
---

# Phase 6 — NGINX Ingress Controller

Expose HTTP(S) services in the cluster via hostnames instead of NodePorts. After this phase, every cluster service can be reached at a real URL like `homer.10.0.0.200.nip.io` instead of `10.0.0.2:30902`.

This phase builds directly on Phase 4 (MetalLB) — the Ingress controller is exposed as a `Service type: LoadBalancer`, which MetalLB binds to a single dedicated IP from the `10.0.0.200–250` pool. The result is the same architecture every cloud Kubernetes cluster uses: one external IP, host-based routing in front of any number of backends.

---

## Architecture

```text
Browser
   │  GET http://homer.10.0.0.200.nip.io/
   ▼
nip.io  →  resolves to 10.0.0.200
   ▼
MetalLB advertises 10.0.0.200 via ARP on the cluster network
   ▼
NGINX Ingress Controller pod (LoadBalancer Service)
   │  reads Ingress resources, picks the rule matching Host header
   ▼
Service "homer" (ClusterIP, port 8080)
   ▼
Pod homer-…
```

`nip.io` is a public DNS service that resolves any subdomain of the form `<anything>.<ip>.nip.io` to that IP. Zero setup; perfect for homelab testing without standing up a real DNS server.

---

## Why F5 NGINX Open Source (not the community `ingress-nginx`)

The community **`kubernetes/ingress-nginx`** project (Helm chart `ingress-nginx/ingress-nginx`) entered read-only / archived maintenance in early 2026 — the upstream maintainers stopped accepting feature work after a string of CVE disclosures and a sustainability-of-volunteers conversation. New deployments should use the actively-maintained alternative:

**F5 NGINX Open Source Ingress Controller** (Helm chart `nginx-stable/nginx-ingress`, repo `https://helm.nginx.com/stable`).

Differences worth knowing if you've used the community chart before:

| | Community `ingress-nginx` (archived) | F5 `nginx-ingress` (this phase) |
|---|---|---|
| Helm chart | `ingress-nginx/ingress-nginx` | `nginx-stable/nginx-ingress` |
| Annotation prefix | `nginx.ingress.kubernetes.io/...` | `nginx.org/...` |
| Extra CRDs | None (just standard `Ingress`) | `VirtualServer`, `VirtualServerRoute`, `Policy`, `TransportServer` |
| IngressClass controller | `k8s.io/ingress-nginx` | `nginx.org/ingress-controller` |
| Configmap name | `ingress-nginx-controller` | `nginx-ingress` |

For most workloads the standard `Ingress` resource is portable — the differences only bite when you start using annotations or controller-specific features.

---

## Step 1 — Disable k3s's bundled Traefik

k3s ships with **Traefik** as the default ingress controller. Running two ingress controllers at once is a footgun (which one binds 80/443? which one handles `/`?), so disable Traefik first.

On the control-plane node (`set-hog`), edit `/etc/rancher/k3s/config.yaml`:

```yaml
disable:
  - servicelb
  - traefik
```

`servicelb` (klipper-lb) was already disabled in Phase 4 when MetalLB took over LoadBalancer duties. Adding `traefik` to the same list keeps things consistent.

Apply by restarting k3s:

```bash
sudo systemctl restart k3s
```

The API server is unavailable for ~10–30 seconds during the restart. Workloads keep running because each kubelet has cached state.

### Cleanup after disable

When `traefik` is added to `disable`, k3s spawns a `helm-delete-traefik` Job that runs `helm uninstall traefik`. On this cluster the Service got stuck on its `service.kubernetes.io/load-balancer-cleanup` finalizer (MetalLB had given it `10.0.0.200`). The Job hangs at `helm uninstall ... --wait` until the finalizer clears.

Force-clear it manually:

```bash
kubectl patch svc traefik -n kube-system -p '{"metadata":{"finalizers":[]}}' --type=merge
kubectl delete svc traefik -n kube-system --grace-period=0 --force
kubectl delete job helm-install-traefik helm-delete-traefik -n kube-system --ignore-not-found
```

The `10.0.0.200` IP is now free in the MetalLB pool.

---

## Step 2 — Install F5 NGINX Ingress via Helm

```bash
helm repo add nginx-stable https://helm.nginx.com/stable
helm repo update

helm install nginx-ingress nginx-stable/nginx-ingress \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.ingressClass.setAsDefaultIngress=true
```

Two `--set` flags do the work:

- `controller.service.type=LoadBalancer` — exposes NGINX via a `LoadBalancer` Service, which MetalLB will assign an IP to.
- `controller.ingressClass.setAsDefaultIngress=true` — makes the `nginx` IngressClass the default, so any `Ingress` resource without an explicit `ingressClassName` field uses NGINX automatically.

Verify:

```bash
kubectl get pods -n ingress-nginx
kubectl get svc -n ingress-nginx
kubectl get ingressclass
```

Expected output:

```text
NAME                                         READY   STATUS    RESTARTS   AGE
nginx-ingress-controller-5587758447-wxqpw    1/1     Running   0          15s

NAME                       TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)
nginx-ingress-controller   LoadBalancer   10.43.27.103   10.0.0.200    80:31030/TCP,443:30326/TCP

NAME    CONTROLLER                     AGE
nginx   nginx.org/ingress-controller   16s
```

The `EXTERNAL-IP` is what MetalLB assigned. Confirm NGINX is serving:

```bash
curl -sI http://10.0.0.200/
# HTTP/1.1 404 Not Found
# Server: nginx/1.29.7
```

A 404 here is correct — NGINX is up but no `Ingress` rule matches yet.

---

## Step 3 — Route a Service through Ingress

Convert Homer (currently NodePort) to ClusterIP and create an Ingress for it.

```yaml
# homer-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: homer
  namespace: homer
spec:
  ingressClassName: nginx
  rules:
    - host: homer.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: homer
                port:
                  number: 8080
```

```bash
kubectl apply -f homer-ingress.yaml

# Demote homer service from NodePort → ClusterIP (Ingress no longer needs it exposed)
kubectl patch svc homer -n homer --type=json \
  -p '[{"op":"replace","path":"/spec/type","value":"ClusterIP"},
       {"op":"remove","path":"/spec/ports/0/nodePort"}]'
```

Test:

```bash
curl -sI http://homer.10.0.0.200.nip.io/
# HTTP/1.1 200 OK
# Server: nginx/1.29.7
```

Or open it in a browser (works from the controller, and from any Tailscale-connected device because the controller advertises `10.0.0.0/24`).

---

## Result on this cluster

Installed and verified on 2026-04-28:

- **Chart:** `nginx-stable/nginx-ingress` (F5 NGINX OSS)
- **NGINX version:** 1.29.7
- **LoadBalancer IP:** `10.0.0.200` (assigned by MetalLB from the `10.0.0.200–250` pool)
- **IngressClass:** `nginx` (default, controller `nginx.org/ingress-controller`)
- **First app routed:** Homer at `homer.10.0.0.200.nip.io` (Service demoted from NodePort to ClusterIP)
- **Traefik:** disabled in `/etc/rancher/k3s/config.yaml`, manually finalizer-cleared and removed

---

## What's still missing (deferred to later phases)

- **TLS / HTTPS** — added in Phase 15 via cert-manager + Let's Encrypt (or an internal CA for `*.nip.io` style hosts).
- **Real DNS** — `nip.io` is fine for testing but ideally apps live behind a real domain. Phase 6 of the remote-access docs covers Cloudflare Tunnel + DNS, which is the natural follow-up.
- **WAF / rate limiting / auth** — F5 NGINX OSS supports basic auth, IP allowlists, and rate-limit annotations (`nginx.org/limit-req-rate`); deeper protection (NAP, ModSecurity) is NGINX Plus territory and out of scope for the homelab build.

---

## Done When

```text
✔ Traefik disabled and removed from kube-system
✔ F5 NGINX Ingress controller pod Running in ingress-nginx
✔ MetalLB assigned a 10.0.0.x IP to the controller's LoadBalancer Service
✔ At least one app reachable via http://<host>.<ip>.nip.io/
```
