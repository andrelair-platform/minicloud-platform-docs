---
id: langfuse
title: Langfuse — LLM Observability
sidebar_label: Langfuse
---

# Langfuse — LLM Observability

## Overview

Langfuse 3.201.1 provides end-to-end observability for the AI Gateway. Every LLM call routed through LiteLLM is automatically captured as a trace in Langfuse, giving full visibility into latency, token usage, costs, and model performance per department.

| Component | Details |
|---|---|
| App version | 3.201.1 (chart 1.5.37) |
| Namespace | `langfuse` |
| Internal URL | `https://langfuse.10.0.0.200.nip.io` |
| Public URL | `https://langfuse.devandre.sbs` |
| Trace backend | ClickHouse (single-node, local-path PVC) |
| Cache | Valkey (Redis-compatible, standalone) |
| Blob storage | MinIO (controller Docker, `langfuse-blobs` + `langfuse-events` buckets) |
| Database | PostgreSQL (`langfuse` DB on `postgresql-ai-0` in `ai` namespace) |
| GitOps | ArgoCD Apps: `langfuse-base` + `langfuse` |

## Architecture

```
Browser / custom app
        │
        ▼
  NGINX Ingress ──► langfuse.devandre.sbs
        │               (Cloudflare Tunnel)
        │
  Langfuse Web (port 3000)
        │
  Langfuse Worker
        │
  ClickHouse (single-node) ◄── trace storage
  Valkey ◄───────────────────── cache / queue
  PostgreSQL (postgresql-ai-0) ◄ metadata / config
  MinIO (controller) ◄───────── blob / event upload
```

## LiteLLM Integration

LiteLLM sends traces to Langfuse via the `success_callback` in its ConfigMap. Every API call from Open WebUI or department virtual keys is captured.

Required env vars in LiteLLM (from `litellm-credentials` Secret via Vault):
- `LANGFUSE_PUBLIC_KEY` — Langfuse project public key
- `LANGFUSE_SECRET_KEY` — Langfuse project secret key
- `LANGFUSE_HOST` — `http://langfuse.langfuse.svc.cluster.local:3000`

ConfigMap entry:
```yaml
general_settings:
  success_callback: ["langfuse"]
```

## Login — Authentik OIDC

Public sign-up is disabled. Authentication is via Authentik SSO only.

1. Open `https://langfuse.devandre.sbs`
2. Click **Sign in with Authentik**
3. Authenticate with `kanmegnea` + TOTP
4. First login auto-creates the user in Langfuse. `kanmegnea@gmail.com` is pre-configured as admin via `AUTH_CUSTOM_ADMIN_EMAILS`.

Authentik application: slug `langfuse`, provider pk=11.

## Project & API Keys

The `minicloud-platform` org and `ai-gateway` project are pre-provisioned via `LANGFUSE_INIT_*` env vars. API keys for LiteLLM integration:
- Public key: stored in Vault at `platform/langfuse.project-public-key`
- Secret key: stored in Vault at `platform/langfuse.project-secret-key`

These are injected into LiteLLM as `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` env vars via the `litellm-credentials` Secret. Every LLM call through LiteLLM generates a trace automatically.

To add a new project/API key pair:
1. Log in to Langfuse → Settings → API Keys → create
2. Store in Vault: `vault kv patch secret/platform/langfuse project-public-key='pk-lf-...' project-secret-key='sk-lf-...'`
3. ESO will refresh `litellm-credentials` within 1h (or annotate to force)
4. Restart LiteLLM: `kubectl rollout restart deployment -n ai litellm`

## What You Can See

- **Traces**: every LLM call with model, prompt, completion, tokens, latency
- **Sessions**: linked calls from the same conversation thread
- **Users**: per-department usage breakdown (via virtual key metadata)
- **Scores**: manual or automated evaluation of responses
- **Datasets**: golden test sets for regression testing

## Department Usage Tracking

LiteLLM can tag traces by department using the virtual key `metadata` field. When creating department keys, add:

```bash
curl http://litellm.ai.svc.cluster.local:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"metadata": {"department": "direction-it"}, "key_alias": "direction-it"}'
```

Langfuse groups these traces under the `metadata.department` tag for per-team analytics.

## Operational Commands

```bash
# Check Langfuse pod health
kubectl get pods -n langfuse

# Check ClickHouse single-node
kubectl get pod -n langfuse -l app.kubernetes.io/name=clickhouse

# View Langfuse web logs
kubectl logs -n langfuse -l app.kubernetes.io/component=web --tail=50

# View Langfuse worker logs
kubectl logs -n langfuse -l app.kubernetes.io/component=worker --tail=50

# Check MinIO buckets used by Langfuse
docker exec minio mc ls myminio/langfuse-events
docker exec minio mc ls myminio/langfuse-blobs

# Restart Langfuse if needed
kubectl rollout restart deployment -n langfuse
```

## Secrets

All secrets are managed via Vault KV → ESO → Kubernetes Secret `langfuse-secrets` in the `langfuse` namespace.

Vault path: `secret/platform/langfuse`

| Key | Purpose |
|---|---|
| `db-password` | PostgreSQL `langfuse` user password |
| `nextauth-secret` | JWT encryption for NextAuth sessions |
| `encryption-key` | 256-bit key for sensitive data at rest |
| `clickhouse-password` | ClickHouse default user password |
| `minio-access-key` | MinIO root username |
| `minio-secret-key` | MinIO root password |

## Storage

| Store | Location | Data |
|---|---|---|
| PostgreSQL | `postgresql-ai-0` (ai ns), DB `langfuse` | Users, projects, config, prompts |
| ClickHouse | StatefulSet in `langfuse` ns | Traces, events, analytics |
| MinIO | Controller Docker, bucket `langfuse-blobs` | Uploaded media, exports |
| MinIO | Controller Docker, bucket `langfuse-events` | Async event queue |

## Known Limitations

- **ClickHouse single-node**: No HA. A ClickHouse pod failure means traces are buffered in the event queue (MinIO) and replayed once ClickHouse recovers. No trace data is lost.
- **OIDC-only auth**: Local account creation is disabled. All users must exist in Authentik and be granted access via the Langfuse Authentik application's policy bindings. `kanmegnea@gmail.com` is pre-configured as admin via `AUTH_CUSTOM_ADMIN_EMAILS`.
