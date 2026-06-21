---
id: sampling-configuration
title: Sampling Configuration
sidebar_position: 11
---

# Sampling Configuration

Sampling parameters control how the model selects each token when generating a response. They are one of the most underrated levers in a production AI system — directly affecting hallucination rate, output consistency, and response quality across different use cases.

This platform configures sampling **per department** via the LiteLLM router, meaning the claims assistant and the IT assistant use fundamentally different generation strategies.

---

## The Four Parameters

| Parameter | What it controls | Range |
|---|---|---|
| **Temperature** | Randomness of token selection. 0 = always pick the most likely token. Higher = more varied/creative output. | 0.0 – 2.0 |
| **Top-K** | Restricts the candidate pool to the K most probable tokens at each step. Top-K=1 is equivalent to greedy decoding. | 1 – vocabulary size |
| **Top-P** (nucleus sampling) | Dynamically selects the smallest set of tokens whose cumulative probability exceeds P. More adaptive than Top-K. | 0.0 – 1.0 |
| **Best-of-N** | Generates N independent responses and returns the best (by log probability or external judge). Multiplies inference cost by N. | 1 – N |

### How they interact

Temperature is applied first, then Top-K, then Top-P. All three narrow the candidate pool before a token is sampled:

```
Full vocabulary (32,000 tokens)
  → Temperature rescales probabilities (lower = sharper distribution)
    → Top-K keeps only the K most likely tokens
      → Top-P keeps only tokens until cumulative probability reaches P
        → Sample one token from what remains
```

At **temperature=0, top_k=1**: the model always picks the single highest-probability token. The output is fully deterministic — the same input always produces the same output.

At **temperature=0.7, top_k=40, top_p=0.9**: the model samples from a varied but still reasonable candidate set. Different runs of the same prompt produce different outputs.

---

## Department Sampling Strategy

The correct sampling configuration maps directly to the risk classification used throughout the AI security controls:

### Temperature = 0 — Deterministic (high-stakes departments)

Used for: Sinistres, Finance, Juridique, Souscription, Actuariat, Réassurance, Audit.

```yaml
temperature: 0.0
top_k: 1
top_p: 1.0
```

These departments ask questions with a single correct answer grounded in documents: franchise amounts, indemnity limits, treaty retention levels, article references, IFRS17 figures. There is no benefit to token sampling diversity — the most probable answer is the correct one. Randomness only introduces the possibility of selecting a less probable (and therefore more likely wrong) token.

**Why this reduces hallucination:** at temperature=0, the model cannot "drift" toward a plausible-sounding alternative. It always produces the response its training and retrieved context consider most likely. Combined with the retrieval grounding gate (issue #44), this makes the system as deterministic as the underlying documents allow.

**Consistency benefit:** the same query on Monday and Friday produces the same answer. Ragas faithfulness scores are reproducible. The counterfactual bias gate (issue #45) compares base and swap responses whose similarity is meaningful because the model is not adding random variation on top of any demographic difference.

### Temperature = 0.3 — Controlled variation (semi-structured tasks)

Used for: Commercial, RH.

```yaml
temperature: 0.3
top_k: 40
top_p: 0.9
```

Sales proposal drafts and HR communications benefit from minor variation — identical boilerplate on every request is not useful — but still need professional, constrained output that stays within policy.

### Temperature = 0.7 — Creative (low-stakes, general assistance)

Used for: IT, Transformation, Opérations, Services généraux, Data & Analytics.

```yaml
temperature: 0.7
top_k: 40
top_p: 0.9
```

IT troubleshooting, explaining technical concepts, brainstorming — varied and exploratory output is useful here and the cost of a wrong answer is low (easily verified by the user).

---

## Configuration in LiteLLM Router

Sampling parameters are set at the model alias level in the LiteLLM ConfigMap. This is a config-only change — no code changes, no Ollama restart. A `helm upgrade litellm` picking up the updated ConfigMap is sufficient.

```yaml
model_list:

  # ── High-stakes: deterministic ──────────────────────────────────────────────
  - model_name: claims-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-set-hog.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  - model_name: finance-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-set-hog.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  - model_name: legal-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-set-hog.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  - model_name: underwriting-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-set-hog.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  - model_name: actuarial-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-fast-skunk.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  - model_name: audit-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-fast-skunk.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  - model_name: reinsurance-assistant
    litellm_params:
      model: ollama/llama3.2:3b
      api_base: http://ollama-fast-skunk.ai.svc:11434
      temperature: 0.0
      top_k: 1
      top_p: 1.0

  # ── Semi-structured: controlled variation ────────────────────────────────────
  - model_name: commercial-assistant
    litellm_params:
      model: ollama/llama3.2:1b
      api_base: http://ollama-fast-heron.ai.svc:11434
      temperature: 0.3
      top_k: 40
      top_p: 0.9

  - model_name: hr-assistant
    litellm_params:
      model: ollama/llama3.2:1b
      api_base: http://ollama-fast-heron.ai.svc:11434
      temperature: 0.3
      top_k: 40
      top_p: 0.9

  # ── General: creative ────────────────────────────────────────────────────────
  - model_name: general-assistant
    litellm_params:
      model: ollama/llama3.2:1b
      api_base: http://ollama-fast-heron.ai.svc:11434
      temperature: 0.7
      top_k: 40
      top_p: 0.9
```

---

## Department → Model Alias Routing

```
direction-sinistres       → claims-assistant      (temp=0.0, 3b)
direction-souscription    → underwriting-assistant (temp=0.0, 3b)
direction-finance         → finance-assistant      (temp=0.0, 3b)
direction-actuariat       → actuarial-assistant    (temp=0.0, 3b)
direction-réassurance     → reinsurance-assistant  (temp=0.0, 3b)
direction-juridique       → legal-assistant        (temp=0.0, 3b)
direction-audit           → audit-assistant        (temp=0.0, 3b)
direction-commercial      → commercial-assistant   (temp=0.3, 1b)
direction-rh              → hr-assistant           (temp=0.3, 1b)
direction-it              → general-assistant      (temp=0.7, 1b)
direction-transformation  → general-assistant      (temp=0.7, 1b)
direction-data-analytics  → general-assistant      (temp=0.7, 1b)
direction-opérations      → general-assistant      (temp=0.7, 1b)
direction-services-gen    → general-assistant      (temp=0.7, 1b)
```

---

## Best-of-N — When and Where

Best-of-N generates N independent responses and selects the best. On CPU-only inference (`llama3.2:3b` at ~10–30s per response), interactive Best-of-N is impractical — Best-of-3 means 30–90s latency. It is appropriate in two scenarios:

### Batch evaluation (nightly CronJob, issue #43)

The golden dataset evaluation has no latency constraint. Running Best-of-3 on each evaluation query gives more stable, reproducible Ragas scores — the CronJob evaluates the highest-quality response rather than a single stochastic sample.

```python
def best_of_n_generate(prompt: str, context: str, n: int = 3) -> str:
    """
    For batch evaluation only — not for interactive use.
    Generates N responses at temperature=0.3 and returns the longest
    coherent one (proxy for completeness). Alternatively, pass all N
    to the LLM judge and return the highest-scoring response.
    """
    candidates = []
    for _ in range(n):
        r = completion(
            model="ollama/llama3.2:3b",
            api_base="http://ollama-set-hog.ai.svc:11434",
            messages=[
                {"role": "system", "content": context},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,    # slight variation to get diverse candidates
            top_k=40,
            top_p=0.9,
        )
        candidates.append(r.choices[0].message.content)
    return max(candidates, key=len)
```

### High-stakes single queries (future, on upgraded hardware)

If the cluster is ever upgraded with GPU nodes, Best-of-3 for Finance and Claims queries becomes viable at interactive latency (~3–5s). At that point, the `finance-assistant` and `claims-assistant` model aliases can be updated to use Best-of-N internally via LiteLLM's `num_completions` parameter.

---

## How Sampling Affects the Existing Controls

Temperature and the AI security controls interact — in most cases, temperature=0 on high-stakes departments strengthens every downstream control:

| Control | Effect of temperature=0 |
|---|---|
| **Ragas faithfulness** (issue #39) | Deterministic output → faithfulness scores are reproducible run-to-run; drift in scores reflects real quality changes, not sampling variance |
| **Citation check** (issue #44) | Model reliably follows "cite your source" instruction rather than occasionally omitting it due to random sampling |
| **LLM-as-judge neutrality** (issue #45) | Consistent output makes sycophancy detection more reliable — variation between responses reflects department differences, not temperature noise |
| **Counterfactual bias gate** (issue #45) | Same prompt → same output: similarity between base/swap response pairs reflects demographic treatment, not random generation variance |
| **Canary token check** (issue #46) | Deterministic model is less likely to spontaneously include unexpected tokens near the system prompt boundary |
| **Verbatim reproduction check** (issue #48) | Consistent output means a single verbatim ratio check is representative, not a lucky sample |

---

## Applying the Change

```bash
# 1. Update the LiteLLM ConfigMap in minicloud-ansible
# Edit: ansible/helm-values/litellm-config.yaml
# Add temperature/top_k/top_p per model alias (see config above)

# 2. Apply via helm upgrade on the controller
ssh controller "/home/ktayl/.local/bin/helm upgrade litellm litellm/litellm \
  --namespace ai \
  --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/litellm-config.yaml \
  --wait"

# 3. Verify the parameter is being passed to Ollama
kubectl logs -n ai deployment/litellm --since=5m | grep -i "temperature"

# 4. Smoke test — claims assistant should be deterministic
# Send the same query twice, compare responses — they must be identical
```

---

## Operational Checks

```bash
# Verify current effective parameters per model alias
curl -s http://litellm.ai.svc:4000/model/info \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  | jq '.data[] | {model: .model_name, temp: .litellm_params.temperature, top_k: .litellm_params.top_k}'

# Confirm claims-assistant is deterministic (run twice, diff output)
for i in 1 2; do
  curl -s http://litellm.ai.svc:4000/chat/completions \
    -H "Authorization: Bearer $CLAIMS_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"claims-assistant","messages":[{"role":"user",
         "content":"Quelle est la franchise standard pour un dégât des eaux?"}]}' \
  | jq -r '.choices[0].message.content'
done
# Both outputs must be identical
```
