---
id: docker-course
title: Docker — project-based course (ktayl-docker-course)
sidebar_label: 🐳 Docker course
---

# Docker — a project-based course, taught from this platform

:::note Map, not library
This page is the **pointer**. The full course + knowledge base lives in its own repo
(**[`andrelair-platform/ktayl-docker-course`](https://github.com/andrelair-platform/ktayl-docker-course)**)
— per `documentation.md` (the org site is a map; detailed libraries live in their own repo).
:::

A complete, **project-grounded** Docker course that uses the whole ktayl/minicloud estate as its
laboratory — from *"why containers exist"* to *"production container architecture in Kubernetes."* Every
concept is taught against a **real specimen** in the platform, not a toy app.

## What's in the repo
- **Master index** — navigate by learning objective · operational problem · technology · project · topic;
  a T·L·P·R progress tracker.
- **Deliverables** (`_meta/`) — the Docker usage **inventory** (25 Dockerfiles across Go/Python/Node/Java/
  legacy + a custom Postgres base), competency map, 14-level **curriculum**, note taxonomy, lab roadmap,
  project-examples map, and a **Docker → Kubernetes** concept map.
- **14 level modules** — fundamentals → images → dockerfile → networking → storage → compose → security →
  debugging → ci-cd → registries → kubernetes → production → advanced, each in a consistent teaching
  format (concept · why · internals · **org example** · architecture · commands · debugging · production ·
  security · mistakes · takeaways · exercise).
- **11 cheatsheets** — fast "problem → command", including the `docker ↔ kubectl` twins.
- **A verified case study** — `platform-demo`'s distroless Go image (confirmed **≈6.27 MiB** from the
  registry), a real **ImagePullBackOff** troubleshooting write-up, and a **prod image-review checklist**.

## Why it maps to this platform
It teaches the exact things documented here from the inside: the **hybrid Harbor(dev) + ghcr(prod)**
registry model, **Kargo → ArgoCD → k3s(containerd)** delivery (see *Delivery workflow* + *Kargo
promotion*), **Gatekeeper** admission (non-root / allowed-registries / NET_RAW), and **cosign + SBOM +
Trivy** supply chain. A reader finishes able to reason about any service here: why it's containerised, how
its image is built, where it lives, how it reaches prod, how it's secured, and how Kubernetes runs it.

→ **Start:** [the repo README](https://github.com/andrelair-platform/ktayl-docker-course#readme) → Module 0.

:::info Simulation
`ktayl-solution` is a fictional insurer used as an engineering laboratory; the course uses synthetic data
+ real platform patterns. No production insurance operations are involved.
:::
