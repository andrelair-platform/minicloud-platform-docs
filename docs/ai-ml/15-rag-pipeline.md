---
id: rag-pipeline
title: RAG Pipeline — pgvector + nomic-embed-text + SearXNG Web Search
sidebar_label: RAG Pipeline & Web Search
---

# RAG Pipeline — pgvector + nomic-embed-text + SearXNG Web Search

**Implemented:** 2026-07-05  
**Status:** Production

Retrieval-Augmented Generation (RAG) enables Open WebUI to answer questions grounded in uploaded documents. Every component runs on-cluster — no external embedding API, no new services.

## Knowledge sources

Open WebUI provides two complementary grounding mechanisms that can be used independently or together:

| Source | What it knows | Latency | Activation |
|---|---|---|---|
| **RAG (pgvector)** | Documents users have uploaded (PDFs, text, CSV) | ~10–50 ms | Paperclip icon → upload file |
| **Web Search (SearXNG)** | Real-time internet — current events, latest docs, live data | ~1–3 s | Globe icon in toolbar |

## Architecture

### RAG path (uploaded documents)

```
Upload document → Open WebUI chunker (1500 tokens, 200 overlap)
    → nomic-embed-text via Ollama (768-dim vectors)
    → pgvector HNSW index (ragdb on postgresql-ai)

User question → nomic-embed-text embeds query
    → pgvector cosine search (TOP_K=5)
    → top 5 chunks injected into LLM context → LLM answer
```

### Web search path (real-time internet)

```
User question (web search toggle ON)
    → Open WebUI → SearXNG /search?q=<query>&format=json
    → SearXNG aggregates: Google + Bing + DuckDuckGo + Wikipedia
    → top 5 results (title + URL + snippet)
    → Open WebUI fetches full page content (via internet egress NP)
    → results injected into LLM context → LLM answer with citations
```

## Components

| Component | Version | Role |
|---|---|---|
| nomic-embed-text | 274 MB | 768-dim embedding model — best-in-class for CPU RAG |
| postgresql-ai | pgvector 0.8.4 | Vector store — `ragdb` database on the existing pod |
| Open WebUI | 0.9.4 | RAG orchestrator + web search frontend (app data → PostgreSQL `openwebui` DB) |
| LiteLLM | 1.90.3 | Exposes `nomic-embed-text` via `/v1/embeddings` for API users |
| SearXNG | 2026.7.3 | Self-hosted meta-search engine — real-time internet results |

## Why these choices

**nomic-embed-text over OpenAI ada-002:** 274 MB pulls in seconds; 768-dim vectors vs ada-002's 1536 cuts pgvector storage and search time in half; semantic quality is competitive on technical English text.

**pgvector (existing pod) over a new Weaviate/Qdrant:** No new services, no new PVCs. `postgresql-ai` already runs in the cluster; just adding a second database (`ragdb`) inside the same pod.

**HNSW over IVFFlat:** pgvector 0.8.4 on the ThinkPad i7-10510U triggers SIGILL (Illegal Instruction) during IVFFlat K-means — the binary uses SIMD instructions not available on this CPU generation. HNSW builds incrementally without SIMD K-means. `PGVECTOR_INDEX_METHOD=hnsw` overrides Open WebUI's default.

**Direct Ollama for embeddings (bypasses LiteLLM):** `RAG_EMBEDDING_ENGINE=ollama` + `RAG_OLLAMA_BASE_URL` points Open WebUI directly at `ollama.ai.svc:11434`. This keeps internal embedding calls out of LiteLLM's spend-tracking database — no phantom costs on the cost dashboard.

## Scaling roadmap

The embedding model and the vector store are **matched components** — you cannot improve one without also addressing the other, because they share the same bottleneck.

**Current ceiling:** nomic-embed-text (CPU, 768-dim) + pgvector HNSW (single pod, 512 Mi RAM) → suitable for tens of thousands of chunks, sub-second search latency at demo scale.

**Why switching embedding models alone changes nothing meaningful:** if you replaced nomic-embed-text with OpenAI ada-002 (1536-dim) without replacing pgvector, the HNSW graph would double in RAM, search latency would increase, and you'd still hit the pgvector ceiling before the embedding quality gap matters. You'd have added cost and external API dependency while the actual constraint — pgvector on a 512 Mi pod — remained unchanged.

**The right upgrade path is a full stack replacement:**

| Scale | Action |
|---|---|
| ~100k chunks (current) | Current stack is correctly matched — tune `HNSW ef_search` if needed |
| ~1M chunks | Replace pgvector with a dedicated Qdrant or Weaviate pod with more RAM |
| ~10M chunks | Managed vector DB (Pinecone, Weaviate Cloud) + OpenAI/Cohere embeddings |

The lesson: **optimize the bottleneck, not adjacent components.** At demo scale, the current stack is the right choice. When document volume grows to the point where pgvector search latency degrades, replace both the vector store and the embedding model together.

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

---

## Part 2 — Web Search (SearXNG)

**Implemented:** 2026-07-05

SearXNG is a self-hosted privacy-preserving meta-search engine. It queries Google, Bing, DuckDuckGo, and Wikipedia simultaneously and returns aggregated results without tracking users.

### Why SearXNG over hosted search APIs

| Option | Self-hosted | Cost | Rate limit | Privacy |
|---|---|---|---|---|
| **SearXNG** | ✅ | Free | None | On-cluster |
| Brave Search | ❌ | $0 / 2k/mo | 2,000 req/mo | External |
| Tavily | ❌ | $0 / 1k/mo | 1,000 req/mo | External |
| DuckDuckGo | ❌ | Free | Unreliable | External |

### Component

| Resource | Namespace | Image | Service |
|---|---|---|---|
| `searxng` Deployment | `searxng` | `docker.io/searxng/searxng:2026.7.3-747cec4c2` | ClusterIP port 8080 |

### NetworkPolicy design

The `searxng` namespace has the tightest egress policy on the cluster:

```
default-deny-ingress + default-deny-egress
    ↓
allow-from-open-webui   — ingress from ai ns, port 8080 only
allow-dns-egress        — UDP/TCP 53 to kube-system (CoreDNS)
allow-internet-egress   — TCP 443/80 to 0.0.0.0/0 (only searxng pod)
```

Open WebUI (in `ai` ns) gets its own internet egress policy (`allow-open-webui-internet-egress`) to fetch full page content from result URLs.

### Configuration (open-webui-values.yaml)

```yaml
- name: ENABLE_WEB_SEARCH
  value: "true"
- name: WEB_SEARCH_ENGINE
  value: "searxng"
- name: SEARXNG_QUERY_URL
  value: "http://searxng.searxng.svc.cluster.local:8080/search?q=<query>&format=json&language=auto"
- name: WEB_SEARCH_RESULT_COUNT
  value: "5"
- name: WEB_SEARCH_CONCURRENT_REQUESTS
  value: "10"
```

> **Gotcha:** Open WebUI config.py reads `ENABLE_WEB_SEARCH` and `WEB_SEARCH_ENGINE` — not the `ENABLE_RAG_*` prefixed variants. Using the wrong names silently has no effect (web search appears configured in the UI settings but does not actually activate).

### Deployment (GitOps)

All resources in `minicloud-gitops/manifests/searxng/`. ArgoCD Application `searxng` auto-syncs.

```bash
# Check SearXNG status
kubectl get pods -n searxng
kubectl logs -n searxng -l app=searxng --tail=20

# Verify it returns results
kubectl port-forward -n searxng svc/searxng 8181:8080 &
curl -s 'http://localhost:8181/search?q=kubernetes+latest&format=json' | \
  python3 -c 'import sys,json; r=json.load(sys.stdin); print("results:", len(r.get("results",[])))'

# Verify Open WebUI can reach it
kubectl exec -n ai open-webui-0 -- python3 -c "
import urllib.request, json
r = json.loads(urllib.request.urlopen(
    'http://searxng.searxng.svc.cluster.local:8080/search?q=test&format=json'
).read())
print('ok, results:', len(r.get('results',[])))
"
```

### How to use web search in Open WebUI

1. Go to `https://chat.devandre.sbs`
2. Start a new chat
3. Click the **globe icon** in the toolbar to enable web search
4. Ask any question — Open WebUI queries SearXNG, retrieves real-time results, and injects them into the LLM context
5. The answer will cite the sources

**Example queries that benefit from web search:**
- "What's new in Kubernetes 1.36?"
- "Latest CVEs affecting containerd"
- "Current EUR/USD exchange rate"
- "Changelog for Helm 3.17"

### gotcha: enableServiceLinks must be false

Kubernetes automatically injects `SEARXNG_PORT=tcp://<cluster-ip>:8080` into all pods in the `searxng` namespace when a service named `searxng` exists. SearXNG uses `SEARXNG_PORT` as its listen port — the injected value is not a valid integer and crashes granian on startup.

Fix: `enableServiceLinks: false` in the pod spec. This disables k8s service env var injection for the pod.

### gotcha: use ENABLE_WEB_SEARCH, not ENABLE_RAG_WEB_SEARCH

Open WebUI config.py reads `ENABLE_WEB_SEARCH` and `WEB_SEARCH_ENGINE`. The `ENABLE_RAG_*` prefixed variants do not exist and are silently ignored — the globe icon may appear in the UI but web search will not trigger.

| Wrong (silent no-op) | Correct |
|---|---|
| `ENABLE_RAG_WEB_SEARCH=true` | `ENABLE_WEB_SEARCH=true` |
| `RAG_WEB_SEARCH_ENGINE=searxng` | `WEB_SEARCH_ENGINE=searxng` |
| `RAG_WEB_SEARCH_RESULT_COUNT=5` | `WEB_SEARCH_RESULT_COUNT=5` |
| `RAG_WEB_SEARCH_CONCURRENT_REQUESTS=10` | `WEB_SEARCH_CONCURRENT_REQUESTS=10` |

### gotcha: BYPASS_WEB_SEARCH_WEB_LOADER must be true

By default, Open WebUI fetches the full HTML content of each search result URL to give the LLM richer context. Most news and sports sites (FIFA.com, BBC Sport, Le Monde, ESPN) block scraping — the content loader gets an empty response or a captcha page. With no content extracted, the LLM responds "Aucune source trouvée" even though SearXNG returned valid results.

`BYPASS_WEB_SEARCH_WEB_LOADER=true` skips the content-fetching step and uses SearXNG's snippets directly (title + URL + excerpt). The snippets are sufficient for the LLM to answer factual questions like match results, news headlines and exchange rates.

```yaml
- name: BYPASS_WEB_SEARCH_WEB_LOADER
  value: "true"
```

### Scaling and replacement

SearXNG is a stateless meta-search proxy — it holds no data. If you need more throughput, scale replicas:

```bash
kubectl scale deployment searxng -n searxng --replicas=3
```

The `allow-from-open-webui` NetworkPolicy uses a namespace selector, not a pod selector — all replicas receive traffic automatically.
