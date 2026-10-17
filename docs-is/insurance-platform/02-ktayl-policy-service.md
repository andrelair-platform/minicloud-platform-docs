---
id: ktayl-policy-service
title: ktayl Policy Service
sidebar_label: ktayl Policy Service
---

# ktayl Policy Service

Go microservice managing the **full lifecycle of insurance policies** — creation, activation, suspension, and termination — with associated coverages and premium tracking.

Part of **CERT-1** (CdCF §4 — Policy Management). Sprint S001–S002 complete.

**Full documentation:** [andrelair-platform.github.io/ktayl-policy-service](https://andrelair-platform.github.io/ktayl-policy-service/)

---

## Responsibility

| In scope | Out of scope |
|---|---|
| Policy lifecycle (draft → active → suspended → terminated) | Claims (ktayl-claims-service) |
| Coverage management (type, insured amount, deductible) | Premium billing / dunning (ERPNext) |
| Premium scheduling and payment tracking | Document generation (Paperless-ngx) |

## Stack

| | |
|---|---|
| Language | Go 1.25 |
| Router | chi v5 |
| Database | PostgreSQL — pgx/v5 + pgxpool |
| Container | `distroless/static-debian12:nonroot` |
| Registry | `harbor.10.0.0.200.nip.io/library/ktayl-policy-service` |

## Domain model (summary)

```
POLICE (1) ─── couvrir ──── (0,n) GARANTIE
POLICE (1) ─── appeler ──── (0,n) PRIME
```

All monetary values (insured amount, deductible, premium amount) are stored as **eurocents** (`int64`) to avoid floating-point errors.

→ [Full MCD / MLD / MPD](https://andrelair-platform.github.io/ktayl-policy-service/data-model/mcd)

## Sprint status

| Story | Status | Deliverable |
|---|---|---|
| S001 | ✅ Done | Go scaffold — chi router, `/healthz`, CI pipeline, distroless image |
| S002 | ✅ Done | Domain model, PostgreSQL repository, 17 unit tests, V1 migration |
| S003 | 🔨 Upcoming | REST API — CRUD on policies, coverages, premiums |
| S004 | 🔨 Upcoming | Auto-migration on startup |

## Links

- [Service documentation](https://andrelair-platform.github.io/ktayl-policy-service/)
- [GitHub repository](https://github.com/andrelair-platform/ktayl-policy-service)
- [Platform backlog #203](https://github.com/andrelair-platform/platform-backlog/issues/203)
