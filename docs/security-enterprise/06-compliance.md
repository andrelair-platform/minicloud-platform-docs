---
id: compliance
title: Compliance (kube-bench + Audit)
sidebar_position: 6
---

:::caution Not deployed on this cluster
kube-bench has **not been run** as a standing deployment. The commands below are valid but have not been executed against this cluster. Run them manually to generate a CIS benchmark report.
:::


# Compliance — CIS Benchmarks, Audit Logs & Hardening

Compliance is the proof layer: evidence that the cluster meets industry standards. This page covers CIS Kubernetes benchmark scanning with kube-bench, Kubernetes API audit logging, and a hardening checklist for k3s.

---

## CIS Kubernetes Benchmark with kube-bench

kube-bench runs the official CIS (Center for Internet Security) Kubernetes benchmark against your cluster and scores each control as PASS / FAIL / WARN.

### Run kube-bench as a Job

```yaml
# kube-bench-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: kube-bench
  namespace: kube-system
spec:
  template:
    spec:
      hostPID: true
      nodeSelector:
        node-role.kubernetes.io/control-plane: "true"
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
      restartPolicy: Never
      containers:
        - name: kube-bench
          image: aquasec/kube-bench:latest
          command: ["kube-bench"]
          args:
            - "--benchmark"
            - "k3s-cis-1.7"        # use k3s-specific benchmark
            - "--json"
          volumeMounts:
            - name: var-lib-etcd
              mountPath: /var/lib/etcd
              readOnly: true
            - name: etc-kubernetes
              mountPath: /etc/kubernetes
              readOnly: true
      volumes:
        - name: var-lib-etcd
          hostPath:
            path: /var/lib/rancher/k3s/server/db
        - name: etc-kubernetes
          hostPath:
            path: /etc/rancher/k3s
```

```bash
kubectl apply -f kube-bench-job.yaml

# Wait for completion
kubectl wait -n kube-system job/kube-bench --for=condition=complete --timeout=120s

# Get the full report
kubectl logs -n kube-system job/kube-bench | jq .

# Get summary (pass/fail/warn counts)
kubectl logs -n kube-system job/kube-bench | jq '.Totals'
```

---

## Understanding the Score

```text
== Summary ==
34 checks PASS
10 checks FAIL
 8 checks WARN

Target score: PASS ≥ 80%, FAIL = 0 critical controls
```

### Critical Controls to Fix First

| Check | Description | Remediation |
|---|---|---|
| 1.2.1 | Anonymous auth disabled | `--anonymous-auth=false` in API server args |
| 1.2.6 | Audit logging enabled | See audit log section below |
| 3.2.1 | Logging at request/response level | Audit policy configured |
| 4.2.6 | Pod security policies | OPA Gatekeeper (Phase 15) |
| 5.1.1 | RBAC enabled | Already enabled in k3s |
| 5.2.2 | No privileged pods | OPA policy enforced |
| 5.7.4 | No default SA token automount | Set `automountServiceAccountToken: false` |

---

## k3s Hardening Configuration

Apply to `/etc/rancher/k3s/config.yaml` on the control plane:

```yaml
# /etc/rancher/k3s/config.yaml (on set-hog)
# API Server hardening
kube-apiserver-arg:
  - "anonymous-auth=false"
  - "audit-log-path=/var/log/kubernetes/audit.log"
  - "audit-policy-file=/etc/rancher/k3s/audit-policy.yaml"
  - "audit-log-maxage=30"
  - "audit-log-maxbackup=10"
  - "audit-log-maxsize=100"
  - "request-timeout=300s"
  - "service-account-lookup=true"
  - "tls-min-version=VersionTLS12"
  - "tls-cipher-suites=TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"

# Controller Manager hardening
kube-controller-manager-arg:
  - "terminated-pod-gc-threshold=10"
  - "use-service-account-credentials=true"
  - "service-account-private-key-file=/var/lib/rancher/k3s/server/tls/service.key"

# Scheduler hardening
kube-scheduler-arg:
  - "bind-address=127.0.0.1"

# etcd hardening
etcd-arg:
  - "cipher-suites=TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
```

```bash
# Apply and restart k3s
sudo systemctl restart k3s

# Verify on workers too
sudo tee -a /etc/rancher/k3s/config.yaml << 'EOF'
kubelet-arg:
  - "anonymous-auth=false"
  - "authorization-mode=Webhook"
  - "read-only-port=0"
  - "protect-kernel-defaults=true"
  - "event-qps=0"
  - "rotate-certificates=true"
  - "tls-min-version=VersionTLS12"
EOF
sudo systemctl restart k3s-agent
```

---

## API Audit Logging

Full audit policy (in addition to what's set in k3s config):

```yaml
# /etc/rancher/k3s/audit-policy.yaml
apiVersion: audit.k8s.io/v1
kind: Policy
omitStages:
  - RequestReceived

rules:
  # Always log exec/attach/portforward at RequestResponse level
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["pods/exec", "pods/attach", "pods/portforward"]

  # Log secret access at Metadata level
  - level: Metadata
    resources:
      - group: ""
        resources: ["secrets", "configmaps"]
    verbs: ["get", "list", "watch"]

  # Log RBAC changes at RequestResponse
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources:
          - clusterroles
          - clusterrolebindings
          - roles
          - rolebindings

  # Log all deletes
  - level: RequestResponse
    verbs: ["delete", "deletecollection"]

  # Log privileged pod creation
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["pods"]
    verbs: ["create", "update", "patch"]

  # Don't log routine read operations for noise reduction
  - level: None
    verbs: ["get", "list", "watch"]
    resources:
      - group: ""
        resources: ["events", "nodes", "endpoints"]

  # Default: log metadata for everything else
  - level: Metadata
```

---

## Ship Audit Logs to Loki

```yaml
# promtail ConfigMap addition — scrape audit log file from host
- job_name: k8s_audit
  static_configs:
    - targets:
        - localhost
      labels:
        job: k8s_audit
        __path__: /var/log/kubernetes/audit.log
  pipeline_stages:
    - json:
        expressions:
          verb: verb
          user: user.username
          resource: objectRef.resource
          namespace: objectRef.namespace
    - labels:
        verb:
        user:
        resource:
```

Query in Grafana:
```logql
{job="k8s_audit"} | json | verb="delete" | resource="secrets"
```

---

## Disable Default Service Account Token Auto-Mount

Most pods don't need Kubernetes API access — but they get a token by default:

```yaml
# Patch default service account in each namespace
apiVersion: v1
kind: ServiceAccount
metadata:
  name: default
  namespace: myteam-staging
automountServiceAccountToken: false
```

Apply across all namespaces:

```bash
for ns in $(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}'); do
  kubectl patch serviceaccount default \
    -n $ns \
    -p '{"automountServiceAccountToken": false}'
done
```

---

## Scheduled Compliance Scan (CronJob)

Run kube-bench weekly and store results:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: kube-bench-weekly
  namespace: kube-system
spec:
  schedule: "0 2 * * 0"   # Sunday 02:00
  jobTemplate:
    spec:
      template:
        spec:
          hostPID: true
          restartPolicy: OnFailure
          containers:
            - name: kube-bench
              image: aquasec/kube-bench:latest
              command:
                - sh
                - -c
                - |
                  kube-bench --benchmark k3s-cis-1.7 --json \
                    > /reports/kube-bench-$(date +%Y%m%d).json
                  # Push to MinIO (Velero bucket)
                  mc alias set minio $MINIO_URL $MINIO_ACCESS_KEY $MINIO_SECRET_KEY
                  mc cp /reports/kube-bench-$(date +%Y%m%d).json \
                    minio/compliance/kube-bench/
```

---

## Compliance Dashboard Checklist

Track posture over time. Target state:

| Control | Target | Owner |
|---|---|---|
| Anonymous auth disabled | ✅ | Platform |
| Audit logging enabled | ✅ | Platform |
| No privileged pods | ✅ | OPA Gatekeeper |
| All images signed | ✅ | Cosign Policy Controller |
| No root containers | ✅ | OPA Gatekeeper |
| RBAC least privilege | ✅ | Namespace owners |
| Network policies in place | ✅ | Cilium |
| Secrets in Vault (not Secrets) | ✅ | Platform |
| MFA for admins | ✅ | Keycloak |
| kube-bench score ≥ 80% | Target | Platform |
| Falco active on all nodes | ✅ | Security |
| SBOM for all prod images | ✅ | CI/CD pipeline |

---

## Done When

```text
✔ kube-bench runs clean with FAIL < 5 (all critical controls passing)
✔ API audit logs shipping to Loki, queryable in Grafana
✔ k3s hardening config applied on all nodes
✔ Default SA token automount disabled in all namespaces
✔ Weekly kube-bench CronJob stores reports to MinIO
✔ Compliance dashboard shows green across all controls
```
