---
id: alertmanager
title: Phase 21 — Alertmanager routing + custom alerts
sidebar_position: 2
---

# Phase 21 — Alertmanager: from "screaming into the void" to validated alerts

The kube-prometheus-stack from Phase 8 ships **32 PrometheusRules out
of the box** plus an Alertmanager pod. But the chart's default config
routes every alert to a `null` receiver. So real alerts fire and
nobody gets paged.

When we surveyed the cluster at the start of Phase 21, **9 alerts were
already firing** and being silently swallowed:

| Alert | Real or noise? | Status |
|---|---|---|
| `Watchdog` | Healthy by design (always-firing self-test) | OK |
| `NodeClockNotSynchronising × 3` | **Real** — DHCP-assigned IPv6 NTP unreachable | Fixed (explicit NTP servers) |
| `KubeProxyDown` | k3s false positive (embedded kube-proxy) | Silenced via routing tree |
| `CPUThrottlingHigh × 3` | **Real** — node-exporter at 100m limit hit 60% throttling | Fixed (limit bumped to 250m) |
| `KubePersistentVolumeFillingUp` | **CRITICAL** — open-webui PVC at **0% free** | Fixed (PVC expanded 1→5 GiB online) |

Phase 21's Alertmanager work fixes the routing AND the underlying
issues the alerts were correctly catching.

---

## The Day-2 fixes (before installing Loki)

### Fix 1 — open-webui PVC filling up

Phase 19 allocated 1 GiB. Open WebUI's RAG embeddings filled it within
a day. Longhorn supports online volume expansion:

```bash
kubectl patch pvc -n ai open-webui --type merge \
  -p '{"spec":{"resources":{"requests":{"storage":"5Gi"}}}}'

# Verify (no pod restart needed)
kubectl exec -n ai open-webui-0 -- df -h /app/backend/data
# /dev/longhorn/...   4.9G   958M   4.0G   20%
```

Update `open-webui-values.yaml` to match (so a future helm upgrade
doesn't try to "shrink"). The volume expansion is a **silent positive
test of Phase 5 Longhorn capabilities** — `allowVolumeExpansion: true`
on the StorageClass actually does what it claims.

### Fix 2 — node-exporter CPU throttling

`CPUThrottlingHigh` was firing on all 3 node-exporter pods at 38-69%
throttling. node-exporter bursts above its 100m limit during scrape
intervals. Bump to 250m:

```yaml
# kube-prometheus-stack-values.yaml
prometheus-node-exporter:
  resources:
    requests: { cpu: 10m,  memory: 32Mi }
    limits:   { cpu: 250m, memory: 128Mi }
```

### Fix 3 — NTP not synchronizing

All 3 nodes reported `System clock synchronized: no`. systemd-timesyncd
was using a DHCP-assigned IPv6 NTP server (`2a02:8424:6ee0:...`) that
wasn't reachable through our NAT. UDP/123 to public NTP servers worked
fine — the issue was just the upstream NTP target.

Fix on each node: `/etc/systemd/timesyncd.conf`:

```ini
[Time]
NTP=time.cloudflare.com pool.ntp.org
FallbackNTPServers=ntp.ubuntu.com
```

Then `sudo systemctl restart systemd-timesyncd` and verify
`timedatectl status | grep synchronized` flips to `yes`.

A future Ansible role will codify this as part of the `common`
play to make it a permanent cluster invariant.

---

## Architecture

```text
                Prometheus (Phase 8)
                 │
                 │ evaluates 32 + 1 PrometheusRule resources
                 │ (32 from kube-prometheus-stack default,
                 │  1 custom: PodinfoAvailabilityLost)
                 ▼
                Alertmanager (Phase 8 install, Phase 21 reconfig)
                 │
                 │ kube-prometheus-stack default → null receiver (BAD)
                 │ Phase 21 → 3-tier routing tree:
                 │
                 ├── alertname = Watchdog                      → null
                 ├── alertname =~ k3s-false-positives          → null
                 ├── severity = critical                       → webhook-critical
                 ├── severity = warning                        → webhook-default
                 └── severity = info                           → null
                 │
                 ▼
                alert-webhook-logger pod (monitoring namespace)
                 │
                 │ 30-line Python receiver, listens :8080,
                 │ pretty-prints alert payloads to stdout
                 ▼
                kubectl logs -n monitoring \
                  -l app=alert-webhook-logger -f
```

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Alertmanager install** | Already present from Phase 8 (kube-prometheus-stack) | No new pod — just config. |
| **Notification target** | **In-cluster webhook receiver pod** (Python `http.server`) | Self-contained, no external dependencies (no Slack workspace, no SMTP). Verifiable via `kubectl logs`. Real Slack/email/PagerDuty is a 5-line YAML change. |
| **Routing tree** | 3-tier (critical / warning / info) | Models real production routing. `severity` label on each rule selects which path. |
| **k3s false positives** | Silenced at the route level (via inhibit-style match → null), not by disabling the rules | The user's pro-tip: this is "more K8s-native." Routes are reversible without re-rendering the chart. |
| **Inhibit rules** | critical suppresses warning+info for same alertname/namespace; warning suppresses info | Prevents alert storms when one underlying issue triggers multiple severity tiers. |
| **`PodinfoAvailabilityLost.for: 2m`** | The user-mandated anti-flapping window | Absolutely critical — see "The flap that proved the rule" below. |

### What's deliberately deferred

| Component | Why deferred |
|---|---|
| Real Slack / email / PagerDuty receivers | One URL change in the receiver config |
| Alertmanager HA cluster (2-3 replicas) | Single replica is fine on a 3-node cluster |
| AlertmanagerConfig CRDs (per-tenant routing) | Single-operator cluster |
| Silence automation | Manual silences via UI work fine |
| Custom alert templates (.tmpl) | Default template formatted clearly enough for the demo |

---

## The webhook receiver

A 30-line Python program in a ConfigMap, mounted into a Deployment:

```python
import http.server, json, sys, datetime, socketserver

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body) if body else {}

        ts = datetime.datetime.utcnow().isoformat() + "Z"
        print(f"\n=== ALERT @ {ts} ===")
        print(f"  receiver: {payload.get('receiver')}")
        print(f"  status:   {payload.get('status')}")
        print(f"  groupKey: {payload.get('groupKey','')}")
        for alert in payload.get("alerts", []):
            lab = alert.get("labels", {})
            anno = alert.get("annotations", {})
            print(f"  - {alert.get('status','?').upper():>8s}: "
                  f"{lab.get('alertname','?')}  severity={lab.get('severity','?')}  "
                  f"namespace={lab.get('namespace','-')}")
            if anno.get('summary'):
                print(f"      summary: {anno['summary']}")
        sys.stdout.flush()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *_): pass

class ReusingServer(socketserver.TCPServer):
    allow_reuse_address = True

with ReusingServer(("", 8080), Handler) as httpd:
    print("webhook receiver listening on :8080")
    sys.stdout.flush()
    httpd.serve_forever()
```

The full Deployment + ConfigMap + Service is at
`/home/ktayl/minicloud-ktaylorganisation/observability/webhook-receiver.yaml`.

The Deployment uses the Phase 16 sovereign registry —
`harbor.10.0.0.200.nip.io/docker-hub/library/python:3.12-slim` —
proving the proxy cache pattern is still working.

Smoke test:

```bash
kubectl run alert-smoke --image=curlimages/curl:latest --rm -it \
  --restart=Never -n monitoring --command -- \
  curl -sf -X POST -H 'Content-Type: application/json' \
       -d '{"receiver":"smoke","status":"firing",
            "alerts":[{"status":"firing",
                       "labels":{"alertname":"SmokeTest","severity":"info"},
                       "annotations":{"summary":"smoke test"}}]}' \
       http://alert-webhook-logger:80/

kubectl logs -n monitoring -l app=alert-webhook-logger
# === ALERT @ 2026-05-09T18:28:58Z ===
#   receiver: smoke
#   status:   firing
#   - FIRING: SmokeTest  severity=info  namespace=-
#       summary: smoke test
```

---

## Alertmanager routing config

In `kube-prometheus-stack-values.yaml`:

```yaml
alertmanager:
  config:
    global:
      resolve_timeout: 5m
    inhibit_rules:
      - source_matchers: ['severity = critical']
        target_matchers: ['severity =~ "warning|info"']
        equal: [namespace, alertname]
      - source_matchers: ['severity = warning']
        target_matchers: ['severity = info']
        equal: [namespace, alertname]
    route:
      group_by: [alertname, namespace]
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 12h
      receiver: webhook-default
      routes:
        - matchers: ['alertname = "Watchdog"']
          receiver: "null"
        # k3s false positives: kube-proxy / controller-manager / scheduler
        # are embedded in k3s-server/agent — no separate process to scrape.
        - matchers:
            - 'alertname =~ "KubeProxyDown|KubeControllerManagerDown|KubeSchedulerDown"'
          receiver: "null"
        - matchers: ['severity = critical']
          receiver: webhook-critical
          continue: false
        - matchers: ['severity = warning']
          receiver: webhook-default
          continue: false
        - matchers: ['severity = info']
          receiver: "null"
    receivers:
      - name: "null"
      - name: webhook-default
        webhook_configs:
          - url: http://alert-webhook-logger.monitoring.svc:80/
            send_resolved: true
      - name: webhook-critical
        webhook_configs:
          - url: http://alert-webhook-logger.monitoring.svc:80/
            send_resolved: true
```

Apply via `helm upgrade kube-prometheus-stack`.

Verify the active config:

```bash
kubectl get secret -n monitoring alertmanager-kps-alertmanager-generated \
  -o jsonpath='{.data.alertmanager\.yaml\.gz}' | base64 -d | gzip -d | head -50
```

---

## Custom rule: `PodinfoAvailabilityLost`

The most interesting part of Phase 21 — a **real custom alert** with a
real chaos-validation moment.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: podinfo-availability
  namespace: podinfo
  labels:
    release: kube-prometheus-stack    # picked up by Prometheus.spec.ruleSelector
spec:
  groups:
    - name: podinfo.availability
      interval: 30s
      rules:
        - alert: PodinfoAvailabilityLost
          # Use kube-state-metrics (deployment status) — NOT podinfo's own
          # http_requests_total ratio. When every replica is broken, NGINX
          # returns 502 before requests reach the backend, so podinfo's
          # metrics stay flat. The deployment metric is the only reliable
          # "no replicas serving" signal.
          expr: |
            kube_deployment_status_replicas_available{namespace="podinfo", deployment="podinfo"} == 0
          for: 2m
          labels:
            severity: critical
            namespace: podinfo
            service: podinfo
          annotations:
            summary: "podinfo has zero available replicas for 2+ min"
            description: |
              Podinfo's deployment shows 0 available replicas for over
              2 minutes. The service is currently unreachable.
            runbook_url: "https://andrelair-platform.github.io/minicloud-platform-docs/docs/observability/alertmanager#podinfoavailabilitylost"
```

### The metric I almost got wrong

The first draft of the rule used `http_requests_total{status=~"2.."}`
ratio. It evaluated to `1.0` (= 100% success) under chaos, because the
**chaos broke the pods so completely that NGINX returned 502 directly,
without forwarding the request to podinfo at all**. Podinfo's metrics
stayed flat. The ratio numerator and denominator both stayed at zero.

`kube_deployment_status_replicas_available` is the right signal — it
comes from kube-state-metrics, which polls the API server, which knows
the deployment has 0 ready replicas regardless of whether any traffic
is reaching the broken pods.

This is the kind of mistake you only catch by **actually running the
chaos test**. Reading the rule and reasoning about it on paper, the
http-ratio approach looks fine.

---

## The validation moment

The user-approved test: kill BOTH podinfo replicas simultaneously
(Phase 20 callback), watch the alert flow through Alertmanager to the
webhook receiver.

```yaml
# chaos-mesh/exp4-killboth.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: podinfo-killboth
  namespace: chaos-mesh
spec:
  action: pod-failure         # keeps pods broken (vs pod-kill which
                              #  lets them restart cleanly)
  mode: all                   # both pods, not just one
  duration: "6m"              # uninterrupted — long enough for
                              # for: 2m to elapse without resets
  selector:
    namespaces: [podinfo]
    labelSelectors:
      "app.kubernetes.io/name": "podinfo"
```

```bash
# Tail the webhook receiver in another shell
kubectl logs -n monitoring -l app=alert-webhook-logger -f

# Apply the chaos
kubectl apply -f chaos-mesh/exp4-killboth.yaml
```

### The flap that proved the rule

The first attempt FAILED — and that failure was the most educational
part of Phase 21.

I'd applied a 4-min PodChaos, then realized it would end before the
2-min for-clause could elapse. So I deleted-and-recreated the chaos to
extend it. **That delete-recreate caused a 30-second window where the
pods came back to Running**. The for-counter restarted from zero, the
alert stayed pending, and the chaos auto-ended before the alert could fire.

This is exactly what the user predicted in the plan refinement:

> When you write the PrometheusRule for `PodinfoAvailabilityLost`,
> ensure you set the **`for: 2m`** parameter. This prevents "flapping"
> alerts from spamming your logs during standard rolling updates,
> ensuring that when the alert fires, it's a real incident.

The for-clause did **exactly its job** — refused to fire because the
bad state wasn't sustained. The rule wasn't broken; my chaos discipline
was. Re-running with a single uninterrupted 6-min chaos gave the alert
the runway it needed.

### The successful run

| Time (UTC) | Event |
|---|---|
| 18:39:24 | Chaos applied — both pods → CrashLoopBackOff within 5 s |
| 18:39:48 | Prometheus rule activates (first 0-reading detected) |
| 18:41:48 | for: 2m elapsed → rule transitions PENDING → FIRING |
| 18:41:48 | Alertmanager receives the firing alert |
| 18:42:18 | Alertmanager `group_wait: 30s` elapses → webhook fires |
| **18:42:18** | **Webhook receiver pod logs the JSON payload** |
| 18:43:31 | Chaos deleted, pods recover |
| ~18:44:00 | Prometheus rule transitions FIRING → INACTIVE |

Total chaos→alert latency: **174 seconds** (mostly the 2-min
for-clause + 30-s group_wait, which is exactly the design).

The webhook payload as logged by the receiver:

```text
=== ALERT @ 2026-05-09T18:42:18.372Z ===
  receiver: webhook-critical
  status:   firing
  groupKey: {}/{severity="critical"}:{alertname="PodinfoAvailabilityLost", namespace="podinfo"}
  -   FIRING: PodinfoAvailabilityLost  severity=critical  namespace=podinfo
      summary: podinfo has zero available replicas for 2+ min
```

Things this proves:
- The 3-tier routing tree correctly sent severity=critical to
  `webhook-critical` (not `webhook-default` or `null`)
- groupKey shows `(alertname, namespace)` grouping working
- summary annotation came through
- The `for: 2m` clause prevents flapping (proven by the failed first
  attempt)
- End-to-end alert path: rule eval → fire → group_wait → receiver

---

## Done When

```text
✔ 9 firing alerts triaged: 5 fixed (PVC, NTP × 3, throttling × 3),
  2 silenced (k3s false positives × 4 — Proxy/Controller/Scheduler/Watchdog),
  1 by-design (Watchdog)
✔ Alertmanager routing tree replaces null receiver with 3-tier webhook
✔ alert-webhook-logger pod Running in monitoring namespace
✔ Custom PodinfoAvailabilityLost rule loaded; visible in Prometheus rules API
✔ Chaos validation: kill both podinfo replicas → webhook receives
  FIRING JSON within ~3 min
✔ for: 2m anti-flap proven by the failed-flap first attempt
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Day-2 alert triage** | Surveying 9 firing alerts and methodically fixing each (or proving it's noise) is exactly how a real on-call shift starts. |
| **Online PVC expansion (Longhorn)** | Knowing that `kubectl patch pvc ... resources.requests.storage` works without pod restart on Longhorn (when `allowVolumeExpansion: true` on the StorageClass) is real Day-2 knowledge. |
| **NTP root-cause analysis** | Tracing "synchronized: no" to a DHCP-assigned unreachable IPv6 NTP server, fixing it with explicit servers — fundamental SRE diagnosis. |
| **`for:` clause anti-flapping** | The user's pro-tip held in practice. Rules without a sufficient `for:` window flap during standard deploys; rules WITH a sensible `for:` are the difference between actionable alerts and noise. |
| **Metric selection vs. failure mode** | Discovering that `http_requests_total` ratio doesn't fire when "all replicas broken" because NGINX 502s never reach the backend → switching to kube-state-metrics deployment status. This is real on-call thinking. |
| **Routing tree vs. rule disable** | Silencing k3s false positives at the routing tree (rather than disabling the kube-prometheus-stack rules) is the K8s-native pattern. |
| **End-to-end alert validation via chaos** | Phase 20 → Phase 21 callback. The platform tools talk to each other. |
| **Senior scope reduction** | In-cluster webhook receiver instead of Slack/email/PagerDuty. Easy to swap later, zero external dependencies now. |
