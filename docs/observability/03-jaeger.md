---
id: jaeger
title: Jaeger / distributed tracing (Deferred)
sidebar_position: 3
---

# Jaeger — Distributed tracing

:::caution Status: Deferred to a future phase
The original Phase 21 plan called for **Loki + Jaeger + Alertmanager**.
We deliberately scoped Phase 21 down to **Loki + Alertmanager
configuration only** — same pattern as Phase 11 (deferred Crossplane),
Phase 13 (deferred GitLab), Phase 15 (deferred Vault), Phase 16
(deferred n8n/Temporal/Airflow), Phase 18 (deferred Backstage plugins),
Phase 19 (deferred MLflow + Kubeflow), Phase 20 (deferred NodeChaos +
automated GameDays).

**Why Jaeger is deferred:**

1. **No microservice topology to trace through.** Distributed tracing
   shows the call graph of a request as it traverses multiple
   services. Our workloads (podinfo, whoami, platform-demo, Open WebUI)
   are **single-service** — each request enters one pod, executes one
   handler, returns. A Jaeger UI under those conditions shows
   single-span boxes — the tool exists, but its value isn't visible.
2. **Without instrumented multi-service apps, Jaeger can't
   demonstrate** what makes it valuable: latency attribution across
   services, finding the slow span in a chain of 8, or root-causing a
   timeout to a DB call three hops downstream.
3. **The metrics + logs pair already covers** request-flow
   observability for our scale. We have request rate / error rate /
   latency from Prometheus, and detailed request logs from Loki — the
   "two of three legs" cover the visible bottlenecks.

**The likely future home** is when we deploy a real microservices
demo — e.g., an API gateway → auth service → business logic service →
database that actually emits traces via OpenTelemetry. At that point
Jaeger (or Grafana Tempo) earns its keep because there's a multi-span
trace tree to look at.

This page is kept as conceptual reference. The implementation has not
been done.
:::

---

## What Jaeger would solve

Distributed tracing follows a single request as it flows through
multiple services. Each service emits **spans** (start time, end time,
parent span ID, attributes); spans assemble into a **trace tree** that
shows where time was spent, where errors occurred, and which service
introduced latency.

Without traces, you debug "why is this user's request slow?" by
correlating timestamps across logs from N services. With traces, you
look at one trace ID and see the full waterfall.

---

## When Jaeger earns its keep

```text
WITHOUT TRACING (single-service apps — what we have today):
  user → ingress → podinfo → response
                   |
                   '-- a single span, easy to debug from logs alone

WITH TRACING (multi-service apps — what would justify Jaeger):
  user → ingress → API gateway → auth → user service → DB
                                  '-- trace shows: which service was slow,
                                      which service errored, total wall-clock
                                      vs sum-of-services time
```

---

## Architecture (when implemented)

```text
Application pods (instrumented with OpenTelemetry SDK)
      │
      │ OTLP traces over gRPC (port 4317)
      ▼
otel-collector (DaemonSet, batches + filters)
      │
      ▼
Jaeger collector (or Grafana Tempo)
      │
      ▼
Storage backend (Cassandra / ES / Badger / S3 for Tempo)
      │
      ▼
Jaeger UI / Tempo Grafana datasource
```

---

## Future install sketch

```bash
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts

# Or, more likely: Grafana Tempo (lighter, integrates with Loki + Prometheus)
helm repo add grafana https://grafana.github.io/helm-charts

helm install tempo grafana/tempo \
  -n observability \
  --set storage.trace.backend=local \
  --set tempo.retention=72h
```

Then wire Tempo as a Grafana datasource alongside Prometheus + Loki.

---

## Done When (not yet — deferred)

```text
✘ Multi-service demo workload exists and is instrumented with OpenTelemetry
✘ Tempo / Jaeger collector running in observability namespace
✘ At least one trace ID visible in Grafana → Explore → Tempo
✘ Trace tree shows >= 3 distinct services involved in a single request
✘ Latency attribution: ability to identify the slowest span in a trace
```
