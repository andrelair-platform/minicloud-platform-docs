---
slug: vllm-vs-ollama-enterprise-inference
title: "Why Enterprises Should Run vLLM Instead of Ollama for AI Inference"
authors: [andrelair]
tags: [ai, llm, vllm, ollama, inference, kubernetes, enterprise, mlops, self-hosted]
date: 2026-08-02
description: "Ollama is a great developer tool. vLLM is what you run when real users are waiting. Here is exactly why the difference matters — and what changes when you move from one to the other."
---

Ollama is how most teams first run a large language model locally. You install it in five minutes, run `ollama pull mistral`, and you have a working API. It feels like magic.

Then you try to serve ten users at once. Or a hundred. Or you need to audit every request for compliance. Or your legal team asks where the data goes. That is when you realise Ollama was built for something else entirely.

{/* truncate */}

## Ollama Is a Developer Tool

This is not a criticism. Ollama is genuinely excellent at what it is designed for: making it effortless for a single developer to run a model locally for experimentation, prototyping, and exploration. The model management, the simple CLI, the one-command API server — all of it is optimised for the experience of one person on one machine.

The problem starts when you try to carry that tool into production.

### One request at a time

Ollama processes requests sequentially. If two users send a prompt at the same moment, the second one waits for the first to finish completely before a single token is generated for them.

On a fast GPU this might add a second or two of latency. On a CPU cluster — which is where most self-hosted deployments actually run — a 7B model can take 30 to 60 seconds to generate a response. With sequential processing, ten concurrent users means user ten waits up to ten minutes.

This is not a configuration issue. It is a design choice appropriate for its target use case: a developer who sends one request at a time.

### Memory that cannot be shared

Every active Ollama request reserves its own slice of GPU or system memory for the key-value cache — the data structure that stores the model's "memory" of the current conversation. When the request finishes, that memory is freed.

There is no mechanism for Ollama to let requests share GPU memory intelligently, to page out inactive contexts, or to reuse cached attention states across requests with the same prefix. Each request starts from scratch.

### No production observability

Ollama exposes no Prometheus metrics, no structured request logs, no latency histograms, no token throughput counters. You cannot build an SLO dashboard around it. You cannot alert on p99 latency or set up autoscaling based on queue depth. You cannot audit which user sent which prompt.

For a personal laptop, none of this matters. For a system processing requests from a company's employees, all of it matters.

---

## vLLM Is an Inference Engine

vLLM was built at UC Berkeley and is maintained by a team whose sole focus is serving language models efficiently in production. Every design decision is oriented around throughput, latency, and resource utilisation under real concurrent load.

### Continuous batching

This is the most important difference.

Traditional inference servers (including Ollama) process a batch of requests, wait for all of them to finish, then start the next batch. This means fast requests waste time waiting for slow ones in the same batch.

vLLM uses **continuous batching** (also called iteration-level scheduling). The moment any request in the current batch finishes generating a token, a new request from the queue immediately takes its slot. The GPU never waits. Every compute cycle is spent generating tokens for someone.

The practical result: under concurrent load, vLLM serves between 10 and 50 times more tokens per second than a sequential server on the same hardware. This is not marketing copy — it is the measured result of replacing batch boundaries with continuous scheduling.

```
Ollama (sequential):
  User 1: [========== 8s ==========]
  User 2:                            [========== 8s ==========]
  User 3:                                                       [== 8s ==]
  Total time for 3 users: 24s

vLLM (continuous batching):
  User 1: [========== 8s ==========]
  User 2:     [========== 8s ==========]
  User 3:         [========== 8s ==========]
  Total time for 3 users: ~10s
```

### PagedAttention

The key-value cache for a long conversation can be several gigabytes. Managing this naively — allocating a large contiguous block per request, holding it for the full duration — wastes most of the allocated memory most of the time.

vLLM implements **PagedAttention**: it treats the KV cache like virtual memory in an operating system, dividing it into fixed-size pages and allocating only the pages actually needed at each decoding step. Pages from completed requests are immediately reclaimed and reused.

The result is that vLLM can serve three to four times as many concurrent conversations in the same GPU memory as a naive implementation. On a 24 GB GPU running a 7B model, the difference between wasting and efficiently paging that memory is the difference between four concurrent users and sixteen.

### OpenAI-compatible API — identical to what you already use

vLLM exposes the exact same HTTP API as OpenAI: `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`. If your application already calls the OpenAI API, it calls vLLM without any code change.

In a LiteLLM proxy configuration, switching from a cloud model to a self-hosted vLLM instance is a single config change:

```yaml
# Before: cloud API
- model_name: qwen2.5:7b
  litellm_params:
    model: groq/llama-3.1-8b-instant
    api_key: os.environ/GROQ_API_KEY

# After: self-hosted vLLM — same proxy, same API surface, no application changes
- model_name: qwen2.5:7b
  litellm_params:
    model: openai/Qwen/Qwen2.5-7B-Instruct
    api_base: http://vllm.ai.svc.cluster.local:8000/v1
    api_key: token-local
```

All guardrails, Langfuse tracing, PII masking, and rate limiting continue to work identically.

### Production-grade observability out of the box

vLLM exposes a Prometheus `/metrics` endpoint that includes:

| Metric | What it tells you |
|--------|-------------------|
| `vllm:num_requests_running` | Active concurrent requests |
| `vllm:num_requests_waiting` | Queue depth — leading indicator of saturation |
| `vllm:gpu_cache_usage_perc` | KV cache utilisation — when this hits 90%, you need more memory |
| `vllm:time_to_first_token_seconds` | p50/p99 time-to-first-token — the user-facing latency metric |
| `vllm:request_success_total` | Request success rate by model |
| `vllm:num_tokens_generated` | Token throughput |

You can build a complete Grafana dashboard, set SLO alerts, and wire autoscaling from these metrics. With Ollama you cannot.

### Multi-GPU tensor parallelism

If you run a model that does not fit in one GPU's memory, vLLM distributes the model's weights across multiple GPUs automatically using tensor parallelism. You set `tensor_parallel_size: 2` and the 70B model that needs 40 GB fits across two 24 GB cards.

Ollama does not support this.

---

## The Enterprise Requirements vLLM Meets

Beyond raw performance, vLLM satisfies requirements that appear in enterprise procurement checklists and security audits.

### Data sovereignty

When vLLM runs inside your Kubernetes cluster, no data leaves your network. Prompts, completions, user identifiers — none of it touches an external API. You can demonstrate this with network policies and egress logs, which is exactly what a CISO or a French ACPR compliance officer will ask for.

Cloud APIs — even enterprise-tier ones with DPAs — require you to trust the provider's infrastructure. Self-hosted vLLM removes that dependency entirely.

### Audit trail

vLLM logs every request with token counts, latency, and model ID. Feeding these logs into your observability stack (Loki, Elasticsearch) gives you a complete audit log: which user sent what, when, how long it took, how many tokens were consumed.

For regulated industries (finance, insurance, healthcare), the ability to produce this log on demand is often a legal requirement.

### No vendor lock-in

vLLM runs any Hugging Face model — Mistral, Llama, Qwen, Phi, Gemma, Falcon, DeepSeek. You switch models by changing the `model` argument. You are not bound to any commercial provider's model selection, pricing changes, or API deprecation schedule.

### RBAC integration

vLLM's API key mechanism integrates with your existing IAM. In a Kubernetes deployment behind LiteLLM, you add a virtual key per team or role, set rate limits and model allowlists per key, and enforce them at the proxy layer — all without touching vLLM's configuration.

---

## When Ollama Still Makes Sense

Ollama is not obsolete. It remains the right tool for:

- **A developer running models locally** on a laptop during development
- **Exploring a new model** before deciding whether to deploy it to production
- **A small team** (< 5 people) with no concurrent request requirement
- **CPU-only hardware** where you value ease of setup over throughput

The moment you have more than one user, a compliance requirement, or a throughput target, you have outgrown it.

---

## Deployment on Kubernetes

A minimal vLLM deployment on Kubernetes with a single GPU looks like this:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - --model
            - Qwen/Qwen2.5-7B-Instruct
            - --tensor-parallel-size
            - "1"
            - --max-model-len
            - "4096"
            - --served-model-name
            - qwen2.5:7b
          resources:
            limits:
              nvidia.com/gpu: "1"
              memory: 20Gi
            requests:
              nvidia.com/gpu: "1"
              memory: 16Gi
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 60
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: vllm
  namespace: ai
spec:
  selector:
    app: vllm
  ports:
    - port: 8000
      targetPort: 8000
```

Add a ServiceMonitor and Prometheus scrapes `/metrics`. Add a LiteLLM entry and your existing applications route to it transparently. The migration from cloud API to on-premise inference is a one-line config change.

---

## Summary

| | Ollama | vLLM |
|---|---|---|
| Target use case | Developer laptop | Production serving |
| Concurrent requests | Sequential (1 at a time) | Continuous batching (N at a time) |
| KV cache management | Per-request allocation | PagedAttention (shared pages) |
| Throughput vs. Ollama | 1× | 10–50× under load |
| Prometheus metrics | None | Full histogram suite |
| Multi-GPU | No | Tensor parallelism |
| OpenAI-compatible API | Yes | Yes |
| Data sovereignty | Yes (local) | Yes (local) |
| Audit logging | None | Full request log |
| Production readiness | No | Yes |

Ollama is how you start. vLLM is how you scale. The good news: if you built your application on top of an OpenAI-compatible API (directly or through a proxy like LiteLLM), switching between them is a configuration change, not a rewrite.
