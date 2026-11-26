---
id: troubleshooting
title: Troubleshooting — when something's wrong
sidebar_label: Troubleshooting
tags: [how-to]
---

# Troubleshooting — when something's wrong

> **How-to.** The first things to check, in order, for the failures a new service hits most. Always pass
> `--context minicloud-oidc` to `kubectl` (your scoped read/debug context).

## Pod won't start / `CrashLoopBackOff`

Check in this order — the cause is almost always one of these:

```bash
kubectl -n <ns> get pods                       # see the state + restart count
kubectl -n <ns> logs <pod> --previous          # logs of the CRASHED container (the real error)
kubectl -n <ns> describe pod <pod>             # Events at the bottom = the why
```

| Symptom in `describe` / logs | Likely cause | Fix |
|---|---|---|
| `ImagePullBackOff` / `ErrImagePull` | image tag doesn't exist, or missing pull secret | check the SHA tag was built; ensure `imagePullSecrets: [ghcr-pull]` + the ESO `ghcr-pull` secret exists in the ns |
| `CreateContainerConfigError` | a referenced Secret/ConfigMap is missing | the ExternalSecret hasn't synced → see [Add a secret](/platform/getting-started/add-a-secret) |
| App logs an error then exits | app config / a missing env var / DB unreachable | fix config; if DB-unreachable see the netpol section below |
| `Liveness probe failed` → restarts | probe path/port wrong, or app slow to boot | fix the probe path/port or raise `initialDelaySeconds` |
| `OOMKilled` | memory limit too low | raise the memory limit in the values file |
| `FailedScheduling` | resource quota / no node fits | check the namespace `ResourceQuota`; lower requests |

## App can't reach its database (or another service)

The cluster is **default-deny** (Cilium) — traffic is blocked unless a NetworkPolicy allows it. A new
cross-namespace call (e.g. app in `myapp` → DB in `myapp` is fine, but → a service in another ns) needs
an explicit allow.

```bash
# Is it actually a network block? curl from inside the pod:
kubectl -n <ns> exec -it <pod> -- sh -c 'nc -zv <db-host> 5432'   # refused/timeout = blocked or down
# See the policies in effect:
kubectl -n <ns> get ciliumnetworkpolicy
```

- **Timeout (not refused)** → almost always a **NetworkPolicy** dropping it. Add/ fix the allow rule
  (egress from your pod's labels → the DB ns/port). See [Network isolation](/platform/security-enterprise/namespace-isolation).
- **Connection refused** → the target isn't listening (DB pod down, wrong port/host).
- **DNS error** → wrong service name; it's `<svc>.<ns>.svc` (e.g. `myapp-cnpg-rw.myapp.svc`).
- The live traffic view (allowed vs dropped, per flow) is **Hubble** — `hubble.10.0.0.200.nip.io`.

## It works on dev but the prod promotion stalls

- **Kargo isn't promoting** → the Warehouse can't rank the image (the NewestBuild monotonic-timestamp
  trap) or a flow-YAML image block broke the `yaml-update`. See [Kargo promotion](/platform/developer-platform/kargo-promotion).
- **App `OutOfSync` but Healthy** → an ExternalSecret without the SSA `ignoreDifferences` (see
  [Add a secret](/platform/getting-started/add-a-secret)), or a CronJob whose last run failed.

## When in doubt

```bash
kubectl -n <ns> get events --sort-by=.lastTimestamp | tail -20   # recent cluster events for the ns
```
Then the service's **metrics/alerts** → [Application monitoring](/platform/observability/application-monitoring).

## Related

- [Add a secret (Vault → ESO)](/platform/getting-started/add-a-secret)
- [Network isolation](/platform/security-enterprise/namespace-isolation) · [Application monitoring](/platform/observability/application-monitoring)
- [Getting Started (A→Z)](/platform/getting-started)
