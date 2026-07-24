---
id: loki-ruler-logql-alerting
title: Gap 3 — Loki Ruler + LogQL Alerting
sidebar_label: Gap 3 — LogQL Alerting
---

# Gap 3 — Loki Ruler + LogQL Alerting

**Status:** Complete (2026-07-24, gitops PRs #233–#243)

The observability stack previously had no log-based alerting. Prometheus alerts on metrics; Loki stored logs — but nothing bridged log patterns to Alertmanager. This gap meant a crashing service only triggered an alert if it crashed often enough to register in kube-state-metrics (OOMKill counter or replica mismatch). A FATAL log line, SMTP delivery failure, or Authentik brute-force pattern would go unnoticed.

Gap 3 enables the Loki ruler and defines 6 LogQL alerting rules, wiring them through Alertmanager → Stalwart SMTP.

---

## Architecture

```
OTel Collector DaemonSet
        │ OTLP
        ▼
    Loki 3.6.7 (SingleBinary)
        │ ruler evaluates LogQL every 1-2m
        ▼
  Alertmanager (kps-alertmanager.monitoring.svc:9093)
        │ SMTP route
        ▼
Stalwart (stalwart.mail.svc:587) → kanmegnea@devandre.sbs
```

The ruler runs inside the same Loki pod, reading from local TSDB. Rules are stored as a YAML file on the Loki PVC (via ConfigMap + subPath mount), not in object storage.

---

## Ruler Storage Layout

Loki's local ruler storage uses a three-level directory structure:

```
<ruler.storage.local.directory>/<tenant_id>/<namespace>
```

Where:
- `ruler.storage.local.directory` = `/var/loki/rules` (set by `common.storage.filesystem.rules_directory`)
- `tenant_id` = `fake` (when `auth_enabled: false`, all data is under the `fake` tenant)
- `namespace` = the YAML **file** name (not a subdirectory)

The ruler API maps directly to this structure:

```
GET /loki/api/v1/rules/{namespace}   → returns /var/loki/rules/fake/{namespace}
```

**Critical:** `{namespace}` must be a plain YAML file, not a directory.

---

## ConfigMap subPath Mount

A plain ConfigMap volume mount always creates a directory. The ruler expects a file. Solution: `subPath` mounts a single ConfigMap key as a file at the target path.

```yaml
# loki-values.yaml — inside singleBinary:
extraVolumes:
  - name: loki-rules
    configMap:
      name: loki-rules
extraVolumeMounts:
  - name: loki-rules
    mountPath: /var/loki/rules/fake/minicloud-alerts
    subPath: app-alerts.yaml
    readOnly: true
```

The ConfigMap key `app-alerts.yaml` is mounted as the FILE `/var/loki/rules/fake/minicloud-alerts` — satisfying the ruler's `<dir>/<tenant>/<namespace-file>` requirement.

### subPath trade-off

`subPath` mounts **do not live-reload** when the ConfigMap changes. The Loki pod must restart to pick up new rules. The Loki StatefulSet carries `reloader.stakater.com/auto: "true"` so Stakater Reloader restarts it automatically on ConfigMap update.

---

## Chart Template Override Problem

Loki chart v7.0.0 generates a `ruler:` stanza in its Helm template unconditionally. Any `loki.ruler.*` values set in `values.yaml` are overwritten at render time by the chart's own template.

**Workaround:** pass the Alertmanager URL as a CLI flag via `singleBinary.extraArgs`:

```yaml
singleBinary:
  extraArgs:
    - -ruler.alertmanager-url=http://kps-alertmanager.monitoring.svc:9093
```

CLI flags take precedence over the generated config file. The ruler picks up the Alertmanager URL from the flag regardless of what the chart template wrote.

To confirm which Alertmanager service name to use (kube-prometheus-stack releases vary by Helm release name):

```bash
kubectl get svc -n monitoring | grep alertmanager
```

This cluster uses release name `kps` → service is `kps-alertmanager`.

---

## ArgoCD App — 3-Source Pattern

The `loki` ArgoCD Application uses three sources: Helm chart, values reference repo, and manifests directory:

```yaml
sources:
  - repoURL: https://grafana.github.io/helm-charts
    chart: loki
    targetRevision: "7.0.0"
    helm:
      releaseName: loki
      valueFiles:
        - $values/helm-values/loki-values.yaml
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    ref: values          # provides $values alias for the first source
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    path: manifests/loki  # deploys the loki-rules ConfigMap
```

`manifests/loki/00-loki-rules.yaml` contains the ConfigMap. ArgoCD deploys it into the `observability` namespace alongside the Loki StatefulSet.

---

## Alert Groups

Six alert groups are defined in `minicloud-gitops/manifests/loki/00-loki-rules.yaml`.

### 1. AppFatalError (critical)

```logql
sum by (namespace, pod, app) (
  count_over_time(
    {namespace=~".+", namespace!~"kube-system|longhorn-system|observability|monitoring|velero|system-upgrade|reloader|vpa-system"}
      |~ `(?i)(FATAL|panic:|runtime error:)`
    [5m]
  )
) > 0
```

Fires immediately (`for: 0m`) on any FATAL, panic, or runtime error in application logs. Infra namespaces are excluded to avoid false positives from services that emit `FATAL` as part of a startup banner.

### 2. StalwartSmtpDeliveryFailure (warning)

```logql
sum(
  count_over_time(
    {namespace="mail"}
      |~ `(?i)(status=5[0-9]{2}|bounce|delivery failed|message rejected|permanent failure)`
    [10m]
  )
) > 3
```

Triggers when >3 SMTP delivery failures occur in 10 minutes. The burst threshold avoids noise from individual invalid recipient addresses. `for: 5m` adds hysteresis.

### 3. AuthentikAuthFailureBurst (warning)

```logql
sum(
  count_over_time(
    {namespace="authentik"}
      |~ `(?i)(Failed to authenticate|authentication.*failed|Login.*Failed|invalid.*credent|Login event.*outcome.*failed)`
    [5m]
  )
) > 10
```

More than 10 authentication failures in 5 minutes exceeds the expected rate for normal user errors. Sustained for 2 minutes before firing.

### 4. ContainerCrashIndicator (critical)

```logql
sum by (namespace, pod, app) (
  count_over_time(
    {namespace=~".+", namespace!~"kube-system|longhorn-system|observability|monitoring"}
      |~ `(?i)(panic:|FATAL|runtime error:|OOM killed|Killed by kernel|exit code 137|signal: killed|segmentation fault)`
    [10m]
  )
) > 5
```

Kubelet's "Back-off restarting failed container" message goes to the systemd journal, not container stdout — the OTel filelogreceiver doesn't capture it. This alert uses crash signals that DO appear in container logs: panics, OOM kill messages, and fatal exits. More than 5 occurrences in 10 minutes sustained for 5 minutes indicates CrashLoopBackOff.

### 5. AIServiceHTTPErrors (warning)

```logql
sum by (app) (
  count_over_time(
    {namespace="ai"}
      |~ `(?i)(status[_=\s:]+5[0-9]{2}|internal server error|bad gateway|service unavailable|litellm\.exceptions)`
    [5m]
  )
) > 5
```

Open WebUI (FastAPI + prometheus-fastapi-instrumentator) and LiteLLM both log HTTP status codes. More than 5 server errors in 5 minutes indicates a degraded AI service.

### 6. ERPNextJobFailure (warning)

```logql
sum(
  count_over_time(
    {namespace="erp"}
      |~ `(?i)(Job Failed|Traceback \(most recent|frappe\.exceptions\.|background.*fail|worker.*error)`
    [10m]
  )
) > 0
```

Frappe background jobs write failure tracebacks to worker pod logs. Any job failure is actionable because the ERPNext → Backstage onboarding webhook depends on background jobs completing.

---

## Verification

```bash
# Port-forward to Loki
kubectl --context minicloud port-forward -n observability svc/loki 3100:3100 &

# List rule namespaces (returns YAML, not JSON)
curl -s http://localhost:3100/loki/api/v1/rules

# Inspect the minicloud-alerts rule group
curl -s http://localhost:3100/loki/api/v1/rules/minicloud-alerts

# Check ruler is connected to Alertmanager (look for "alertmanager" in logs)
kubectl --context minicloud logs -n observability loki-0 | grep -i "alertmanager\|ruler" | tail -20

# Confirm the file is correctly mounted
kubectl --context minicloud exec -n observability loki-0 -- ls -la /var/loki/rules/fake/
kubectl --context minicloud exec -n observability loki-0 -- cat /var/loki/rules/fake/minicloud-alerts

kill %1
```

Expected: `GET /loki/api/v1/rules/minicloud-alerts` returns HTTP 200 with YAML containing all 6 groups.

---

## Gotchas

### 1. Ruler API path is `/loki/api/v1/rules`, not `/ruler/api/v1/rules`

The correct path prefix is `/loki/`, matching the main Loki API. `/ruler/` returns 404.

### 2. `{namespace}` in the ruler path must be a YAML file, not a directory

A plain `ConfigMap` volume mount always creates a directory. The Loki ruler calls `os.ReadFile()` on `<dir>/<tenant>/<namespace>` — it must be a regular file. Use `subPath` to mount a single ConfigMap key as a file.

```yaml
# Wrong — creates a directory:
mountPath: /var/loki/rules/fake/minicloud
# (no subPath)

# Correct — mounts as a file:
mountPath: /var/loki/rules/fake/minicloud-alerts
subPath: app-alerts.yaml
```

### 3. Stale directories block subPath mounts

When a ConfigMap directory mount is replaced by a subPath file mount at the same path, Kubernetes may find an existing directory on the PVC left over from the previous pod lifecycle. runc rejects mounting a file over an existing directory:

```
error mounting ... to rootfs at "/var/loki/rules/fake/minicloud": not a directory
```

**Fix:** use a different namespace name (e.g., `minicloud-alerts` instead of `minicloud`). The Loki ruler skips directories when listing the tenant directory (`fi.IsDir() → continue`), so stale directories are silently ignored.

Alternatively, add an initContainer to remove the stale directory — but note that initContainers inherit the pod's `runAsUser: 10001` and cannot remove root-owned directories created by an earlier mount. The namespace rename approach is simpler.

### 4. Loki chart v7.0.0 overwrites `loki.ruler.*` values

The chart template generates a `ruler:` config block that overrides anything in `values.yaml`. Pass the Alertmanager URL via a CLI flag instead:

```yaml
singleBinary:
  extraArgs:
    - -ruler.alertmanager-url=http://kps-alertmanager.monitoring.svc:9093
```

### 5. LogQL requires at least one non-empty-compatible positive matcher

A stream selector with only negative or regex-exclude matchers is rejected:

```logql
# Invalid — no positive matcher:
{namespace!~"kube-system|monitoring"}

# Valid — positive matcher required:
{namespace=~".+", namespace!~"kube-system|monitoring"}
```

Error: `queries require at least one regexp or equality matcher that does not have an empty-compatible value`.

### 6. Loki ruler API returns YAML, not JSON

`GET /loki/api/v1/rules` returns `Content-Type: application/yaml`. Using `json.load()` on the response body fails with `JSONDecodeError`. Use `yaml.safe_load()` or check the HTTP status code (200 = rules loaded successfully).

---

## Files

| File | Purpose |
|------|---------|
| `minicloud-gitops/helm-values/loki-values.yaml` | extraArgs, extraVolumes, extraVolumeMounts for ruler |
| `minicloud-gitops/manifests/loki/00-loki-rules.yaml` | ConfigMap with 6 alert groups |
| `minicloud-gitops/apps/loki.yaml` | 3-source ArgoCD Application |
