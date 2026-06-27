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

## What cert-manager manages (and what it doesn't)

This is the most common source of confusion when looking at TLS certificates on the platform.

### Three types of TLS material in the cluster

| Type | Count | Visible in Grafana dashboard | Managed by |
|---|---|---|---|
| **Certificate CRs** — cert-manager resources that declaratively request a TLS cert | 17 | Yes | cert-manager |
| **`kubernetes.io/tls` Secrets without a Certificate CR** | 3 | No | k3s / Longhorn (self-managed) |
| **`Opaque` Secrets** (e.g. `argocd-oidc`, `grafana-oidc`) | 40+ | No | ESO / manually created |

The Grafana dashboard (ID 20842) and the PrometheusRule alerts **only cover Certificate CRs**. They do not see TLS Secrets that were created outside cert-manager.

### The 17 cert-manager Certificates

All 17 have a `cert-manager.io/issuer-name` annotation on their Secret and a corresponding `Certificate` CR. They are all signed by the internal `minicloud-ca` ClusterIssuer (except the root CA itself, which uses `selfsigned-bootstrap`).

```bash
kubectl get certificate -A
# Returns exactly 17 — one Certificate CR per row
```

| Certificate | Namespace | Issuer | Expiry batch |
|---|---|---|---|
| argocd-tls | argocd | minicloud-ca | 2026-08-07 |
| backstage-tls | backstage | minicloud-ca | 2026-08-07 |
| chat-tls | ai | minicloud-ca | 2026-08-07 |
| platform-demo-tls | gitops-demo | minicloud-ca | 2026-08-07 |
| whoami-tls | gitops-demo | minicloud-ca | 2026-08-07 |
| harbor-tls-cert | harbor | minicloud-ca | 2026-08-07 |
| homer-tls | homer | minicloud-ca | 2026-08-07 |
| nats-tls | messaging | minicloud-ca | 2026-08-07 |
| grafana-tls | monitoring | minicloud-ca | 2026-08-07 |
| podinfo-tls | podinfo | minicloud-ca | 2026-08-07 |
| authentik-tls | authentik | minicloud-ca | 2026-09-15 |
| ktayl-web-tls | ktayl-web | minicloud-ca | 2026-09-18 |
| alertmanager-tls | monitoring | minicloud-ca | 2026-09-20 |
| prometheus-tls | monitoring | minicloud-ca | 2026-09-20 |
| nextcloud-tls | nextcloud | minicloud-ca | 2026-09-19 |
| vault-tls | vault | minicloud-ca | 2026-09-19 |
| minicloud-root-ca | cert-manager | selfsigned-bootstrap | 2036-05-06 |

### The 3 TLS Secrets NOT managed by cert-manager

These exist as `kubernetes.io/tls` Secrets but have **no Certificate CR** and **no `cert-manager.io/*` annotation**. They will never appear in the Grafana dashboard or trigger the PrometheusRule alerts.

| Secret | Namespace | Managed by | Rotation |
|---|---|---|---|
| `k3s-serving` | `kube-system` | k3s control plane (`listener.cattle.io`) | Rotated automatically by k3s on each node restart or cert expiry. Covers the API server endpoint (`kubernetes.default.svc.cluster.local`, `set-hog`, `10.0.0.2`). |
| `longhorn-webhook-ca` | `longhorn-system` | Longhorn operator | Internal CA for Longhorn's admission webhooks. Longhorn regenerates this on startup if expired. |
| `longhorn-webhook-tls` | `longhorn-system` | Longhorn operator | Webhook TLS cert signed by `longhorn-webhook-ca`. Same lifecycle — Longhorn owns it. |

**Why you don't need to worry about these three:** k3s and Longhorn each handle their own certificate lifecycle internally. They are not exposed via Ingress and are never sent to a browser. If either rotates a cert, the component that needs it (kubelet, admission controller) picks it up automatically with no human action.

### How to tell if a TLS Secret is cert-manager-managed

```bash
# cert-manager-managed: has this annotation
kubectl get secret <name> -n <ns> -o jsonpath='{.metadata.annotations.cert-manager\.io/issuer-name}'
# → "minicloud-ca"  (or any non-empty value)

# NOT cert-manager-managed: annotation is empty or absent
kubectl get secret k3s-serving -n kube-system -o jsonpath='{.metadata.annotations.cert-manager\.io/issuer-name}'
# → ""
```

Alternatively, check for a Certificate CR with a matching `spec.secretName`:

```bash
kubectl get certificate -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.spec.secretName}{"\n"}{end}' | sort
```

If your TLS Secret name does not appear in that list, cert-manager does not control it.

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
