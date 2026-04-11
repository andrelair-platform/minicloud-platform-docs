---
id: metallb
title: Phase 4 — MetalLB
sidebar_position: 1
---

# MetalLB — Real LoadBalancer IPs on Bare-Metal

On cloud providers (AWS, GCP, Azure) when you create a Kubernetes Service of type `LoadBalancer`, the cloud automatically provisions a load balancer with a real IP. On bare-metal, this does nothing — services stay in `<pending>` state forever.

MetalLB fixes this by assigning real IPs from your local network to LoadBalancer services.

---

## How It Works

```text
kubectl expose deployment my-app --type=LoadBalancer --port=80
        │
        ▼
MetalLB assigns: 10.0.0.200
        │
        ▼
Any machine on 10.0.0.0/24 can reach:
http://10.0.0.200:80  → my-app
```

MetalLB announces the IP via ARP (Layer 2 mode) so the network switch routes traffic correctly.

---

## Install MetalLB

```bash
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.5/config/manifests/metallb-native.yaml
```

Wait for pods:

```bash
kubectl get pods -n metallb-system --watch
```

---

## Configure IP Address Pool

Define a range of IPs MetalLB can hand out — these must be in your `10.0.0.0/24` subnet and **not** assigned to anything else:

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: cluster-pool
  namespace: metallb-system
spec:
  addresses:
    - 10.0.0.200-10.0.0.250
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: cluster-l2
  namespace: metallb-system
spec:
  ipAddressPools:
    - cluster-pool
```

```bash
kubectl apply -f metallb-config.yaml
```

---

## Test It

```bash
kubectl create deployment nginx --image=nginx
kubectl expose deployment nginx --type=LoadBalancer --port=80
kubectl get svc nginx
```

Expected output:

```text
NAME    TYPE           CLUSTER-IP     EXTERNAL-IP    PORT(S)
nginx   LoadBalancer   10.96.12.34    10.0.0.200     80:31234/TCP
```

`EXTERNAL-IP` is no longer `<pending>` — it has a real IP.

```bash
curl http://10.0.0.200
# → nginx welcome page
```

Via Tailscale (subnet route advertised), this works from any remote machine too.

---

## Assigned IP Pool Plan

| Range | Use |
|---|---|
| `10.0.0.1` | MAAS Controller |
| `10.0.0.2–10.0.0.10` | Cluster nodes (MAAS DHCP) |
| `10.0.0.200–10.0.0.250` | MetalLB LoadBalancer pool |

---

## Done When

```text
✔ MetalLB pods Running
✔ IPAddressPool and L2Advertisement applied
✔ LoadBalancer service gets a 10.0.0.200+ IP
✔ Service reachable directly by IP
```
