---
id: rag-pipeline
title: RAG Pipeline — pgvector + nomic-embed-text + SearXNG Web Search
sidebar_label: RAG Pipeline & Web Search
---

# RAG Pipeline — pgvector + nomic-embed-text + SearXNG Web Search

**Implemented:** 2026-07-05 (RAG + web search + re-ranking), 2026-07-06 (Docling OCR)
**Status:** Production

Retrieval-Augmented Generation (RAG) enables Open WebUI to answer questions grounded in uploaded documents. Every component runs on-cluster — no external embedding API, no new services.

## Knowledge sources

Open WebUI provides two complementary grounding mechanisms that can be used independently or together:

| Source | What it knows | Latency | Activation |
|---|---|---|---|
| **RAG (pgvector)** | Documents users have uploaded (PDFs, text, CSV) | 0.3–7 ms (pgvector) + 2–8 s (inference) | Paperclip icon → upload file |
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

**HNSW, with a custom pgvector build:** pgvector 0.8.4 in the upstream Bitnami image contains AVX-512 EVEX-encoded instructions in its HNSW and IVFFlat index-update routines. All four cluster CPUs (i7-8565U and i7-10510U) lack AVX-512 — every INSERT that triggers an HNSW or IVFFlat graph update terminates the PostgreSQL backend with SIGILL (signal 4, Illegal Instruction). The fix is a custom pgvector build compiled with `-mno-avx512f -mno-avx512bw -mno-avx512vl -mno-avx512dq`, keeping the AVX2/SSE4 code paths intact. The new image (`harbor.../postgresql:18.4.0-noavx512`) is maintained in `minicloud-ansible/docker/postgresql-noavx512/`. Sequential-scan vector distance queries and GIN FTS are unaffected — only the index maintenance code path contained the AVX-512 instructions.

**Direct Ollama for embeddings (bypasses LiteLLM):** `RAG_EMBEDDING_ENGINE=ollama` + `RAG_OLLAMA_BASE_URL` points Open WebUI directly at `ollama.ai.svc:11434`. This keeps internal embedding calls out of LiteLLM's spend-tracking database — no phantom costs on the cost dashboard.

## Measured latency profile

All values measured on the live cluster (2026-07-06) with 500 rows in `ragdb.document_chunk`.

| Operation | p50 latency | Notes |
|---|---|---|
| HNSW vector search | **0.31 ms** | `SET enable_seqscan=off` forces index path; planner prefers seqscan at <1k rows |
| Sequential scan vector search | 1.29 ms | Planner-selected at 500 rows; faster than HNSW at this scale |
| GIN FTS (BM25 leg of hybrid) | **2.71 ms** | Bitmap index scan on `idx_document_chunk_text_search` |
| INSERT + HNSW update | **6.8 ms/row** | Dominated by HNSW graph maintenance, not the INSERT itself |
| nomic-embed-text embedding | **393 ms** | Network-dominated (port-forward); in-cluster latency is ~30–80 ms |
| Ollama inference | **2,000–8,000 ms** | Model-dependent; CPU-only; dominates end-to-end latency |

**Key takeaway:** pgvector contributes less than 1% of total RAG latency. Ollama inference (2–8 s) is the bottleneck at every scale. Optimizing HNSW parameters or switching index types has no user-visible impact. The right levers for latency reduction are model size (phi4-mini vs deepseek-r1:7b) and cloud routing (DeepSeek API at 5–8 s vs local CPU at 40+ s).

HNSW is auto-selected by PostgreSQL's cost model at ~1,000+ rows. Below that threshold the planner uses sequential scan, which is faster at small table sizes and produces identical quality — the planner is correct. To force HNSW for benchmarking, run `SET enable_seqscan=off` in the session.

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

## Document ingestion quality roadmap

Compared to RAGFlow (the leading self-hosted enterprise RAG platform), three gaps exist in the current stack. All three are **additive improvements** on top of the existing deployment — no stack replacement required, because Open WebUI 0.9.4 already has native hooks for each.

### Phase A — Re-ranking (cross-encoder) ✅ Live (2026-07-05)

**The gap:** after HNSW cosine-distance search returns the top-K chunks, they are ranked by embedding similarity — which measures topic proximity, not answer quality. A chunk that mentions the query terms in passing ranks the same as one that directly answers the question.

**What re-ranking adds:** a cross-encoder model reads the query and each candidate chunk together (not as independent vectors) and scores the pair holistically. Top-K after re-ranking is meaningfully better than top-K from cosine distance alone.

**Deployed config (minicloud-ansible commit `2fc03f7`):**

```yaml
# open-webui-values.yaml extraEnvVars
- name: RAG_RERANKING_ENGINE
  value: "sentence_transformers"
- name: RAG_RERANKING_MODEL
  value: "cross-encoder/ms-marco-MiniLM-L-6-v2"   # 80 MB, CPU-friendly
- name: RAG_TOP_K_RERANKER
  value: "3"                                         # keep top 3 after reranking
```

The model runs in-process inside the Open WebUI pod. No new Deployment or Service. Smoke test: "Paraguay 0-1 France FIFA World Cup 2026" scored `5.587`; irrelevant "History of football in South America" scored `-11.295` — correct ordering confirmed. For a larger reranker (BGE-Reranker-v2-M3, 568 MB), use `RAG_EXTERNAL_RERANKER_URL` pointing to a dedicated pod to keep Open WebUI pod RAM under control.

---

### Phase B — OCR & advanced document parsing (Docling) ✅ Live (2026-07-06)

**The gap:** the current stack handles text-based PDFs only. Scanned insurance documents, contract images, and mixed-format files (PDF with embedded tables + scanned pages) produce empty or garbled chunks.

**What Docling adds:** IBM Docling (open-source, self-hostable) converts scanned PDFs, images, and complex layouts into clean text before chunking. It handles tables, multi-column layouts, headers/footers, and embedded images with text — producing extraction quality close to commercial solutions.

**Deployed config:**

- `manifests/ai/08-docling.yaml` (minicloud-gitops commit `116d5e4`) — Deployment + Service in the `ai` namespace
- `open-webui-values.yaml` (minicloud-ansible commit `d8a4bf6`) — `CONTENT_EXTRACTION_ENGINE=docling` + `DOCLING_SERVER_URL`

```yaml
# 08-docling.yaml (key fields)
image: ghcr.io/docling-project/docling-serve-cpu:v1.26.0   # CPU-only, 4.4 GB, models bundled
resources:
  requests: {cpu: 200m, memory: 1500Mi}
  limits:   {cpu: 2000m, memory: 3Gi}
readinessProbe: GET /ready   initialDelaySeconds: 30
livenessProbe:  GET /health  initialDelaySeconds: 120
```

```yaml
# open-webui-values.yaml extraEnvVars
- name: CONTENT_EXTRACTION_ENGINE
  value: "docling"
- name: DOCLING_SERVER_URL
  value: "http://docling.ai.svc.cluster.local:5001"
```

Open WebUI calls `POST /v1/convert/file` and reads `response.document.md_content`. Text-based PDFs still work — Docling handles both. NetworkPolicy: `allow-same-namespace` in the `ai` namespace already covers Open WebUI → docling port 5001 (cluster-internal, no internet egress needed).

**Gotcha — image size:** `docling-serve-cpu:v1.26.0` is 4.4 GB (AMD64). First pull on a node takes 10–20 minutes. Models are bundled, so no runtime downloads occur after that. Use the CPU-only variant (`-cpu` suffix); the base image is 8.7 GB (includes GPU libs for no reason on CPU-only nodes).

---

### Phase C — True hybrid search ✅ Live (2026-07-06)

Open WebUI 0.9.4 with pgvector implements **native hybrid search** — not a lightweight approximation. When `ENABLE_RAG_HYBRID_SEARCH=true`, the pgvector client runs two independent queries against PostgreSQL and combines them with Reciprocal Rank Fusion:

| Component | Implementation | Index |
|---|---|---|
| **Vector search** | HNSW cosine similarity (`vector_cosine_ops`) | `idx_document_chunk_vector` (HNSW) |
| **Full-text search** | `plainto_tsquery('simple') @@ to_tsvector('simple', text)` + `ts_rank_cd` | `idx_document_chunk_text_search` (GIN) ✅ |

**Deployed config (minicloud-ansible commit `7a2e75e`):**

```yaml
# open-webui-values.yaml extraEnvVars
- name: ENABLE_RAG_HYBRID_SEARCH
  value: "true"
- name: RAG_HYBRID_BM25_WEIGHT
  value: "0.5"   # 50% FTS + 50% vector; raise for keyword-heavy corpora
```

The GIN index was created manually on ragdb (`CREATE INDEX CONCURRENTLY`) — the pgvector `__init__` generates the DDL but it requires an explicit session commit that doesn't always fire on first start.

**Weight tuning guide:**
- `0.5` — balanced (default, good for mixed semantic + keyword queries)
- `0.3` — lean toward vector (better for abstract questions: "what is our risk exposure?")
- `0.7` — lean toward FTS (better for exact-term lookup: "article 42", "IBNR", specific policy numbers)

**Gap closure vs RAGFlow:** RAGFlow uses a standalone BM25 index (Elasticsearch/Typesense). Open WebUI uses PostgreSQL's built-in `ts_rank_cd` with a GIN index — same result-quality class, no extra service required.

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
  value: "hnsw"                  # requires custom no-AVX512 image — see pgvector SIGILL fix below
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

### pgvector AVX-512 SIGILL fix (critical for ThinkPad i7-8565U / i7-10510U)

**Symptom:** PostgreSQL backend processes terminate with `signal 4: Illegal Instruction` whenever a document INSERT triggers HNSW or IVFFlat index maintenance. Open WebUI shows "server closed the connection unexpectedly". RAG document uploads fail silently.

**Root cause:** pgvector 0.8.4 in the upstream Bitnami postgresql image contains EVEX-encoded AVX-512 instructions in `vector.so` (in the HNSW graph traversal and IVFFlat K-means code paths). All four cluster CPUs (i7-8565U Whiskey Lake, i7-10510U Comet Lake) lack AVX-512 support. Sequential-scan vector distance queries are not affected — only index maintenance triggers the SIGILL.

**Diagnosis:**
```bash
# Confirm SIGILL in PostgreSQL pod logs
kubectl logs -n ai postgresql-ai-0 | grep -i "signal 4\|Illegal instruction\|terminated by signal"
# Expected: "client backend (PID ...) was terminated by signal 4: Illegal instruction"
```

**Fix — custom pgvector build:**

The fix is a custom Docker image that rebuilds `vector.so` from pgvector 0.8.4 source with AVX-512 disabled:

```bash
# Dockerfile at: minicloud-ansible/docker/postgresql-noavx512/Dockerfile
# Build and push (on controller):
docker build -t harbor.10.0.0.200.nip.io/library/postgresql:18.4.0-noavx512 \
  /home/ktayl/docker-builds/pgvector/
docker save harbor.10.0.0.200.nip.io/library/postgresql:18.4.0-noavx512 \
  -o /tmp/pgvec-noavx512.tar
crane push --insecure /tmp/pgvec-noavx512.tar \
  harbor.10.0.0.200.nip.io/library/postgresql:18.4.0-noavx512
```

Key Dockerfile excerpt:
```dockerfile
RUN cd /tmp/pgvector-0.8.4 && \
    make OPTFLAGS="-mno-avx512f -mno-avx512bw -mno-avx512vl -mno-avx512dq" \
         PG_CONFIG=/opt/bitnami/postgresql/bin/pg_config && \
    cp vector.so /tmp/vector-nosimd.so
```

The deployed image is `harbor.10.0.0.200.nip.io/library/postgresql:18.4.0-noavx512` (set in `postgresql-ai-values.yaml`, minicloud-ansible commit `9f2c2ab`). This image is required — any upgrade to a newer Bitnami postgresql image must be tested for AVX-512 usage before deploying.

**After rebuilding image, if the HNSW index was corrupted during a failed INSERT session:**
```bash
PG_PASS=$(kubectl get secret -n ai ai-postgresql-secret \
  -o jsonpath='{.data.password}' | base64 -d)

kubectl scale statefulset open-webui -n ai --replicas=0

kubectl exec -n ai postgresql-ai-0 -- \
  env PGPASSWORD="$PG_PASS" psql -U aiplatform -d ragdb \
  -c "DROP TABLE IF EXISTS document_chunk;"

kubectl scale statefulset open-webui -n ai --replicas=1
# Open WebUI recreates the table and HNSW index cleanly on startup
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
