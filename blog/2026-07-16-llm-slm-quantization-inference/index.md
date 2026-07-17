---
slug: llm-slm-quantization-inference-serving
title: "LLMs on Bare Metal: Quantization, SLMs, and Replacing phi4-mini with Qwen 2.5 7B"
authors: [andrelair]
tags: [ai, llm, ollama, litellm, kubernetes, inference, quantization, mlops]
date: 2026-07-16
description: "How we think about model size, quantization formats, and inference tuning for a 5-node CPU-only k3s cluster — and why we replaced phi4-mini with Qwen 2.5 7B Q4_K_M."
---

Running LLMs on bare-metal CPU hardware forces you to understand the numbers behind model files. This post documents how we reason about model size, quantization, and inference serving on minicloud — and the concrete change we made: replacing phi4-mini with Qwen 2.5 7B across all three Ollama instances.

{/* truncate */}

## What "7B" Actually Means

The "7B" in a model name is the number of parameters — floating-point weights stored in the neural network. Each parameter holds learned knowledge from training. More parameters generally means better reasoning, broader knowledge, and fewer hallucinations on complex tasks.

The catch: more parameters means more RAM.

| Size | RAM at FP32 (raw) | Typical use |
|---|---|---|
| 1–3B | 4–12 GB | Edge, mobile, very constrained hardware |
| 7B | 28 GB | The quality/resource sweet spot |
| 13B | 52 GB | Good reasoning, feasible on 48 GB GPU |
| 30–34B | ~120 GB | Multi-GPU or quantized on 24 GB |
| 70B | 280 GB | High-end multi-GPU or cloud |

Our cluster has no dedicated GPU — swift-mac has 8 GB RAM, ThinkPad workers have 16–32 GB. At FP32, even a 7B model is out of reach. This is where quantization becomes essential.

## Quantization — Why It Changes Everything

One FP32 parameter = 4 bytes. Quantization represents the same weight with fewer bits, accepting a small precision loss in exchange for dramatically lower memory usage.

```
FP32   → 4 bytes/param  → 7B model = 28 GB   (baseline)
FP16   → 2 bytes/param  → 7B model = 14 GB
Q8_0   → 1 byte/param   → 7B model =  7 GB
Q4_K_M → ~0.5 bytes/param → 7B model = 4.1 GB  ← most popular
Q2_K   → ~0.25 bytes/param → 7B model = 2.7 GB  (notable quality loss)
```

The quality loss from Q4_K_M vs FP16 is measurable on benchmarks but imperceptible in practical use for chat and RAG. Q2 and Q3 are a different story — avoid them for anything that requires accurate reasoning.

**Rule of thumb:** step down one quantization level before stepping down to a smaller model. A 7B Q4 beats a 3B Q8 on almost every task.

### The Format Zoo

You'll encounter four main formats depending on your runtime:

- **GGUF** (llama.cpp / Ollama) — CPU-first format with optional GPU offloading. Suffixes like `Q4_K_M`, `Q5_K_M`, `Q8_0` tell you the quantization level. This is what Ollama uses.
- **GPTQ** — GPU-oriented post-training quantization. Better than GGUF if you have sufficient VRAM.
- **AWQ** — Activation-aware Weight Quantization. Better quality than GPTQ at the same size, increasingly standard.
- **EXL2** — ExLlamaV2 format, very efficient for GPU batch inference.

For a CPU-only or CPU-primary cluster: GGUF Q4_K_M is your format.

## SLM Candidates — The Real Options Under 8B

Small Language Models (≤7B) have caught up dramatically since 2024. These are the relevant ones for a constrained inference cluster:

| Model | Size | Strengths | Best for |
|---|---|---|---|
| phi4-mini (Microsoft) | 3.8B | Strong reasoning for its size | RAG, factual Q&A — we had it running |
| Llama 3.2 3B | 3B | Good instruct, multilingual | Chat, summarization |
| Llama 3.1 8B | 8B | Quality reference for 7-8B | General purpose |
| Gemma 3 4B | 4B | Excellent code + instruction following | Code assistant |
| Mistral 7B v0.3 | 7B | Strong French natively, long context | French-speaking users |
| Qwen 2.5 7B | 7B | Top-ranked 7B on recent benchmarks | General purpose — our choice |
| deepseek-r1 7B (distilled) | 7B | Chain-of-thought reasoning | Analytical tasks |

## Why We Replaced phi4-mini

phi4-mini isn't a bad model — Microsoft did good work on reasoning at 3.8B. But it has two structural limits:

**3.8B is the quality ceiling.** At 3.8B parameters, the model has less "memory" of training patterns. It hallucinates more on precise facts, multi-step reasoning degrades faster, and complex instruction following is less reliable than a 7B.

**The market moved.** In 2024–2025, 7B models became what 13B models were in 2023. Qwen 2.5 7B in particular outperforms phi4-mini on nearly every benchmark while fitting in the same RAM constraint once quantized.

The comparison that made the decision clear:

| Model | MMLU | HumanEval | French | RAM at Q4_K_M |
|---|---|---|---|---|
| phi4-mini 3.8B | 69% | 62% | Passable | 2.5 GB |
| Mistral 7B v0.3 | 64% | 45% | Native | 4.1 GB |
| Llama 3.1 8B | 73% | 72% | Good | 4.7 GB |
| **Qwen 2.5 7B** | **75%** | **83%** | **Excellent** | **4.5 GB** |

Qwen 2.5 is natively trained on 29 languages including French. For French-speaking end users interacting with Open WebUI, that's a direct advantage over Llama.

## What Metrics Actually Matter for Inference Serving

Three metrics to optimize, depending on the use case:

**Time To First Token (TTFT)** — latency before the user sees the first word. Critical for interactive chat. Smaller models win here. Groq's LPU hardware achieves TTFT < 200ms even on 8B models.

**Tokens per second (throughput)** — generation speed. GPU >> CPU. On CPU, phi4-mini Q4 generates ~15 tok/s on a ThinkPad, Llama 3.1 8B ~6 tok/s.

**Concurrency** — how many simultaneous users. Ollama handles one request at a time per instance by default. For multi-user, you need multiple instances (we have three) or a batching server like vLLM.

### Decision Matrix

```
User expects response in < 2s?
├── Yes → Groq (cloud LPU) or phi4-mini local Q4
└── No  → Llama 3.1 8B Q4 or Qwen 2.5 7B Q4

Task requires reasoning (math, analysis)?
├── Yes → deepseek-r1 distill or phi4-mini (strong on reasoning)
└── No  → Mistral 7B or Llama 3.2 3B (faster, cheaper)

French-speaking users?
├── Yes → Mistral 7B (native FR) or Llama 3.1 8B (solid multilingual)
└── No  → Qwen 2.5 7B or Gemma 3 4B
```

## Tuning Ollama for CPU Inference

Beyond the model choice, there are several environment variables that have immediate impact.

### Keep the Model Loaded

The most impactful single change: set `OLLAMA_KEEP_ALIVE=-1` so the model is never unloaded from RAM. Without this, Ollama evicts the model after 5 minutes of inactivity — the next request pays a 3–5 second cold start penalty while the model reloads.

```yaml
env:
  - name: OLLAMA_KEEP_ALIVE
    value: "-1"
```

### Flash Attention

Reduces KV cache memory usage and speeds up the attention computation:

```yaml
  - name: OLLAMA_FLASH_ATTENTION
    value: "1"
```

Gain: ~15–20% less RAM, ~10% faster on longer contexts.

### Context Window — the Most Underrated Lever

Ollama defaults to loading the model's maximum context window (128k for Qwen 2.5). The KV cache grows linearly with context length. For standard chat, you don't need 128k tokens.

Forcing `num_ctx=4096` in the LiteLLM params:

```yaml
litellm_params:
  model: ollama/qwen2.5:7b-instruct-q4_k_m
  api_base: http://ollama.ai.svc.cluster.local:11434
  num_ctx: 4096
```

Impact: going from `num_ctx=32768` to `num_ctx=4096` can **double throughput** on CPU by reducing the amount of memory the model reads per token generation step.

### CPU Threads — Align With Physical Cores

Ollama uses all available cores by default, but hyperthreading can hurt inference (two logical threads on the same physical core compete for the same ALU). Set threads to physical core count:

```yaml
  - name: OLLAMA_NUM_THREADS
    value: "6"   # physical cores, not logical — avoids hyperthreading overhead
```

### Parallelism and Loaded Models

```yaml
  - name: OLLAMA_NUM_PARALLEL
    value: "4"   # max concurrent requests per instance
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "2"   # keep at most 2 models in RAM simultaneously
  - name: OLLAMA_KV_CACHE_TYPE
    value: "q8_0"  # quantize the KV cache itself — saves RAM during long conversations
```

### Summary: What Each Tuning Gains

| Optimization | Estimated gain on ThinkPad CPU |
|---|---|
| `OLLAMA_KEEP_ALIVE=-1` | −3–5s cold start per request |
| `num_ctx: 4096` instead of 32k | ×1.8–2× tokens/s |
| `OLLAMA_FLASH_ATTENTION=1` | −15–20% RAM, +10% speed |
| `OLLAMA_NUM_THREADS=6` (physical cores) | +5–10% stability under load |
| 3 LiteLLM load-balanced instances | ×3 simultaneous users |
| phi4-mini → Qwen 2.5 7B Q4 | +15–20% quality on benchmarks |

## What We Actually Did on minicloud

All three Ollama instances (`ollama`, `ollama-secondary`, `ollama-tertiary` in the `ai` namespace) already had all the environment variables set from a previous tuning session. The only missing piece was the model itself.

The model pull from inside a pod was blocked: the default-deny-egress NetworkPolicy and a routing difference between pod-level and node-level IPv4 traffic to Cloudflare R2 caused `connection refused` on `172.64.66.x:443`. The node itself could reach the registry fine, but the CNI (flannel) traffic path from pod IPs didn't work the same way.

**Workaround used:** temporarily patched `hostNetwork: true` on all three deployments. This makes the pod use the node's network namespace directly, bypassing CNI. The node can reach registry.ollama.ai — so the pull works.

```bash
# Add hostNetwork temporarily
kubectl patch deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/hostNetwork","value":true}]'

# Pull the model (4.7 GB per instance)
kubectl exec -n ai deployment/ollama -- ollama pull qwen2.5:7b-instruct-q4_k_m
kubectl exec -n ai deployment/ollama-secondary -- ollama pull qwen2.5:7b-instruct-q4_k_m
kubectl exec -n ai deployment/ollama-tertiary -- ollama pull qwen2.5:7b-instruct-q4_k_m

# Remove hostNetwork — pods restart with normal CNI networking
kubectl patch deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --type=json \
  -p '[{"op":"remove","path":"/spec/template/spec/hostNetwork"}]'
```

The model files are stored on a PVC, so they persist across pod restarts. After removing `hostNetwork`, all three instances came back up with `qwen2.5:7b-instruct-q4_k_m` cached locally — and LiteLLM started routing to it immediately.

The underlying networking issue (pod-to-Cloudflare IPv4 path via flannel) is a known limitation. **Phase 76 will replace flannel with Cilium**, which adds FQDN-based egress policies and Hubble observability — making this kind of debugging trivial next time.

## What's Next

With Qwen 2.5 7B running on all three instances and LiteLLM routing traffic via least-busy, the AI stack is:

- **phi3-financial pipeline**: Groq `llama-3.1-8b-instant` as primary (LPU-fast), Qwen 2.5 7B ×3 as local fallback
- **Open WebUI chat**: Qwen 2.5 7B for general use, deepseek-r1 7B for reasoning tasks
- **RAG ingest**: `nomic-embed-text` for embeddings (unchanged)

The speculative decoding optimization (a small draft model pre-generates tokens that the main model verifies) is available in Ollama v0.5+ and could push throughput 2–3× further on predictable outputs. That's the next tuning frontier once this setup is stable.
