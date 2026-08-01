---
id: coredns-ha
title: CoreDNS HA — Two Replicas on Separate Nodes
sidebar_position: 3
---

# CoreDNS HA — Two Replicas on Separate Nodes

k3s ships CoreDNS with `replicas: 1` by default. A single CoreDNS pod is a
cluster-wide DNS single point of failure: if the pod crashes or its node goes
down, every pod that opens a new connection (service discovery, external
lookups, Vault leases, ArgoCD repo polling) stalls until CoreDNS reschedules.
With 323 pods across 5 nodes, that blast radius is unacceptable.

This page documents the fix applied on **2026-08-01** and the incident that
occurred during it.

---

## Root cause: k3s default

k3s manages CoreDNS via a static manifest at
`/var/lib/rancher/k3s/server/manifests/coredns.yaml` on the control-plane
node (`set-hog`). The Deployment spec has no `replicas:` field, which
Kubernetes defaults to 1.

The manifest already included well-formed `topologySpreadConstraints`:

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        k8s-app: kube-dns
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        k8s-app: kube-dns
```

`whenUnsatisfiable: DoNotSchedule` means a second replica is **guaranteed** to
land on a different node — no explicit pod anti-affinity rule needed. The only
missing piece was `replicas: 2`.

---

## The incident

The first patch attempt used a Python script whose output was piped directly
into `sudo tee`:

```bash
# WRONG — if the script exits non-zero, tee still runs with empty stdin
python3 /tmp/patch.py | sudo tee /var/lib/rancher/k3s/server/manifests/coredns.yaml
```

The script exited with code 1 (pattern not found), printed nothing to stdout,
and `sudo tee` overwrote the manifest with an empty file. k3s's manifest
watcher detected the change within seconds and deleted the CoreDNS Deployment.

**DNS was down cluster-wide for ~8 minutes.**

Recovery: `sudo systemctl restart k3s` on `set-hog` causes k3s to regenerate
`coredns.yaml` from its embedded templates, restoring CoreDNS to a working
single-replica state.

**Lesson:** never pipe a script that may fail into `tee` on a live system
file. Write to a temp file, verify, then move atomically:

```python
out = path + '.tmp'
with open(out, 'w') as f:
    f.write(patched)
shutil.move(out, path)  # atomic on same filesystem
```

---

## The fix

```python
# /tmp/patch-coredns.py — run as: sudo python3 /tmp/patch-coredns.py
import sys, shutil

path = '/var/lib/rancher/k3s/server/manifests/coredns.yaml'

with open(path, 'r') as f:
    content = f.read()

old = '  revisionHistoryLimit: 0\n  strategy:'
new = '  replicas: 2\n  revisionHistoryLimit: 0\n  strategy:'

if old not in content:
    print(f"ERROR: pattern not found", file=sys.stderr)
    sys.exit(1)

if '  replicas:' in content:
    print("already patched"); sys.exit(0)

patched = content.replace(old, new, 1)

out = path + '.tmp'
with open(out, 'w') as f:
    f.write(patched)
shutil.move(out, path)
print("OK")
```

k3s picks up the change via inotify within a few seconds and patches the live
Deployment. No k3s restart needed.

---

## Verification

```bash
# Confirm the Deployment has replicas: 2
kubectl get deployment coredns -n kube-system \
  -o jsonpath='replicas={.spec.replicas} ready={.status.readyReplicas}{"\n"}'
# → replicas=2 ready=2

# Confirm pods are on separate nodes
kubectl get pods -n kube-system -o wide | grep coredns
# coredns-...  1/1  Running  fast-heron
# coredns-...  1/1  Running  set-hog
```

---

## After a k3s upgrade

k3s regenerates `coredns.yaml` from embedded templates during version
upgrades, which resets `replicas` back to 1. Re-apply the patch after any
`system-upgrade-controller` k3s upgrade:

```bash
# On set-hog
scp /tmp/patch-coredns.py set-hog:/tmp/patch-coredns.py
ssh set-hog "sudo python3 /tmp/patch-coredns.py"
```

Or check first:

```bash
ssh set-hog "sudo grep 'replicas:' /var/lib/rancher/k3s/server/manifests/coredns.yaml || echo 'needs patch'"
```

---

## Current state

| Before | After |
|---|---|
| 1 replica on `fast-skunk` | 2 replicas: `fast-heron` + `set-hog` |
| Single node failure → DNS outage | One node can die, DNS keeps serving |
| `cache 30` (k3s default) | `cache 30` (unchanged — adequate for this load) |

---

## Real-world skills demonstrated

| Skill | Context |
|---|---|
| **Understanding k3s's static manifest system** | k3s manages system components via `/var/lib/rancher/k3s/server/manifests/`, not Helm. Changes are picked up live via inotify. This is different from managed k8s (EKS, GKE) where control-plane components aren't user-accessible. |
| **`topologySpreadConstraints` vs pod anti-affinity** | TSC with `whenUnsatisfiable: DoNotSchedule` is stricter and cleaner than `podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution`. The constraint was already in place — recognizing it was sufficient shows familiarity with the spread semantics. |
| **Atomic file replacement** | Write to `.tmp`, then `shutil.move()` — not `open(path, 'w')` directly. On the same filesystem, `move` is a rename syscall and is atomic. Directly opening for write truncates immediately, which is what caused the incident. |
| **Controlled recovery from a self-inflicted outage** | Diagnosed the failure mechanism (inotify + empty manifest → delete), identified the fastest recovery path (k3s restart regenerates templates), restored service in ~8 minutes, then applied the correct fix. |
