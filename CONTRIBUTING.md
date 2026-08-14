# Contributing

## Branch conventions

| Branch | Rules |
|---|---|
| `dev` | Direct push. CI runs tests + builds image tagged `dev-<sha>`. |
| `staging` | PR required. Image is cosign-signed. |
| `main` | PR required. GPG-signed commits. cosign + SBOM on image. |

## Commit style

Follow conventional commits: `type(scope): message`

Common types: `feat`, `fix`, `docs`, `chore`, `ci`, `refactor`, `test`

Examples:
```
feat(S003): add policy CRUD REST endpoints
fix(go): bump to 1.25.13 — patch GO-2026-6090
docs: update data model MLD diagram
```

## PR requirements

- All CI checks must pass before merge
- `staging → main` PRs require GPG-signed commits (key `FD6D39D681DEFA34`)
- No `Co-Authored-By` lines — commits represent the portfolio owner's work

## Running tests locally

```bash
make test       # unit tests + race detector (< 5 min, no Docker needed)
make test-cov   # with coverage report
make vuln       # govulncheck
make sec        # gosec
```
