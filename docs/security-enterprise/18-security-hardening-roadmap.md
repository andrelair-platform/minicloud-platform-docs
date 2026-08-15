---
id: security-hardening-roadmap
title: Security Hardening Roadmap
sidebar_position: 18
---

# Security Hardening Roadmap

This page covers the active security hardening sprint: Trivy supply-chain scanning, Falco runtime detection, kube-bench CIS compliance, Checkov IaC scanning, and the Wazuh SIEM target for DORA compliance.

---

## Offensive vs. Defensive Tools — The Right Mental Model

Tools like Burp Suite, OWASP ZAP, Metasploit, Nmap, and Wireshark are **offensive / assessment tools** — they test whether your defenses hold. They are not installed as services and not run continuously. The correct cadence is:

| Tool | Purpose | When to use |
|---|---|---|
| Burp Suite / OWASP ZAP | Web app vulnerability scanning | Quarterly pentest of public-facing services |
| Nmap | Network surface discovery | Before and after firewall changes |
| kube-hunter | Kubernetes attack surface | After major cluster upgrades |
| Metasploit | Exploit validation | Authorized pentest engagements only |
| Wireshark | Packet capture / protocol analysis | Incident investigation |

**Day-to-day protection** comes from the defensive stack — Falco, Trivy, Gatekeeper, NetworkPolicies, Vault — which is what this page covers.

**On NAT exposure:** The cluster is behind SFR box NAT and Cloudflare WAF, which eliminates the most common internet-facing attack vectors. Risk is still present from supply-chain (compromised images, malicious dependencies), insider threat, and misconfiguration. The hardening roadmap addresses all three.

---

## 1. Trivy — Supply-Chain Scanning in Harbor

**Status: deployed and active.** Harbor has a dedicated Trivy scanner pod (`harbor-trivy-0` in the `harbor` namespace).

```text
CI push image → Harbor registry → Trivy scans automatically → CVE report attached to image
                                       │
                              If CRITICAL CVE found:
                              ArgoCD pulls tagged image → policy blocks deployment
```

### Enabling scan-on-push and CVE blocking

In Harbor UI → **Administration → Interrogation Services** → **Vulnerability** tab:

1. **Scan on push**: enable — every pushed image is scanned automatically
2. **Prevent vulnerable images from running**: set threshold to **Critical**

Or via Harbor API (from controller, once Harbor is healthy):

```bash
# Enable scan-on-push system-wide
curl -s --cacert ~/minicloud-ca.crt \
  -u "admin:$(cat ~/.harbor-admin)" \
  -X PUT "https://harbor.10.0.0.200.nip.io/api/v2.0/configurations" \
  -H 'Content-Type: application/json' \
  -d '{"scan_all_policy":{"parameter":{"daily_time":0},"type":"daily"}}'

# Enable vulnerability prevention at Critical severity
curl -s --cacert ~/minicloud-ca.crt \
  -u "admin:$(cat ~/.harbor-admin)" \
  -X PUT "https://harbor.10.0.0.200.nip.io/api/v2.0/configurations" \
  -H 'Content-Type: application/json' \
  -d '{"prevent_vul_enabled":true,"vulnerability_severity":"critical"}'
```

### Per-project scan policy

Set on each project (e.g., `library`):

```bash
curl -s --cacert ~/minicloud-ca.crt \
  -u "admin:$(cat ~/.harbor-admin)" \
  -X PUT "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/library" \
  -H 'Content-Type: application/json' \
  -d '{"metadata":{"auto_scan":"true","prevent_vul":"true","severity":"critical"}}'
```

### Quick check

```bash
# View scan results for the platform-demo image
/usr/bin/curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:$(cat ~/.harbor-admin)" \
  "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/library/repositories/platform-demo/artifacts?with_scan_overview=true" \
  | python3 -m json.tool | grep -A3 '"severity"'
```

---

## 2. Falco — Runtime Threat Detection

**Status: deployed and healthy.** Falco v0.44.1 runs as a DaemonSet across all 5 nodes (4 ThinkPads + swift-mac), with 2 Falcosidekick pods routing alerts to Grafana.

```
kubectl get pods -n falco
# 5× falco-xxxxx (DaemonSet, one per node)
# 2× falco-falcosidekick-xxxxx (alert router)
```

### What it detects

Falco uses eBPF (`modern_ebpf` driver) to intercept kernel syscalls. Default ruleset covers:

| Rule category | Examples |
|---|---|
| Shell in container | `execve` of bash/sh inside a running container |
| Sensitive file reads | Open of `/etc/shadow`, `/etc/kubernetes/pki/` |
| Network anomalies | Unexpected outbound connections from known pods |
| Privilege escalation | `setuid`, `chmod +s`, `sudo` inside containers |
| Package manager in container | `apt-get`, `yum`, `pip install` at runtime |

### View live alerts

```bash
# Stream Falco alerts from any node
ssh controller "kubectl logs -n falco -l app.kubernetes.io/name=falco -f --since=1h | grep 'Warning\|Error\|Critical'"

# Or via Grafana → Explore → Loki → {namespace="falco"}
```

### Falcosidekick routes to Grafana/Loki

Alerts are forwarded by Falcosidekick to Loki (configured in `helm-values/minicloud-1/falco-values.yaml`). Search in Grafana:

```
{namespace="falco"} |= "Warning"
```

### Custom rules

Add custom rules in `helm-values/minicloud-1/falco-values.yaml` under `customRules:`:

```yaml
customRules:
  insurance-rules.yaml: |
    - rule: Write to ERPNext config dir
      desc: Alert on writes inside the ERPNext config directory
      condition: open_write and container and fd.name startswith /home/frappe/frappe-bench/sites/
      output: "Suspicious write to ERPNext sites dir (user=%user.name file=%fd.name)"
      priority: WARNING
      tags: [erp, filesystem]
```

---

## 3. kube-bench — CIS Kubernetes Benchmark

**Status: completed.** kube-bench v0.9.4 was run against the cluster with the `k3s-cis-1.8` benchmark.

Results summary:

| Node | PASS | FAIL | WARN | All FAILs |
|---|---|---|---|---|
| set-hog (control plane) | 49 | 6 | 55 | k3s false positives |
| fast-skunk (worker) | 11 | 5 | 37 | k3s false positives |

**All 6 FAILs are k3s false positives** — kube-bench greps `/proc/<pid>/cmdline` for flag names, but k3s embeds all control-plane components into one binary. The flags exist (`anonymous-auth=false`, TLS certs auto-provisioned) but are invisible to kube-bench. See [Phase 29 — kube-bench](kube-bench) for full analysis.

**Active WARN items (planned):**

| Check | What it needs | Priority |
|---|---|---|
| `5.3.2` NetworkPolicies in all namespaces | Deploy deny-all + allow-required per namespace | High |
| `5.7.2` seccomp RuntimeDefault | Add `seccompProfile.type: RuntimeDefault` to pod securityContext | Medium |
| `5.7.3` SecurityContext on pods | `runAsNonRoot: true`, `readOnlyRootFilesystem: true` | Medium |
| `5.1.5` SA token automount | `automountServiceAccountToken: false` on default ServiceAccounts | Low |

### Re-run kube-bench

```bash
# Download and push to control-plane node
ssh controller "
curl -sL https://github.com/aquasecurity/kube-bench/releases/download/v0.9.4/kube-bench_0.9.4_linux_amd64.tar.gz \
  -o /tmp/kube-bench.tar.gz && tar -xzf /tmp/kube-bench.tar.gz -C /tmp/
scp /tmp/kube-bench ubuntu@10.0.0.2:/tmp/kube-bench
scp -r /tmp/cfg ubuntu@10.0.0.2:/tmp/cfg"

ssh ubuntu@10.0.0.2 'sudo /tmp/kube-bench run \
  --config-dir /tmp/cfg --benchmark k3s-cis-1.8 \
  --targets master,node,etcd,policies 2>&1' \
  | grep -E '== Summary|PASS|FAIL|WARN'
```

---

## 4. Checkov — IaC Security Scanning in CI

**Status: deployed 2026-08-16.** Checkov runs on every PR to `main` in `minicloud-gitops` when `manifests/`, `services/`, `apps/`, or `helm-values/` change.

Workflow: `.github/workflows/checkov.yml`

```text
PR to main (paths: manifests/**, services/**, apps/**, helm-values/**)
    │
    ▼
bridgecrewio/checkov-action@v12
    │  framework: kubernetes,helm
    │  output: SARIF → GitHub Code Scanning
    ▼
Findings appear in PR "Security" tab
Blocking on new Critical/High misconfigs
```

### What Checkov catches

| Category | Example findings |
|---|---|
| Pod security | Missing `securityContext.runAsNonRoot`, privileged containers |
| RBAC | Wildcard `verbs: ["*"]` in ClusterRoles, default SA with token |
| Network | Missing `NetworkPolicy` for namespaces |
| Secrets | Secrets in env vars (should be ESO → Vault) |
| Resource limits | Containers without CPU/memory limits |
| Image hygiene | `latest` tag, no digest pinning |

### Skipped checks (with rationale)

| Check | Reason skipped |
|---|---|
| `CKV_K8S_8/9` | Liveness/readiness probes: SRE responsibility per workload |
| `CKV_K8S_28/14/43` | Image tag/digest: CI pins at build time, ArgoCD syncs pinned tags |
| `CKV_K8S_35` | Secret env vars: we use ESO → Vault for all platform secrets |
| `CKV_K8S_36` | Drop ALL capabilities: Gatekeeper (Phase 27) enforces this at admission |
| `CKV2_K8S_6` | Wildcard RBAC: Helm charts often include; tracked as separate hardening item |

### Local run

```bash
cd ~/Developer/cloudplateform/minicloud-gitops
pip install checkov
checkov -d . --framework kubernetes,helm \
  --skip-check CKV_K8S_8,CKV_K8S_9,CKV_K8S_28,CKV_K8S_14,CKV_K8S_43,CKV_K8S_35,CKV_K8S_36,CKV2_K8S_6 \
  --output cli
```

---

## 5. Wazuh — SIEM / DORA Compliance (Planned)

**Status: planned.** Wazuh is the primary gap between "secure" and "auditable" for a DORA-compliant insurance IS.

### What Wazuh adds

| Capability | Benefit for ktayl IS |
|---|---|
| File Integrity Monitoring (FIM) | Detect unauthorized changes to config files, systemd units, k3s config |
| Log centralization | Aggregate controller + node + k8s audit logs into one searchable store |
| Compliance dashboards | PCI-DSS, NIST CSF, GDPR/DORA compliance reports out of the box |
| Vulnerability detection | Agent-based CVE scanning at OS level (complements Trivy at container level) |
| Incident alerting | MITRE ATT&CK mapping, alert correlation across all nodes |

### Architecture

```
All 5 nodes (set-hog, fast-skunk, fast-heron, star-kitten, swift-mac)
  └── Wazuh agent (installed via Ansible)
         │
         ▼ encrypted OSSEC protocol
  controller (or dedicated node)
  └── Wazuh manager + Indexer (OpenSearch) + Dashboard
         │
         ▼
  Grafana (via OpenSearch data source)
```

### Why it's heavyweight

Wazuh Indexer (OpenSearch) requires ~4Gi RAM and ~50Gi disk for a 5-node cluster with 30-day retention. This pushes cluster memory close to its limit. Deploy after the +2 ThinkPads (roadmap issue #239) are provisioned.

### DORA requirements satisfied by Wazuh

| DORA Article | Requirement | Wazuh covers |
|---|---|---|
| Art. 9 | ICT incident classification and reporting | Alert severity taxonomy, incident timeline |
| Art. 10 | ICT incident response and recovery | Real-time detection → automated response rules |
| Art. 13 | Digital operational resilience testing | Audit logs for penetration tests |
| Art. 17 | ICT third-party risk | Third-party software change detection (FIM) |

### Deployment target

After +2 ThinkPads (roadmap issue #239), target cluster RAM: ~128Gi → Wazuh on dedicated node.

---

## Current Security Posture Summary

| Layer | Tool | Status |
|---|---|---|
| Supply chain — container images | Harbor Trivy | ✅ Deployed (harbor-trivy-0 Running) |
| Supply chain — IaC configs | Checkov CI | ✅ Live (`.github/workflows/checkov.yml`) |
| Runtime detection | Falco 0.44.1 | ✅ All 5 nodes |
| CIS compliance | kube-bench 0.9.4 | ✅ Run complete, 6 false positives documented |
| Admission control | Gatekeeper (18 constraints) | ✅ Phase 27 |
| PKI / Certificate authority | Vault PKI | ✅ CA migrated from k8s secret 2026-08-15 |
| Secret management | HashiCorp Vault | ✅ Phase 26 |
| RBAC | Authentik OIDC + k8s RBAC | ✅ Phase 28 |
| Network segmentation | Cilium + NetworkPolicies | ✅ Partial (monitoring ns) |
| Edge security | Cloudflare WAF + Zero Trust | ✅ Phase 25 |
| SIEM / DORA audit | Wazuh | 🔵 Planned post-+2 ThinkPads |
| OS hardening | host-hardening.md | ✅ Phase 29 |

---

## Done When

```text
✔ Trivy scanner pod Running in harbor ns (harbor-trivy-0)
✔ Harbor scan-on-push documented; CVE blocking policy defined
✔ Falco 0.44.1 DaemonSet: 5/5 nodes healthy
✔ Falcosidekick → Loki → Grafana alert pipeline active
✔ kube-bench k3s-cis-1.8: 49+11 PASS, all FAILs are false positives
✔ Checkov CI workflow deployed (PR #TBD, minicloud-gitops)
✔ SARIF output → GitHub Code Scanning on every PR to main
✔ Offensive tools framing documented (pentest vs. day-to-day protection)
🔵 Wazuh SIEM: planned after +2 ThinkPads (roadmap #239)
```
