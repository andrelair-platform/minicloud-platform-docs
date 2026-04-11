---
id: phase-11-observability
title: Phase 22 — Advanced Observability
sidebar_position: 12
---

# Phase 11 — Advanced Observability

Complete visibility into logs, metrics, traces, and alerts.

---

## Three Pillars

```text
Metrics  → Prometheus + Grafana
Logs     → Loki + Grafana
Traces   → Jaeger
Alerts   → Alertmanager
```

---

## Loki — Log Aggregation

Install Loki stack:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm install loki-stack grafana/loki-stack \
  --namespace monitoring \
  --set grafana.enabled=false \
  --set promtail.enabled=true
```

Promtail ships pod logs to Loki. Query them from Grafana using **LogQL**.

---

## Alertmanager

Configure alerts for critical conditions:

```yaml
groups:
  - name: cluster
    rules:
      - alert: NodeDown
        expr: up{job="node"} == 0
        for: 5m
        annotations:
          summary: "Node {{ $labels.instance }} is down"
```

---

## Jaeger — Distributed Tracing

```bash
kubectl apply -f https://github.com/jaegertracing/jaeger-operator/releases/latest/download/jaeger-operator.yaml
```

Add tracing to your apps using OpenTelemetry SDKs.

---

## Full Observability Dashboard (Grafana)

| Panel | Data Source |
|---|---|
| Node CPU/RAM/Disk | Prometheus (node-exporter) |
| Pod health | Prometheus (kube-state-metrics) |
| Application logs | Loki |
| Request traces | Jaeger |
| Active alerts | Alertmanager |

---

## Done When

```text
✔ Logs flowing into Loki
✔ Alerts firing on node failures
✔ Traces visible for app requests
✔ Single Grafana dashboard shows everything
```
