---
id: inference-optimization
title: Inference Optimization — CPU Tuning & Horizontal Scaling
sidebar_label: Inference Optimization
---

# Inference Optimization — CPU Tuning & Horizontal Scaling

**Phase complete:** 2026-07-04  
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

Applied to both Ollama instances (primary on fast-heron, secondary on star-kitten):

```yaml
OLLAMA_NUM_PARALLEL: "4"      # 4 concurrent requests (8 threads / 2 per worker)
OLLAMA_NUM_THREADS: "6"       # leave 2 threads for k8s node agent + OS
OLLAMA_MAX_LOADED_MODELS: "2" # keep 2 most-used models hot in RAM at once
OLLAMA_FLASH_ATTENTION: "1"   # reduced memory bandwidth on CPU attention path
OLLAMA_KV_CACHE_TYPE: "q8_0"  # 8-bit KV cache: half the memory of fp16
OLLAMA_NUM_CTX: "4096"        # caps context — 4096 covers RAG TOP_K=5 @ 512t each
```

Config is in `minicloud-ansible/helm-values/ollama-values.yaml` and `ollama-secondary-values.yaml`.

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

## Part 3 — Horizontal scaling: dual Ollama

Two independent Ollama Deployments, each pinned to a dedicated node:

| Instance | Node | Service | PVC |
|---|---|---|---|
| `ollama` | fast-heron | `ollama.ai.svc:11434` | local-path 10Gi |
| `ollama-secondary` | star-kitten | `ollama-secondary.ai.svc:11434` | local-path 10Gi |

LiteLLM routes across both with `routing_strategy: least-busy` — requests always go to the instance with fewer active inference threads.

### Models on each instance

```
llama3.2:1b      (1.3 GB) — ultra-fast tier
phi4-mini        (2.5 GB) — instruction following, Microsoft CPU-optimised
phi3-financial   (2.2 GB) — financial domain specialist (local-only)
qwen3.5:4b       (3.4 GB) — primary smart tier, native tool calling
deepseek-r1:7b   (4.7 GB) — reasoning specialist (math, code, logic)
moondream        (1.7 GB) — vision: fast OCR + image description
llava-phi3       (2.9 GB) — vision: detailed image analysis + document OCR
```

**Model selection rationale (CPU-only):** On an i7-8565U/10510U with ~9 GB RAM available to Ollama, the 4–7B Q4_K_M range (Ollama default quantization) delivers the best quality-per-second. Models above 8B (fp16) would require swapping and become unusable at interactive speeds. Vision models (moondream, llava-phi3) are kept separate from text models — they load a vision encoder that is not needed for text-only requests.

Verify:

```bash
kubectl exec -n ai deploy/ollama -- ollama list
kubectl exec -n ai deploy/ollama-secondary -- ollama list
```

### Add a model to both instances

Model pulls require a temporary egress NetworkPolicy (ai namespace has default-deny-egress):

```bash
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

curl -s -X POST http://localhost:11434/api/pull \
  -d '{"model":"<model-name>","stream":false}'
curl -s -X POST http://localhost:11435/api/pull \
  -d '{"model":"<model-name>","stream":false}'

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
| 4 concurrent requests | All 4 start immediately (no queuing until 5th) |
| Cold start after governor set | CPU stays at 3.5–4.9 GHz under sustained load |
