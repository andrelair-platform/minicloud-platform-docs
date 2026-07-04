---
id: ai-gateway
title: AI Gateway — LiteLLM + PostgreSQL
sidebar_label: AI Gateway
---

# AI Gateway — LiteLLM + PostgreSQL

**Phase complete:** 2026-07-04  
**Issues closed:** #34 (LiteLLM proxy), #41 (inference optimization)  
**GitOps:** `manifests/ai/` in minicloud-gitops — ArgoCD Application `litellm` Synced/Healthy

## Architecture

```
Open WebUI → LiteLLM Gateway (4000) → least-busy router
                                         ├── Ollama primary  (fast-heron,  port 11434)
                                         └── Ollama secondary (star-kitten, port 11434)
```

All components run in the `ai` namespace. LiteLLM is the single OpenAI-compatible endpoint — Open WebUI no longer talks to Ollama directly.

## Components

| Component | Image | Storage | Node |
|---|---|---|---|
| LiteLLM gateway | `harbor.10.0.0.200.nip.io/library/litellm:1.90.3-prisma-v3` | stateless | any |
| PostgreSQL (ai) | `harbor.10.0.0.200.nip.io/library/postgresql:18.4.0` | Longhorn 5Gi | any |
| Ollama primary | `ollama/ollama` | local-path 10Gi | fast-heron |
| Ollama secondary | `ollama/ollama` | local-path 10Gi | star-kitten |

## Models

| Model | Primary | Secondary |
|---|---|---|
| `phi3-financial` | ✓ (2.2 GB) | ✓ (2.2 GB) |
| `llama3.2:3b` | ✓ (2.0 GB) | ✓ (2.0 GB) |
| `llama3.2:1b` | ✓ (1.3 GB) | ✓ (1.3 GB) |
| `phi3.5` | ✓ (2.2 GB) | ✓ (2.2 GB) |

## PostgreSQL databases

| Database | Owner | Used by |
|---|---|---|
| `openwebui` | `aiplatform` | Open WebUI session/user data |
| `litellm` | `aiplatform` | LiteLLM virtual keys, spend tracking |

Credentials managed by ESO ExternalSecret `ai-postgresql-secret` (Vault KV `secret/platform/ai-postgresql`).

## Inference tuning (both Ollama instances)

```yaml
OLLAMA_NUM_PARALLEL: "4"
OLLAMA_NUM_THREADS: "6"
OLLAMA_MAX_LOADED_MODELS: "2"
OLLAMA_FLASH_ATTENTION: "1"
OLLAMA_KV_CACHE_TYPE: "q8_0"
OLLAMA_NUM_CTX: "4096"
```

CPU governor set to `performance` on all 4 cluster nodes (persistent via `cpu-performance.service`).

## Custom LiteLLM image

The upstream `ghcr.io/berriai/litellm-database` image pre-downloads Prisma engine binaries to `/root/.cache/` (mode 700). The `prisma-client-py` 0.11.0 package's generated `BINARY_PATHS` dict hardcodes those paths — `Path.exists()` raises `PermissionError` for UID 1000 before any override env var can take effect.

**Fix:** `chmod -R 755 /root /root/.cache /root/.cache/prisma-python` in the Dockerfile.

Source at `~/Developer/cloudplateform/litellm-custom/Dockerfile`. Rebuild procedure:

```bash
cd ~/Developer/cloudplateform/litellm-custom
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build --platform linux/amd64 \
  -t "litellm-prisma:<version>-amd64" .
docker save "litellm-prisma:<version>-amd64" -o /tmp/litellm.tar
crane push /tmp/litellm.tar "harbor.10.0.0.200.nip.io/library/litellm:<version>"
rm /tmp/litellm.tar
```

When upgrading the base image, verify the new Prisma engine version hash hasn't changed; if it has, rebuild.

## LiteLLM configuration

Config at `minicloud-ansible/litellm-manifests.yaml` (applied directly, not GitOps-managed):

```yaml
model_list:
  - model_name: phi3-financial
    litellm_params:
      model: ollama/phi3-financial
      api_base: http://ollama.ai.svc.cluster.local:11434
  - model_name: phi3-financial
    litellm_params:
      model: ollama/phi3-financial
      api_base: http://ollama-secondary.ai.svc.cluster.local:11434
  # llama3.2:3b similarly on both

router_settings:
  routing_strategy: least-busy
  num_retries: 2
  timeout: 120

general_settings:
  store_model_in_db: true
```

Apply changes:
```bash
scp ~/Developer/cloudplateform/minicloud-ansible/litellm-manifests.yaml controller:/tmp/
ssh controller "kubectl apply -f /tmp/litellm-manifests.yaml"
```

## Virtual key management

LiteLLM master key in `litellm-credentials` secret (ESO-synced from `secret/platform/litellm`).

Create a department virtual key (example — IT department):

```bash
MASTER_KEY=$(kubectl get secret -n ai litellm-credentials \
  -o jsonpath='{.data.master-key}' | base64 -d)

kubectl port-forward -n ai svc/litellm 4000:4000 &

curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "key_alias": "dept-it",
    "team_id": "direction-it",
    "rpm_limit": 60,
    "tpm_limit": 100000,
    "models": ["phi3-financial", "llama3.2:3b"]
  }'
```

Keys persist in PostgreSQL `litellm` database — survive pod restarts.

## Health check

```bash
# Via port-forward
kubectl port-forward -n ai svc/litellm 4000:4000 &
curl http://localhost:4000/health/readiness
# Expected: {"status": "healthy", "db": "connected"}

# Model list
curl -H "Authorization: Bearer $MASTER_KEY" http://localhost:4000/v1/models
```

## Adding models to secondary Ollama

```bash
SECONDARY_POD=$(kubectl get pods -n ai -l app.kubernetes.io/instance=ollama-secondary \
  -o jsonpath='{.items[0].metadata.name}')

# Pull base model (needs temp internet egress NetworkPolicy — see below)
# Create custom model
kubectl exec -n ai $SECONDARY_POD -- sh -c '
  cat > /tmp/Modelfile << '"'"'EOF'"'"'
FROM phi3.5
SYSTEM """..."""
PARAMETER temperature 0.1
EOF
  ollama create my-model -f /tmp/Modelfile
'
```

Temp egress NetworkPolicy for model pulls:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: temp-allow-secondary-pull
  namespace: ai
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/instance: ollama-secondary
  egress:
  - ports:
    - port: 443
  policyTypes:
  - Egress
```

Delete after pulling: `kubectl delete networkpolicy temp-allow-secondary-pull -n ai`

## Secrets in Vault

```bash
# ai-postgresql-secret
kubectl exec -n vault vault-0 -- sh -c "
  VAULT_TOKEN=\$(cat /vault/data/root-token) VAULT_ADDR=http://127.0.0.1:8200 \
  vault kv get secret/platform/ai-postgresql"

# litellm-credentials
kubectl exec -n vault vault-0 -- sh -c "
  VAULT_TOKEN=\$(cat /vault/data/root-token) VAULT_ADDR=http://127.0.0.1:8200 \
  vault kv get secret/platform/litellm"
```
