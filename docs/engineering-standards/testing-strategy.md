---
id: testing-strategy
title: Org-Wide Testing Strategy
sidebar_label: Testing Strategy
---

# Org-Wide Testing Strategy

## Principle

One standard, applied consistently across all repositories. The depth scales with the repo's **risk**, not the language. Every repo must pass the same CI gate structure before anything reaches `staging` or `main`.

> Tests are not optional — they are a first-class deliverable on the same level as the feature code.

---

## The 5 Layers

| Layer | What it checks | Speed | When it runs |
|---|---|---|---|
| **L0 — Static** | Lint, format, types, YAML schema | < 1 min | Every push, every branch |
| **L1 — Unit** | Pure logic, no external deps, mocks everything | < 5 min | Every push |
| **L2 — Integration** | Real DB, real queue, mocked HTTP | < 15 min | PR to `staging` |
| **L3 — Contract** | API shape matches what consumers expect | < 5 min | PR to `staging` |
| **L4 — E2E / Smoke** | Full happy path on real infra | < 10 min | PR to `main` |

---

## CI Gate Mapping

This maps directly onto the existing branch strategy (`dev` → `staging` → `main`).

```
dev push          →  L0 + L1              (~5 min, fast feedback)
PR → staging      →  L0 + L1 + L2 + L3   (~20 min, blocking)
PR → main         →  L0 + L1 + L2 + L3 + L4  (full suite + SBOM/cosign)
```

**Fail-fast rule:** L0 always runs before L1, L1 before L2. No point spinning up a database if linting fails.

---

## Language Matrix

| Stack | L0 | L1 | L2 | L3 | L4 |
|---|---|---|---|---|---|
| **Python (Frappe)** | ruff + mypy | pytest | bench run-tests + httpx | schemathesis | kubectl exec + httpx |
| **Python (scripts)** | ruff + mypy | pytest | pytest + testcontainers | — | manual |
| **Go** | golangci-lint | go test ./... | go test + testcontainers | openapi-validator | httpx / curl |
| **TypeScript** | eslint + tsc | vitest | vitest + MSW | — | Playwright |
| **YAML / Helm** | yamllint + kubeconform | helm lint | helm template + kube-score | — | ArgoCD diff |
| **HCL (OpenTofu)** | tofu fmt + validate | — | tofu plan (dry-run) | — | manual |
| **Ansible** | ansible-lint | molecule test | molecule converge | — | manual |

---

## Mandatory Conventions (every repo)

### Directory layout

```
tests/
  unit/         # L1 — pure logic, no external deps
  integration/  # L2 — real DB / queue, Docker Compose or testcontainers
  e2e/          # L4 — smoke tests against real cluster
  fixtures/     # shared test data, factory functions
```

### Rules

1. **`make test`** runs L1 locally — no Docker, no network, <5 min
2. **`make test-integration`** runs L2 with Docker Compose
3. **Coverage threshold: 70%** on business logic files (excludes config, glue, `__init__.py`)
4. Every new public function or API endpoint → at least one happy-path test + one failure case
5. No `# noqa` / `// nolint` without an inline comment explaining the exception
6. Test file names mirror the module they test: `dsn_generator.py` → `test_dsn_generator.py`
7. Fixtures live in `tests/fixtures/` — never inline large data blobs in test functions

---

## Repo Classification

Not all repos carry the same risk. Required test layers scale accordingly:

| Tier | Repos | Required layers |
|---|---|---|
| **A — Business logic** | `minicloud-erpnext`, `minicloud-plane`, `platform-demo` | L0 → L4 (full) |
| **B — Infrastructure code** | `minicloud-gitops`, `minicloud-opentofu`, `minicloud-ansible` | L0, L2 (plan/dry-run), L4 (ArgoCD diff) |
| **C — UI / docs** | `minicloud-backstage`, `ktayl-solution-web`, `minicloud-platform-docs` | L0, L1, L4 (Playwright) |
| **D — Tooling / ops** | `minicloud-ops`, `minicloud-open-webui`, `minicloud-onlyoffice` | L0, L1 |

---

## Rollout Plan

| Week | Repo | Tier | First deliverable |
|---|---|---|---|
| 1 | `minicloud-erpnext` | A | L0 + L1: ruff/mypy + pytest for DSN generator, CRM parser, Factur-X |
| 2 | `platform-demo` | A | L0 + L1: golangci-lint + go test (already has CI structure) |
| 3 | `minicloud-plane` | A | L0 + L1: golangci-lint + go test for webhook/NATS logic |
| 4 | `minicloud-gitops` | B | L0: yamllint + kubeconform + helm lint on every PR |
| 5+ | remaining repos | C/D | L0 + L1 in parallel |

---

## Reference: minicloud-erpnext

The first implementation. Serves as the template for all Tier A Python repos.

### Test file map

```
tests/
  conftest.py              # mock frappe module for unit tests (no bench needed)
  fixtures/
    employees.py           # standard + edge-case employee dicts
    crm_responses.py       # ACCEPTE, REJETE, SOAP fault, empty — as strings
  unit/
    test_dsn_generator.py  # build_dsn(): CRLF, UTF-8, S10/S20/S90 blocks
    test_dsn_submitter.py  # _response_is_ok(): 8 CRM XML scenarios
    test_api_helpers.py    # _contract_type_code(), _collect_warnings()
    test_facturx.py        # _build_cii_xml(): CII XML structure assertions
  integration/             # L2 — bench run-tests (future)
  e2e/                     # L4 — kubectl exec smoke test (future)
```

### CI jobs

```yaml
# .github/workflows/test.yml
jobs:
  lint:       # ruff check + ruff format --check + mypy  (every push)
  test-unit:  # pytest tests/unit/ --cov --cov-fail-under=70  (every push, needs: lint)
```

### Running locally

```bash
# Install test deps (once)
pip install -r requirements-test.txt

# L0 — lint + type check
make lint

# L1 — unit tests with coverage
make test-cov

# Auto-fix formatting
make fmt
```

---

## Why This Approach

**No Frappe in unit tests.** The bench/frappe runtime is only available inside the ERPNext Docker image. Unit tests mock the `frappe` module via `sys.modules` so they run in any Python 3.11 environment — CI, local, GitHub Actions — without a running site.

**Coverage on business logic only.** Frappe hooks, `__init__.py` files, and setup scripts are excluded. The 70% threshold applies to the files that actually contain business logic (`dsn_generator.py`, `dsn_submitter.py`, `facturx.py`, etc.).

**Tests document behaviour.** Test names use the form `test_<what>_<condition>` (e.g. `test_response_is_ok_rejete_returns_false`) so the test suite doubles as executable specification of what each function must do.
