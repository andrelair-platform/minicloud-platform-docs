---
id: falco
title: Falco (Runtime Security)
sidebar_position: 4
---

# Falco — Runtime Security & Threat Detection

Falco monitors every system call made by containers at runtime using eBPF. It detects threats that admission control misses: a container that was clean at deploy time but later spawns a shell, reads sensitive files, or makes unexpected network connections.

---

## What Falco Detects

```text
CATEGORY               EXAMPLE RULE
─────────────────────────────────────────────────────────────────────
Shell execution        bash/sh/zsh spawned inside a container
File access            /etc/passwd, /etc/shadow read by container
Privilege escalation   setuid/setgid binary executed
Sensitive mounts       /proc, /sys, host path mounted
Network activity       Unexpected outbound connection
Crypto mining          CPU-hogging process with mining patterns
Container escape       nsenter, chroot into host namespace
Secret access          .kube/config, AWS credentials file read
Kubernetes API abuse   kubectl exec from unexpected user agent
```

---

## Install Falco (eBPF mode)

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update
```

### values-falco.yaml

```yaml
# values-falco.yaml
driver:
  kind: ebpf           # eBPF is safer than kernel module; no kernel reboot needed

falcosidekick:
  enabled: true        # sidekick forwards alerts to Slack, PagerDuty, etc.
  config:
    slack:
      webhookurl: "${SLACK_WEBHOOK}"
      minimumpriority: warning
      channel: "#security-alerts"
    pagerduty:
      routingKey: "${PAGERDUTY_KEY}"
      minimumpriority: critical

customRules:
  platform-rules.yaml: |-
    # Custom rule: alert on any exec inside a running pod
    - rule: Shell Spawned in Container
      desc: A shell was spawned in a container
      condition: >
        spawned_process and
        container and
        not container.image.repository in (allowed_shell_images) and
        proc.name in (shell_binaries)
      output: >
        Shell spawned (user=%user.name user_loginuid=%user.loginuid
        %container.info shell=%proc.name parent=%proc.pname
        cmdline=%proc.cmdline terminal=%proc.tty container_id=%container.id
        image=%container.image.repository)
      priority: WARNING
      tags: [shell, container, mitre_execution]

    # Alert on kubectl exec
    - rule: K8s Exec Into Container
      desc: A user executed kubectl exec to exec into a container
      condition: >
        ka.verb=create and
        ka.target.resource=pods/exec and
        not ka.user.name in (allowed_kube_users)
      output: >
        kubectl exec into container (user=%ka.user.name
        pod=%ka.target.name ns=%ka.target.namespace
        container=%ka.req.pod.containers.image)
      priority: WARNING
      source: k8s_audit

tolerations:
  - effect: NoSchedule
    operator: Exists
  - effect: NoExecute
    operator: Exists

resources:
  requests:
    cpu: "100m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
```

```bash
kubectl create namespace falco

kubectl create secret generic falco-secrets \
  --from-literal=slack-webhook=$SLACK_WEBHOOK \
  --from-literal=pagerduty-key=$PAGERDUTY_KEY \
  --namespace falco

helm upgrade --install falco falcosecurity/falco \
  --namespace falco \
  --values values-falco.yaml
```

---

## Enable Kubernetes Audit Logs (for k8s_audit source)

k3s ships with audit logging disabled. Enable it:

```bash
# On the control plane node (set-hog)
sudo tee /etc/rancher/k3s/audit-policy.yaml << 'EOF'
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["pods/exec", "pods/attach", "pods/portforward"]
  - level: Metadata
    resources:
      - group: ""
        resources: ["secrets", "configmaps"]
  - level: Metadata
    verbs: ["delete"]
    resources:
      - group: "rbac.authorization.k8s.io"
        resources: ["clusterrolebindings", "rolebindings"]
  - level: None
    resources:
      - group: ""
        resources: ["events"]
EOF

# Add to k3s server args
sudo tee -a /etc/rancher/k3s/config.yaml << 'EOF'
kube-apiserver-arg:
  - "audit-log-path=/var/log/kubernetes/audit.log"
  - "audit-policy-file=/etc/rancher/k3s/audit-policy.yaml"
  - "audit-log-maxage=30"
  - "audit-log-maxbackup=10"
  - "audit-log-maxsize=100"
EOF

sudo systemctl restart k3s
```

---

## Falco Rules Tuning

Falco ships with 100+ default rules. Tune noisy ones:

```yaml
# Add to customRules in Helm values
- macro: allowed_shell_images
  condition: >
    container.image.repository in (
      "harbor.local/platform/debug-tools",
      "harbor.local/platform/kubectl"
    )

- macro: allowed_kube_users
  condition: >
    ka.user.name in (
      "system:serviceaccount:argocd:argocd-server",
      "system:serviceaccount:kube-system:k3s"
    )

# Suppress noisy rules
- rule: Write below root
  enabled: false

- rule: Read sensitive file trusted after startup
  enabled: false
```

---

## Falco Sidekick — Alert Routing

Falco Sidekick routes alerts to multiple outputs simultaneously:

```yaml
# Additional sidekick targets
config:
  slack:
    webhookurl: "${SLACK_WEBHOOK}"
    minimumpriority: warning

  webhook:
    address: "https://n8n.yourdomain.com/webhook/falco"     # n8n automation
    minimumpriority: critical

  loki:
    hostport: "http://loki.monitoring.svc:3100"              # log storage
    minimumpriority: notice

  prometheus:
    # Falco exposes /metrics — scrape via Prometheus
    # metrics include: falco_events_total, falco_rules_matches_total
```

---

## Monitoring Falco Alerts

```bash
# Real-time alert stream
kubectl logs -n falco daemonset/falco -f | jq .

# Count alerts by rule (last hour)
kubectl logs -n falco daemonset/falco --since=1h \
  | jq -r '.rule' \
  | sort | uniq -c | sort -rn

# Critical alerts only
kubectl logs -n falco daemonset/falco --since=24h \
  | jq 'select(.priority == "CRITICAL")'
```

### Grafana Dashboard

Falco exposes Prometheus metrics. Import dashboard ID `11914` from Grafana.com for the Falco overview panel.

---

## Automated Response — Kill Suspicious Pod

Use n8n or a custom webhook to auto-kill pods that trigger critical rules:

```python
# n8n HTTP webhook → Python function
import subprocess, json, sys

alert = json.loads(sys.stdin.read())
if alert["priority"] == "CRITICAL" and "Shell Spawned" in alert["rule"]:
    container_id = alert["output_fields"]["container.id"]
    pod_name = alert["output_fields"]["k8s.pod.name"]
    namespace = alert["output_fields"]["k8s.ns.name"]

    # Delete the pod
    subprocess.run([
        "kubectl", "delete", "pod", pod_name,
        "-n", namespace,
        "--grace-period=0", "--force"
    ])

    # Notify security channel
    print(f"AUTO-KILLED pod {pod_name} in {namespace}: {alert['rule']}")
```

---

## Done When

```text
✔ Falco DaemonSet running on all nodes in eBPF mode
✔ Slack alerts firing for WARNING priority events
✔ PagerDuty paged on CRITICAL (shell in container, escape attempt)
✔ Kubernetes audit log enabled — kubectl exec events captured
✔ Custom rules tuned to reduce false positives
✔ Falco metrics scraped by Prometheus, dashboard in Grafana
```
