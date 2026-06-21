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

Monitors `package.json`, `requirements.txt`, `go.mod`, and `pyproject.toml` for known CVEs. Opens automatic PRs to bump vulnerable dependencies to safe versions.

**High-priority dependency surfaces:**

| Repo | Package files | Critical packages to watch |
|---|---|---|
| `minicloud-ansible` | `requirements.txt` | `langfuse`, `ragas`, `qdrant-client`, `litellm`, `sentence-transformers` |
| `minicloud-backstage` | `package.json` | `@backstage/*`, `express`, `passport` |
| `ktayl-solution-web` | `package.json` | `astro`, `tailwindcss` |
| `platform-demo` | `go.mod` | `gin`, `prometheus/client_golang` |

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
