---
id: distributed-tracing-gaps
title: Distributed Tracing — Gap Analysis & Implementation
sidebar_position: 12
---

# Distributed Tracing — Gap Analysis & Implementation

Phase 21 added Jaeger as a tracing backend. After the full-stack review,
Jaeger was replaced with **Grafana Tempo** and the tracing pipeline was
rebuilt end-to-end around the existing OTel Collector DaemonSet that already
ships logs to Loki.

The design principle: **traces, logs, and metrics share a single collector
and are correlated in Grafana without any extra infrastructure**.

---

## Gap inventory

| # | Gap | Files changed | Status |
|---|-----|---------------|--------|
| A | No production-grade tracing backend | `helm-values/tempo-values.yaml`, `apps/tempo.yaml`, `manifests/tempo/` | ✅ |
| B | OTel Collector has no traces pipeline | `helm-values/otelcol-values.yaml`, `manifests/otelcol/01-networkpolicy-traces.yaml`, `manifests/otelcol/02-service-otlp.yaml` | ✅ |
| C | Go services emit no spans | `platform-demo/tracing.go`, `minicloud-plane/internal/tracing/tracer.go`, NATS publisher | ✅ |
| D | No Traces→Logs correlation in Grafana | `helm-values/kube-prometheus-stack-values.yaml` (datasource config) | ✅ |
| E | No Traces→Metrics exemplars | `platform-demo/main.go`, `minicloud-plane/internal/metrics/middleware.go`, kube-prometheus-stack-values.yaml | ✅ |

---

## Architecture

```
Go service (platform-demo / minicloud-plane)
    │  OTLP gRPC :4317
    │  (W3C TraceContext propagated on HTTP headers + NATS headers)
    ▼
OTel Collector DaemonSet  ─── node-local, same pod handles logs + traces
    │  traces pipeline:
    │  [otlp receiver] → [memory_limiter] → [k8sattributes/traces] → [batch] → [otlp/tempo]
    │
    ▼
Grafana Tempo 2.9.0 (observability ns, Longhorn 10Gi PVC, 14-day retention)
    │  HTTP query :3200
    ▼
Grafana (Tempo datasource uid=tempo)
    ├─ TraceQL search
    ├─ Node graph (service dependency from spans)
    ├─ Traces→Logs (clicks open Loki Explore filtered to same pod/namespace)
    └─ Traces→Metrics (exemplar dots on Prometheus histograms link to Tempo)
```

---

## Gap A — Grafana Tempo 2.9.0

### Problem

Jaeger (Phase 21) requires a separate query daemon and collector, stores
traces in-memory by default, and has no native Prometheus exemplar
integration. It does not fit the "single pipeline" design.

Grafana Tempo is a **trace-only backend** that accepts OTLP directly, stores
to a local filesystem or object store, and is queried natively by Grafana with
TraceQL. It costs one `StatefulSet`, one PVC, and one Service.

### Implementation

`helm-values/tempo-values.yaml` — key decisions:

```yaml
tempo:
  retention: 336h       # 14 days — enough for post-incident debugging

  receivers:
    otlp:
      protocols:
        grpc: {endpoint: 0.0.0.0:4317}
        http: {endpoint: 0.0.0.0:4318}

  storage:
    trace:
      backend: local
      local: {path: /var/tempo/traces}
      wal:   {path: /var/tempo/wal}

  securityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop: [ALL]     # satisfies K8sBlockNetRaw Gatekeeper constraint

persistence:
  enabled: true
  storageClassName: longhorn
  size: 10Gi
```

ArgoCD app `tempo` uses a 3-source pattern (chart 1.24.4 + values file +
`manifests/tempo/` for the NetworkPolicy):

```yaml
# manifests/tempo/01-networkpolicy.yaml
# allows monitoring namespace to query Tempo on port 3200
# (OTel Collector → Tempo 4317 is covered by allow-same-namespace)
```

Verify:

```bash
kubectl -n observability exec deploy/tempo -- \
  wget -qO- http://localhost:3200/ready
# ready
```

---

## Gap B — OTel Collector traces pipeline

### Problem

The OTel Collector DaemonSet already ran for logs (Gaps 1+2 from the log
pipeline work). Adding traces required three things:

1. Open OTLP ports (4317/4318) on the DaemonSet
2. Add a `traces` pipeline in the collector config
3. Expose a **ClusterIP Service** so instrumented pods can send spans without
   knowing which node they're on

### The chart gotcha

The `opentelemetry-collector` Helm chart **does not create a ClusterIP
Service in DaemonSet mode**. In DaemonSet mode the chart assumes each pod is
reached via its node IP. But application pods don't know their node IP at
startup — they need a stable DNS name.

Fix: a manually-managed Service in `manifests/otelcol/02-service-otlp.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: otelcol-opentelemetry-collector
  namespace: observability
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: opentelemetry-collector
    component: agent-collector
  ports:
    - name: otlp-grpc
      port: 4317
      targetPort: 4317
    - name: otlp-http
      port: 4318
      targetPort: 4318
```

The selector (`component: agent-collector`) matches the DaemonSet pods
in DaemonSet mode. kube-proxy round-robins across all healthy collector pods.

### Traces pipeline config

Added to `otelcol-values.yaml` alongside the existing `logs` pipeline:

```yaml
receivers:
  otlp:
    protocols:
      grpc: {endpoint: 0.0.0.0:4317}
      http: {endpoint: 0.0.0.0:4318}

processors:
  # Separate instance from the logs k8sattributes.
  # Traces use pod_association "from: connection" because the OTLP client
  # connects from the pod IP — that's how the collector looks up the pod.
  # The log pipeline uses "from: resource_attribute k8s.pod.uid" because
  # the filelog receiver parses the UID from the file path.
  k8sattributes/traces:
    auth_type: serviceAccount
    extract:
      metadata:
        - k8s.namespace.name
        - k8s.pod.name
        - k8s.pod.uid
        - k8s.node.name
        - k8s.container.name
        - k8s.deployment.name
    pod_association:
      - sources:
          - from: connection

exporters:
  otlp/tempo:
    endpoint: tempo.observability.svc:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers:  [otlp]
      processors: [memory_limiter, k8sattributes/traces, batch]
      exporters:  [otlp/tempo]
```

:::note Two k8sattributes instances
The logs pipeline uses `k8sattributes` (pod UID from file path).
The traces pipeline uses `k8sattributes/traces` (pod IP from connection).
Both use the same RBAC ClusterRole (`00-rbac.yaml`) — no additional permissions needed.
:::

NetworkPolicy `manifests/otelcol/01-networkpolicy-traces.yaml` opens
ports 4317/4318 from all namespaces:

```yaml
ingress:
  - from:
      - namespaceSelector: {}   # any namespace can push spans
    ports:
      - protocol: TCP
        port: 4317
      - protocol: TCP
        port: 4318
```

Memory bumped 256Mi → 384Mi (`limit_mib: 300`) to absorb the traces
pipeline alongside the existing logs workload without triggering the
memory limiter too aggressively.

:::caution Deprecation warnings in 0.156.0
The receiver names `otlp` and `otlphttp` are deprecated — the new names
are `otlp_grpc` and `otlp_http`. In 0.156.0 these are warnings only, not
errors. The config above uses the old names which still work. Update when
upgrading to 0.160+.
:::

---

## Gap C — Go service instrumentation

Both Go services (`platform-demo` and `minicloud-plane`) follow the same
pattern. The implementation is intentional about being **non-intrusive**:
the tracer is initialised once at startup; if it can't connect it falls back
to a no-op and the service keeps running without tracing.

### Shared tracer init pattern

```go
// platform-demo/tracing.go
func initTracer(ctx context.Context) func(context.Context) {
    endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint == "" {
        endpoint = "otelcol-opentelemetry-collector.observability.svc:4317"
    }

    exp, err := otlptracegrpc.New(ctx,
        otlptracegrpc.WithEndpoint(endpoint),
        otlptracegrpc.WithInsecure(),
    )
    if err != nil {
        log.Printf("warn: OTel exporter init: %v — running without tracing", err)
        return func(context.Context) {}  // no-op shutdown, service keeps running
    }

    res, _ := resource.New(ctx,
        resource.WithAttributes(semconv.ServiceName("platform-demo")),
    )
    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exp),
        sdktrace.WithResource(res),
        sdktrace.WithSampler(sdktrace.AlwaysSample()),
    )
    otel.SetTracerProvider(tp)
    otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
        propagation.TraceContext{},
        propagation.Baggage{},
    ))
    return func(ctx context.Context) { _ = tp.Shutdown(ctx) }
}
```

`minicloud-plane` uses the same code, extracted to `internal/tracing/tracer.go`
as `tracing.Init(ctx, serviceName string)` to avoid duplication across its
multiple binaries.

### HTTP handler wrapping

One line wraps the entire mux — no per-handler changes needed:

```go
// main.go (platform-demo)
handler := otelhttp.NewHandler(mux, "platform-demo")
http.ListenAndServe(":9898", handler)
```

`otelhttp.NewHandler` creates a root span per request, propagates the
W3C `traceparent` header from incoming requests (so cross-service traces
work if a client sends the header), and puts the span on the request context.

### NATS publish span (minicloud-plane)

The NATS publisher creates an explicit child span with `SpanKindProducer`
so the trace shows the full path: HTTP → handler → NATS publish:

```go
// internal/nats/publisher.go
func (p *Publisher) Publish(ctx context.Context, subject string, payload []byte) error {
    tracer := otel.Tracer("minicloud-plane/nats")
    ctx, span := tracer.Start(ctx, "nats.publish",
        trace.WithSpanKind(trace.SpanKindProducer),
        trace.WithAttributes(
            semconv.MessagingSystemKey.String("nats"),
            semconv.MessagingDestinationKey.String(subject),
        ),
    )
    defer span.End()

    if err := p.nc.Publish(subject, payload); err != nil {
        span.RecordError(err)
        return err
    }
    span.SetAttributes(attribute.Int("messaging.message.body.size", len(payload)))
    return nil
}
```

### Go version note

Adding `go.opentelemetry.io/otel v1.44.0` bumped the `go.mod` directive
in both repos (Go toolchain follows the minimum version of its dependencies).
CI `go-version` must be `>= 1.25`. If the CI step uses a pinned older version,
it will fail with a `go.mod` directive error.

---

## Gap D — Traces → Logs correlation

### Problem

Tempo shows a span, but the developer wants to see the log lines emitted
by that pod during that request window. Without a link, they have to
manually copy the pod name, open Loki, and reconstruct the time range.

### Implementation

Pre-wired in the Grafana Tempo datasource config when Tempo was deployed
(Gap A):

```yaml
# kube-prometheus-stack-values.yaml → grafana.additionalDataSources
- name: Tempo
  uid: tempo
  type: tempo
  url: http://tempo.observability.svc:3200
  jsonData:
    nodeGraph:
      enabled: true    # service dependency graph from span data

    tracesToLogsV2:
      datasourceUid: P8E80F9AEF21F6940   # Loki datasource UID
      spanStartTimeShift: "-5m"
      spanEndTimeShift:   "+5m"
      filterByTraceID: false
      filterBySpanID: false
      # Tag mappings: span resource attribute → Loki stream label
      # These match the OTTL copy statements in the OTel log pipeline:
      #   set(resource.attributes["namespace"], resource.attributes["k8s.namespace.name"])
      #   set(resource.attributes["pod"],       resource.attributes["k8s.pod.name"])
      tags:
        - {key: k8s.namespace.name, value: namespace}
        - {key: k8s.pod.name,       value: pod}
        - {key: service.name,       value: app}
```

The tag mappings translate OTel semantic attribute names (set by the
`k8sattributes` processor) to the Loki stream label names that the OTTL
`transform` processor copies them to. Without this alignment, Grafana
generates a Loki query with zero results.

When a developer clicks **View Logs** on any span, Grafana opens Loki
Explore pre-filtered to `{namespace="...", pod="..."}` with the span's
time window expanded by ±5 minutes.

---

## Gap E — Prometheus exemplars (Traces → Metrics)

### Problem

Metrics (histograms) and traces exist independently. A developer looking at
a p99 latency spike in Grafana cannot click through to the trace that caused
that specific slow sample. They have to search Tempo separately with a
manually constructed time range.

**OpenMetrics exemplars** solve this: each histogram observation carries an
optional label set. Prometheus stores and renders them as scatter-plot dots
on top of the histogram. Clicking a dot opens the linked trace.

### Three-part implementation

**Part 1 — Prometheus exemplar storage**

```yaml
# kube-prometheus-stack-values.yaml
prometheusSpec:
  enableFeatures:
    - exemplar-storage   # Prometheus TSDB stores exemplars (disabled by default)
```

Without this flag, Prometheus discards exemplar data even if services send it.

**Part 2 — Go services emit exemplars**

In the metrics middleware (both services), the standard `Observe(duration)` call is
replaced with a type-assertion to the `ExemplarObserver` interface:

```go
// platform-demo/main.go  (same pattern in minicloud-plane/internal/metrics/middleware.go)
sc := trace.SpanFromContext(r.Context()).SpanContext()

if eo, ok := obs.(prometheus.ExemplarObserver); ok {
    eo.ObserveWithExemplar(duration, prometheus.Labels{
        "traceID": sc.TraceID().String(),
    })
} else {
    obs.Observe(duration)
}
```

`otelhttp.NewHandler` (Gap C) sets the active span on the request context
before calling the handler. `trace.SpanFromContext` retrieves it.
The type assertion is required because `prometheus.Observer` does not expose
`ObserveWithExemplar` — only the concrete `*prometheus.Histogram` and
`*prometheus.Summary` implement `prometheus.ExemplarObserver`.

The `traceID` label key must match the Grafana datasource config in Part 3.

**Part 3 — Grafana links exemplar dots to Tempo**

```yaml
# kube-prometheus-stack-values.yaml → grafana.sidecar.datasources
exemplarTraceIdDestinations:
  name: traceID           # label key emitted by the Go services
  datasourceUid: tempo    # Tempo datasource UID
```

:::note kube-prometheus-stack template quirk
In kps 84.5.0, `exemplarTraceIdDestinations` is templated as a single
object, not a list. Pass it as `name: traceID / datasourceUid: tempo`
directly — not as `- name: ...`. Using a list causes a Helm render error.
:::

### End-to-end flow

```
request arrives at platform-demo
    │
    ├─ otelhttp creates span (trace ID: abc123)
    ├─ handler runs, records duration=312ms
    └─ metrics middleware:
         obs.(ExemplarObserver).ObserveWithExemplar(0.312, {"traceID":"abc123"})
              │
              ▼
         Prometheus scrapes histogram + exemplar
              │
              ▼
         Grafana histogram panel renders dot at t=now, y=312ms
              │  (click dot)
              ▼
         Tempo opens trace abc123
```

---

## Correlation matrix — what links to what

| From | To | Mechanism | Direction |
|------|----|-----------|-----------|
| Trace (Tempo) | Logs (Loki) | `tracesToLogsV2` tag mapping | Span → pod logs |
| Trace (Tempo) | Metrics (Prometheus) | `tracesToMetrics` datasource link | Span → histogram |
| Metric (Prometheus) | Trace (Tempo) | Exemplar with `traceID` label | Histogram dot → trace |
| Logs (Loki) | Trace (Tempo) | (future: `traceID` extraction in OTTL) | Log line → trace |

All three signals share the same Grafana instance with a single Explore view.

---

## Files changed

| File | What changed |
|------|--------------|
| `helm-values/tempo-values.yaml` | New — Tempo 2.9.0 single-binary, Longhorn 10Gi, 14-day retention, OTLP receivers |
| `helm-values/otelcol-values.yaml` | Added `otlp` receiver, `k8sattributes/traces` processor, `otlp/tempo` exporter, `traces` pipeline; memory 256→384Mi |
| `helm-values/kube-prometheus-stack-values.yaml` | Tempo datasource (tracesToLogsV2, nodeGraph, tracesToMetrics); `exemplarTraceIdDestinations`; `enableFeatures: [exemplar-storage]` |
| `manifests/otelcol/01-networkpolicy-traces.yaml` | New — opens 4317/4318 to all namespaces |
| `manifests/otelcol/02-service-otlp.yaml` | New — manual ClusterIP Service (chart doesn't create one in DaemonSet mode) |
| `manifests/tempo/01-networkpolicy.yaml` | New — monitoring → Tempo 3200 |
| `apps/tempo.yaml` | New — ArgoCD 3-source app |
| `platform-demo/tracing.go` | New — initTracer with OTLP gRPC exporter + graceful fallback |
| `platform-demo/main.go` | otelhttp.NewHandler wraps mux; ExemplarObserver in metrics middleware |
| `minicloud-plane/internal/tracing/tracer.go` | New — shared Init(ctx, serviceName) |
| `minicloud-plane/internal/nats/publisher.go` | NATS publish span (SpanKindProducer) |
| `minicloud-plane/internal/metrics/middleware.go` | ExemplarObserver in duration observation |

---

## Verification

```bash
# Tempo ready
kubectl -n observability exec statefulset/tempo -- wget -qO- http://localhost:3200/ready
# ready

# Collector traces pipeline active — check for otlp receiver in running config
kubectl -n observability exec daemonset/otelcol-opentelemetry-collector \
  -- wget -qO- http://localhost:13133/ | python3 -m json.tool | grep -i trace

# Manual OTLP push (no Go service needed)
kubectl -n observability run otlp-test --rm -it --image=ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest \
  --restart=Never -- traces \
  --otlp-endpoint=otelcol-opentelemetry-collector.observability.svc:4317 \
  --otlp-insecure --duration=5s --rate=5
# Then open Grafana Explore → Tempo → search "service.name = telemetrygen"

# Prometheus exemplar storage enabled
kubectl -n monitoring exec statefulset/prometheus-kps-prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=http_request_duration_seconds_bucket' \
  | python3 -c "
import json, sys
r = json.load(sys.stdin)['data']['result']
with_exemplar = [s for s in r if s.get('exemplars')]
print(f'{len(with_exemplar)} series have exemplars')
"
```
