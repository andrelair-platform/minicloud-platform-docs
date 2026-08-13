---
id: sprint-log
title: Sprint Log & Velocity — CERT-1
sidebar_label: Sprint Log & Velocity
---

# Sprint Log & Velocity

**Project:** ktayl-solution Claims & Policy Platform (CERT-1 / RNCP39583 BC01)

---

## Development Tracking Tool

:::note Plane CE is for business teams only
Plane CE on this platform is used exclusively by the **business team** to pilot their own projects (insurance operations, HR, compliance). It is **not** used for the software development process.

Development tracking uses:
- **GitHub Issues** (`andrelair-platform/platform-backlog`) — backlog, acceptance criteria, priorities
- **GitHub Projects** (`minicloud platform roadmap` board) — Backlog / In Progress / Done columns
- **GitHub Milestones** — per-sprint grouping on platform-backlog

This is consistent with the team's engineering workflow: every deliverable has an associated GitHub Issue, every PR references that issue, and the board reflects real-time status without a separate tool.
:::

---

## Methodology

| Dimension | Choice | Rationale |
|-----------|--------|-----------|
| Framework | **Scrumban** | Continuous flow for infra work; time-boxed review sessions for deliverable sprints |
| Sprint unit | **Session** (1–3 days of focused work) | Solo/micro-team context — week-long sprints create false overhead |
| Velocity metric | **Issues closed per sprint** | Honest for a solo project; avoids story-point inflation |
| Definition of Done | Per [Testing Standard](../engineering-standards/testing-strategy): L0 lint ✅ · L1 unit tests ✅ · PR merged ✅ · ArgoCD Synced ✅ | |
| Retrospective cadence | End of each sprint session | Written in this document |
| Risk review cadence | Weekly (or when a risk materialises) | See [Risk Register & Retrospectives](retrospective-risk-register) |

---

## CERT-1 Sprint Plan

The CdCF delivery plan runs **M0 (Aug 2026) → Soutenance (Apr 2027)**. Each milestone below maps to a GitHub Milestone on `platform-backlog`.

| Milestone | Period | Focus | Issues |
|-----------|--------|-------|--------|
| **M0 — Architecture & Cadrage** | Aug 2026 | CdCF, architecture, governance | #195 + CERT-1 docs |
| **M1–M2 — Policy Service** | Sep–Oct 2026 | `ktayl-policy-service` Go | #203 |
| **M3–M5 — Claims Service** | Nov 2026–Jan 2027 | `ktayl-claims-service` Java + Spring Batch COREP | #198 |
| **M6 — AI Assistant** | Feb 2027 | `ktayl-ai-claims-assistant` Python / LangGraph | #200 |
| **M7 — Portal** | Mar 2027 | `ktayl-portal` Next.js 14, RGAA AA | #202 + #204 |
| **M8 — Integration & Tests** | Mar–Apr 2027 | E2E, UAT, all REC-* acceptance criteria | all |
| **Soutenance** | Apr 2027 | Oral presentation | — |

---

## Sprint History

### Sprint 0 — Architecture & Cadrage (M0)
**Dates:** 2026-08-13 · **Status:** ✅ Closed

| # | Deliverable | Issue | Status |
|---|-------------|-------|--------|
| 1 | Cahier des charges fonctionnel (CdCF v1.0) | #195 | ✅ Merged PR #92 |
| 2 | Architecture microservices (4 services, NATS, OIDC) | #195 | ✅ In CdCF §8 |
| 3 | Modèle de données logique (Contrats + Sinistres) | #195 | ✅ In CdCF §9 |
| 4 | Critères d'acceptation (8 scénarios REC-*) | #195 | ✅ In CdCF §13 |
| 5 | Gouvernance du projet — RACI (15 rôles, 6 phases) | #195 | ✅ Merged PR #97 |
| 6 | Standard gouvernance plateforme | — | ✅ Merged PR #97 |
| 7 | Sprint log & velocity (ce document) | — | ✅ This document |
| 8 | Registre des risques + rétrospectives | — | ✅ Merged same PR |

**Velocity Sprint 0:** 8 livrables · 3 PRs fusionnés · 0 items reportés

**Retrospective →** See [Sprint 0 Retrospective](retrospective-risk-register#sprint-0--architecture-et-cadrage)

---

### Platform Sprint — P1 Tooling (2026-08-07)
**Context:** Platform resilience — not a CERT-1 sprint, but demonstrates BC01 delivery rhythm.

| # | Deliverable | PR/Commit | Status |
|---|-------------|-----------|--------|
| 1 | minicloud-ops heartbeat (healthchecks.io UUID b2ac9ab5) | e4c016b | ✅ |
| 2 | RTO log (`/var/log/minicloud-rto.log`) | 15c2f53 | ✅ |
| 3 | swift-mac WoL auto-wake service | 0391ca7 | ✅ |
| 4 | Backup age check (check 15/15) + kine-backup trigger | 0391ca7 | ✅ |

**Velocity:** 4 items · 3 commits · 0 rollbacks

---

### Platform Sprint — P2 Reliability (2026-08-07)
**Context:** Platform reliability hardening — demonstrates BC04 maintenance evidence.

| # | Deliverable | PR | Status |
|---|-------------|----|--------|
| 1 | Longhorn replica auto-balance (`least-effort`) | #612 | ✅ |
| 2 | Velero off-site backup to Cloudflare R2 | #613 | ✅ |
| 3 | PriorityClasses (3 tiers, 11 workloads patched) | #614 + #616 + #617 + #619 + #620 | ✅ |

**Velocity:** 3 items · 7 PRs · 1 rollback (quota undersized → fixed PR #620)

---

### Platform Sprint — ERP-1 (2026-08-10)
**Context:** ERPNext French insurance configuration — demonstrates BC02 configuration capability.

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | French PCG 2025 (845 accounts) | ✅ |
| 2 | CRM pipeline (8 stages, 5 opportunity types) | ✅ |
| 3 | Tax templates (TVA + TSCA) | ✅ |
| 4 | LOB hierarchy (IARD + Vie & Prévoyance) | ✅ |
| 5 | 3 insurance products + test invoice | ✅ |
| 6 | Factur-X Minimum PoC (5 assertions) | ✅ |

**Velocity:** 6 items · Issue #50 → Done · 2 technical gotchas documented

---

### Platform Sprint — Infra Automation (2026-08-13)
**Context:** Infrastructure hardening — demonstrates BC04 operational maintenance.

| # | Deliverable | PR | Status |
|---|-------------|----|--------|
| 1 | cloudflared → k8s 2-replica HA Deployment | #678 + #679 | ✅ |
| 2 | SSH backup path (`controller.devandre.sbs → ssh://10.0.0.1:22`) | #680 | ✅ |
| 3 | MinIO disk-recovery auto-restart (minicloud-ops) | commit | ✅ |
| 4 | GRUB NVMe fix — all 4 ThinkPads (`GRUB_TIMEOUT=3`) | applied | ✅ |
| 5 | k3s upgrade v1.36.2 → v1.36.3+k3s1 (5 nodes) | #691 + #692 + #693 | ✅ |
| P4 | MAAS → dnsmasq | — | 🚫 Deferred — MAAS kept |

**Velocity:** 5 items delivered · 1 item deferred · 1 mid-sprint pivot (drain → cordon pattern)

---

## Velocity Summary

| Sprint | Period | Items delivered | Items deferred | Rollbacks |
|--------|--------|----------------|----------------|-----------|
| CERT-1 Sprint 0 (M0) | 2026-08-13 | 8 | 0 | 0 |
| Platform P1 Tooling | 2026-08-07 | 4 | 0 | 0 |
| Platform P2 Reliability | 2026-08-07 | 3 | 0 | 1 (quota fix) |
| ERP-1 | 2026-08-10 | 6 | 0 | 0 |
| Infra Automation | 2026-08-13 | 5 | 1 | 1 (empty PR #689) |
| **Total to date** | | **26** | **1** | **2** |

**Average velocity:** ~5 deliverables / sprint session. Deferred rate: 4%.

---

## Upcoming — Sprint 1 (M1–M2) Backlog

**Target:** September–October 2026 · **Focus:** `ktayl-policy-service` (Go 1.23)

| Priority | Item | Issue | Estimate |
|----------|------|-------|----------|
| P0 | Create `ktayl-policy-service` repo + Go module scaffold | #203 | 0.5 day |
| P0 | OpenAPI spec (policy CRUD endpoints) | #203 | 1 day |
| P0 | Domain model: Policy, Coverage, Premium, Document | #203 | 1 day |
| P1 | PostgreSQL schema + Flyway migrations | #203 | 0.5 day |
| P1 | NATS JetStream publisher (`policy.created`, `policy.amended`) | #203 | 1 day |
| P1 | L1 unit tests (≥70% coverage) | #203 | 1 day |
| P1 | CI pipeline (golangci-lint + go test + Harbor push) | #203 | 0.5 day |
| P1 | k8s manifests + ArgoCD Application | #203 | 0.5 day |
| P2 | L2 integration test (testcontainers PostgreSQL) | #203 | 0.5 day |
| P2 | Validate REC-POL-01 (policy creation acceptance test) | #203 | 0.5 day |

**Sprint 1 target velocity:** 10 items · REC-POL-01 validated
