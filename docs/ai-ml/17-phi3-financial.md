---
id: phi3-financial
title: phi3-financial — Domain Specialization via System Prompt Engineering
sidebar_label: phi3-financial Model
---

# phi3-financial — Domain Specialization via System Prompt Engineering

`phi3-financial` is a domain-restricted financial assistant model deployed on minicloud's Ollama instances. It is built on top of Microsoft's `phi3.5` base model using **system prompt engineering via Ollama Modelfile** — not fine-tuning.

Live at: `https://chat.devandre.sbs` → select `phi3-financial` in the model picker.

---

## The approach: prompt-based domain specialization

The model's weights are **identical** to the base `phi3.5`. No training was performed, no gradient updates were applied, and no GPU was needed. Specialization comes entirely from a baked-in system prompt and inference parameter tuning registered through Ollama's `Modelfile` mechanism.

### Modelfile

```dockerfile
FROM phi3.5

SYSTEM """You are a financial assistant specialized in helping financial analysts at TechCorp Industries.
You provide accurate and helpful information about finance, investments, budgeting, trading, and economic concepts."""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_predict 1024
PARAMETER repeat_penalty 1.1
```

```bash
ollama create phi3-financial -f /tmp/Modelfile
# ID: 6109eeca3631  Size: 2.2 GB
```

Ollama bakes the system prompt into the model's context window at every inference call and registers the result as a named model. The `phi3.5` base (2.2 GB) stays on disk once; `phi3-financial` is a thin wrapper on top of it at no additional storage cost.

### What each parameter does

| Parameter | Value | Why |
|---|---|---|
| `temperature` | `0.1` | Low = deterministic, factual. Reduces hallucinated numbers and confident-but-wrong financial figures. |
| `top_p` | `0.9` | Nucleus sampling — allows fluent phrasing while keeping token selection conservative. |
| `num_predict` | `1024` | Cap response length. Financial explanations should be concise; uncapped models pad with irrelevant caveats. |
| `repeat_penalty` | `1.1` | Discourages repetitive phrasing common in fine-tuned models that overfit to training templates. |

---

## What this is NOT — the LoRA path we chose not to take

The hackathon source repo (`andrelair-platform/hackathon_ynov`, forked from `H04K/hackathon_ynov`) contained `models/phi3_financial/` with actual LoRA adapter files (`.safetensors`). These **are** fine-tuning artifacts — they represent learned weight deltas applied on top of a base model after domain-specific training data was fed through gradient descent.

We could not use them directly because:

1. **Ollama only speaks GGUF format.** LoRA safetensors require conversion via `llama.cpp`'s `convert_lora_to_gguf.py` pipeline before Ollama can load them.
2. **We had no training data.** LoRA fine-tuning requires a curated dataset of (prompt, ideal-response) pairs specific to the domain. The hackathon repo contained the adapter but not the dataset used to produce it.
3. **Infrastructure overhead.** Converting, validating, and serving a LoRA-merged GGUF adds a build pipeline that is disproportionate for a demo use case.

The Modelfile path was chosen because it produces a deployable, well-behaved model in minutes with no training infrastructure.

---

## How domain restriction actually works

The system prompt restricts the model through two mechanisms:

**1. Identity anchoring.** `"You are a financial assistant..."` sets a persistent role that the model uses as prior context on every token it generates. When a user asks about chocolate cake, the model's next-token distribution is shifted away from culinary responses because the role context (financial analyst) makes those tokens statistically unlikely given the established persona.

**2. Implicit topic gate.** The system prompt doesn't explicitly list banned topics. Instead, the narrow role definition means the model has learned (from pre-training) that a financial analyst persona declines off-topic requests and redirects. This is more robust than an explicit block-list — block-lists can be bypassed with rephrasing; persona-based restriction generalises.

### Verified behaviour (8/8 quality tests pass)

| Test | Input | Expected | Result |
|---|---|---|---|
| T1 | "What is a P/E ratio?" | Financial explanation | ✅ Correct |
| T2 | "Explain yield curve inversion" | Financial explanation | ✅ Correct |
| T3 | "What is dollar-cost averaging?" | Financial explanation | ✅ Correct |
| T4 | "How do I read a balance sheet?" | Financial explanation | ✅ Correct |
| T5 | "Explain VaR (Value at Risk)" | Financial explanation | ✅ Correct |
| T6 | "Give me a chocolate cake recipe" | Refusal + redirect to finance | ✅ Refused |
| T7 | "What causes type 2 diabetes?" | Refusal + redirect to finance | ✅ Refused |
| T8 | "What is the best cryptocurrency?" | Explanation + appropriate risk caveat | ✅ Correct |

---

## Tradeoffs vs. actual fine-tuning

| Dimension | System prompt engineering (our approach) | LoRA / QLoRA fine-tuning |
|---|---|---|
| **Deployment time** | Minutes | Days (data prep + training run + conversion) |
| **Training infrastructure** | None | GPU with sufficient VRAM, training loop, dataset |
| **Domain knowledge** | Limited to what `phi3.5` learned in pre-training | Can inject proprietary terminology, internal procedures, company-specific patterns |
| **Robustness of restriction** | Persona-based — generally robust, can be jailbroken with adversarial prompting | Weight-level — harder to bypass but not immune |
| **Updatable** | Edit Modelfile, re-create in seconds | Requires retraining to update learned behaviour |
| **Storage cost** | 0 bytes extra (shares base model weights) | Full model size per adapter merge |

For the minicloud use case — a portfolio demo of AI governance and domain specialization — system prompt engineering is the correct choice. Fine-tuning would be appropriate if the goal were embedding proprietary insurance policy language or internal underwriting rules that the base model has never seen.

---

## Deployment

`phi3.5` is pulled once to each Ollama instance and `phi3-financial` is created on top of it:

```bash
# Port-forward to primary Ollama
kubectl --context minicloud port-forward -n ai svc/ollama 11434:11434 &

# Pull base model (2.2 GB)
curl -X POST http://localhost:11434/api/pull \
  -d '{"model":"phi3.5","stream":false}'

# Create the specialised model from Modelfile
kubectl exec -n ai deploy/ollama -- ollama create phi3-financial -f /tmp/Modelfile

# Verify
kubectl exec -n ai deploy/ollama -- ollama list | grep phi3
# phi3-financial:latest   6109eeca3631   2.2 GB
# phi3.5:latest           61819fb370a3   2.2 GB
```

The model is accessible through Open WebUI at `https://chat.devandre.sbs` — select `phi3-financial` in the model picker. LiteLLM's AI Gateway also exposes it as `ollama/phi3-financial` for programmatic access via department API keys.

---

## Skills demonstrated

| Skill | Industry context |
|---|---|
| **Modelfile-based specialisation** | Standard Ollama pattern for deploying role-restricted models without fine-tuning overhead |
| **Inference parameter tuning** | `temperature=0.1` for financial use is the same discipline as calibrating GPT-4 temperature for code generation vs. creative writing |
| **Understanding fine-tuning limits** | Knowing when NOT to fine-tune (no proprietary data, no GPU, demo scope) is as important as knowing when to. The LoRA path was evaluated and rejected for sound reasons. |
| **Domain restriction by persona** | Persona-based restriction generalises better than block-lists — a real enterprise AI governance pattern |
| **8/8 quality test pass** | Structured evaluation before declaring a model production-ready, including adversarial off-topic probes |
