---
slug: platform-engineering-bare-metal-kubernetes
title: "Platform Engineering on a Budget: Running Production Kubernetes on 5 ThinkPads"
authors:
  - name: Andre Kanmegne
    title: Software Engineer & Cloud Architect
    url: https://www.devandre.sbs
description: >
  How I built a production-grade Kubernetes platform on five bare-metal ThinkPad laptops —
  with MAAS provisioning, GitOps, SSO, observability, and AI services — and what I learned
  about real platform engineering along the way.
tags: [kubernetes, platform-engineering, devops, k3s, gitops, bare-metal]
date: 2026-07-13
image: /img/docusaurus-social-card.jpg
---

Most cloud platforms hide the infrastructure from you. MAAS provisioning, PXE boot sequences, NIC bonding, storage backends, certificate chains — all of it abstracted behind a few CLI flags or a dashboard. That abstraction is valuable in production, but it can also keep engineers at arm's length from the system they're supposed to understand deeply.

This project started from a simple question: **what does it actually take to build a production-grade Kubernetes platform from scratch?**

<!-- truncate -->

## The Setup

The hardware is five laptops: four Lenovo ThinkPad X390s acting as cluster nodes and a MacBook Pro 2012 running as a storage worker. A fifth ThinkPad X390 runs as the MAAS controller — handling PXE boot, DHCP, DNS, and Tailscale NAT for the entire rack. Total cost: well under a cloud provider's monthly invoice for equivalent compute.

```
Controller (MAAS):    ktayl-ThinkPad-X390  — Tailscale endpoint, NAT, kubectl
Control plane:        set-hog              — k3s master, 10.0.0.2
Workers:              fast-skunk           — 10.0.0.4
                      fast-heron           — 10.0.0.7
                      star-kitten          — 10.0.0.8
                      swift-mac            — 10.0.0.10 (MacBook Pro 2012, Longhorn storage)
```

Every node is provisioned by MAAS via PXE: the controller broadcasts a boot offer, nodes pick it up, and Ubuntu 22.04 is deployed with a pre-seeded cloud-init. That means any node can be wiped and re-provisioned in under 10 minutes — the same discipline you'd apply in a real cloud provider's bare-metal service.

## What "Production-Grade" Actually Means Here

Running a home lab is easy. Running it like a platform team would run production is a different discipline entirely. The constraints I imposed on myself:

- **No manual `kubectl apply`** — all workloads live in Git and sync via ArgoCD (app-of-apps pattern, Kustomize base+overlays, 3-branch CI promotion flow)
- **Zero-trust networking** — OPA Gatekeeper admission policies in deny mode across all 23 namespaces, NetworkPolicy enforced everywhere, Vault auto-unseal via AWS KMS
- **Observability from day one** — Prometheus + Grafana + Loki + Tempo deployed before any application workload; node_exporter on the controller itself so disk alerts fire before MinIO crashes
- **OIDC SSO on every service** — Authentik as the identity provider, OIDC/PKCE protecting ArgoCD, Grafana, Harbor, Backstage, Open WebUI, and Vaultwarden
- **Automated regression testing** — 62 checks across infra, GitOps, security, storage, AI, and observability that I run after every significant change

## The Things That Surprised Me

**Storage is the hardest part of bare metal.** Longhorn on the MacBook Pro 2012 (swift-mac) required hand-tuning mount propagation, replica counts, and scheduling tolerations. When the node goes down unexpectedly — and it does, because Apple's SMC doesn't support Wake-on-AC — Longhorn's replica recovery needs headroom that you only understand by watching it fail twice.

**Certificate chains break in non-obvious ways.** I run a private CA (`minicloud-ca.crt`) for all internal HTTPS endpoints. The macOS System Keychain trusts it, but `/opt/anaconda3/bin/curl` uses OpenSSL and ignores it silently. Two hours of debugging a Harbor push failure taught me to always check which `curl` binary is in `$PATH`.

**GitOps and ArgoCD StatefulSet sync have edge cases.** When a StatefulSet's `VolumeClaimTemplate` is defined without explicit `apiVersion`, `kind`, and `volumeMode`, ArgoCD v3.4.1 perpetually shows a diff — even after sync. The fix is to write the full spec in the manifest; `ignoreDifferences` doesn't work for these fields.

**Velero backup timeouts need tuning per workload.** The default 4-hour `itemOperationTimeout` on Velero's kopia plugin wasn't enough for a 4.5 GB ClickHouse PV (Langfuse LLM trace data). Kopia transferred ~2.5 GB and then the backup was cancelled. Bumping to 8 hours fixed it — but the lesson is that backup SLOs depend on data size, not just infrastructure configuration.

## What's Running Today

After 35+ phases of incremental build-out, the current platform runs:

| Service | Purpose |
|---|---|
| ArgoCD | GitOps delivery — 8 custom app repos, 23 namespaces |
| Harbor | Private container registry with cosign image signing |
| Backstage | Internal developer portal with catalog, TechDocs, scaffolder |
| Authentik | OIDC/SSO identity provider |
| Grafana + Prometheus | Metrics, dashboards, alerting |
| Loki + Tempo | Log aggregation and distributed tracing |
| Vault | Secrets management with Kubernetes auth |
| Longhorn | Distributed block storage across the cluster |
| Open WebUI + Ollama | Self-hosted LLM chat with local models |
| RAG pipeline | Document ingestion → chunking → embeddings → pgvector |
| Velero | Scheduled backups to MinIO (daily, 7-day TTL) |
| Vaultwarden | Self-hosted password manager with SSO |
| Cloudflare Tunnel | Public HTTPS access without port-forwarding |

All publicly reachable at `*.devandre.sbs` via Cloudflare Tunnel, protected by Authentik SSO.

## Why This Matters for Engineering

The goal was never to run Kubernetes at home for its own sake. The goal was to develop the kind of platform instinct that only comes from operating infrastructure through failure: disk fills up and MinIO hangs in memory with no alert; a node's SMC doesn't respond to WoL and a cron job has to compensate; a Velero CRD upgrade job never sets `status.succeeded` because of a k3s Job controller bug.

Those incidents — and the fixes — are what platform engineering actually looks like beneath the abstractions. The next posts in this series will go deeper into specific components: the RAG pipeline architecture, the GitOps promotion workflow, and the OPA Gatekeeper policy set.

---

*The full runbooks for every phase live in the [Documentation](/platform-roadmap/roadmap-overview) section of this site.*
