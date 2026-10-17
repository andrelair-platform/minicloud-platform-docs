---
id: plane-ce
title: Phase 68 — Plane CE (Project Tracker)
sidebar_label: Phase 68 — Plane CE
---

# Phase 68 — Plane CE v1.3.1 — Project Tracker

Plane CE is the open-source project management tool deployed in the `plane` namespace. It provides Kanban boards, issue tracking, and a full REST API consumed by the Phase 69 minicloud-plane integration service.

---

## Why Plane

| Criterion | Plane CE | Linear | GitHub Projects | Jira |
|---|---|---|---|---|
| Self-hosted | ✅ | ❌ | ❌ | ❌ (Data Center only) |
| REST API | ✅ Full | ✅ Full | Limited | ✅ Full |
| Webhook support | ✅ HMAC-signed | ✅ | ✅ | ✅ |
| OIDC (Authentik) | ❌ Pro only | ❌ | ❌ | ✅ |
| Homelab resource fit | ~1 GiB RAM | N/A | N/A | ~8 GiB RAM |
| Portfolio demonstrability | Visible via API | Vendor-locked | Vendor-locked | Vendor-locked |

The critical limitation: **OIDC is Plane Pro only**. Plane CE supports Google, GitHub, GitLab, and Gitea OAuth but not a generic OIDC provider like Authentik. Authentication is email + password with TOTP optional. An Authentik OIDC provider (pk=13) exists as a placeholder for a future Plane Pro upgrade.

---

## Architecture

```
plane namespace
├── plane-web         (Next.js frontend — SSR)
├── plane-space       (public board view)
├── plane-admin       (admin panel)
├── plane-api         (Django REST API — plane.api module, /api/v1/)
├── plane-worker      (Celery background tasks — webhooks, emails)
├── plane-beat        (Celery beat scheduler)
├── plane-live        (WebSocket live collaboration)
├── plane-postgres    (StatefulSet, 5 GiB Longhorn PVC)
├── plane-redis       (StatefulSet, 500 MiB Longhorn PVC)
├── plane-rabbitmq    (StatefulSet, 500 MiB Longhorn PVC — task queue)
└── plane-minio       (StatefulSet, 10 GiB Longhorn PVC — file uploads)
```

**Ingress:** `https://plane.devandre.sbs` (Cloudflare Tunnel, public) and `https://plane.10.0.0.200.nip.io` (internal).

**Secrets:** All secrets (Postgres password, Redis URL, RabbitMQ credentials, MinIO keys, SECRET_KEY) sourced from Vault via External Secrets Operator → `plane-app-secrets`, `plane-pgdb-secrets`, etc.

---

## Key Gotcha — Plane Has Two Django Modules

This is the most important architectural detail for API consumers:

| Module | URL prefix | Auth header | Auth value |
|---|---|---|---|
| `plane.app` | `/api/` | `Authorization` | `Bearer <session-token>` (browser) |
| `plane.api` | `/api/v1/` | `X-Api-Key` | `<api-token>` |

Everything reachable via API key (the standard integration path) is under `/api/v1/`. Using `/api/` with an API key returns 401 or 403. Using `X-Api-Token` (a common guess) also returns 401 — the header is `X-Api-Key`.

Source: `/code/plane/app/middleware/api_authentication.py`, `auth_header_name = "X-Api-Key"`.

---

## Workspace Bootstrap — Critical

**Plane CE does not auto-create a workspace.** The onboarding flow (workspace name, invite, plan selection) must be completed in the browser at first login, OR via the Django shell. The API returns 403 on all workspace endpoints until a `Workspace` row and corresponding `WorkspaceMember` row exist in the database.

If onboarding was skipped (common in automated setups), bootstrap via Django shell:

```bash
# On any plane-api pod
kubectl exec -n plane -it deploy/plane-api -- python manage.py shell
```

```python
from plane.db.models import Workspace, WorkspaceMember, User

owner = User.objects.get(email="your@email.com")
ws = Workspace.objects.create(
    name="andrelair",
    slug="andrelair",
    owner=owner,
)
WorkspaceMember.objects.create(
    workspace=ws,
    member=owner,
    role=20,   # 20 = Admin
)
print(ws.id)  # save this UUID
```

---

## API Token Creation

API tokens (for the `X-Api-Key` header) are not exposed in the CE web UI. Create them via Django shell:

```bash
kubectl exec -n plane -it deploy/plane-api -- python manage.py shell
```

```python
from plane.db.models import APIToken, User, Workspace

user = User.objects.get(email="your@email.com")
ws = Workspace.objects.first()

token = APIToken.objects.create(
    user=user,
    workspace=ws,
    label="minicloud-plane-integration",
    is_service=True,
)
print(token.token)
```

Store the token in Vault: `vault kv put secret/platform/minicloud-plane PLANE_TOKEN=<token>`.

---

## SSRF Protection — WEBHOOK_ALLOWED_HOSTS

Plane CE's `validate_url()` function blocks webhook delivery to private IPs (RFC1918) and internal cluster hostnames. This is intentional SSRF protection but breaks delivery to internal services.

The escape hatch is the `WEBHOOK_ALLOWED_HOSTS` environment variable — a comma-separated list of hostnames that bypass IP validation.

```yaml
# helm-values/plane-values.yaml
env:
  webhook_allowed_hosts: "minicloud-plane.minicloud-plane-dev.svc.cluster.local"
```

The Plane Helm chart maps snake_case env keys → `UPPER_SNAKE_CASE` environment variables. After updating `helm-values/plane-values.yaml`, ArgoCD syncs and the worker pods pick up the new env.

Source: `/code/plane/utils/ip_address.py`.

---

## Helm Values (minicloud-gitops)

```yaml
# helm-values/plane-values.yaml
planeVersion: "v1.3.1"

ingress:
  enabled: true
  appHost: "plane.devandre.sbs"

env:
  cors_allowed_origins: "https://plane.devandre.sbs,https://plane.10.0.0.200.nip.io"
  webhook_allowed_hosts: "minicloud-plane.minicloud-plane-dev.svc.cluster.local"

# All secrets from Vault via ESO
external_secrets:
  app_env_existingSecret: "plane-app-secrets"
  pgdb_existingSecret: "plane-pgdb-secrets"
  rabbitmq_existingSecret: "plane-rabbitmq-secrets"
  doc_store_existingSecret: "plane-doc-store-secrets"
  live_env_existingSecret: "plane-live-secrets"
```

---

## Current Projects

| Project | Identifier | UUID |
|---|---|---|
| Platform Tasks | `PT` | `870d8973-8525-4d5d-9bab-43a4d6a517f1` |

Create new projects at `https://plane.devandre.sbs` or via the minicloud-plane REST API once authenticated.

---

## Quick Health Check

```bash
# Pod status
kubectl get pods -n plane

# API reachability (from controller)
curl -s -H "X-Api-Key: <token>" \
  http://plane-api.plane.svc.cluster.local/api/v1/workspaces/ | jq '.[].name'

# Webhook delivery status (Celery worker logs)
kubectl logs -n plane -l app=worker --tail=20
```

---

## Access

- **URL:** https://plane.devandre.sbs (public, no Tailscale needed)
- **Login:** email + password (admin creds at `~/.plane-admin` on controller)
- **Admin panel:** https://plane.devandre.sbs/god-mode/ (superuser only)
