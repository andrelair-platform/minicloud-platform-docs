---
id: build-the-cluster
title: How the cluster was built
sidebar_label: How the cluster was built
slug: /build-the-cluster
tags: [how-to]
---

# How the cluster was built — bare metal → Kubernetes

> **How-to.** The order I actually built the 6-node cluster, from second-hand laptops to a running
> Kubernetes platform. This page is the **entry point** — each step links to its detailed walkthrough.

**Who this is for:** anyone who wants the "how did you build this?" story end-to-end, without hunting
through the sidebar.

## The build, in order

| # | Step | What happens | Detailed guide |
|---|------|--------------|----------------|
| 1 | **Hardware** | 6 second-hand laptops + a controller — the physical fleet and why | [MAAS — Objective & hardware](/platform/phase-0-maas/objective) |
| 2 | **Bare-metal provisioning** | MAAS PXE-boots and installs Ubuntu on each node, hands-off | [MAAS — Provisioning](/platform/phase-0-maas/provisioning) |
| 3 | **Install Kubernetes (k3s)** | A lightweight k3s control plane + workers across the nodes | [k3s — Install](/platform/platform-roadmap/phase-1-kubernetes) |
| 4 | **Access the cluster** | kubectl + OIDC access from the Mac / off-cluster | [Remote & kubectl access](/platform/platform-roadmap/phase-2-access) |
| 5 | **Networking & ingress** | MetalLB + Cilium + the ingress that exposes apps | [Ingress](/platform/platform-roadmap/phase-6-ingress) |
| 6 | **First workload** | Deploy the first app to prove the platform runs | [First workload](/platform/platform-roadmap/phase-9-workload) |

From here the platform grows via **GitOps** (ArgoCD/Kargo), observability, security and the AI/data
platforms — see the [Architecture Hub](/platform/architecture) for the full picture, or the
[roadmap overview](/platform/platform-roadmap/roadmap-overview) for the phase-by-phase story.

## Related

- [MAAS & Bare-Metal Provisioning](/platform/phase-0-maas/objective) — the full bare-metal section (12 pages)
- [Production Stack Architecture](/platform/developer-platform/production-stack-architecture) — what's running now
- [Architecture Hub](/platform/architecture) — how the whole platform fits together
