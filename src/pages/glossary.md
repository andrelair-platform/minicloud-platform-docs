---
title: Glossary
description: The minicloud / ktayl-solution vocabulary — platform, delivery, data, security, reliability and compliance terms in one place.
---

# Glossary

A cross-pillar reference for the vocabulary used across these docs. It spans both the **Platform**
(the shared technical capabilities) and the **Information System** (the insurance business apps) — see
the first two entries, which are the single most important distinction to keep straight.

## Core model

- **Platform (minicloud)** — the technical *capabilities* layer: compute, networking, storage, delivery
  (GitOps/CI/Kargo), secrets, identity-as-a-service, observability, the AI platform and the data platform.
  Business-agnostic — it would survive unchanged if the company stopped selling insurance.
- **Information System (ktayl-solution)** — the *applications, data and processes* that run the insurer:
  policy, claims, underwriting, billing, the digital workplace, ERP, ITSM, IAM governance, compliance. It
  *consumes* platform capabilities. (Provider ↔ consumer: Platform provides, the IS consumes.)
- **Retrieva** — the RNCP39583 certification project: a real DORA third-party-ICT compliance product that
  *runs on and benefits from* the IS. Distinct from the IS itself (the IS is its organisational context).

## Delivery & GitOps

- **GitOps** — Git is the single source of truth for the desired cluster state; a controller continuously
  reconciles the cluster to match it.
- **ArgoCD** — the GitOps controller here: it reconciles one environment from Git and auto-syncs it.
- **Kargo** — promotes one immutable image across stages by *writing the Git change* (opening PRs) that
  ArgoCD then deploys. Division of labour: **CI builds & proves the artifact; Kargo promotes it; ArgoCD
  deploys it.**
- **Warehouse / Freight / Stage** (Kargo) — a *Warehouse* watches for new artifacts; a *Freight* is a
  promotable set (an image or a commit); a *Stage* (dev, prod) is an environment a Freight is promoted to.
- **GAP wrapper chart** — the Helm golden path: a custom app is a thin chart depending on the shared
  `minicloud-app-deployment` library chart. One Helm render, one ArgoCD source.
- **CODEOWNERS gate** — the prod approval lives in Git: a PR touching a gated path (prod overlays,
  `services/*/helm`, `apps/`, `helm-values/`, `.claude/`) requires code-owner review before merge.
- **merge-gate** — an always-on required CI check that scans every PR for unresolved git conflict markers.
- **Harbor / ghcr** — the hybrid registry: **Harbor** holds dev/ephemeral images; **ghcr.io** holds the
  durable, immutable-SHA prod images.
- **cosign / SBOM / Trivy** — supply-chain controls: keyless image signing, a software bill of materials
  attached to the image, and a CRITICAL-severity vulnerability scan gate.

## Engineering process

- **BMAD** — the story-authoring workflow (intent → spec → stories → build → review), organised per product.
- **Delivery paths (A/B/C/E)** — the artefact burden scales to the work: **A** small change · **B**
  feature/epic · **C** new product/major initiative · **E** emergency/hotfix.
- **Test pyramid (L0–L4)** — L0 static · L1 unit · L2 integration (real DB/queue) · L3 contract · L4 e2e/smoke.
- **QA gate (L5)** — an adversarial test pass against the *live dev* service, mandatory before prod
  promotion (catches integration/deploy/runtime bugs that mocked tests cannot).

## Infrastructure

- **k3s** — the lightweight Kubernetes distribution the cluster runs on (6 nodes).
- **Cilium** — the eBPF CNI (networking + NetworkPolicy + Hubble observability).
- **Longhorn** — the distributed block storage providing network-attached PersistentVolumes.
- **CNPG (CloudNativePG)** — the Postgres operator and the database standard: HA failover + PITR backups.
- **ESO + Vault** — External Secrets Operator delivers secrets from HashiCorp Vault into pods; no secret
  material is ever committed to Git.
- **Authentik** — the identity provider: SSO/OIDC + MFA that every app trusts. Identity is the perimeter.
- **cert-manager** — issues TLS certificates from the internal `minicloud-ca` ClusterIssuer.
- **NATS / JetStream** — the messaging backbone for event-driven, asynchronous workflows.
- **Tailscale / Cloudflare Tunnel** — private mesh access (internal) and public ingress (for published apps).

## Reliability

- **SLO / SLI / error budget** — the reliability *objective*, the *indicator* that measures it, and the
  `1 − SLO` allowance whose burn gates risky changes.
- **RTO / RPO** — Recovery Time Objective (how fast service is restored) and Recovery Point Objective
  (how much data loss is tolerable) — proven by DR drills.
- **Game Day** — a deliberately induced failure, measured and written up in a postmortem — reliability as
  evidence.
- **MTTR** — Mean Time To Recovery: how long it takes to recover from an incident.

## Compliance

- **DORA** — the EU Digital Operational Resilience Act (ICT risk, third-party-ICT, resilience testing).
- **EU AI Act** — risk-tiered obligations for AI systems; controls scale with the tier.
- **GDPR** — EU data-protection regulation governing personal-data handling.
- **Solvency II** — the EU prudential framework for insurers (the regulatory spine of the IS).
