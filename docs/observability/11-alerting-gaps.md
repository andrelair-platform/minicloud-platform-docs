---
id: alerting-gaps
title: Alerting Gap Analysis & Fixes — 9 Gaps Closed
sidebar_position: 11
---

# Alerting Gap Analysis & Fixes — 9 Gaps Closed

**Principle: alert only on actionable issues.**

An alert that can't be acted on is noise. Noise trains people to ignore
alerts. Ignored alerts miss real incidents.

Every gap below was evaluated against that principle: does the signal
translate into a concrete human action? If yes, it gets a receiver and
a description that says what to do. If no (k3s structural impossibilities,
benign OCC retries), it is either silenced or excluded by label.

---

## Gap inventory

| # | Severity | Gap | Files changed | Status |
|---|----------|-----|---------------|--------|
| 1 | **Critical** | Watchdog → external dead-man's switch | `kube-prometheus-stack-values.yaml` | ✅ |
| 2 | **Critical** | Gmail delivery path via Amazon SES | SES config, Alertmanager global SMTP | ✅ |
| 3 | **High** | No Slack receiver — SMTP outage silences all alerts | `kube-prometheus-stack-values.yaml`, `19-alertmanager-slack-externalsecret.yaml` | ✅ |
| 4 | **High** | Longhorn not scraped by Prometheus at all | `20-longhorn-servicemonitor.yaml`, `21-longhorn-alerts.yaml` | ✅ |
| 5 | **Medium** | CPU/Memory thresholds wrong (kps default 90% vs required 80%/85%) | `22-node-resource-alerts.yaml` | ✅ |
| 6 | **Medium** | KubeAPIDown self-defeating without external check | `kube-prometheus-stack-values.yaml` | ✅ |
| 7 | **Low** | Infrastructure alerts have no runbook or recovery steps | `04-infrastructure-alerts.yaml` | ✅ |
| 8 | **Low** | KubeControllerManagerDown/KubeSchedulerDown wrongly silenced | `kube-prometheus-stack-values.yaml` | ✅ |
| 9 | **Low** | Kine/SQLite write failures completely invisible | `23-kine-alerts.yaml` | ✅ |

---

## Gap 1 — Dead-man's switch (Watchdog → healthchecks.io)

### Problem

The kube-prometheus-stack ships a `Watchdog` alert that fires constantly
(always-on self-test). The original routing silenced it to `null`.
Result: if the entire cluster died — Prometheus, Alertmanager, and all
email — there would be zero external notification. A complete outage
would be indistinguishable from silence.

### Fix

Route `Watchdog` to a dedicated receiver that pings `healthchecks.io`
every 60 seconds. If the pings stop for 8 minutes, healthchecks.io
sends an alert via its own delivery path (Gmail, independent of the
cluster SMTP).

```yaml
# kube-prometheus-stack-values.yaml
route:
  routes:
    - matchers: ['alertname = "Watchdog"']
      receiver: watchdog
      repeat_interval: 1m   # ping every 60s — healthchecks.io notices silence after 8 min

receivers:
  - name: watchdog
    webhook_configs:
      - url: https://hc-ping.com/cc3f232b-2dbf-4852-821d-3eb6ecf0ff29
        send_resolved: false
```

The `send_resolved: false` is critical — if Alertmanager goes down,
healthchecks.io should NOT receive a "resolved" ping and reset its timer.
Silence is the signal.

### Why it's actionable

The only action is "start investigating the cluster." healthchecks.io
delivers that prompt via an out-of-band channel (Gmail) that does not
depend on anything inside the cluster.

---

## Gap 2 — Gmail delivery via Amazon SES

### Problem

The cluster SMTP uses Stalwart Mail Server (`stalwart.mail.svc.cluster.local:587`).
Stalwart runs on a Longhorn PVC. A storage failure that takes down
Stalwart also silences all email alerts.

Critical alerts need a second delivery path: Gmail, which is external
and always reachable.

### Fix

Amazon SES (eu-west-1) is configured as Stalwart's outbound relay for
`@devandre.sbs` addresses. Gmail (`kanmegnea@gmail.com`) is added as a
recipient in the `webhook-critical` receiver alongside the cluster mail
address.

```yaml
receivers:
  - name: webhook-critical
    email_configs:
      - to: kanmegnea@devandre.sbs,kanmegnea@gmail.com
        send_resolved: true
        headers:
          Subject: '[CRITICAL] {{ .GroupLabels.alertname }} — minicloud'
```

SES domain verification, SPF (`include:amazonses.com`), DKIM (AWS-managed
CNAMEs), and DMARC (`p=none`) are all applied to `devandre.sbs`.

---

## Gap 3 — Slack receiver (parallel critical path)

### Problem

If both Stalwart and SES are unreachable simultaneously, all critical
alerts are lost. A third, independent channel removes that single point
of failure.

### Architecture

```
critical alert fires
        │
        ├─ email → kanmegnea@devandre.sbs (Stalwart → SES → Gmail)
        ├─ email → kanmegnea@gmail.com    (SES → Gmail direct)
        └─ Slack → #general              (Slack API — independent of cluster mail)
```

### Implementation

The Slack webhook URL is stored in Vault at `secret/platform/alertmanager`
(key `slack-webhook-url`) and synced into the `monitoring` namespace via
an ExternalSecret — keeping it out of git.

```yaml
# 19-alertmanager-slack-externalsecret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: alertmanager-slack
  namespace: monitoring
spec:
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: alertmanager-slack
  data:
    - secretKey: slack-webhook-url
      remoteRef:
        key: secret/platform/alertmanager
        property: slack-webhook-url
```

The Alertmanager pod mounts it via `alertmanagerSpec.secrets`:

```yaml
alertmanager:
  alertmanagerSpec:
    secrets:
      - alertmanager-slack

receivers:
  - name: webhook-critical
    slack_configs:
      - api_url_file: /etc/alertmanager/secrets/alertmanager-slack/slack-webhook-url
        channel: '#general'
        send_resolved: true
        title: '[{{ .Status | toUpper }}] {{ .CommonLabels.alertname }} — minicloud'
        text: |
          {{ range .Alerts }}
          *Severity:* {{ .Labels.severity }}  |  *Namespace:* {{ .Labels.namespace }}
          *Summary:* {{ .Annotations.summary }}
          *Description:* {{ .Annotations.description }}
          {{ end }}
```

`api_url_file` is the standard pattern for keeping the webhook URL out
of the in-memory YAML config and therefore out of the Alertmanager API.

### Validation

A live `KubePersistentVolumeFillingUp` alert arrived in `#general` within
seconds of the receiver going live — no synthetic test needed, the
cluster provided a real alert.

---

## Gap 4 — Longhorn health alerts

### Problem

Prometheus had zero visibility into Longhorn. No ServiceMonitor existed.
Volume degradation, node storage pressure, and node storage faults would
produce no alert until pods started crashing (too late).

### Root cause of "zero visibility"

Longhorn's manager pod binds its metrics endpoint to the **pod IP**
(`:9500`), not `localhost`. The `longhorn-backend` Service routes to that
pod. A ServiceMonitor must target the Service, not try to scrape a
localhost port.

```bash
# Confirmed: metrics at pod IP only
kubectl exec -n longhorn-system deploy/longhorn-manager \
  -- curl -s http://$(hostname -i):9500/metrics | head -5
```

### Fix

`20-longhorn-servicemonitor.yaml` — targets the `longhorn-backend` Service
in `longhorn-system`, port `manager` (9500):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: longhorn
  namespace: monitoring
spec:
  namespaceSelector:
    matchNames: [longhorn-system]
  selector:
    matchLabels:
      app.kubernetes.io/name: longhorn
      app.kubernetes.io/instance: longhorn
  endpoints:
    - port: manager
      path: /metrics
      interval: 30s
```

`21-longhorn-alerts.yaml` — 5 PrometheusRules:

| Alert | Metric | Threshold | Severity |
|-------|--------|-----------|----------|
| `LonghornVolumeDegraded` | `longhorn_volume_robustness == 2` | 5 min | warning |
| `LonghornVolumeFaulted` | `longhorn_volume_robustness == 3` | 1 min | critical |
| `LonghornNodeNotReady` | `longhorn_node_status{condition="ready"} == 0` | 5 min | critical |
| `LonghornNodeDiskPressure` | storage >85% | 10 min | warning |
| `LonghornNodeDiskCritical` | storage >95% | 5 min | critical |

`longhorn_volume_robustness` encoding: 0=Unknown, 1=Healthy, 2=Degraded, 3=Faulted.

Degraded means replicas are rebuilding but the volume is still accessible.
Faulted means no healthy replicas — the volume is inaccessible and pods
that mount it will block.

:::tip Multipathd / IET context
The `LonghornVolumeFaulted` description references the multipathd incident
(Phase 80): `multipathd` claims Longhorn's iSCSI volumes as `mpatha`,
blocking kubelet mounts. The fix (blacklist in `/etc/multipath.conf`) is
already applied to all 5 nodes. The description explains how to recognise
a recurrence.
:::

---

## Gap 5 — Node CPU / Memory alert thresholds

### Problem

kube-prometheus-stack ships `NodeCPUHighUsage` (fires at >90%,
`severity: info`) and `NodeMemoryHighUtilization` (fires at >90%,
`severity: warning`).

Stated requirements: warn at CPU >80% for 10 min, warn at Memory >85%
for 10 min. At 90%, there is almost no headroom before OOMKill.

Additionally, the kps defaults use `severity: info` for CPU — which is
routed to `null`. Warnings at 90% CPU are never delivered to anyone.

The controller node (`10.0.0.1:9100`, scraped via `additionalScrapeConfigs`)
is also covered by node_exporter metrics, so the same rules fire for it.

### Fix

`22-node-resource-alerts.yaml` — 4 custom rules:

```yaml
- alert: NodeCPUWarning
  expr: >-
    sum without(mode) (
      avg without(cpu) (
        rate(node_cpu_seconds_total{mode!~"idle|iowait"}[2m])
      )
    ) * 100 > 80
  for: 10m
  labels:
    severity: warning   # routes to webhook-critical → email + Slack

- alert: NodeCPUCritical
  expr: same > 95
  for: 5m
  labels:
    severity: critical

- alert: NodeMemoryWarning
  expr: >-
    100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100) > 85
  for: 10m
  labels:
    severity: warning

- alert: NodeMemoryCritical
  expr: same > 95
  for: 5m
  labels:
    severity: critical
```

The kps built-in rules are NOT disabled — they provide a safety net at
90%. The custom rules fire first at 80%/85%, giving earlier warning.

---

## Gap 6 — KubeAPIDown with external-check context

### Problem

The default `KubeAPIDown` alert fires when `absent(up{job="apiserver"})`.
But: if the API server is truly down, Prometheus may also be down
(it runs in the cluster). If Prometheus is down, Alertmanager is down.
If Alertmanager is down, the alert is never sent.

This makes `KubeAPIDown` partially self-defeating. The alert description
must reference the dead-man's switch (Gap 1) as the actual "API is down"
notification, not the alert itself.

Additionally, the default description gives no recovery steps specific
to a k3s single-control-plane setup.

### Fix

Disable the built-in rule via `defaultRules.disabled` and replace with
an enhanced version:

```yaml
# kube-prometheus-stack-values.yaml
defaultRules:
  disabled:
    KubeAPIDown: true

additionalPrometheusRulesMap:
  kubeapidown-enhanced:
    groups:
      - name: kubernetes-system-apiserver
        rules:
          - alert: KubeAPIDown
            expr: absent(up{job="apiserver"})
            for: 15m
            labels:
              severity: critical
            annotations:
              runbook_url: "https://runbooks.prometheus-operator.dev/runbooks/kubernetes/kubeapidown"
              summary: "Kubernetes API server (set-hog) unreachable for 15 min"
              description: |
                The k3s API server on set-hog (10.0.0.2) has been unreachable for 15 minutes.

                NOTE: If Prometheus itself is down, this alert will never send.
                The dead-man's switch (healthchecks.io) is the authoritative
                "cluster is completely offline" signal — check there first.

                Recovery:
                  ssh set-hog "sudo systemctl status k3s && sudo journalctl -u k3s -n 50"
                  # If k3s is stopped: sudo systemctl start k3s
                  # Check disk space: df -h /var/lib/rancher/k3s/
                  # Check NAT (after power failure):
                  #   ssh -t controller "sudo sh -c 'iptables-restore < /etc/iptables/rules.v4'"
```

The 15-minute `for:` (vs default 0 minutes) prevents false alerts during
rolling updates of the k3s server binary.

---

## Gap 7 — Runbooks and recovery steps on infrastructure alerts

### Problem

The `04-infrastructure-alerts.yaml` PrometheusRules (`NodeSchedulingDisabled`,
`NodeFrequentlyNotReady`, `PodStuckPending`, `ContainerOOMKilled`) had
terse descriptions. A 3am alert with "pod is pending" and no next step
does not help.

### Fix

Every alert now carries:
- `runbook_url` — link to the relevant Prometheus community runbook
- `description` — inline, cluster-specific recovery steps

Selected details added:

**NodeFrequentlyNotReady** — includes swift-mac specifics (Apple SMC never
auto-restarts after power failure; manual power button required), the
multipathd/IET fix, and the full iptables NAT restoration sequence for
post-power-failure controller reboots.

**PodStuckPending** — lists the 5 most common causes in priority order:
image pull failure, resource exhaustion, PVC not bound, Longhorn volume
stuck, Gatekeeper policy violation, and NAT loss after power failure.

**ContainerOOMKilled** — includes the VPA workflow (check `kubectl get vpa`,
compare recommendation to current limit, switch to `updateMode: Auto`
after 7 days of data), and lists historically OOMKill-prone workloads
(ArgoCD controller, Authentik server) with their resolved limits.

---

## Gap 8 — Unsilence KubeControllerManagerDown / KubeSchedulerDown

### Problem

Phase 21 silenced three alerts that fire on vanilla k3s because no
separate kube-proxy, kube-controller-manager, or kube-scheduler process
exists (they are embedded in the k3s binary):

```yaml
- matchers:
    - 'alertname =~ "KubeProxyDown|KubeControllerManagerDown|KubeSchedulerDown"'
  receiver: "null"
```

This was correct at Phase 21 — there were no scrape targets for the
controller manager or scheduler, so the alerts were structural
false-positives.

**Gap 5 (k8s-monitoring-gaps)** added a socat DaemonSet proxy on
`set-hog` (PR #157) that exposes these components via dedicated Services
and ServiceMonitors. Both targets are now confirmed `up` in Prometheus.

Keeping them silenced after the socat proxy went live means a real
controller-manager or scheduler failure would produce zero alert.

### Fix

```yaml
# Before (Phase 21)
- matchers:
    - 'alertname =~ "KubeProxyDown|KubeControllerManagerDown|KubeSchedulerDown"'
  receiver: "null"

# After
- matchers:
    - 'alertname = "KubeProxyDown"'
  receiver: "null"
```

`KubeProxyDown` stays silenced. k3s does not have a kube-proxy component
and that alert is structurally impossible — silencing it is permanent,
not a workaround.

`KubeControllerManagerDown` and `KubeSchedulerDown` now route through the
normal severity tree (`severity: critical` → `webhook-critical`).

---

## Gap 9 — Kine/SQLite write failure alert

### Problem

k3s stores all cluster state in SQLite via Kine (a Kubernetes datastore
adapter). A SQLite I/O error, disk-full condition, or database corruption
on `set-hog` would silently corrupt cluster state. No alert existed for this.

### Metric structure

Kine exposes two relevant metrics:

| Metric | Labels | Meaning |
|--------|--------|---------|
| `kine_sql_total` | `name` (operation) | Successful operation counter — no error dimension |
| `kine_sql_time_seconds` | `name`, `error_code` | Timing histogram. `error_code` is absent on success; present with a string on error |

Known benign `error_code` values (must be excluded from alerts):

| `error_code` | Operation | Cause |
|---|---|---|
| `constraint failed` | `InsertLastInsertID` | Optimistic concurrency control — kine's normal CAS retry loop |
| `context canceled` | `CompactRev` | Watch canceled during API server rotation — benign |

Any other `error_code` (disk I/O errors, `SQLITE_FULL`, `SQLITE_CORRUPT`,
etc.) indicates a genuine storage failure.

### Fix

`23-kine-alerts.yaml`:

```yaml
- alert: KineSQLError
  expr: >-
    increase(
      kine_sql_time_seconds_count{
        error_code!="",
        error_code!~"constraint failed|context canceled"
      }[5m]
    ) > 0
  for: 2m
  labels:
    severity: critical
  annotations:
    runbook_url: "https://andrelair-platform.github.io/minicloud-platform-docs/docs/runbooks/kine-sqlite"
    summary: "Kine/SQLite error on {{ $labels.name }}: {{ $labels.error_code }}"
    description: |
      k3s control plane database (kine/SQLite) is reporting an unexpected error.
      Operation: {{ $labels.name }}
      Error: {{ $labels.error_code }}

      Diagnose:
        ssh set-hog "df -h /var/lib/rancher/k3s/"
        ssh set-hog "sudo sqlite3 /var/lib/rancher/k3s/server/db/state.db 'PRAGMA integrity_check;'"
        ssh set-hog "sudo journalctl -u k3s -n 100 --no-pager | grep -i 'error|fail|corrupt'"

      If disk full: free space on set-hog root partition.
      If corrupt: restore from Velero (velero restore create --from-schedule velero-daily-full).
      Dead-man's switch: healthchecks.io will alert if cluster goes fully silent.
```

Verified: `KineSQLError` loads `health=ok`, state `inactive` (no current
unexpected error codes in the cluster — both `constraint failed` and
`context canceled` are excluded).

---

## Final alert routing tree

```
alert fires
    │
    ├─ alertname = "Watchdog"
    │        └─ watchdog receiver (hc-ping.com every 1m)
    │
    ├─ alertname = "KubeProxyDown"
    │        └─ null (k3s has no kube-proxy — structurally impossible)
    │
    ├─ severity = critical
    │        └─ webhook-critical:
    │               ├─ email → kanmegnea@devandre.sbs + kanmegnea@gmail.com
    │               ├─ Slack → #general
    │               └─ webhook-logger (in-cluster log)
    │
    ├─ severity = warning
    │        └─ webhook-default:
    │               └─ webhook-logger only (no external notification)
    │
    └─ severity = info
             └─ null
```

Inhibit rules: critical suppresses warning+info for the same
`(alertname, namespace)`. This prevents alert storms when a single
root cause fires across multiple severity tiers.

---

## Files changed

| File | What changed |
|------|--------------|
| `helm-values/kube-prometheus-stack-values.yaml` | Watchdog receiver, Slack mount, KubeAPIDown override, null route narrowed, defaultRules.disabled |
| `manifests/monitoring/04-infrastructure-alerts.yaml` | runbook_url + recovery steps on all 4 rules |
| `manifests/monitoring/19-alertmanager-slack-externalsecret.yaml` | New — ESO sync from Vault → k8s Secret |
| `manifests/monitoring/20-longhorn-servicemonitor.yaml` | New — first Prometheus scrape of Longhorn |
| `manifests/monitoring/21-longhorn-alerts.yaml` | New — 5 Longhorn health rules |
| `manifests/monitoring/22-node-resource-alerts.yaml` | New — 4 node CPU/Memory rules at correct thresholds |
| `manifests/monitoring/23-kine-alerts.yaml` | New — KineSQLError rule for unexpected SQLite errors |

---

## Verification commands

```bash
# All custom PrometheusRules loaded and healthy
kubectl -n monitoring get prometheusrule \
  infrastructure-alerts longhorn-alerts node-resource-alerts kine-alerts

# Longhorn targets up in Prometheus
kubectl port-forward svc/kps-prometheus -n monitoring 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import json, sys
t = json.load(sys.stdin)['data']['activeTargets']
longhorn = [x for x in t if 'longhorn' in x['labels'].get('job','')]
for x in longhorn:
    print(x['labels']['job'], x['health'])
"

# KineSQLError rule state (should be inactive — no unexpected errors)
curl -s 'http://localhost:9090/api/v1/rules' | python3 -c "
import json, sys
for g in json.load(sys.stdin)['data']['groups']:
    for r in g['rules']:
        if 'kine' in r.get('name','').lower():
            print(r['name'], r['state'], r['health'])
"

# Live Alertmanager config — verify null route
kubectl -n monitoring exec statefulset/alertmanager-kps-alertmanager \
  -- cat /etc/alertmanager/config_out/alertmanager.env.yaml \
  | grep -A2 'KubeProxy\|KubeControl\|KubeSchedul'
```
