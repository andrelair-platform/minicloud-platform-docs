---
id: techdocs
title: Phase 71 — TechDocs
sidebar_label: Phase 71 — TechDocs
---

# Phase 71 — TechDocs

TechDocs is Backstage's built-in documentation system. It turns any `mkdocs.yml` in a repo into a rendered, searchable documentation site that lives inside the Backstage portal — no separate Confluence or Wiki needed.

---

## What Was Deployed

| Component | Change |
|---|---|
| `packages/app/src/App.tsx` | Added `techdocsPlugin` from `@backstage/plugin-techdocs/alpha` |
| `packages/backend/Dockerfile` | Added `python3-pip` + `pip3 install mkdocs-techdocs-core==1.4.0` |
| `backstage-values.yaml` | Added `techdocs.builder: 'local'` config |
| `minicloud-backstage/mkdocs.yml` | TechDocs site for Backstage itself |
| `minicloud-backstage/docs/` | Overview, Architecture, CI/CD, Plugins pages |
| `go-service` skeleton | `mkdocs.yml` + `docs/` (index, api, runbook) scaffolded per service |
| `custom-image` skeleton | `mkdocs.yml` + `docs/` (index, build) scaffolded per image |

---

## Architecture — Local Builder

```
User opens TechDocs page in Backstage
          │
          ▼
  Backstage backend (plugin-techdocs-backend)
          │
          ├─ Clone repo via GitHub integration
          │
          ├─ Run mkdocs build (local subprocess in the pod)
          │    requires: mkdocs-techdocs-core installed in the container
          │
          └─ Serve rendered HTML directly from pod filesystem
               (ephemeral — rebuilt on next access if not cached)
```

**Builder mode: `local`** — mkdocs runs as a subprocess inside the Backstage pod. No external CI step, no object storage needed. Simpler than the external builder; suitable for a sub-20-service catalog.

**Publisher mode: `local`** — rendered HTML stored in the pod's ephemeral filesystem (`/tmp/backstage/techdocs`). Lost on pod restart, rebuilt on next access. Acceptable for a homelab-scale platform where regen takes ~2 seconds.

:::info Upgrade path to MinIO
When the catalog grows beyond ~50 services, switch to `builder: 'external'` + `publisher.type: 'awsS3'` pointing at MinIO (`http://10.0.0.1:9000`, bucket `techdocs`). Each repo's CI adds a `@techdocs/cli publish` step. The MinIO root user is `admin`; the password is in Vault at `secret/platform/minio`.
:::

---

## Configuration (backstage-values.yaml)

```yaml
appConfig:
  techdocs:
    builder: 'local'
    generator:
      runIn: 'local'
    publisher:
      type: 'local'
```

---

## Dockerfile Change

The `node:24-trixie-slim` base image has Python 3 pre-installed but not pip. Two additions:

```dockerfile
# In the first apt-get layer:
apt-get install -y --no-install-recommends python3 python3-pip g++ build-essential

# New layer after apt installs:
RUN pip3 install mkdocs-techdocs-core==1.4.0 --break-system-packages
```

`mkdocs-techdocs-core` is a Backstage meta-package that bundles mkdocs-material, the search plugin, and the Backstage TechDocs theme in a single install.

---

## Enabling TechDocs for a Component

Any component can get TechDocs with two additions:

**1. `catalog-info.yaml` annotation:**
```yaml
metadata:
  annotations:
    backstage.io/techdocs-ref: dir:.
```

**2. `mkdocs.yml` at the repo root:**
```yaml
site_name: my-service
site_description: One-line description

docs_dir: docs
nav:
  - Overview: index.md
  - Runbook: runbook.md

plugins:
  - techdocs-core
```

Then create `docs/index.md` (and any other pages listed in `nav:`).

---

## What Every New Service Gets

Both scaffold templates (`go-service` and `custom-image`) now include a ready-to-go TechDocs setup:

**go-service skeleton:**
```
mkdocs.yml
docs/
  index.md    ← Overview + deployment table + secrets reference
  api.md      ← GET /healthz + GET /readyz documentation
  runbook.md  ← kubectl one-liners, Vault secret rotation, rollback steps
```

**custom-image skeleton:**
```
mkdocs.yml
docs/
  index.md    ← Overview + image registry info
  build.md    ← CA cert injection, CI pipeline, local build steps
```

All pages use `${{ values.name }}` and `${{ values.description }}` substitution — they're pre-filled with real content, not placeholder text.

---

## Gotcha — `{% raw %}` in mkdocs.yml skeleton

The scaffold template renders `mkdocs.yml` through Nunjucks. The `${{ values.name }}` substitution works because Nunjucks sees `${{ }}` as a template expression.

If you ever need literal `${{ }}` in a TechDocs page (e.g., to document GHA syntax), use Nunjucks escaping:
```
{{ '{{' }}  becomes  {{
```
Or wrap the whole file in `{% raw %}...{% endraw %}` in the skeleton if the file has no Nunjucks substitutions.

---

## Gotcha — `catalog-info.yaml` already present in minicloud-backstage

The `minicloud-backstage/catalog-info.yaml` already had `backstage.io/techdocs-ref: dir:.` from Phase 70 catalog hardening. Adding `mkdocs.yml` and `docs/` was all that was needed to activate TechDocs for it.
