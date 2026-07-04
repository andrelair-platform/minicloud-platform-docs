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
OLLAMA_MAX_LOADED_MODELS: "2" # keep llama3.2:3b + phi3-financial hot in RAM
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
llama3.2:1b  (1.3 GB) — fast tier
llama3.2:3b  (2.0 GB) — standard/quality tier
phi3.5       (2.2 GB) — base for phi3-financial
phi3-financial (2.2 GB) — financial domain model
```

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

| Tier | Departments | Models | TPM limit |
|---|---|---|---|
| **High** | platform-admins, direction-it, direction-data-analytics | phi3-financial, llama3.2:3b, llama3.2:1b | 500K |
| **Medium** | direction-cybersecurity, direction-transformation, direction-actuariat, direction-audit | phi3-financial, llama3.2:3b | 200K |
| **Standard** | direction-sinistres, direction-operations, direction-finance, direction-reinsurance, direction-juridique, direction-souscription | phi3-financial, llama3.2:3b | 50K |
| **Fast (1b)** | direction-commercial, direction-rh, direction-services-generaux | llama3.2:1b | 50K |

All 16 keys persist in the `litellm` PostgreSQL database. Keys are stored at `~/.litellm-department-keys` (mode 600) on the controller.

### Verify a key's model restriction

```bash
MASTER_KEY=$(kubectl get secret -n ai litellm-credentials \
  -o jsonpath='{.data.master-key}' | base64 -d)
kubectl port-forward -n ai svc/litellm 4000:4000 &

# Attempt a model the key doesn't have access to — should return 403/401
DEPT_KEY=$(grep direction-commercial ~/.litellm-department-keys | awk '{print $2}')
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $DEPT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"test"}]}'
# Expected: 403 — model not allowed for this key
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
| Single request (llama3.2:3b) | ~12–18 t/s |
| Single request (llama3.2:1b) | ~25–35 t/s |
| 4 concurrent requests | All 4 start immediately (no queuing until 5th) |
| Cold start after governor set | CPU stays at 3.5–4.9 GHz under sustained load |
