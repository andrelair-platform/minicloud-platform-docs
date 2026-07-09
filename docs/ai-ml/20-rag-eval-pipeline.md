---
id: rag-eval-pipeline
title: RAG Evaluation Pipeline
sidebar_label: RAG Eval Pipeline
---

# RAG Evaluation Pipeline

Automated quality gate and continuous monitoring for the `phi3-financial` RAG pipeline (pgvector + BM25 French + HNSW + cross-encoder). Built as a reusable evaluation framework in the `minicloud-rag-eval` repo.

---

## Why a RAG evaluation pipeline

The RAG pipeline has more failure modes than a plain LLM call:

- **Retrieval failures** — the wrong chunks are returned (low precision) or key information is missed (low recall)
- **Hallucination** — the model answers using knowledge not present in the retrieved context
- **Chunk size drift** — changing `CHUNK_SIZE`, `TOP_K`, or the embedding model silently degrades retrieval quality
- **Embedding model regression** — a new embedding model may produce less relevant results on financial French text

Without a gate, any of these regressions reach production silently. The eval pipeline catches them at the ArgoCD sync step, before the change goes live.

---

## Architecture

```
minicloud-rag-eval (GHCR image)
       │
       ├─── Offline Eval (k8s Job, ArgoCD PostSync hook)
       │         every git push → ai namespace sync
       │         5 representative samples, fast mode (~30 min on CPU)
       │         exits 1 → ArgoCD marks sync Degraded → PrometheusAlert
       │
       └─── Online Sampler (k8s CronJob, every 15 min)
                 5% of recent phi3-financial production traces
                 faithfulness score attached to existing Langfuse trace
                 drift visible in Langfuse Scores tab
```

```
Developer pushes config change (chunk size, TOP_K, embedding model…)
        │
        ▼ ArgoCD syncs ai namespace
        │
        ▼ PostSync hook fires: Job rag-eval-postsync
        │
        ├─ Open WebUI /api/v1/retrieval/query/collection  × 5 samples
        │       BM25 French + HNSW pgvector + cross-encoder reranker
        │
        ├─ LiteLLM phi3-financial (phi4-mini on Ollama) × 5 samples
        │       sequential (_GENERATION_SEM=1), ~6 min/call on CPU
        │
        ├─ Ragas (GPT-4o judge via LiteLLM)
        │       faithfulness, answer_relevancy, context_precision, context_recall
        │
        ├─ Deterministic metrics
        │       ROUGE-L, hit_rate, MRR
        │
        ├─ Langfuse score POST per sample per metric
        │
        └─ CI gate: faithfulness ≥ 0.70 AND hit_rate ≥ 0.80
                PASS → ArgoCD Synced+Healthy
                FAIL → ArgoCD Degraded → alert fires
```

---

## Repository: `minicloud-rag-eval`

```
minicloud-rag-eval/
├── rag_eval/
│   ├── cli.py               # entrypoint: offline | online | generate-dataset
│   ├── offline.py           # orchestrates retrieve → generate → score → report
│   ├── retriever.py         # POST open-webui /api/v1/retrieval/query/collection
│   ├── generator.py         # POST litellm /v1/chat/completions (phi3-financial)
│   ├── ragas_runner.py      # Ragas batch eval: 4 LLM-as-judge metrics
│   ├── metrics.py           # ROUGE-L, hit_rate, MRR (deterministic, free)
│   ├── langfuse_reporter.py # POST langfuse /api/public/scores
│   └── online_sampler.py    # fetch traces → 5% sample → faithfulness score
├── Dockerfile               # python:3.11-slim, all deps baked in
├── pyproject.toml           # ragas, langchain-openai, rouge-score, langfuse
└── .github/workflows/ci.yml # build → push GHCR → cosign sign → gitops bump
```

**Image registry:** `ghcr.io/andrelair-platform/minicloud-rag-eval:<sha>-amd64`

ML/data images go to GHCR (not Harbor) because Cloudflare Tunnel caps request body size at ~100MB and ML images are typically 500MB–1GB.

---

## Metrics

### Ragas (LLM-as-judge, GPT-4o via LiteLLM)

| Metric | What it measures | Score range |
|---|---|---|
| `faithfulness` | Does the answer contain only information from the retrieved context? Hallucination check. | 0.0–1.0 |
| `answer_relevancy` | Does the answer actually address the question asked? | 0.0–1.0 |
| `context_precision` | Are the retrieved chunks relevant to the question? Measures retrieval precision. | 0.0–1.0 |
| `context_recall` | Does the retrieved context contain all information needed to answer? | 0.0–1.0 |

### Deterministic (free, no API call)

| Metric | What it measures | Score range |
|---|---|---|
| `rouge_l` | Longest common subsequence overlap between answer and ground truth. | 0.0–1.0 |
| `hit_rate` | Is the ground truth answer string present in any retrieved chunk? | 0 or 1 |
| `mrr` | Mean Reciprocal Rank — how high in the result list does the relevant chunk appear? | 0.0–1.0 |

### CI gate thresholds

```
faithfulness ≥ 0.70   (hard block — hallucination is the primary risk)
hit_rate     ≥ 0.80   (hard block — relevant chunks must be retrieved)
```

Other metrics are logged to Langfuse for trending but do not block the sync.

---

## Eval dataset

10 French financial Q&A samples across 4 domains, stored in a ConfigMap:

```
manifests/ai/eval/eval-dataset-configmap.yaml
```

| Domain | Count | Example question |
|---|---|---|
| `regulatory_capital` | 4 | Quel est le ratio CET1 de BNP Paribas Fortis en 2024 ? |
| `liquidity` | 2 | Quel est le ratio LCR minimum requis par les accords de Bâle ? |
| `profitability` | 2 | Quelle est la marge opérationnelle de LVMH en 2023 ? |
| `lvmh` | 2 | Quel est le chiffre d'affaires total de LVMH en 2023 ? |

Each sample has:
```json
{
  "id": "bnp-cet1-2024-01",
  "query": "Quel est le ratio CET1 de BNP Paribas Fortis en 2024 ?",
  "ground_truth": "14.0%",
  "source_doc": "BNP Paribas Fortis Annual Report 2024",
  "domain": "regulatory_capital"
}
```

**Fast mode (5 samples):** picks 2 from `regulatory_capital`, 1 from each other domain. Runs in ~30 min on CPU. Used by the PostSync hook.

**Full mode (10 samples):** all samples, ~60 min. For periodic deep evaluation.

---

## k8s manifests

Both manifests live in `minicloud-gitops/manifests/ai/` and are managed by the `litellm` ArgoCD app.

### Offline eval Job (PostSync hook)

```yaml
# manifests/ai/16-rag-eval-job.yaml
metadata:
  name: rag-eval-postsync
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  backoffLimit: 0          # no retry — fail fast, let ArgoCD mark Degraded
  template:
    spec:
      containers:
        - image: ghcr.io/andrelair-platform/minicloud-rag-eval:<sha>-amd64
          env:
            - name: EVAL_MODE
              value: offline
            - name: EVAL_FAST_MODE
              value: "true"    # 5 samples
            - name: JUDGE_MODEL
              value: gpt-4o
```

The image tag is bumped automatically by the `minicloud-rag-eval` CI on every push to `main`.

### Online sampling CronJob

```yaml
# manifests/ai/17-rag-eval-cronjob.yaml
spec:
  schedule: "*/15 * * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 0
      template:
        spec:
          containers:
            - image: ghcr.io/andrelair-platform/minicloud-rag-eval:<sha>-amd64
              env:
                - name: EVAL_MODE
                  value: online
                - name: SAMPLE_RATE
                  value: "0.05"          # 5% of recent traces
                - name: SAMPLING_WINDOW_MINUTES
                  value: "15"
```

---

## Secrets (ESO-managed)

```yaml
# manifests/eso-platform-secrets/11-rag-eval-credentials.yaml
# Vault path: secret/platform/rag-eval-credentials
```

| Secret key | Purpose |
|---|---|
| `litellm-api-key` | LiteLLM auth for generation + judge calls |
| `openwebui-api-key` | Open WebUI API key for retrieval calls |
| `langfuse-public-key` | Langfuse score POSTs |
| `langfuse-secret-key` | Langfuse score POSTs |

The `WEBUI_SECRET_KEY` is also pinned via ESO (`manifests/eso-platform-secrets/14-openwebui-secret-key.yaml`) so Open WebUI JWT tokens remain valid across pod restarts — without this, the eval job gets 401 after any Open WebUI restart.

---

## How to run manually

```bash
# 1. Port-forward Open WebUI and LiteLLM
kubectl --context minicloud port-forward -n ai svc/open-webui 8080:80 &
kubectl --context minicloud port-forward -n ai svc/litellm 4000:4000 &

# 2. Create a one-shot offline eval job
kubectl --context minicloud create job rag-eval-manual -n ai \
  --from=job/rag-eval-postsync

# 3. Watch logs
kubectl --context minicloud logs -n ai -l app=rag-eval -f

# 4. Kill port-forwards
kill %1 %2
```

Or trigger via ArgoCD — any sync of the `litellm` app fires the PostSync hook automatically.

---

## Reuse pattern for a new RAG project

The `minicloud-rag-eval` image is project-agnostic. To add evaluation to a new RAG project:

```
new-project-gitops/manifests/rag-eval/
├── rag-eval-job.yaml          # same image, different RAG_COLLECTION_UUID
├── rag-eval-cronjob.yaml      # same image
└── eval/
    ├── eval_dataset.json       # new domain Q&A pairs
    └── eval-dataset-configmap.yaml
```

Only three things differ: `RAG_COLLECTION_UUID`, `LANGFUSE_PROJECT_ID`, and `eval_dataset.json`. Zero changes to the `minicloud-rag-eval` image. Full eval pipeline for a new RAG project in ~30 min.

---

## Operational gotchas

### Open WebUI WEBUI_SECRET_KEY must be pinned
Open WebUI generates a random `WEBUI_SECRET_KEY` on startup if not set. Any pod restart invalidates all existing JWT tokens — the eval job gets 401 on every retrieval call. Fix: ESO ExternalSecret `openwebui-secret-key` (Vault `secret/platform/openwebui.webui-secret-key`) injects a stable key via `extraEnvFrom`.

### phi4-mini generation takes 6–7 min on CPU
`phi3-financial` routes to `ollama/phi4-mini` (phi4-mini with a financial system prompt injected by `LangfusePromptHandler`). phi4-mini is 3.6GB; CPU-only inference takes 350–420s per call. The eval job uses `_GENERATION_SEM = threading.Semaphore(1)` to run generations sequentially and avoid Ollama saturation.

### LiteLLM internal timeout is 300s; phi4-mini needs up to 420s
LiteLLM's internal per-deployment timeout fires at 300s and retries to the next deployment. If the second Ollama instance is also busy, the client sees a 504. The generator retries up to 3 times with 420s timeout each. With 3 Ollama instances (primary, secondary, tertiary), at least one is usually available.

### Langfuse /api/public/traces limit=100 causes 422
With `limit=100`, the Langfuse v3.201.1 traces endpoint runs a slow full-table DB scan, times out internally, and returns 422 "Unprocessable Entity". Fixed: use `limit=20` and add explicit `toTimestamp` to bound the scan to the 15-min sampling window.

### ArgoCD PostSync hook finalizer blocks deletion
The `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation` annotation tells ArgoCD to delete the previous hook job before creating a new one. If a job has a `hook-finalizer`, remove it manually before force-deleting:
```bash
kubectl patch job rag-eval-postsync -n ai --type json \
  -p '[{"op":"remove","path":"/metadata/finalizers"}]'
kubectl delete job rag-eval-postsync -n ai --force --grace-period=0
```

### Open WebUI OOMKill under concurrent reranking
The cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) runs in-process in the Open WebUI pod and uses ~500MB peak. More than 2 concurrent retrieval+rerank calls → OOMKill → `RemoteDisconnected`. Fixed: `_RETRIEVAL_SEM = threading.Semaphore(2)` and memory limit raised to `3Gi`.

---

## Langfuse scores

After each eval run, scores appear in **Langfuse → Scores** tab on the corresponding `phi3-financial` traces:

| Score name | Source |
|---|---|
| `rag_faithfulness` | Ragas (GPT-4o) |
| `rag_answer_relevancy` | Ragas (GPT-4o) |
| `rag_context_precision` | Ragas (GPT-4o) |
| `rag_context_recall` | Ragas (GPT-4o) |
| `rag_rouge_l` | Deterministic |
| `rag_hit_rate` | Deterministic |
| `rag_mrr` | Deterministic |
| `online_faithfulness` | Online CronJob (GPT-4o, 5% sample) |

The `online_faithfulness` metric is attached to existing production traces (not new ones) — it retrofits the score onto the trace that was already logged when the user made the real chat request.
