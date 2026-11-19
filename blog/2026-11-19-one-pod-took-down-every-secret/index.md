---
slug: one-pod-took-down-every-secret
title: "One Pod Took Down Every Secret in the Cluster — and Why the Fix Wasn't 'Restart It'"
authors: [andrelair]
tags: [reliability, external-secrets, vault, cilium, kubernetes, sre, incident]
date: 2026-11-19
description: "A power event left 126 ExternalSecrets failing cluster-wide. The symptom pointed at Vault; the cause was a single controller pod on a flaky node. The interesting part is why the obvious fix — restart it — does nothing, and what actually makes it self-heal."
---

I was verifying a routine production deploy when ArgoCD flipped the app to **Degraded**. The pods were
healthy, the endpoints answered — so I looked wider. *Every* app was Degraded. A cluster-wide query showed
**126 ExternalSecrets failing to sync**, and they had been failing silently for hours after a power event
earlier that day.

Nothing had broken that I could see from the outside. That's the kind of incident worth writing down.

{/* truncate */}

## The misdiagnosis trap

The surface reading is "Vault is down" or "the secrets operator is broken." Both were wrong. Vault was
**unsealed and healthy**. The external-secrets operator (ESO) was **Running**. Yet the `vault-backend`
ClusterSecretStore sat `InvalidProviderConfig`, and the real error, buried in the store status, was not
about Vault at all:

```
cannot request a ServiceAccount token for external-secrets:
Post https://10.43.0.1:443/.../token: dial tcp 10.43.0.1:443: network is unreachable
```

ESO authenticates to Vault using a Kubernetes ServiceAccount token it mints from the **API server**
(`10.43.0.1:443`). The single ESO controller pod happened to be scheduled on the oldest, flakiest node in
the cluster, and *that node* had lost its pod-to-API-server routing across the reboot. So ESO couldn't mint
its token → couldn't build its Vault client → **every** ExternalSecret stopped refreshing. One pod, on one
bad node, took out secret refresh for the whole cluster.

(There's a sibling failure mode with the identical symptom but a different cause — node clock skew making
Vault reject the token's `nbf` claim with a 403. Same store error, completely different fix. The lesson
that saved time: **read the exact error string before acting** — `network is unreachable` and
`invalid nbf claim` send you to opposite ends of the stack.)

## Why "restart it" does nothing

The reflex is `kubectl rollout restart`. It doesn't help — the fresh pod reschedules straight back onto the
same broken node and fails the same way. (A one-off `cilium` restart on *that* node fixes the routing and
recovers everything in two minutes — but that's a human noticing and intervening, and the incident had
already run for hours unnoticed.)

The deeper problem isn't the flaky node. It's that **a critical cluster-wide controller was a single pod** —
a hidden single point of failure hiding inside something that *looks* stateless and disposable.

## The fix that makes the failure self-heal

Two replicas with **leader election**, spread across nodes. The mechanism is the elegant part, and it's
worth understanding rather than cargo-culting:

- The leader holds a **lease in the API server**. Only the leader reconciles; the second pod is a hot
  standby.
- When the leader's node loses API-server routing, it **can't renew its lease**. The standby — on a healthy
  node, which *can* reach the API server — sees the lease expire and **acquires it**, then resumes
  reconciling.

So the exact event that broke ESO (a node losing the API server) is now the thing that **triggers
failover**. No human, no `cilium` restart.

Two details mattered:

1. **`leaderElect` defaults to `false`.** Bumping to two replicas *without* enabling it would be worse than
   the bug — both pods would reconcile at once. That one line is the whole fix.
2. **Spread, don't pin.** The tempting shortcut is "just keep ESO off the bad node." But pinning-away is
   still a pin, and it only defends against the *one* node you've already seen fail. A topology spread
   across hostnames survives *any* single bad node — which is the actual requirement.

I scoped it to the controller (the proven failure path) and left the admission webhook alone — narrow beats
broad when you're changing a component the whole cluster depends on.

## The meta-lesson

This outage was **latent**. Running pods were unaffected (their secrets were already materialised); the only
victims-in-waiting were any pod that would restart and need a fresh secret. Green CI, healthy dashboards, no
alert — it was invisible until someone *verified a deploy end-to-end* and noticed an unrelated app was
Degraded.

That's the entire case for checking the real system over trusting the pipeline. The finance feature I was
shipping that day was fine. Verifying it is what surfaced a cluster-wide reliability bug that had nothing to
do with it — and that's exactly the kind of thing a pipeline can't show you.
