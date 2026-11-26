---
id: run-locally
title: Run & test your app locally
sidebar_label: Run & test locally
tags: [how-to]
---

# Run & test your app locally

> **How-to.** You do **not** need the cluster to develop. Run and test on your laptop first — the cluster
> is for *dev/prod*, not your inner loop.

## The inner loop

```bash
# 1. Build the image your CI will build
docker build -t myapp:dev .

# 2. Run the app + its dependencies locally
docker compose up          # the reference services ship a compose file for this

# 3. Run the tests (fast, no cluster)
make test                  # L0 (lint/format/types) + L1 (unit) — < 5 min
make test-integration      # L2 — real DB/queue via Docker Compose (testcontainers)
```

If your reference service has no `docker-compose.yml` yet, the minimum is: the app + a Postgres
(`postgres:16`) + any queue it needs. Copy the compose file from the closest
[reference service](/platform/getting-started/day-1-setup#4-pick-your-stack--clone-a-reference-service).

## The test commands per stack

| Stack | Lint + unit (L0–L1) | Integration (L2) |
|---|---|---|
| **Python / FastAPI** | `ruff check . && mypy . && pytest` | `pytest tests/integration` (testcontainers) |
| **Go** | `golangci-lint run && go test ./...` | `go test -tags=integration ./...` |
| **Java / Spring** | `./mvnw verify` | `./mvnw verify -Pintegration` (Testcontainers) |
| **TypeScript / NestJS** | `npm run lint && npm test` | `npm run test:integration` (MSW / testcontainers) |

> The authoritative per-language matrix + what each layer catches is the
> [Testing strategy (L0–L4)](/platform/engineering-standards/testing-strategy). The rule: **a Tier-A
> service is not Done on unit tests alone** — run L2/L3 locally before you push.

## Why not just deploy to dev to test?

Because the inner loop must be **seconds, not a deploy**. Deploying to dev is for the **L5 QA gate**
(adversarial testing against the live service before prod) — not for "does my function work?". Keep those
separate: **unit/integration local → push → CI → dev → QA gate → prod.**

## Related

- [Testing strategy (L0–L4)](/platform/engineering-standards/testing-strategy)
- [New business service — zero → prod](/platform/app-deployment/new-business-service)
- [Getting Started (A→Z)](/platform/getting-started)
