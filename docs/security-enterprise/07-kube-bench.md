---
id: kube-bench
title: Phase 29 — kube-bench (CIS Benchmark)
sidebar_position: 7
---

# Phase 29 — kube-bench — CIS Kubernetes Benchmark

kube-bench scores the cluster against the CIS Kubernetes Benchmark. It checks API server flags, kubelet config, etcd security, RBAC posture, and pod security policies — producing a PASS/FAIL/WARN report with remediation steps for every finding.

---

## How It Works

kube-bench reads running process flags and config files on each node and compares them against the CIS Benchmark specification. It runs as a one-shot command (not a DaemonSet) — typically invoked on-demand or as a scheduled Job.

```text
set-hog (control plane)              fast-skunk / fast-heron (workers)
   kube-bench                             kube-bench
   --targets master,node,etcd,policies    --targets node,policies
         │                                      │
         ▼                                      ▼
   Read: /proc/<pid>/cmdline             Read: /proc/<pid>/cmdline
         /etc/rancher/k3s/              /etc/rancher/k3s/
         /var/lib/rancher/k3s/          /var/lib/rancher/k3s/
         │                                      │
         ▼                                      ▼
   Compare against                       Compare against
   k3s-cis-1.8 benchmark                k3s-cis-1.8 benchmark
```

---

## Run kube-bench on k3s

kube-bench must run on the nodes themselves (not the controller) with root privileges. Run it by downloading the binary to the controller, SCPing to nodes, and executing over SSH:

```bash
# On controller
curl -sL https://github.com/aquasecurity/kube-bench/releases/download/v0.9.4/kube-bench_0.9.4_linux_amd64.tar.gz \
  -o /tmp/kube-bench.tar.gz
tar -xzf /tmp/kube-bench.tar.gz -C /tmp/

# Copy binary + config to nodes
scp /tmp/kube-bench ubuntu@10.0.0.2:/tmp/kube-bench
scp -r /tmp/cfg ubuntu@10.0.0.2:/tmp/cfg
scp /tmp/kube-bench ubuntu@10.0.0.4:/tmp/kube-bench
scp -r /tmp/cfg ubuntu@10.0.0.4:/tmp/cfg

# Run on control-plane (all targets)
ssh ubuntu@10.0.0.2 'sudo /tmp/kube-bench run \
  --config-dir /tmp/cfg \
  --benchmark k3s-cis-1.8 \
  --targets master,node,etcd,policies'

# Run on worker (node + policies)
ssh ubuntu@10.0.0.4 'sudo /tmp/kube-bench run \
  --config-dir /tmp/cfg \
  --benchmark k3s-cis-1.8 \
  --targets node,policies'
```

**Why not as a Kubernetes Job?** kube-bench is published to `ghcr.io/aquasecurity/kube-bench`, not to Docker Hub — Harbor's proxy-cache projects cover docker-hub, ghcr, quay, and k8s-registry, but the image still needs to be cached on first pull. Running the binary directly avoids the pull entirely.

---

## Results — Control Plane (set-hog, k3s-cis-1.8)

```
Section              PASS   FAIL   WARN   INFO
──────────────────────────────────────────────
1 — Master           38      1     11     10
2 — etcd              0      0      7      0
4 — Node             11      5      2      5
5 — Policies          0      0     35      0
──────────────────────────────────────────────
Total                49      6     55     15
```

## Results — Worker Node (fast-skunk, k3s-cis-1.8)

```
Section              PASS   FAIL   WARN   INFO
──────────────────────────────────────────────
4 — Node             11      5      2      5
5 — Policies          0      0     35      0
──────────────────────────────────────────────
Total                11      5     37      5
```

---

## FAIL Analysis — All Are k3s False Positives

All 6 FAIL items are **detection limitations of kube-bench on k3s**, not real security issues. k3s configures its components through a single `k3s server` process and config file (`/etc/rancher/k3s/config.yaml`), not through the individual `--flag=value` CLI arguments that kube-bench scans for.

| Check | kube-bench FAIL reason | Actual state |
|---|---|---|
| `1.2.27` etcd-cafile | No `--etcd-cafile` arg found on kube-apiserver | k3s uses embedded SQLite — no external etcd |
| `4.2.1` anonymous-auth | No `--anonymous-auth=false` on kubelet process | **Verified**: `curl https://10.0.0.2:10250/pods` → `Unauthorized` |
| `4.2.2` authorization-mode | No `--authorization-mode` arg found | k3s defaults to `Webhook,Node` — not `AlwaysAllow` |
| `4.2.3` client-ca-file | No `--client-ca-file` arg found | Auto-provisioned at `/var/lib/rancher/k3s/agent/client-ca.crt` |
| `4.2.4` read-only-port | No `--read-only-port=0` arg found | **Verified**: port 10255 returns connection refused |
| `4.2.9` tls-cert-file | No `--tls-cert-file` arg found | Auto-provisioned at `/var/lib/rancher/k3s/agent/serving-kubelet.crt` |

**Why kube-bench can't find them:** kube-bench greps `/proc/<pid>/cmdline` for the kubelet/apiserver process. k3s embeds all control-plane components into a single `k3s server` binary — the individual flags aren't visible as separate process arguments.

---

## WARN Analysis — What We Already Satisfy

The policies section (5) is entirely manual WARNs — kube-bench can't auto-detect these. Several are already addressed by earlier phases:

| Check | Benchmark concern | Our status |
|---|---|---|
| `5.2.1` Active policy control mechanism | No Pod Security Admission or external policy controller | **Satisfied** — Gatekeeper (Phase 27) enforces 3 admission policies |
| `5.2.2` Minimize privileged containers | No admission control blocking `privileged: true` | **Satisfied** — `no-privileged-containers` Gatekeeper constraint active |
| `5.2.6` Block allowPrivilegeEscalation | No policy enforcement | **Partially satisfied** — covered by no-privileged constraint |
| `5.4.2` External secret storage | Secrets in etcd/k8s Secret objects | **Satisfied** — Vault (Phase 26) stores platform credentials; Agent Injector delivers to pods |

**Future actionable items** (not addressed on this cluster):

| Check | What it needs |
|---|---|
| `5.3.2` NetworkPolicies in all namespaces | Requires defining `NetworkPolicy` objects per namespace — Flannel supports it but none are deployed |
| `5.7.2` seccomp profile `RuntimeDefault` | Add `seccompProfile.type: RuntimeDefault` to pod `securityContext` |
| `5.7.3` SecurityContext on pods | Add `runAsNonRoot: true`, `readOnlyRootFilesystem: true` to workload pods |
| `5.1.5` Default SA token automount disabled | Add `automountServiceAccountToken: false` to default ServiceAccounts |

---

## Verification

```bash
# Run on control plane
ssh ubuntu@10.0.0.2 'sudo /tmp/kube-bench run \
  --config-dir /tmp/cfg --benchmark k3s-cis-1.8 \
  --targets master,node,etcd,policies 2>&1' \
  | grep -E '== Summary|checks (PASS|FAIL|WARN)'

# Verify anonymous-auth is actually disabled (should return Unauthorized)
curl -sk https://10.0.0.2:10250/pods
# Unauthorized

# Verify read-only-port is closed (should return connection refused)
curl -sk http://10.0.0.2:10255/healthz
# curl: (7) Failed to connect to 10.0.0.2 port 10255
```

---

## Done When

```text
✔ kube-bench v0.9.4 runs on control-plane node with k3s-cis-1.8 benchmark
✔ Control-plane: 49 PASS, 6 FAIL, 55 WARN — all 6 FAILs are k3s false positives
✔ Worker node: 11 PASS, 5 FAIL, 37 WARN — same false positives
✔ FAILs verified: anonymous-auth disabled (401), read-only-port closed (refused), SQLite not etcd
✔ WARN analysis: Gatekeeper (Ph27) and Vault (Ph26) already satisfy 5.2.1, 5.2.2, 5.4.2
✔ Future items documented: NetworkPolicies, seccomp, SecurityContext, SA token automount
```
