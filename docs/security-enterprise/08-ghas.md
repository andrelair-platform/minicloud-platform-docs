---
id: ghas
title: GitHub Advanced Security (GHAS)
sidebar_position: 8
---

# GitHub Advanced Security (GHAS)

GHAS is the application security layer for the `andrelair-platform` GitHub organisation. It covers static code analysis, dependency vulnerability scanning, and secret leak prevention — all native to GitHub, zero additional tooling required.

---

## Why GHAS for This Stack

| Factor | Why it fits |
|---|---|
| Already on GitHub | CodeQL, Dependabot, and Secret Scanning are org-level toggles — no new platform to onboard |
| Language coverage | All repos use Go, Python, TypeScript/JavaScript — all in CodeQL's 12 supported languages |
| No legacy code | Veracode's 100+ language advantage covers COBOL and VB6 — irrelevant here |
| GHA already in use | CodeQL runs as a GitHub Actions workflow step alongside existing CI quality gates |
| Secret risk documented | CLAUDE.md explicitly prohibits committing controller admin passwords — push protection enforces this at the git layer |
| DAST gap acceptable | Runtime monitoring via Grafana/Alertmanager + AI-specific hooks (issues #44–#49) cover the runtime attack surface |

---

## Three Components

### 1. CodeQL — Static Application Security Testing (SAST)

Treats source code as a relational database and runs semantic queries against it. Tracks tainted user input through data-flow graphs to detect injection flaws, insecure deserialisation, path traversal, and other CWE-listed vulnerabilities.

**What it scans in this platform:**

| Repo | Language | Key risks scanned |
|---|---|---|
| `platform-demo` | Go | SQL injection, SSRF, path traversal, command injection |
| `minicloud-backstage` | TypeScript | XSS, prototype pollution, insecure `eval` |
| `ktayl-solution-web` | TypeScript (Astro) | XSS, open redirect |
| `minicloud-ansible` | Python | Shell injection in Ansible task `shell:` modules |
| `minicloud-platform-docs` | TypeScript | Dependency vulnerabilities (Docusaurus plugins) |

### 2. Dependabot — Software Composition Analysis (SCA)

Monitors `package.json`, `requirements.txt`, `go.mod`, and `pyproject.toml` for known CVEs. Opens automatic pull requests to bump vulnerable dependencies to patched versions. Also monitors `.github/workflows/*.yml` files to keep GitHub Actions at current versions.

**High-priority dependency surfaces:**

| Repo | Package files | Critical packages to watch |
|---|---|---|
| `minicloud-backstage` | `package.json` | `@backstage/*`, `express`, `passport` |
| `ktayl-solution-web` | `package.json` | `astro`, `tailwindcss` |
| `platform-demo` | `go.mod` | `gin`, `prometheus/client_golang` |
| `minicloud-gitops` | `.github/workflows/*.yml` | `actions/*`, `tailscale/github-action` |

---

## Dependabot Configuration Reference

### Which repos have Dependabot enabled

Dependabot is enabled at the org level for security alerts on all repos. The `.github/dependabot.yml` config file (which controls automated PRs) is deployed only to repos that have the relevant package files:

| Repo | `dependabot.yml` | Ecosystems monitored |
|---|---|---|
| `minicloud-gitops` | ✅ | `github-actions` |
| `ktayl-solution-web` | ✅ | `npm`, `github-actions` |
| `platform-demo` | ✅ | `gomod`, `github-actions` |
| `minicloud-backstage` | ✅ | `npm`, `github-actions` |
| `minicloud-rag-ingest` | ✅ | `pip`, `github-actions` |
| `minicloud-markitdown-proxy` | ✅ | `pip`, `github-actions` |
| `minicloud-open-webui` | ✅ | `docker`, `github-actions` |
| `minicloud-onlyoffice` | ✅ | `docker`, `github-actions` |
| `minicloud-plane` | ✅ | `gomod`, `github-actions` |
| `minicloud-ansible` | ❌ removed | Had no `.github/workflows/` — caused weekly failures |
| `minicloud-opentofu` | ❌ not applicable | No package manager files tracked |

**Why `minicloud-ansible` has no `dependabot.yml`:** The original config declared `package-ecosystem: github-actions` but the repo has no CI workflows. Dependabot failed every week with `dependency_file_not_found`. The config was removed (commit `70efb61`). If a CI workflow is ever added to this repo, re-add the `github-actions` ecosystem entry.

### Standard `dependabot.yml` for CI repos

```yaml
version: 2
updates:
  # Keep GitHub Actions current
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 3
    labels:
      - dependencies
      - github-actions
```

For repos with application dependencies, add the relevant ecosystem block below the `github-actions` block:

```yaml
  # npm (Backstage, Astro)
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 5
    groups:
      patch-updates:
        update-types:
          - patch

  # Go modules
  - package-ecosystem: gomod
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 5

  # Python (pip)
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 5
    groups:
      ai-stack:
        patterns:
          - "langfuse*"
          - "ragas*"
          - "litellm*"
```

---

## Dependabot PR Review Policy

Not every Dependabot PR is safe to merge automatically. The policy below defines what level of review is required by version bump type.

### Decision rules

| Bump type | Example | Policy | Rationale |
|---|---|---|---|
| **Patch** (`x.y.Z`) | `tailwindcss` 4.3.1 → 4.3.2 | Merge after CI passes | Bug fixes and security patches only — no API changes permitted by semver |
| **Minor** (`x.Y.0`) | `fastapi` 0.115.0 → 0.116.0 | Read changelog, merge if no breaking notes | New features; backwards-compatible by semver but real-world projects sometimes slip |
| **Major** (`X.0.0`) | `astro` 6.x → 7.0.0 | **Hold** — test build locally first | API changes expected; migration guide required before merging |
| **GitHub Actions** (major) | `actions/github-script` v7 → v9 | Read release notes for breaking changes, then merge | Check if any deprecated API (e.g. `require('@actions/github')`) is used in the workflow |

### Quick reference — packages requiring extra caution

| Package | Why extra caution |
|---|---|
| `astro` (major) | Config API and routing changes between major versions; must run `npm run build` locally |
| `@backstage/*` (major) | Backstage's plugin API changes frequently across major versions; test in staging first |
| `actions/github-script` | v9 is ESM-only — `require('@actions/github')` no longer works; audit workflow scripts before merging |
| `tailscale/github-action` | Auth method changes can break all CI pipelines simultaneously |

### Checking if a GitHub Actions bump is safe

Before merging any `actions/*` major version bump, audit the workflow file:

```bash
# Find all uses of the action in the repo
grep -r "github-script" .github/workflows/

# Check the PR description — Dependabot includes a release notes summary
gh pr view <N> --repo andrelair-platform/<repo> --json body --jq '.body'
```

For `actions/github-script` specifically: the v9 breaking changes are:
- `require('@actions/github')` fails at runtime (ESM-only) — if not used in the script, the PR is safe
- `const getOctokit = ...` redeclaration throws `SyntaxError` — check if the script declares this variable

---

## Operational Workflow

### Reviewing open Dependabot PRs

```bash
# All open Dependabot PRs across the org
gh search prs --owner andrelair-platform --author app/dependabot --state open \
  --json repository,title,url --jq '.[] | "\(.repository.nameWithOwner) | \(.title) | \(.url)"'

# PRs in a specific repo
gh pr list --repo andrelair-platform/ktayl-solution-web \
  --author app/dependabot --json number,title,mergeable
```

### Merging a safe patch PR

```bash
gh pr merge <N> --repo andrelair-platform/<repo> --merge
```

### Handling conflicts between simultaneous Dependabot PRs

When two Dependabot PRs both modify `package.json` and `package-lock.json`, one will conflict after the other is merged. Tell Dependabot to rebase:

```bash
gh pr comment <N> --repo andrelair-platform/<repo> --body "@dependabot rebase"
```

Dependabot processes the comment within a few minutes and force-pushes an updated branch. Poll until the conflict clears, then merge:

```bash
gh pr view <N> --repo andrelair-platform/<repo> --json mergeable --jq '.mergeable'
# MERGEABLE → safe to merge
```

### Checking open vulnerability alerts

```bash
# All unfixed Dependabot security alerts across the org
gh api /orgs/andrelair-platform/dependabot/alerts \
  --jq '.[] | select(.state=="open") | {
    repo: .repository.name,
    pkg: .dependency.package.name,
    severity: .security_advisory.severity,
    title: .security_advisory.summary
  }'
```

### Dismissing a false positive

If Dependabot flags a vulnerability that doesn't affect this platform (e.g. a CVE in a feature not used):

```bash
gh api --method PATCH \
  /repos/andrelair-platform/<repo>/dependabot/alerts/<alert-id> \
  -f state=dismissed \
  -f dismissed_reason=not_used \
  -f dismissed_comment="This code path is not reachable in our deployment"
```

---

## Dependabot vs Renovate — Two-Bot Architecture

This platform uses **two automated dependency update bots** that operate on different layers. They do not overlap.

| | Dependabot | Renovate |
|---|---|---|
| **What it watches** | Application code dependencies (`package.json`, `go.mod`, `pip`, `docker`), GitHub Actions | Helm chart versions in `apps/*.yaml`, image tags in `helm-values/*.yaml` |
| **Where it runs** | All custom code repos (`minicloud-backstage`, `platform-demo`, etc.) | `minicloud-gitops` only |
| **PR frequency** | Weekly (Monday 06:00 UTC) | Weekly (weekends) |
| **What a PR looks like** | `chore(deps): bump fastapi from 0.115.0 to 0.116.0` | `chore(deps): bump grafana from 8.12.0 to 8.13.0` |
| **Who merges** | Human, following the policy above | Human, after reading Renovate's embedded changelog |
| **Security PRs** | Immediate — security updates bypass the schedule | N/A — Renovate covers versions, not CVEs |

**Rule of thumb:** if the update is in a `.github/workflows/` file, `package.json`, `go.mod`, or `requirements.txt` → it's a Dependabot PR. If it's in `apps/*.yaml` or `helm-values/*.yaml` → it's a Renovate PR.

---

## Known Gotchas

### `github-actions` ecosystem requires `.github/workflows/` to exist

Declaring `package-ecosystem: github-actions` in `dependabot.yml` causes a weekly `dependency_file_not_found` failure if the repo has no `.github/workflows/` directory. Do not add the `github-actions` ecosystem to repos without CI workflows.

**Affected repo:** `minicloud-ansible` — config deleted (commit `70efb61`, 2026-07-16).

### Two concurrent npm PRs always conflict

When Dependabot opens two PRs that both touch `package.json` (e.g. bumping `tailwindcss` and `@tailwindcss/vite` in the same week), the second one will show `CONFLICTING` after the first merges. This is expected — use `@dependabot rebase` to resolve. Consider using `groups:` in `dependabot.yml` to bundle related npm packages into a single PR:

```yaml
groups:
  tailwind:
    patterns:
      - "tailwindcss"
      - "@tailwindcss/*"
```

### Major version PRs sit open indefinitely without action

Dependabot does not close stale PRs. A `astro` 6→7 PR will remain open until manually merged or closed. Set a calendar reminder to revisit major version PRs after the upstream project's migration guide is published (typically 2–4 weeks after the major release).

### 3. Secret Scanning + Push Protection

Detects API keys, tokens, and passwords in commits and blocks pushes containing known secret patterns before they reach the remote. Covers 200+ token patterns including: GitHub PATs, AWS credentials, Cloudflare tokens, Docker Hub tokens, and generic high-entropy strings.

**Relevant to this platform:** the CLAUDE.md explicitly documents secrets that must never be committed (`~/.argocd-admin`, `~/.grafana-admin`, `~/.harbor-admin`, `~/.minio-admin`, `~/.authentik-api-token`, `~/.backstage-postgres`). Push protection is the automated enforcement of that rule.

---

## Setup

### Step 1 — Enable org-level settings

In the GitHub org (`andrelair-platform`) → Settings → Security & analysis:

```
✅ Dependency graph             — on (free, always available)
✅ Dependabot alerts            — on
✅ Dependabot security updates  — on (auto-PRs for vulnerable deps)
✅ Secret scanning              — on
✅ Push protection              — on  ← blocks the push, not just alerts
✅ CodeQL default setup         — on (or use custom workflow below)
```

### Step 2 — Add CodeQL workflow to each repo

Create `.github/workflows/codeql.yml` in each repo. Pick the correct language matrix per repo:

**`platform-demo` (Go):**

```yaml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'       # weekly Monday 02:00 UTC — catches new CVEs on unchanged code
jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      matrix:
        language: [go]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended    # broader ruleset than default
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
        with:
          category: /language:${{ matrix.language }}
```

**`minicloud-ansible` (Python — AI hooks and evaluation scripts):**

```yaml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'
jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      matrix:
        language: [python]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended
      - uses: github/codeql-action/analyze@v3
        with:
          category: /language:${{ matrix.language }}
```

**`minicloud-backstage` and `ktayl-solution-web` (TypeScript):**

```yaml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'
jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      matrix:
        language: [javascript-typescript]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended
      - uses: github/codeql-action/analyze@v3
        with:
          category: /language:${{ matrix.language }}
```

### Step 3 — Add Dependabot config to each repo

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  # Python dependencies (AI hooks, evaluation scripts)
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 5
    groups:
      ai-stack:
        patterns:
          - "langfuse*"
          - "ragas*"
          - "litellm*"
          - "qdrant*"
          - "sentence-transformers*"
          - "transformers*"

  # Node dependencies (Backstage, Docusaurus, Astro)
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 5

  # Go dependencies (platform-demo)
  - package-ecosystem: gomod
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
    open-pull-requests-limit: 5

  # GitHub Actions themselves
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

---

## Integration with Existing CI

GHAS runs alongside — not instead of — the existing quality gates. In `minicloud-ansible` for example, a PR touches AI hook code and triggers:

```
PR opened
  ├── CodeQL analyze (Python)           ← GHAS: code vulnerabilities
  ├── ragas-quality-gate                ← issue #39: RAG evaluation
  ├── bias-counterfactual-gate          ← issue #45: fairness check
  └── CodeQL results → Security tab     ← findings visible in PR review
```

CodeQL findings appear as PR comments and in the repository Security tab → Code scanning alerts. They do not block merges by default — configure branch protection rules to require CodeQL to pass if desired:

```
Repository → Settings → Branches → main → Require status checks:
  ✅ CodeQL / Analyze (python)
  ✅ CodeQL / Analyze (go)
```

---

## What GHAS Covers vs AI-Specific Hooks

GHAS and the AI security hooks (issues #44–#49) address different layers:

| Concern | GHAS | AI hooks (#44–#49) |
|---|---|---|
| SQL/command injection in Go service code | ✅ CodeQL | — |
| XSS in Backstage frontend | ✅ CodeQL | — |
| Vulnerable `langfuse` version | ✅ Dependabot | — |
| Authentik API token committed to git | ✅ Secret scanning | — |
| Model hallucinating a wrong policy amount | — | ✅ Retrieval gate + citation check |
| Demographic bias in claims responses | — | ✅ Counterfactual gate + neutrality judge |
| Prompt injection via Open WebUI | — | ✅ PromptGuard + regex hook |
| Poisoned document in Qdrant | — | ✅ Provenance + integrity scan |
| Specific claim file existence probed | — | ✅ Identifier stripping + neutral error |

GHAS secures the **application code and its dependencies**. The AI hooks secure the **AI runtime behaviour**. Both layers are necessary; neither replaces the other.

---

## Operational Checks

```bash
# View open Dependabot alerts across all repos
gh api /orgs/andrelair-platform/dependabot/alerts \
  --jq '.[] | select(.state=="open") | {repo: .repository.name, pkg: .dependency.package.name, severity: .security_advisory.severity}'

# View open code scanning alerts
gh api /repos/andrelair-platform/platform-demo/code-scanning/alerts \
  --jq '.[] | select(.state=="open") | {rule: .rule.id, severity: .rule.severity, file: .most_recent_instance.location.path}'

# Check secret scanning alerts (should always be 0)
gh api /orgs/andrelair-platform/secret-scanning/alerts \
  --jq '.[] | select(.state=="open") | {repo: .repository.name, type: .secret_type}'

# List Dependabot PRs waiting for review
gh pr list --repo andrelair-platform/minicloud-ansible \
  --author app/dependabot --json title,createdAt,url
```

---

## Known Limitations

| Gap | Notes |
|---|---|
| No DAST | GHAS has no runtime scanner. Runtime coverage comes from Grafana + AI hooks. |
| No IaC scanning natively | CodeQL does not scan Helm charts or OpenTofu `.tf` files for misconfigurations. Add `kics` or `checkov` as a separate GHA step for IaC. |
| No container image scanning | CodeQL scans source, not built images. Harbor's Trivy integration (Phase 7) covers container CVEs. |
| PHP / legacy languages | Not applicable to this stack today. |
