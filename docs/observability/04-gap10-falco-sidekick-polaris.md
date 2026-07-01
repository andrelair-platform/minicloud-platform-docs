---
id: falco-sidekick-polaris
title: Observability Gap 10 — Falco Sidekick + Polaris
sidebar_position: 4
---

# Observability Gap 10 — Falco Sidekick + Polaris

Two gaps identified in the observability checklist audit:

- **Gap 10a** — Falco detected runtime threats (failed logins, cluster-admin bindings, privileged pods) but events stayed in pod stdout; no path to Alertmanager.
- **Gap 10b** — No static workload quality scorer; Gatekeeper blocks violations but provides no scored dashboard for third-party charts.

Both closed 2026-07-01.

---

## Gap 10a — Falco Sidekick → Alertmanager

### What Was Missing

Falco 0.44.1 was deployed and firing rules (logs confirmed `K8s ClusterRoleBinding Created`, `Launch Privileged Container`, `Read sensitive file untrusted`), but there was no routing path from Falco events to Alertmanager. Events were only visible via `kubectl logs -n falco`.

### Solution

Falcosidekick is included in the Falco Helm chart (`falcosecurity/falco`). Enabling it adds a 2-replica Deployment that receives Falco events via HTTP and fans them out to configured outputs.

**`minicloud-ansible/helm-values/falco-values.yaml`** change:

```yaml
falcosidekick:
  enabled: true
  config:
    alertmanager:
      hostport: "http://kps-alertmanager.monitoring.svc.cluster.local:9093"
      minimumpriority: "warning"
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 128Mi
```

**Helm upgrade (on controller):**

```bash
scp ~/minicloud-ansible/helm-values/falco-values.yaml controller:/tmp/falco-values.yaml
ssh controller "helm upgrade falco falcosecurity/falco -n falco -f /tmp/falco-values.yaml --timeout 5m --wait"
# REVISION: 5
```

**NetworkPolicy** — monitoring namespace has `default-deny-ingress`, so a new policy was added to allow Falco Sidekick to push alerts to Alertmanager on port 9093:

```yaml
# minicloud-gitops/manifests/network-policies/monitoring.yaml (appended)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-falco-sidekick
  namespace: monitoring
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: falco
      ports:
        - port: 9093
          protocol: TCP
```

### Verification

```bash
# Sidekick pods running with AlertManager output enabled
kubectl logs -n falco -l app.kubernetes.io/name=falcosidekick --tail=5
# 2026/07/01 20:27:22 [INFO]  : Enabled Outputs: [AlertManager]
# 2026/07/01 20:27:22 [INFO]  : Falcosidekick is up and listening on :2801

# Falco alerts present in Alertmanager
kubectl port-forward -n monitoring svc/kps-alertmanager 9093:9093 &
curl -s http://localhost:9093/api/v2/alerts | python3 -c \
  'import sys,json; a=json.load(sys.stdin); print(len(a), "active alerts")'
```

### Alert Coverage Closed

| Alert Requirement | Before | After |
|---|---|---|
| Failed login attempts | Falco logs only | Falco → Sidekick → Alertmanager ✅ |
| New cluster-admin binding | Falco logs only | Falco → Sidekick → Alertmanager ✅ |
| Privileged pod created | Gatekeeper blocks + Falco logs only | Gatekeeper blocks + Falco alert ✅ |
| Unexpected image pulled | K8sAllowedRegistries blocks + logs only | K8sAllowedRegistries blocks + Falco alert ✅ |

---

## Gap 10b — Polaris Workload Quality Scorer

### What Was Missing

Gatekeeper enforces hard policy at admission but provides no scored visibility for third-party charts (Helm-managed workloads that pre-date constraints or are in excluded namespaces). Polaris fills this gap with a dashboard that scores every Deployment across the cluster on security and reliability best practices.

### Solution

Polaris 10.2.0 (Helm chart 6.0.0, `charts.fairwinds.com/stable`) deployed in **dashboard-only mode** — no admission webhook (Gatekeeper handles that) — scoring all workloads continuously.

**`minicloud-gitops/apps/polaris.yaml`** — multi-source ArgoCD App:

```yaml
sources:
  - repoURL: https://charts.fairwinds.com/stable
    chart: polaris
    targetRevision: "6.*"
    helm:
      valueFiles:
        - $values/helm-values/polaris-values.yaml
  - repoURL: https://github.com/andrelair-platform/minicloud-ansible.git
    targetRevision: main
    ref: values
```

**`minicloud-ansible/helm-values/polaris-values.yaml`:**

```yaml
dashboard:
  enable: true
  port: 8080
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 200m
      memory: 256Mi
  containerSecurityContext:
    allowPrivilegeEscalation: false
    runAsNonRoot: true
    runAsUser: 10324
    capabilities:
      drop: ["ALL"]

webhook:
  enable: false   # Gatekeeper handles admission control
```

:::info Polaris resources must be under `dashboard.resources`
The top-level `resources:` key is NOT applied to the dashboard container. Gatekeeper `require-resource-limits` blocks the deployment without `dashboard.resources.limits` explicitly set.
:::

**AppProject updates** (`minicloud-gitops/manifests/argocd-project/00-project.yaml`):
- `sourceRepos`: added `https://charts.fairwinds.com/stable`
- `destinations`: added `polaris` namespace

**K8sAllowedRegistries exclusion**: Polaris uses `us-docker.pkg.dev/fairwinds-ops/oss/polaris` — added `polaris` to the excluded namespaces list in `13-constraint-allowed-registries.yaml`.

**Dashboard URL:** `https://polaris.10.0.0.200.nip.io` (TLS via `minicloud-ca` ClusterIssuer)

### Startup Behavior Gotcha

:::danger Polaris 10.x starts HTTP server AFTER first audit completes
Polaris loads all cluster resources and runs a full audit before the HTTP server starts listening on port 8080. With 23+ namespaces and hundreds of resources, this takes ~22 seconds. During this window, the NGINX Ingress backend returns 504. This is expected and resolves automatically after the first audit.

Do not restart the pod during this window — the liveness probe is tolerant enough to wait.

Check if the server is ready:
```bash
kubectl logs -n polaris -l app.kubernetes.io/name=polaris | grep "Starting Polaris dashboard"
```
:::

### Verification

```bash
# Both ArgoCD apps Synced/Healthy
kubectl get applications -n argocd | grep polaris
# polaris        Synced  Healthy
# polaris-base   Synced  Healthy

# Both dashboard pods running
kubectl get pods -n polaris
# NAME                                 READY   STATUS    RESTARTS
# polaris-dashboard-...                1/1     Running   0

# TLS cert issued by minicloud CA
kubectl get certificate -n polaris
# NAME          READY   SECRET        AGE
# polaris-tls   True    polaris-tls   ...

# Dashboard reachable
/usr/bin/curl -sk --cacert ~/minicloud-ca.crt https://polaris.10.0.0.200.nip.io/ -o /dev/null -w '%{http_code}\n'
# 200
```

---

## Full Observability Checklist — Final State

| Item | Status |
|---|---|
| Prometheus + Grafana | ✅ kube-prometheus-stack in `monitoring` |
| Loki + Promtail | ✅ All 3 nodes in `observability` |
| Alertmanager | ✅ `kps-alertmanager` receiving Prometheus + Falco alerts |
| Falco runtime detection | ✅ 3 DaemonSet pods + Sidekick routing to Alertmanager |
| kube-bench CIS scan | ✅ Phase 29 (on-demand Job) |
| Polaris workload scorer | ✅ Dashboard at `polaris.10.0.0.200.nip.io` |
| Pod crash loops | ✅ `KubePodCrashLooping` PrometheusRule |
| Node disk/memory pressure | ✅ `NodeFilesystemAlmostOutOfSpace` + `NodeMemoryHighUtilization` |
| Cert expiration | ✅ `CertificateExpiringSoon` / `CertificateExpiringCritical` |
| Failed login attempts | ✅ Falco `Failed Kubernetes API Server Authentication` → Sidekick → Alertmanager |
| New cluster-admin binding | ✅ Falco `K8s ClusterRoleBinding Created` → Sidekick → Alertmanager |
| Privileged pod created | ✅ Gatekeeper deny at admission + Falco `Launch Privileged Container` |
| Unexpected image pulled | ✅ `K8sAllowedRegistries` deny at admission + Falco registry rule |

13/13 items covered. ✅

---

## Done When

```text
✔ kubectl get pods -n falco — 2 falcosidekick pods Running
✔ kubectl logs -n falco -l app.kubernetes.io/name=falcosidekick shows "Enabled Outputs: [AlertManager]"
✔ kubectl get applications -n argocd polaris polaris-base — both Synced/Healthy
✔ kubectl get pods -n polaris — 2 dashboard pods 1/1 Running
✔ kubectl get certificate polaris-tls -n polaris — READY True
✔ /usr/bin/curl --cacert ~/minicloud-ca.crt https://polaris.10.0.0.200.nip.io/ → HTTP 200
```
