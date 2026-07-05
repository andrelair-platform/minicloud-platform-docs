---
id: rag-pipeline
title: RAG Pipeline — pgvector + nomic-embed-text + Open WebUI
sidebar_label: RAG Pipeline
---

# RAG Pipeline — pgvector + nomic-embed-text + Open WebUI

**Implemented:** 2026-07-05  
**Status:** Production

Retrieval-Augmented Generation (RAG) enables Open WebUI to answer questions grounded in uploaded documents. Every component runs on-cluster — no external embedding API, no new services.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Open WebUI (chat.devandre.sbs)               │
│                                                                      │
│  Upload document ──► Chunker ──────────────────────────────────────► │
│                      (1500 tokens, 200 overlap)                       │
│                             │                                        │
│                             ▼                                        │
│               nomic-embed-text via Ollama (768-dim)                  │
│                             │                                        │
│                             ▼                                        │
│                pgvector HNSW index (document_chunk)                  │
│                         ragdb on postgresql-ai                       │
│                                                                      │
│  User question ─────────────────────────────────────────────────────►│
│       │                                                              │
│       ▼                                                              │
│  nomic-embed-text embeds query ──► pgvector cosine search (TOP_K=5)  │
│       │                                                              │
│       ▼                                                              │
│  Top 5 chunks injected into LLM context ──► LLM answer              │
└──────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Version | Role |
|---|---|---|
| nomic-embed-text | 274 MB | 768-dim embedding model — best-in-class for CPU RAG |
| postgresql-ai | pgvector 0.8.4 | Vector store — `ragdb` database on the existing pod |
| Open WebUI | 0.9.4 | RAG orchestrator — chunking, embedding, retrieval, context injection |
| LiteLLM | 1.90.3 | Exposes `nomic-embed-text` via `/v1/embeddings` for API users |

## Why these choices

**nomic-embed-text over OpenAI ada-002:** 274 MB pulls in seconds; 768-dim vectors vs ada-002's 1536 cuts pgvector storage and search time in half; semantic quality is competitive on technical English text.

**pgvector (existing pod) over a new Weaviate/Qdrant:** No new services, no new PVCs. `postgresql-ai` already runs in the cluster; just adding a second database (`ragdb`) inside the same pod.

**HNSW over IVFFlat:** pgvector 0.8.4 on the ThinkPad i7-10510U triggers SIGILL (Illegal Instruction) during IVFFlat K-means — the binary uses SIMD instructions not available on this CPU generation. HNSW builds incrementally without SIMD K-means. `PGVECTOR_INDEX_METHOD=hnsw` overrides Open WebUI's default.

**Direct Ollama for embeddings (bypasses LiteLLM):** `RAG_EMBEDDING_ENGINE=ollama` + `RAG_OLLAMA_BASE_URL` points Open WebUI directly at `ollama.ai.svc:11434`. This keeps internal embedding calls out of LiteLLM's spend-tracking database — no phantom costs on the cost dashboard.

## Implementation

### Step 1 — Create the database

```bash
# Connect as postgres superuser to create DB and enable extension
PG_SUPER=$(kubectl get secret -n ai ai-postgresql-secret \
  -o jsonpath='{.data.postgres-password}' | base64 -d)

kubectl exec -n ai postgresql-ai-0 -- \
  env PGPASSWORD="$PG_SUPER" psql -U postgres -c "
    CREATE DATABASE ragdb;
    GRANT ALL PRIVILEGES ON DATABASE ragdb TO aiplatform;
  "

kubectl exec -n ai postgresql-ai-0 -- \
  env PGPASSWORD="$PG_SUPER" psql -U postgres -d ragdb -c "
    CREATE EXTENSION IF NOT EXISTS vector;
    GRANT ALL ON SCHEMA public TO aiplatform;
  "
```

### Step 2 — Pull nomic-embed-text on both Ollama instances

```bash
# Temporary egress NetworkPolicy (ai namespace has default-deny-egress)
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: temp-allow-model-pull
  namespace: ai
spec:
  podSelector: {}
  egress:
  - ports: [{port: 443}, {port: 80}]
  policyTypes: [Egress]
EOF

kubectl port-forward -n ai deploy/ollama 11434:11434 &
PF1=$!
sleep 3
curl -s -X POST http://localhost:11434/api/pull \
  -d '{"model":"nomic-embed-text","stream":false}'
kill $PF1

kubectl port-forward -n ai deploy/ollama-secondary 11435:11434 &
PF2=$!
sleep 3
curl -s -X POST http://localhost:11435/api/pull \
  -d '{"model":"nomic-embed-text","stream":false}'
kill $PF2

kubectl delete networkpolicy temp-allow-model-pull -n ai
```

### Step 3 — Update Open WebUI Helm values

Add to `open-webui-values.yaml` in the `extraEnvVars` section (before `SSL_CERT_FILE`):

```yaml
# ── RAG / Vector Search (pgvector) ──────────────────────────────────
- name: VECTOR_DB
  value: "pgvector"
- name: PGVECTOR_DB_URL
  value: "postgresql://aiplatform:$(PG_PASSWORD)@postgresql-ai.ai.svc.cluster.local:5432/ragdb"
- name: PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH
  value: "768"
- name: PGVECTOR_INDEX_METHOD
  value: "hnsw"                  # IVFFlat triggers SIGILL on i7-10510U
- name: PGVECTOR_HNSW_M
  value: "16"
- name: PGVECTOR_HNSW_EF_CONSTRUCTION
  value: "64"
- name: RAG_EMBEDDING_ENGINE
  value: "ollama"                # bypass LiteLLM — keep embeddings out of cost tracking
- name: RAG_EMBEDDING_MODEL
  value: "nomic-embed-text"
- name: RAG_OLLAMA_BASE_URL
  value: "http://ollama.ai.svc.cluster.local:11434"
- name: CHUNK_SIZE
  value: "1500"
- name: CHUNK_OVERLAP
  value: "200"
- name: RAG_TOP_K
  value: "5"
- name: ENABLE_RAG_HYBRID_SEARCH
  value: "true"
```

```bash
scp ~/Developer/cloudplateform/minicloud-ansible/helm-values/open-webui-values.yaml \
  controller:/home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/

ssh controller "helm upgrade open-webui open-webui/open-webui \
  --namespace ai \
  --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/open-webui-values.yaml \
  --timeout 4m --wait"
```

Open WebUI creates the `document_chunk` table and HNSW index automatically on first start.

### Step 4 — Add nomic-embed-text to LiteLLM ConfigMap

Add to `manifests/ai/00-litellm-configmap.yaml`:

```yaml
- model_name: nomic-embed-text
  litellm_params:
    model: ollama/nomic-embed-text
    api_base: http://ollama.ai.svc.cluster.local:11434
- model_name: nomic-embed-text
  litellm_params:
    model: ollama/nomic-embed-text
    api_base: http://ollama-secondary.ai.svc.cluster.local:11434
```

Update department key allowlists in LiteLLM PostgreSQL:

```bash
DB_URL=$(kubectl get secret -n ai litellm-credentials \
  -o jsonpath='{.data.database-url}' | base64 -d)
kubectl exec -n ai postgresql-ai-0 -- psql "$DB_URL" -c "
  UPDATE \"LiteLLM_VerificationToken\"
  SET models = array_append(models, 'nomic-embed-text')
  WHERE 'nomic-embed-text' != ALL(models)
    AND key_alias NOT IN ('direction-operations','direction-rh','direction-services-generaux','direction-sinistres');
"
```

After merging ConfigMap to git (ArgoCD syncs), restart LiteLLM:

```bash
kubectl rollout restart deployment/litellm -n ai
```

## Verification

### Embedding chain

```bash
# 1. nomic-embed-text via Ollama (direct)
kubectl port-forward -n ai svc/ollama 11434:11434 &
curl -s -X POST http://localhost:11434/api/embeddings \
  -d '{"model":"nomic-embed-text","prompt":"test sentence"}' | \
  python3 -c 'import sys,json; e=json.load(sys.stdin)["embedding"]; print(f"dims={len(e)}")'
# Expected: dims=768

# 2. nomic-embed-text via LiteLLM (API users)
MASTER=$(kubectl get secret -n ai litellm-credentials \
  -o jsonpath='{.data.master-key}' | base64 -d)
kubectl port-forward -n ai svc/litellm 4000:4000 &
curl -s -X POST http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"test"}' | \
  python3 -c 'import sys,json; r=json.load(sys.stdin); print(f"dims={len(r[\"data\"][0][\"embedding\"])}")'
# Expected: dims=768
```

### pgvector table

```bash
PG_PASS=$(kubectl get secret -n ai ai-postgresql-secret \
  -o jsonpath='{.data.password}' | base64 -d)
kubectl exec -n ai postgresql-ai-0 -- \
  env PGPASSWORD="$PG_PASS" psql -U aiplatform -d ragdb \
  -c "\d document_chunk"
# Expected: vector(768) column with hnsw index idx_document_chunk_vector
```

### End-to-end RAG test

1. Go to `https://chat.devandre.sbs`
2. Login via Authentik (Authentik credentials or demo.it/data/sinistres @devandre.sbs)
3. Start a new chat
4. Upload any PDF or text file via the paperclip icon
5. Ask: "What does this document say about X?" — Open WebUI retrieves top 5 matching chunks and generates a grounded answer

## Operational notes

### Adding more documents to the knowledge base

Upload via Open WebUI UI → the embedding happens automatically. For bulk ingestion via API:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:4000",
    api_key="sk-direction-it-..."
)

# Get embeddings for a text chunk
response = client.embeddings.create(
    model="nomic-embed-text",
    input="Your document text here"
)
vector = response.data[0].embedding  # 768-dim float list
# INSERT INTO ragdb.document_chunk (id, vector, collection_name, text, vmetadata) VALUES (...)
```

### If Open WebUI crashes on startup with SIGILL

This means pgvector tried to create an IVFFlat index. Drop the table and ensure `PGVECTOR_INDEX_METHOD=hnsw` is set:

```bash
PG_PASS=$(kubectl get secret -n ai ai-postgresql-secret \
  -o jsonpath='{.data.password}' | base64 -d)

kubectl scale statefulset open-webui -n ai --replicas=0

kubectl exec -n ai postgresql-ai-0 -- \
  env PGPASSWORD="$PG_PASS" psql -U aiplatform -d ragdb \
  -c "DROP TABLE IF EXISTS document_chunk;"

# Verify env var is set in helm values, then:
kubectl scale statefulset open-webui -n ai --replicas=1
```

### If pgvector extension is missing after a DB rebuild

```bash
PG_SUPER=$(kubectl get secret -n ai ai-postgresql-secret \
  -o jsonpath='{.data.postgres-password}' | base64 -d)
kubectl exec -n ai postgresql-ai-0 -- \
  env PGPASSWORD="$PG_SUPER" psql -U postgres -d ragdb \
  -c "CREATE EXTENSION IF NOT EXISTS vector; GRANT ALL ON SCHEMA public TO aiplatform;"
```
