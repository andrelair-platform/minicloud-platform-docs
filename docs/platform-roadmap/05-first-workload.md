---
id: phase-5-workload
title: Phase 9 — First Workload
sidebar_position: 6
---

# Phase 5 — Deploy First Workload

Verify the cluster can run real applications.

---

## Deploy nginx

```bash
kubectl create deployment nginx --image=nginx
kubectl expose deployment nginx --port=80 --type=NodePort
```

---

## Find the NodePort

```bash
kubectl get svc nginx
```

Look for the `NodePort` value (e.g. `30080`).

---

## Access the App

```bash
curl http://10.0.0.2:30080
```

Or open in browser: `http://10.0.0.2:30080`

---

## What This Proves

```text
✔ Container runtime (containerd) is working
✔ Scheduler placing pods correctly
✔ Service networking (kube-proxy) working
✔ NodePort routing working
```

---

## Clean Up

```bash
kubectl delete deployment nginx
kubectl delete svc nginx
```

---

## Done When

```text
✔ nginx returns 200 OK
✔ Pod scheduled on a worker node
```
