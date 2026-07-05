---
id: inference-optimization
title: Inference Optimization — CPU Tuning & Horizontal Scaling
sidebar_label: Inference Optimization
---

# Inference Optimization — CPU Tuning & Horizontal Scaling

**Phase complete:** 2026-07-05  
**Issue closed:** #41

## Hardware baseline

```
4× Intel Core i7-10510U (set-hog, fast-skunk, fast-heron, star-kitten)
├── 4 cores / 8 threads per node
├── 1.8 GHz base → 4.9 GHz turbo
├── 15.6 GB RAM per node
├── AVX2 ✅ (used automatically by llama.cpp inside Ollama)
└── No GPU — all optimizations are CPU-path only
```

## Part 1 — Ollama env var tuning

Applied to all three Ollama instances (primary on fast-heron, secondary on star-kitten, tertiary on fast-skunk):

```yaml
# Primary + secondary (7B model tier — full context)
OLLAMA_NUM_PARALLEL: "6"      # 6 concurrent requests per instance (raised from 4 on 2026-07-05)
OLLAMA_NUM_THREADS: "6"       # leave 2 threads for k8s node agent + OS
OLLAMA_MAX_LOADED_MODELS: "2" # keep 2 most-used models hot in RAM at once
OLLAMA_FLASH_ATTENTION: "1"   # reduced memory bandwidth on CPU attention path
OLLAMA_KV_CACHE_TYPE: "q8_0"  # 8-bit KV cache: half the memory of fp16
OLLAMA_NUM_CTX: "8192"        # raised from 4096 — gives deepseek-r1:7b think phase room (500–1500 tokens)

# Tertiary (light-model tier — fast-skunk, no 7B models)
OLLAMA_NUM_PARALLEL: "6"      # 6 concurrent requests
OLLAMA_NUM_CTX: "4096"        # lower context — light conversational use, more parallel headroom
```

Config is in `minicloud-ansible/helm-values/ollama-values.yaml`, `ollama-secondary-values.yaml`, and `ollama-tertiary-values.yaml`.

## Part 2 — CPU governor: performance mode

Intel i7-10510U throttles from 4.9 GHz turbo to 1.8 GHz base under sustained load in `powersave` mode. Setting `performance` keeps turbo boost active.

### Verify current governor on all nodes

```bash
for node in set-hog fast-skunk fast-heron star-kitten; do
  ssh $node "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
done
# All should return: performance
```

### How it was set (persistent across reboots)

A systemd unit `cpu-performance.service` was deployed on all 4 nodes:

```ini
[Unit]
Description=Set CPU governor to performance
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

```bash
# Verify service status on a node:
ssh fast-heron "systemctl status cpu-performance"
```

### Re-apply if needed (after a new node joins)

```bash
ssh <new-node> "cat > /etc/systemd/system/cpu-performance.service << 'EOF'
[Unit]
Description=Set CPU governor to performance
After=multi-user.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor'
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now cpu-performance"
```

## Part 3 — Horizontal scaling: three Ollama instances

Three independent Ollama Deployments, each pinned to a dedicated node (2026-07-05):

| Instance | Node | Service | Models | PVC | NUM_CTX |
|---|---|---|---|---|---|
| `ollama` | fast-heron | `ollama.ai.svc:11434` | all 7 (incl. 7B + vision) | local-path 10Gi | 8192 |
| `ollama-secondary` | star-kitten | `ollama-secondary.ai.svc:11434` | all 7 (incl. 7B + vision) | local-path 10Gi | 8192 |
| `ollama-tertiary` | fast-skunk | `ollama-tertiary.ai.svc:11434` | light only (1B + 3.8B + embed) | local-path 10Gi | 4096 |

LiteLLM routes across all three with `routing_strategy: least-busy`. The tertiary adds 6 concurrent slots for light workloads without competing with 7B inference.

### Total concurrent capacity (2026-07-05)

| What changed | Before | After |
|---|---|---|
| NUM_PARALLEL per instance | 4 | 6 |
| Ollama instances | 2 | 3 |
| Light-model slots (phi4-mini + llama3.2:1b) | 8 (4×2) | 18 (6×3) |
| deepseek-r1:7b | 40+ s on CPU | 5–8 s via DeepSeek cloud API (fallback: local) |
| Estimated concurrent users | ~20 | ~80–90 |

### Models per instance

```
Primary + Secondary (fast-heron, star-kitten):
  llama3.2:1b      (1.3 GB) — ultra-fast tier
  phi4-mini        (2.5 GB) — instruction following, Microsoft CPU-optimised
  phi3-financial   (2.2 GB) — financial domain specialist (local-only)
  qwen3.5:4b       (3.4 GB) — primary smart tier, native tool calling
  deepseek-r1:7b   (4.7 GB) — reasoning specialist (local fallback only)
  moondream        (1.7 GB) — vision: fast OCR + image description
  llava-phi3       (2.9 GB) — vision: detailed image analysis + document OCR

Tertiary (fast-skunk — light workloads only):
  llama3.2:1b      (1.3 GB) — ultra-fast tier
  phi4-mini        (2.5 GB) — instruction following
  nomic-embed-text (0.3 GB) — 768-dim embedding for RAG
```

**deepseek-r1:7b cloud routing:** The reasoning model routes to DeepSeek cloud API (5–8 s) as first choice. If the cloud is unavailable (balance, outage), LiteLLM automatically falls back to `deepseek-r1:7b-local` on the primary/secondary Ollama instances. The `fallbacks` block in `router_settings` handles this automatically — no client-side changes needed.

### Verify all three instances

```bash
kubectl exec -n ai deploy/ollama -- ollama list
kubectl exec -n ai deploy/ollama-secondary -- ollama list
kubectl exec -n ai deploy/ollama-tertiary -- ollama list
```

### Add a model to all three instances

Model pulls require a temporary egress NetworkPolicy (ai namespace has default-deny-egress).  
Use `podSelector: matchLabels: app.kubernetes.io/instance: <instance-name>` to target specific pods:

```bash
# Apply per-instance temp egress
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: temp-allow-model-pull
  namespace: ai
spec:
  podSelector: {}
  egress:
  - ports:
    - port: 443
    - port: 80
  policyTypes:
  - Egress
EOF

# Pull via REST (avoid interactive TTY)
kubectl port-forward -n ai deploy/ollama 11434:11434 &
kubectl port-forward -n ai deploy/ollama-secondary 11435:11434 &
kubectl port-forward -n ai deploy/ollama-tertiary 11436:11434 &

curl -s -X POST http://localhost:11434/api/pull -d '{"model":"<model-name>","stream":false}'
curl -s -X POST http://localhost:11435/api/pull -d '{"model":"<model-name>","stream":false}'
curl -s -X POST http://localhost:11436/api/pull -d '{"model":"<model-name>","stream":false}'

# Remove temp policy
kubectl delete networkpolicy temp-allow-model-pull -n ai
```

## Part 4 — Department tier routing

Virtual keys created in LiteLLM control which models each department can call:

| Tier | Departments | Local models | Cloud access | Budget/30d | TPM |
|---|---|---|---|---|---|
| **premium** | IT, Data Analytics, Actuariat, Transformation | all (incl. vision) | all cloud models | $100 | 200k |
| **standard** | Cybersecurity, Audit, Finance, Reinsurance, Juridique, Souscription, Commercial | phi3-financial, qwen3.5:4b, phi4-mini, llama3.2:1b, moondream | groq + deepseek + mistral-small + gpt-4o-mini + gemini-2.0-flash + hf-* | $30 | 100k |
| **basic** | Sinistres, Operations, RH, Services Généraux | phi3-financial, phi4-mini, llama3.2:1b | none | $5 | 50k |

All 15 keys persist in the `litellm` PostgreSQL database. Keys are stored at `~/.litellm-department-keys` (mode 600) on the controller.

### Verify a key's model restriction

```bash
kubectl port-forward -n ai svc/litellm 4000:4000 &

# Attempt a model the key doesn't have access to — should return 403
DEPT_KEY=$(grep direction-sinistres ~/.litellm-department-keys | awk '{print $2}')
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $DEPT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet","messages":[{"role":"user","content":"test"}]}'
# Expected: 403 — model not in basic tier allowlist
```

## Part 5 — Vision and multimodal capability

Two vision-language models are deployed alongside the text models:

| Model | Size | Best for |
|---|---|---|
| `moondream` | 1.7 GB | Fast image description, basic OCR, scene classification |
| `llava-phi3` | 2.9 GB | Detailed document analysis, structured form extraction, complex OCR |

### How to call a vision model

Vision requests use the standard OpenAI image_url format through LiteLLM:

```python
import openai, base64

client = openai.OpenAI(
    base_url="http://localhost:4000",   # LiteLLM gateway
    api_key="sk-direction-it-..."       # premium tier key — llava-phi3 access
)

# Base64-encode a local image
with open("invoice.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

response = client.chat.completions.create(
    model="llava-phi3",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            {"type": "text",
             "text": "Extract all text from this document as structured JSON."}
        ]
    }]
)
print(response.choices[0].message.content)
```

### Vision model limitations on CPU

- Image encoding adds 2–5 seconds before token generation starts (no GPU encoder).
- Maximum reliable image resolution: ~1024×1024 — larger images slow encoding significantly.
- Multi-image requests are not recommended in CPU mode (memory pressure).
- Neither model supports real-time video or streaming video frames.
- moondream handles basic printed text well; llava-phi3 handles handwritten text and complex layouts better.

## Part 6 — RAG pipeline: pgvector + nomic-embed-text + Open WebUI

Retrieval-Augmented Generation (RAG) allows Open WebUI to answer questions using uploaded documents. All components run on-cluster — no external embedding API needed.

### Architecture

```
User uploads document → Open WebUI chunks text (1500 tokens, 200 overlap)
    → nomic-embed-text (768-dim) via Ollama → pgvector HNSW index
                                                      ↓
User asks question → nomic-embed-text embeds query → pgvector cosine search (TOP_K=5)
    → retrieved chunks injected into context → LLM generates answer
```

### Components

| Component | Role | Config |
|---|---|---|
| nomic-embed-text (274 MB) | Embedding model — 768-dim vectors, best-in-class for CPU RAG | Pulled on both Ollama instances |
| postgresql-ai | pgvector 0.8.4 host — `ragdb` database | Existing pod, new DB |
| document_chunk table | HNSW index — m=16, ef_construction=64 | Created by Open WebUI on first start |
| Open WebUI | RAG orchestrator — chunking, embedding, retrieval, context injection | REVISION: 20 |

### Key configuration (open-webui-values.yaml)

```yaml
- name: VECTOR_DB
  value: "pgvector"
- name: PGVECTOR_DB_URL
  value: "postgresql://aiplatform:<password>@postgresql-ai.ai.svc.cluster.local:5432/ragdb"
- name: PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH
  value: "768"
- name: PGVECTOR_INDEX_METHOD
  value: "hnsw"
- name: PGVECTOR_HNSW_M
  value: "16"
- name: PGVECTOR_HNSW_EF_CONSTRUCTION
  value: "64"
- name: RAG_EMBEDDING_ENGINE
  value: "ollama"
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

`RAG_EMBEDDING_ENGINE: ollama` bypasses LiteLLM for embeddings — avoids polluting cost/spend metrics with internal embedding calls.

### Why HNSW instead of IVFFlat

pgvector 0.8.4 was compiled with SIMD instructions not supported on the ThinkPad i7-10510U (SIGILL during IVFFlat K-means build). HNSW uses a different code path that builds incrementally and does not trigger the SIGILL. Set `PGVECTOR_INDEX_METHOD=hnsw` in the Open WebUI env.

### How to use RAG in Open WebUI

1. Log in at `https://chat.devandre.sbs`
2. Start a new chat
3. Click the paperclip icon → upload a PDF, text, or CSV
4. Ask questions — Open WebUI retrieves the top 5 relevant chunks and injects them into the LLM context

### Verify the embedding chain

```bash
# Direct Ollama embedding (what Open WebUI uses internally)
kubectl port-forward -n ai svc/ollama 11434:11434 &
curl -s -X POST http://localhost:11434/api/embeddings \
  -d '{"model":"nomic-embed-text","prompt":"Kubernetes manages containers"}' | \
  python3 -c 'import sys,json; e=json.load(sys.stdin)["embedding"]; print(f"dims={len(e)}, ok")'
# Expected: dims=768, ok

# Via LiteLLM (for external API users)
curl -s -X POST http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer <direction-it-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"test"}' | \
  python3 -c 'import sys,json; r=json.load(sys.stdin); print(f"dims={len(r[\"data\"][0][\"embedding\"])}")'
# Expected: dims=768

# pgvector table status
kubectl exec -n ai postgresql-ai-0 -- psql postgresql://aiplatform:<pw>@localhost/ragdb \
  -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='document_chunk';"
```

## What is NOT possible on CPU-only nodes

Document these so engineers don't spend time investigating:

| Technique | Reason not available |
|---|---|
| CUDA / ROCm GPU acceleration | No NVIDIA/AMD GPU — Intel UHD 620 integrated only |
| vLLM PagedAttention | GPU VRAM management — not applicable on CPU |
| TensorRT / ONNX Runtime GPU | NVIDIA-only compilation target |
| Flash Attention v2 kernel | CUDA kernel — the `OLLAMA_FLASH_ATTENTION=1` env var uses a CPU-path approximation |
| AWQ / GPTQ inference | Require GPU for dequantization at inference time |
| Speculative decoding | Not yet natively supported by Ollama |

## Performance observed

After applying Parts 1–3:

| Scenario | Throughput |
|---|---|
| Single request (llama3.2:1b) | ~25–35 t/s |
| Single request (phi4-mini, 3.8B) | ~12–18 t/s |
| Single request (qwen3.5:4b) | ~10–15 t/s |
| Single request (deepseek-r1:7b) | ~6–10 t/s (includes think phase) |
| Vision request (moondream) | ~5–8 t/s + image encode time |
| Vision request (llava-phi3) | ~4–7 t/s + image encode time |
| 4 concurrent requests (before 2026-07-05) | All 4 start immediately (no queuing until 5th) |
| 6 concurrent requests per instance (after 2026-07-05) | All 6 start immediately (no queuing until 7th) |
| deepseek-r1:7b via cloud API | 5–8 s (vs 40+ s on CPU) |
| 18 concurrent light-model slots (3 instances × 6 parallel) | ~80–90 simultaneous users |
| Cold start after governor set | CPU stays at 3.5–4.9 GHz under sustained load |
