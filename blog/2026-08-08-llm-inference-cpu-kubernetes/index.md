---
slug: llm-inference-cpu-kubernetes
title: "We Replaced Ollama With vLLM on CPU-Only Kubernetes — Here Is What Changed"
authors: [andrelair]
tags: [ai, llm, vllm, ollama, inference, kubernetes, cpu, self-hosted, mlops, enterprise, data-sovereignty]
date: 2026-08-08
description: "We ran Ollama in production on bare-metal ThinkPads with no GPU. Then we replaced it with vLLM. This is the honest account of what broke, what improved, and what the right tool actually is for CPU-only inference in a real cluster."
---

Most write-ups about vLLM versus Ollama assume you have a GPU. The benchmarks show impressive VRAM utilisation. The architecture diagrams include CUDA drivers. The recommendation — vLLM wins — comes with an implicit asterisk: *assuming you have the hardware for it*.

We did not. Our inference cluster is four ThinkPad laptops, each with an i7-8565U (4 cores, 8 threads, up to 4.6 GHz turbo), 16 GB of RAM, and no GPU of any kind. We ran Ollama first. Then we replaced it with vLLM. This is the honest account of that migration: what broke, what improved, and what the tradeoffs actually look like when you run LLM inference on commodity x86 CPUs.

{/* truncate */}

## Why We Started With Ollama

Ollama's appeal is real. You pull a model in one command, you get an OpenAI-compatible API, and it works immediately. For a single developer querying a model locally, or for a small team validating whether a self-hosted model is useful at all, there is nothing faster to get started with.

We deployed Ollama as two instances — primary on one ThinkPad, secondary on another — and placed LiteLLM in front of them as a proxy. This gave us model routing, virtual API keys, and Langfuse tracing from day one, without Ollama needing to provide any of those features itself. The setup was intentional: we knew Ollama was not a production server, so we compensated at the proxy layer.

For low concurrency it worked. A single user asking a question about a financial document got a response in 15–25 seconds for a 4B model. Acceptable for internal tooling where users understood the latency.

Then we tried to use it for anything beyond that.

---

## What Broke Under Real Load

### Sequential processing is not a configuration issue

Ollama processes one request at a time. When a second request arrives while the first is still generating, it waits. Not in a queue that feeds continuously — it waits for the entire first response to complete before a single token is generated for the second user.

On a CPU with a 4B model taking 20 seconds to respond, two simultaneous users means one of them waits 40 seconds. Five simultaneous users means the last one waits nearly two minutes before their response starts. This is not something you tune away. It is the architecture.

For a RAG pipeline that calls the model in a loop — one call to rerank chunks, one to synthesise an answer, one to generate a follow-up question — you are serialising what should be parallel work. Three sequential calls on a 20-second model is a minute of wall-clock time for a single user query.

### No metrics, no visibility

Ollama exposes nothing to Prometheus. No queue depth. No time-to-first-token. No token throughput. No error rates.

When a model started responding slowly — which happened regularly as the loaded model competed for memory with other cluster workloads — we had no signal from Ollama itself. We saw latency spikes in Langfuse traces (because every LiteLLM call was traced), but we could not distinguish between "Ollama is slow" and "the model is doing something computationally expensive" or "the node is memory-constrained". The lack of internal metrics made capacity planning impossible.

### Memory pressure without visibility

A 4B model at 4-bit quantisation is roughly 2.5 GB in memory. Loading two models simultaneously — which Ollama will do if `OLLAMA_MAX_LOADED_MODELS` is set above one — consumes 5+ GB of system RAM just for model weights. On a 16 GB node running k3s, Longhorn iSCSI, and various other pods, this leaves limited headroom.

Ollama does not tell you its current memory usage in any structured way. You can see the process memory in `kubectl top`, but you cannot see the split between model weights, KV cache, and pending request buffers. When the node started evicting pods due to memory pressure, we found out from Kubernetes events rather than from Ollama.

---

## The Migration to vLLM

vLLM v0.6.6 supports CPU inference via `--device=cpu`. It is not the primary use case — the vLLM team optimises heavily for NVIDIA CUDA — but the CPU backend is functional and receives the same continuous batching and PagedAttention logic as the GPU path.

Our deployment targets the same fast-heron node (i7-8565U, 16 GB RAM) that previously ran Ollama primary:

```yaml
containers:
  - name: vllm
    image: docker.io/vllm/vllm-openai:v0.6.6
    args:
      - --model=microsoft/Phi-3-mini-4k-instruct
      - --device=cpu
      - --dtype=float16
    env:
      - name: VLLM_CPU_KVCACHE_SPACE
        value: "2"
    resources:
      requests:
        cpu: 2000m
        memory: 6Gi
      limits:
        cpu: 7000m
        memory: 14Gi
```

A few decisions worth explaining:

**`--dtype=float16` on CPU.** CPU inference with float16 works on modern x86 via AVX-512 or AVX2 instructions. The i7-8565U supports AVX2. Using float16 rather than float32 halves the model size in memory and reduces the arithmetic cost per token.

**`VLLM_CPU_KVCACHE_SPACE=2`.** This reserves 2 GB of RAM for the KV cache. On CPU, PagedAttention manages this allocation across concurrent requests. Without this setting, vLLM defaults to a conservative allocation that limits concurrency unnecessarily.

**7 CPU cores allocated.** We leave one core for the OS, k3s agent, and other system processes. vLLM uses all allocated cores for parallel attention computation and tensor operations across the model's layers.

---

## What Actually Improved

### Concurrent requests work

This is the primary reason for the migration. vLLM's continuous batching means that as soon as one request finishes a decoding step, the next request in the queue gets scheduled. Multiple users can be actively receiving tokens simultaneously rather than waiting in a strict serial queue.

For a RAG pipeline making multiple model calls per user query, this matters enormously. The LiteLLM proxy can dispatch three calls and receive responses as they complete, rather than waiting for each to finish before issuing the next.

### Prometheus metrics are real

vLLM's `/metrics` endpoint provides everything needed to operate the service properly:

```
vllm:num_requests_running          # active concurrent requests right now
vllm:num_requests_waiting          # queue depth — leading saturation indicator
vllm:gpu_cache_usage_perc          # KV cache utilisation (same metric, works for CPU)
vllm:time_to_first_token_seconds   # p50/p99 TTFT histograms
vllm:request_success_total         # request success rate by model
vllm:num_tokens_generated          # total throughput
```

We added a ServiceMonitor and Prometheus now scrapes these every 15 seconds. When latency spikes, we have the queue depth and cache utilisation to diagnose whether the cause is request volume, memory pressure, or model behaviour. This was simply not possible with Ollama.

### Fine-tuned model serving

We ran a QLoRA fine-tuning job in Google Colab to produce a phi3-financial adapter — a Phi-3-mini-4k-instruct base with a LoRA adapter trained on financial domain data. vLLM can load LoRA adapters and serve them as named models alongside the base:

```yaml
args:
  - --model=microsoft/Phi-3-mini-4k-instruct
  - --enable-lora
  - --lora-modules
  - phi3-financial-ft=/model-cache/phi3-financial-lora
```

Ollama has no equivalent. If you want to serve a fine-tuned model with Ollama, you must convert it to GGUF format and create a Modelfile. vLLM loads the HuggingFace-format LoRA adapter directly, with no conversion step.

---

## The Real Tradeoffs on CPU

Being honest about what you give up matters as much as what you gain.

**Time to first token is slower.** On a GPU, a 3B model generates first tokens in 200–500ms. On our i7-8565U with vLLM, it is 3–8 seconds depending on prompt length. For interactive chat this is noticeable. For document processing pipelines where the result matters more than the wait, it is acceptable.

**Throughput ceiling is lower.** A single CPU node running vLLM with a 3B model handles roughly 4–8 tokens per second for a single request. A mid-range GPU handles 50–200 tokens per second. We compensate by sizing models conservatively (phi3-mini at 3.8B rather than llama3 at 8B) and routing heavy requests to cloud APIs via LiteLLM when local throughput is insufficient.

**One model at a time is practical.** Loading two different models simultaneously on a 16 GB CPU node leaves insufficient headroom for the KV cache when concurrent requests arrive. We run vLLM with a single model loaded and handle model diversity through LiteLLM routing to cloud providers.

**Startup is slow.** vLLM on CPU takes 90–120 seconds to initialise — it loads model weights into memory, quantises where applicable, and warms up the attention kernels. We set `initialDelaySeconds: 120` on the readiness probe. During rolling updates, old pods must stay live until the new pod is ready, which means 2–3 minutes of overlap where both pods are running and consuming memory.

---

## The Architecture After Migration

```
LiteLLM Gateway
      │
      ├── vLLM (fast-heron, CPU, Phi-3-mini) ← local fine-tuned model, data stays on-cluster
      │
      ├── Groq             ← auto-fallback for general queries when local is saturated
      ├── DeepSeek         ← reasoning tasks
      ├── Mistral / GPT-4o ← premium tier
      └── Gemini / Claude  ← premium tier
```

vLLM handles the local inference that must stay on-cluster — the fine-tuned domain model and any request where data sovereignty matters. Cloud providers handle general-purpose queries and premium-tier requests where latency or capability matters more than locality.

LiteLLM routes transparently between them. When a department's key reaches its cloud budget, requests stay local. When local is saturated (queue depth > threshold via KEDA ScaledObject), the proxy escalates to the cloud fallback. The application layer sees a single API endpoint throughout.

---

## Should You Do This?

CPU inference with vLLM is viable for models up to 4B parameters on hardware with 16 GB of RAM, when your primary requirements are data sovereignty, correct concurrent request handling, and production observability — and your secondary requirement is throughput.

It is not the right tool if users expect sub-second responses, if you need to serve 7B+ models locally, or if you have the budget for even a single consumer GPU. An RTX 3090 at €800 would give you 10–20× the throughput of a ThinkPad i7 for LLM inference.

But if you are running on commodity hardware, have a genuine data sovereignty requirement, and need a system you can actually operate — with metrics, with concurrent requests, with LoRA adapter support — vLLM on CPU is significantly better than Ollama in the same position.

The migration from Ollama to vLLM was not about GPU. It was about replacing a developer tool with a production server. The CPU happened to be the only hardware available. The improvement was real regardless.
