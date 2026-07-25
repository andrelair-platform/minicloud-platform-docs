---
id: cicd-gap-analysis
title: CI/CD Gap Analysis — Unit Tests, Security Scans, Progressive Delivery
sidebar_label: CI/CD Gap Analysis ✅
---

# CI/CD Gap Analysis — Unit Tests, Security Scans, Progressive Delivery

A structured audit of CI/CD quality gates across the minicloud platform services, identifying 10 gaps and closing all of them across 5 priority levels.

---

## Gap Inventory

| ID | Gap | Service(s) | Priority | Status |
|----|-----|-----------|----------|--------|
| 1 | Integration tests — real dependency coverage | platform-demo, minicloud-plane | P3 | ✅ |
| 2 | Unit tests — zero test files | minicloud-plane | P1 | ✅ |
| 3 | Post-deploy smoke test — complete the deploy loop | platform-demo, minicloud-plane | P3 | ✅ |
| 4 | Load test (k6) | platform-demo | P4 | ✅ |
| 5 | gosec + govulncheck source-level security scans | platform-demo, minicloud-plane | P2 | ✅ |
| 6 | kubeconform — manifest validation PR gate | minicloud-gitops | P2 | ✅ |
| 7 | Container image scan (Trivy CRITICAL exit-1) | All image repos | Pre-existing | ✅ |
| 8 | Blue/Green deployment — minicloud-plane | minicloud-plane | P4 | ✅ |
| 9 | Staging gate automation | platform-demo, minicloud-plane | P5 | ✅ |
| 10 | AnalysisTemplate NaN from KEDA scale-to-zero | platform-demo, minicloud-plane | P1 | ✅ |

---

## P1 — Gap 2: minicloud-plane Unit Tests

minicloud-plane had zero test files. The service has three layers:
- `internal/webhook` — HMAC-signed Plane webhook receiver → NATS publisher
- `internal/api` — REST proxy exposing Plane projects/issues to Backstage
- `internal/plane` — HTTP client for the Plane CE REST API
- `internal/metrics` — Prometheus middleware

### Interface extraction (enables test doubles)

**`internal/webhook/handler.go`** — extracted `Publisher` interface:

```go
type Publisher interface {
    Publish(ctx context.Context, event, action string, data any) error
}

type Handler struct {
    secret    string
    publisher Publisher
}
```

**`internal/api/handler.go`** — extracted `PlaneClient` interface:

```go
type PlaneClient interface {
    Projects() ([]plane.Project, error)
    Issues(projectID string) ([]plane.Issue, error)
}
```

Both handlers now accept interfaces rather than concrete types — the real NATS publisher and Plane HTTP client implement them. Tests inject mocks.

### Test coverage (19 tests across 4 packages)

| File | Tests | What is covered |
|------|-------|----------------|
| `internal/webhook/handler_test.go` | 7 | MethodNotAllowed, valid HMAC, invalid HMAC, no-secret passthrough, invalid JSON, publish error non-fatal, signature helper |
| `internal/api/handler_test.go` | 6 | Projects OK + trailing slash, Issues OK, unknown path 404, upstream errors |
| `internal/plane/client_test.go` | 6 | Projects list, auth header sent, Issues list, Issue single, HTTP 4xx, HTTP 5xx |
| `internal/metrics/middleware_test.go` | 2 | Status passthrough (table: 200/201/400/404/500), default 200 |

All use `httptest.NewServer` — no real NATS or Plane API needed.

---

## P1 — Gap 10: AnalysisTemplate NaN from KEDA Scale-to-Zero

KEDA `ScaledObject` in dev scales the service to 0 replicas outside 08:00–19:00 CET Mon–Fri. When a deploy happens during off-hours, the `AnalysisTemplate` fires while there are 0 running pods — no traffic, empty Prometheus vector, `NaN >= 0.95` evaluates to `false`, rollback.

### Root cause

```promql
# Before — empty series when no pods → returns empty vector → NaN
sum(rate(http_requests_total{service="platform-demo"}[2m]))
/
sum(rate(http_requests_total{service="platform-demo"}[2m]))
```

### Fix — `or vector(N)`

The Prometheus `or` binary operator returns the right-hand side when the left-hand series is empty:

```yaml
# services/platform-demo/base/analysis-template.yaml
query: |
  (
    sum(rate(http_requests_total{service="platform-demo",code!~"5.."}[2m]))
    /
    sum(rate(http_requests_total{service="platform-demo"}[2m]))
  ) or vector(1)   # ← 1.0 = 100% success when no traffic
```

```yaml
query: |
  histogram_quantile(
    0.95,
    job:http_request_duration_seconds_bucket:rate5m{service="platform-demo"}
  ) or vector(0)   # ← 0s latency when no traffic, satisfies ≤ 0.5 threshold
```

The same fix was applied to `services/minicloud-plane/base/analysis-template.yaml`.

Why `vector(1)` for success rate and `vector(0)` for latency:
- Success rate gate: `result[0] >= 0.95` — returning 1.0 means "all requests succeeded" which is accurate when there are no error requests
- Latency gate: `result[0] <= 0.5` — returning 0 means "zero latency" which satisfies the threshold; the readinessProbe already confirmed pod health

---

## P2 — Gap 5: gosec + govulncheck

Added to the `test` job in both `platform-demo` and `minicloud-plane` CI:

```yaml
- name: Vulnerability check (govulncheck)
  run: |
    go install golang.org/x/vuln/cmd/govulncheck@latest
    govulncheck ./...

- name: Static security analysis (gosec)
  run: |
    go install github.com/securego/gosec/v2/cmd/gosec@latest
    gosec -severity high -confidence medium ./...
```

**govulncheck** checks the Go vulnerability database against call graphs — it only flags vulnerabilities in code paths actually reachable from the binary, not every transitive dependency in `go.sum`. This eliminates false positives from packages that are present but not called.

**gosec** performs AST-level static analysis. The `-severity high -confidence medium` flags catch real issues (hardcoded credentials, SQL injection, path traversal, command injection, unsafe TLS, integer overflow) without triggering on low-confidence stylistic findings.

Both run before the Docker build step — a vulnerability blocks the image from being built.

---

## P2 — Gap 6: kubeconform Manifest Validation

`.github/workflows/validate-manifests.yml` in `minicloud-gitops` — triggers on PRs that touch `services/**` or `manifests/**`:

```yaml
- name: Build all kustomize overlays and validate
  run: |
    while IFS= read -r overlay; do
      echo "=== $overlay ==="
      kustomize build "$overlay" | \
        kubeconform \
          -strict \
          -kubernetes-version "${{ env.K8S_VERSION }}" \
          -ignore-missing-schemas \
          -summary
    done < <(find services -name kustomization.yaml -path "*/overlays/*" \
               -exec dirname {} \;)

- name: Validate raw manifests
  run: |
    find manifests -name "*.yaml" ! -path "*/gatekeeper-policies/*" | \
      kubeconform \
        -strict \
        -kubernetes-version "${{ env.K8S_VERSION }}" \
        -ignore-missing-schemas \
        -summary
```

`-ignore-missing-schemas` skips unknown CRDs (Rollout, AnalysisTemplate, ExternalSecret, etc.) — kubeconform validates native Kubernetes types strictly (apiVersion, kind, required fields, field types) without erroring on custom resources.

`-strict` rejects unknown fields — catches typos in field names (`containerPort` vs `ports[].containerPort`, `securityContex` vs `securityContext`).

---

## P3 — Gap 1: Integration Tests

Integration tests use `//go:build integration` and `httptest.NewServer` — they test the full request/response cycle including routing, content-type headers, Prometheus instrumentation, and JSON encoding, but without any cluster dependency.

### platform-demo

`newHandler()` extracted from `main()`:

```go
func newHandler() http.Handler {
    mux := http.NewServeMux()
    mux.HandleFunc("/", instrument("/", handleRoot))
    mux.HandleFunc("/healthz", instrument("/healthz", handleHealthz))
    mux.HandleFunc("/readyz", instrument("/readyz", handleReadyz))
    mux.Handle("/metrics", promhttp.Handler())
    return otelhttp.NewHandler(mux, "platform-demo")
}
```

5 integration tests share a single `httptest.Server` via `sync.Once`:

| Test | Asserts |
|------|---------|
| `TestIntegration_Root` | 200, `Content-Type: application/json`, `body.app == "platform-demo"`, `body.goVersion` non-empty |
| `TestIntegration_Healthz` | 200, body starts with `ok` |
| `TestIntegration_Readyz` | 200 |
| `TestIntegration_Metrics` | 200, `text/plain` Content-Type, `http_requests_total` + `http_request_duration_seconds` present |
| `TestIntegration_Concurrent` | 10 workers × 5 requests each, all 200 |

### minicloud-plane

`newServer()` extracted from `main()`:

```go
func newServer(client planeapi.PlaneClient, pub webhook.Publisher, webhookSecret string) http.Handler {
    mux := http.NewServeMux()
    mux.Handle("/health", ...)
    mux.Handle("/webhook", metrics.Instrument("/webhook", webhook.NewHandler(webhookSecret, pub)))
    mux.Handle("/api/", metrics.Instrument("/api/", planeapi.NewHandler(client)))
    mux.Handle("/metrics", promhttp.Handler())
    return otelhttp.NewHandler(mux, "minicloud-plane")
}
```

6 integration tests with `mockPlane` (in-memory projects/issues map) and `mockPub` (atomic call counter):

| Test | Asserts |
|------|---------|
| `TestIntegration_Health` | 200, `{"status":"ok","service":"minicloud-plane"}` |
| `TestIntegration_APIProjects` | 200, returns seeded project `p1` |
| `TestIntegration_APIIssues` | 200, returns seeded issue `i1` for project `p1` |
| `TestIntegration_WebhookPublishes` | POST → 200, `mockPub.n` incremented by 1 |
| `TestIntegration_Metrics` | 200, `http_requests_total` in body |
| `TestIntegration_APIUnknownPath` | `/api/unknown/path` → 404 |

---

## P3 — Gap 3: Post-Deploy Smoke Test

The `smoke-test` CI job (main branch only) closes the loop between "image pushed to Harbor" and "service is actually healthy in the cluster":

```
main push
  → unit tests
  → integration tests (httptest)
  → build + scan + sign
  → gitops bump (ArgoCD auto-sync picks up new tag)
  → smoke-test:
      1. Tailscale + CA + KUBE_CONFIG_BASE64 (static cert context, no OIDC)
      2. Poll rollout phase every 10s, max 5 min
      3. curl pod inside cluster namespace → /healthz + /
  → load-test (platform-demo only)
  → promote-staging PR
```

**Polling loop:**

```bash
for i in $(seq 1 27); do
  PHASE=$(kubectl get rollout platform-demo -n platform-demo-dev \
    -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
  [ "$PHASE" = "Healthy" ] && exit 0
  [ "$PHASE" = "Degraded" ] && exit 1
  sleep 10
done
```

**Curl pod probe:**

```bash
kubectl run smoke-${{ github.run_id }} \
  --image=curlimages/curl:8 \
  --restart=Never \
  --rm \
  -n platform-demo-dev \
  --timeout=30s \
  -- -sf --max-time 5 http://platform-demo:9898/healthz
```

The pod runs inside the namespace — it goes through the Service selector, confirms real routing works, then exits and is garbage-collected (`--rm`). Using the cluster-internal service URL rather than the Ingress avoids Cloudflare and TLS variables.

**KUBE_CONFIG_BASE64** is a GitHub Actions org secret (visibility: all) containing a minimal kubeconfig with the `minicloud-break-glass` static cert context. It gives CI kubectl access without browser OIDC. The static cert is the emergency break-glass credential — the read scope is sufficient for `get rollout`, `run`, etc.

---

## P4 — Gap 4: k6 Load Test

`platform-demo/k6/smoke.js` — 35-second staged load against the dev service:

```javascript
export const options = {
  stages: [
    { duration: '10s', target: 5 },  // ramp up to 5 VUs
    { duration: '20s', target: 5 },  // hold — generates Prometheus histogram data
    { duration: '5s',  target: 0 },  // ramp down
  ],
  thresholds: {
    http_req_failed:                      ['rate<0.01'],  // < 1% HTTP errors
    http_req_duration:                    ['p(95)<500'],  // overall p95 < 500ms
    'http_req_duration{endpoint:root}':   ['p(95)<200'],  // root endpoint
    'http_req_duration{endpoint:health}': ['p(95)<50'],   // health check
    errors:                               ['rate<0.01'],
  },
};
```

The 20-second hold window at 5 VUs generates enough histogram samples for Prometheus to compute accurate `histogram_quantile` values — this is the window the post-deploy `http-regression-gate` AnalysisTemplate uses.

The `load-test` CI job port-forwards the dev service before running k6:

```bash
kubectl port-forward svc/platform-demo 9898:9898 -n platform-demo-dev &
PF_PID=$!
sleep 3
k6 run k6/smoke.js
kill $PF_PID
```

---

## P4 — Gap 8: BlueGreen for minicloud-plane

minicloud-plane is a single-replica webhook bridge. The previous canary strategy was:

```yaml
canary:
  steps:
    - setWeight: 100      # atomic swap — no real split with 1 pod
    - pause: {duration: 2m}
    - analysis:
        templates: [http-regression-gate]
```

This has no zero-downtime guarantee — the old pod terminates before the 2-minute pause begins.

### BlueGreen strategy

```
Deploy new image
  → Rollout controller creates new RS (blue)
  → minicloud-plane-preview Service selector → new RS pods
  → prePromotionAnalysis: preview-health-gate
      3× GET http://minicloud-plane-preview:8080/health (every 10s)
      assert result.status == "ok"
  → autoPromotionSeconds: 30 after analysis passes
  → Active service selector atomically switches to new RS
  → postPromotionAnalysis: http-regression-gate (Prometheus RED signals)
  → Old RS stays 30s (scaleDownDelaySeconds) for instant rollback
```

**New files in `services/minicloud-plane/base/`:**

`service-preview.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: minicloud-plane-preview
spec:
  selector:
    app: minicloud-plane
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

`analysis-template-preview.yaml` — uses Argo's built-in **Web provider** to call the preview service directly (no Prometheus lag — immediate health check before traffic switches):

```yaml
spec:
  metrics:
    - name: health
      count: 3
      interval: 10s
      successCondition: result.status == "ok"
      failureLimit: 1
      provider:
        web:
          url: http://minicloud-plane-preview:8080/health
          jsonPath: "{$.status}"
```

`deployment.yaml` strategy change:

```yaml
strategy:
  blueGreen:
    activeService: minicloud-plane
    previewService: minicloud-plane-preview
    autoPromotionEnabled: true
    autoPromotionSeconds: 30
    scaleDownDelaySeconds: 30
    prePromotionAnalysis:
      templates:
        - templateName: preview-health-gate
    postPromotionAnalysis:
      templates:
        - templateName: http-regression-gate
```

The Rollout controller manages the `rollouts-pod-template-hash` label selector on both services dynamically — the preview service automatically points to the candidate RS, the active service to the stable RS.

### Why BlueGreen here vs canary

| | Canary | BlueGreen |
|---|---|---|
| Works with 1 replica | No meaningful split | Yes — two RS exist simultaneously |
| Zero-downtime guarantee | No | Yes — old pod alive until switch |
| Rollback mechanism | Scale down canary RS | Keep old RS for `scaleDownDelaySeconds` |
| Analysis timing | After traffic switched | Before (prePromotion) and after (postPromotion) |

---

## P5 — Gap 9: Staging Gate Automation

The `promote-staging` CI job opens a GPG-signed PR in `minicloud-gitops` to bump the staging overlay after the smoke test (minicloud-plane) or load test (platform-demo) passes:

```yaml
promote-staging:
  needs: load-test   # platform-demo: after k6 passes
  # needs: smoke-test  # minicloud-plane: after curl pod passes
  if: github.ref_name == 'main'
```

The job:
1. Checks out minicloud-gitops with `GITOPS_TOKEN`
2. Imports the GPG key (crazy-max action)
3. Creates a branch `ci/promote-<service>-staging-<sha>`
4. Runs `kustomize edit set image` on the staging overlay
5. Commits with `-S` (GPG-signed) and pushes
6. Opens a PR — no auto-merge: the PR is the gate

**What the PR body says:**
```
Auto-generated staging promotion after:
- Unit tests passed
- Integration tests passed (httptest)
- Container image built, Trivy scanned, Cosign signed
- Argo Rollout reached Healthy in dev
- HTTP smoke probes passed
- k6 load test passed (p95 < 500ms, error rate < 1%)

**Merge this PR to deploy to staging. Manual ArgoCD sync required after merge.**
```

The human merge is intentional — staging is the final checkpoint before prod, and ArgoCD manual sync on the staging app provides a second gate. The automation does the evidence gathering; the engineer decides.

---

## Full CI Pipeline (main branch)

```
push to main
│
├─ test (unit tests + govulncheck + gosec)
│   └─ integration-test (httptest suite, no cluster)
│       └─ build-and-push (Docker build, Trivy CRITICAL, Cosign sign, SBOM attach)
│           └─ bump-gitops (kustomize set image on dev overlay, PR + auto-merge)
│               └─ smoke-test (cluster: wait Rollout Healthy, curl pod probe)
│                   └─ load-test (platform-demo only: port-forward + k6 35s)
│                       └─ promote-staging (open signed PR on staging overlay)
```

PRs against main trigger only `test` + `integration-test` + (when needed) `kubeconform` — no build, no push, no cluster access.

---

## Gotchas

**`or vector(N)` in PromQL requires the left-hand expression to also be a vector.**
`histogram_quantile(...) or vector(0)` works because `histogram_quantile` returns a vector. A scalar expression would cause a parse error.

**`KUBE_CONFIG_BASE64` must use the static cert context, not the OIDC context.**
OIDC (`minicloud-oidc`) requires a browser callback for kubelogin. CI has no browser. The `minicloud-break-glass` context uses a client certificate embedded in the kubeconfig — base64-encode the entire kubeconfig, set as org secret.

**`kubectl run --rm` pod may linger if the CI job is cancelled.**
The pod has `--restart=Never` and `--timeout=30s`. If CI is cancelled mid-probe, the pod stays in the namespace. Clean up manually: `kubectl delete pod -n <ns> -l run=smoke-<run_id>` or wait for the 5-minute default eviction.

**BlueGreen `scaleDownDelaySeconds` holds the old RS alive — ArgoCD shows 2 pods temporarily.**
This is expected. ArgoCD health check for Rollouts waits for `phase: Healthy` which is set only after the old RS is scaled to 0. The smoke-test polling correctly waits for `Healthy`, not just `Progressing`.

**`prePromotionAnalysis` Web provider URL must use the short DNS name.**
`http://minicloud-plane-preview:8080/health` resolves inside the namespace because AnalysisRuns are created in the same namespace as the Rollout. Using the full FQDN (`minicloud-plane-preview.minicloud-plane-dev.svc.cluster.local`) also works but is unnecessary.
