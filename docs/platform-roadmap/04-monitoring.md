---
id: phase-4-monitoring
title: Phase 8 — Monitoring
sidebar_position: 5
---

# Phase 4 — Monitoring Stack

Visibility into cluster health, node metrics, and application performance.

---

## Stack

| Tool | Purpose |
|---|---|
| **Prometheus** | Metrics collection & storage |
| **Grafana** | Dashboards & visualization |
| **Loki** | Log aggregation (phase 11) |
| **Alertmanager** | Alerts & notifications |

---

## Install kube-prometheus Stack

```bash
kubectl apply -f https://github.com/prometheus-operator/prometheus-operator/releases/latest/download/bundle.yaml
```

This deploys the Prometheus Operator which manages Prometheus, Grafana, and Alertmanager via CRDs.

---

## Access Grafana

```bash
kubectl port-forward svc/grafana -n monitoring 3000:3000
```

Open: `http://localhost:3000`

Default credentials: `admin / admin`

---

## Key Dashboards to Import

| Dashboard | Grafana ID |
|---|---|
| Kubernetes cluster overview | 7249 |
| Node exporter full | 1860 |
| k3s cluster monitoring | 13770 |

---

## Done When

```text
✔ Prometheus scraping all nodes
✔ Grafana dashboards showing metrics
✔ Node CPU, RAM, disk visible
```
