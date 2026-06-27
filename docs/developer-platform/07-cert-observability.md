---
id: cert-observability
title: Phase 60 — Cert Observability
sidebar_position: 7
---

# Phase 60 — Cert Observability

Implemented 2026-06-27. Adds Prometheus alerting and Grafana visibility for all cert-manager-managed TLS certificates on the platform.

---

## The Problem This Solves

Without cert observability, certificates expire silently. The platform has 17 certificates across 16 namespaces — the 2026-08-07 batch (10 certs) all share the same expiry, meaning a single missed renewal causes a cascade of HTTPS failures across argocd, grafana, harbor, backstage, homer, and more.

Additionally, 3 certificates had no explicit `duration` or `renewBefore` set, relying on cert-manager's implicit defaults with unpredictable renewal windows.

---

## What Was Implemented

### ServiceMonitor

cert-manager's Helm chart ships a `ServiceMonitor` in the `cert-manager` namespace targeting port `tcp-prometheus-servicemonitor` (9402). The existing ServiceMonitor was adopted by ArgoCD via the `cert-observability` Application.

Prometheus scrapes cert-manager every 60s and exposes the key metric:

```
certmanager_certificate_expiration_timestamp_seconds{namespace, name, issuer_name, ...}
```

### PrometheusRule (3 alerts)

| Alert | Condition | Severity | For |
|---|---|---|---|
| `CertificateExpiringSoon` | Expires in < 14 days | warning | 1h |
| `CertificateExpiringCritical` | Expires in < 3 days | critical | 15m |
| `CertificateNotReady` | `Ready != True` for 10m | warning | 10m |

```yaml
# manifests/cert-observability/01-prometheusrule.yaml
(certmanager_certificate_expiration_timestamp_seconds - time()) / 86400 < 14
```

### Grafana Dashboard

Import dashboard ID **20842** from grafana.com:

1. Grafana → **Dashboards** → **New** → **Import**
2. Enter ID `20842`
3. Select datasource: **Prometheus**
4. Click **Import**

Shows per-cert expiry timeline, renewal history, and ready status.

---

## Certificate Duration Standardisation

All platform certificates now have explicit `duration: 2160h` (90 days) and `renewBefore: 720h` (30 days). Three were missing these fields:

| Certificate | Namespace | Fix method |
|---|---|---|
| `ktayl-web-tls` | `ktayl-web` | Added to Certificate manifest in minicloud-gitops |
| `prometheus-tls` | `monitoring` | Ingress annotations + cert delete/recreate |
| `alertmanager-tls` | `monitoring` | Ingress annotations + cert delete/recreate |

### Why ingress-shim certs require a different approach

`prometheus-tls` and `alertmanager-tls` are managed by cert-manager's **ingress-shim** — they're owned by their Ingress object, not standalone Certificate manifests. Duration is controlled by annotations on the Ingress:

```yaml
# Added to kps-prometheus and kps-alertmanager Ingresses:
cert-manager.io/duration: "2160h"
cert-manager.io/renew-before: "720h"
```

cert-manager only reads these annotations at Certificate **creation** time. Updating the annotations on an existing cert has no effect — the Certificate must be deleted and recreated:

```bash
kubectl annotate ingress kps-prometheus -n monitoring \
  cert-manager.io/duration=2160h cert-manager.io/renew-before=720h --overwrite
kubectl annotate ingress kps-alertmanager -n monitoring \
  cert-manager.io/duration=2160h cert-manager.io/renew-before=720h --overwrite

kubectl delete certificate prometheus-tls alertmanager-tls -n monitoring
# cert-manager recreates them immediately from the Ingress annotations
kubectl get certificate -n monitoring   # both Ready=True within seconds
```

---

## ArgoCD Application

```yaml
# apps/cert-observability.yaml
path: manifests/cert-observability
destination.namespace: cert-manager
syncPolicy: automated, prune, selfHeal, ServerSideApply
```

---

## Verification

```bash
# Confirm Prometheus is scraping cert-manager
kubectl exec -n monitoring prometheus-kps-prometheus-0 -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=certmanager_certificate_expiration_timestamp_seconds' \
  | python3 -c "
import json, sys, time
d = json.load(sys.stdin)
results = d.get('data', {}).get('result', [])
now = time.time()
for r in sorted(results, key=lambda x: float(x['value'][1])):
    m = r.get('metric', {})
    ns = m.get('namespace', '?')
    name = m.get('name', '?')
    days = (float(r['value'][1]) - now) / 86400
    print(f'{ns}/{name}: {days:.0f} days')
"

# Confirm PrometheusRule is loaded
kubectl exec -n monitoring prometheus-kps-prometheus-0 -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/rules' 2>/dev/null | \
  python3 -c "
import json,sys
d=json.load(sys.stdin)
for g in d['data']['groups']:
    if 'cert' in g.get('name','').lower():
        print(g['name'], ':', [r.get('name') for r in g['rules']])
"
# cert-manager : ['CertificateExpiringSoon', 'CertificateExpiringCritical', 'CertificateNotReady']

# Check all certs have explicit duration
kubectl get certificates -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: duration={.spec.duration}{"\n"}{end}'
```

---

## Cert Expiry Schedule

| Batch | Expiry | Auto-renew (30d before) | Namespaces |
|---|---|---|---|
| Main batch | 2026-08-07 | ~2026-07-08 | argocd, backstage, ai, gitops-demo ×2, harbor, homer, messaging, monitoring/grafana, podinfo |
| Recent | 2026-09-15–20 | ~2026-08-15 | authentik, ktayl-web, prometheus, alertmanager, nextcloud, vault |
| Root CA | 2036-05-06 | 2034-05-06 | cert-manager |
