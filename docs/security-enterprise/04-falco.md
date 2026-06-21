---
id: falco
title: Phase 28 — Falco (Runtime Threat Detection)
sidebar_position: 4
---

# Phase 28 — Falco — Runtime Threat Detection

Gatekeeper (Phase 27) blocks bad workloads at admission time. Falco is the complementary layer: it watches what containers **do at runtime**, using eBPF to intercept every kernel syscall. A container that was clean when deployed can still be detected when it reads `/etc/shadow`, spawns an unexpected shell, or calls out to an unexpected endpoint.

---

## How It Works

```text
container process
     │
     │ syscall (open, connect, execve...)
     ▼
  Linux kernel
     │
     │ eBPF probe (modern_ebpf driver, BPF CO-RE)
     ▼
  Falco daemon
     │
     ▼
  Rule evaluation (Rego-like Falco rule language)
     │
  ┌──┴──────────────┐
  ▼                 ▼
PASS           ALERT → JSON log entry with full context
               (hostname, container, user, process, file/network)
```

**modern_ebpf driver** — uses BPF CO-RE (Compile Once, Run Everywhere). No kernel module compilation, no kernel headers needed on nodes. Requires kernel ≥ 5.8. Nodes run 6.8.0 — fully supported.

**DaemonSet model** — one Falco pod per node. Each pod monitors all containers on that node at the syscall level. No sidecar injection needed (compare to Vault Agent Injector).

---

## Architecture

```text
falco namespace
  ├── falco-<hash>  (DaemonSet, 1 per node — 3 total)
  │     ├── falco-ct-artifact-install (initContainer, downloads rules via falcoctl)
  │     └── falco  (main container, eBPF probe, rule evaluation)
  └── (falcosidekick — disabled, using stdout log output)
```

---

## Install

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update falcosecurity

~/.local/bin/helm install falco falcosecurity/falco \
  --namespace falco \
  --create-namespace \
  --version 9.1.0 \
  --values ~/minicloud-ktaylorganisation/ansible/helm-values/falco-values.yaml \
  --timeout 5m
```

`falco-values.yaml`:

```yaml
driver:
  kind: modern_ebpf

falco:
  json_output: true
  json_include_output_property: true
  log_stderr: true
  log_syslog: false
  log_level: info
  priority: debug
  watch_config_files: false   # avoids inotify exhaustion on control-plane node

falcoctl:
  artifact:
    install:
      env:
        - name: HTTPS_PROXY
          value: http://10.0.0.1:8000
        - name: HTTP_PROXY
          value: http://10.0.0.1:8000
        - name: NO_PROXY
          value: 10.0.0.0/8,127.0.0.1,localhost,.svc,.cluster.local
    follow:
      enabled: false          # disables live rule-update sidecar

falcosidekick:
  enabled: false

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

---

## Gatekeeper Exemption Required

Falco runs as `privileged: true` (needs kernel-level eBPF access). Without exempting the `falco` namespace from the `no-privileged-containers` Gatekeeper constraint, the DaemonSet will fail to schedule:

```
Error: admission webhook "validation.gatekeeper.sh" denied the request:
[no-privileged-containers] Container 'falco' must not run as privileged
```

Fix — add `falco` to the constraint's excluded namespaces (`minicloud-gitops/manifests/gatekeeper-policies/11-constraint-no-privileged.yaml`):

```yaml
namespaceSelector:
  matchExpressions:
    - key: kubernetes.io/metadata.name
      operator: NotIn
      values:
        - ...existing namespaces...
        - falco       # Falco needs privileged for eBPF kernel access
```

---

## Install Gotchas

**1. Squid proxy for falcoctl**

The `falcoctl-artifact-install` init container downloads the Falco rule index from `https://falcosecurity.github.io`. Cluster nodes reach the internet via the MAAS Squid proxy at `10.0.0.1:8000`. Without proxy env vars, the init container crashes with:

```
ERROR: unable to fetch index "falcosecurity" with URL
  "https://falcosecurity.github.io/falcoctl/index.yaml": dial tcp: i/o timeout
```

Fix: inject `HTTPS_PROXY` into the `falcoctl.artifact.install.env` and `falcoctl.artifact.follow.env` sections (see values above).

**2. inotify exhaustion on the control-plane node**

Falco uses `inotify` to watch rule files for hot-reload. The control-plane node (`set-hog`) runs many k3s system processes that already consume most of the 128 `inotify` instances available per user. Falco fails with:

```
Error: could not initialize inotify handler
```

Fix: `watch_config_files: false` disables the file watcher. Rules load at pod start from `/etc/falco/falco_rules.yaml` and don't hot-reload. For a homelab this is fine — restart the DaemonSet to pick up rule changes.

Also disable the `falcoctl follow` sidecar (`follow.enabled: false`) which runs a separate inotify watcher for the same reason.

**3. Deprecated `collectors.containerd` key**

Chart 9.x removed `collectors.containerd`. Use `collectors.containerEngine` instead, or omit the section entirely — auto-detection finds containerd at `/run/k3s/containerd/containerd.sock`.

---

## Live Detections Verified

### Detection 1 — `Contact K8S API Server From Container` (Notice)

Triggered automatically by the Vault pod connecting to the Kubernetes API for Kubernetes auth validation. No manual trigger needed — fires continuously every 5 seconds.

```json
{
  "rule": "Contact K8S API Server From Container",
  "priority": "Notice",
  "output": "Unexpected connection to K8s API Server from container | connection=10.42.1.190:56084->10.43.0.1:443 ... container_name=vault k8s_pod_name=vault-0",
  "tags": ["T1565", "container", "k8s", "maturity_stable", "mitre_discovery"]
}
```

This is the Vault Kubernetes auth backend polling the k8s API to validate ServiceAccount tokens. Falco correctly identifies it as `mitre_discovery` — a MITRE ATT&CK tag meaning "network discovery inside cluster."

### Detection 2 — `Read sensitive file untrusted` (Warning)

Triggered by running `cat /etc/shadow` inside a container running as root:

```bash
kubectl exec -n default falco-test2 -- bash -c 'cat /etc/shadow'
```

```json
{
  "rule": "Read sensitive file untrusted",
  "priority": "Warning",
  "output": "Sensitive file opened for reading by non-trusted program | file=/etc/shadow ... user=root user_uid=0 ... container_name=falco-test2"
}
```

---

## Verification (regression)

```bash
# 3/3 DaemonSet pods running (one per node)
kubectl get pods -n falco -o wide
# falco-xxx   1/1  Running  fast-heron
# falco-yyy   1/1  Running  fast-skunk
# falco-zzz   1/1  Running  set-hog

# Live alert stream (Ctrl-C to stop)
kubectl logs -n falco -l app.kubernetes.io/name=falco -f --since=1m | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        print(f'[{d[\"priority\"]}] {d[\"rule\"]}')
        print(' ', d['output'][:120])
    except: pass
"

# Trigger a test alert (read sensitive file as root)
kubectl run falco-demo --image=nginx:1.27 -n default --restart=Never --command -- sleep 60
kubectl exec -n default falco-demo -- cat /etc/shadow
kubectl delete pod falco-demo -n default
```

---

## Done When

```text
✔ falco DaemonSet 3/3 Running (set-hog, fast-skunk, fast-heron)
✔ modern_ebpf driver active (no kernel module / no kernel headers)
✔ Gatekeeper no-privileged constraint exempts falco namespace
✔ Detection 1: Contact K8S API Server From Container — firing continuously (Vault pod)
✔ Detection 2: Read sensitive file untrusted — verified with cat /etc/shadow in container
✔ Values committed to minicloud-ansible (falco-values.yaml)
```
