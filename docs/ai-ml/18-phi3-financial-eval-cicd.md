---
id: phi3-financial-eval-cicd
title: phi3-financial Prompt Eval CI/CD
sidebar_label: Prompt Eval CI/CD
---

# phi3-financial Prompt Eval CI/CD

Automated prompt regression gate for the `phi3-financial` model. Any change to the Ollama `Modelfile` (system prompt) or `scripts/eval.py` triggers the suite on GitHub Actions. The merge is blocked if pass rate < 100%.

Repo: `andrelair-platform/hackathon_ynov`

---

## Why a prompt eval pipeline

System prompts are code. A one-word change to the persona definition can cause the model to stop refusing off-topic queries, start hallucinating financial figures, or break domain grounding. Without a gate, these regressions reach production silently.

The pipeline enforces the same discipline as a unit test suite: every proposed change to the Modelfile must prove the model still behaves correctly before it can merge.

---

## Architecture

```
Developer edits Modelfile or eval.py
         │
         ▼ (push / PR to main)
GitHub Actions — ubuntu-latest runner
         │
         ├─ tailscale/github-action@v2
         │    joins GHA runner to Tailnet (ephemeral device, auto-removed on job end)
         │    controller advertises 10.0.0.0/24 subnet route
         │
         ├─ Trust minicloud CA
         │    appends internal CA cert to certifi bundle
         │    so httpx (used by openai client) trusts TLS on litellm.10.0.0.200.nip.io
         │
         ├─ python scripts/eval.py
         │    │
         │    ├─ registers system prompt in Langfuse Prompt Management
         │    ├─ syncs 8 test cases to Langfuse Dataset
         │    ├─ calls phi3-financial (via LiteLLM → Ollama on fast-heron) × 8
         │    ├─ scores each response (keyword-based)
         │    ├─ logs trace + score to Langfuse
         │    └─ exits 1 if pass_rate < 1.0
         │
         └─ merge BLOCKED if any test fails
```

**Network path (no Cloudflare):**
```
GHA runner ──[Tailscale]──► controller (100.88.123.8)
                                │  subnet route: 10.0.0.0/24
                                ▼
                         NGINX Ingress (10.0.0.200:443)
                                │  litellm.10.0.0.200.nip.io
                                ▼
                         LiteLLM (ai namespace, port 4000)
                                │  model: ollama/phi3-financial
                                ▼
                         Ollama (fast-heron, NVMe local-path)
```

Cloudflare was deliberately bypassed because its Security Level (Medium) blocks GHA datacenter IPs (Azure `eastus2`). Tailscale gives the runner direct private network access without weakening the public security posture.

---

## Test dataset

Eight cases cover both halves of the system prompt contract:

| ID | Input | Behavior | Required keywords |
|---|---|---|---|
| T1 | What is a P/E ratio and how is it used? | answer | price, earnings, ratio, valuation, stock |
| T2 | Explain yield curve inversion and what it signals. | answer | yield, bond, recession, interest, rate |
| T3 | What is dollar-cost averaging? | answer | invest, average, price, regular |
| T4 | How do I read a balance sheet? | answer | asset, liabilit, equity, financ |
| T5 | What is Value at Risk (VaR)? | answer | risk, loss, portfolio, confidence, probabilit |
| T8 | What is the best cryptocurrency to invest in? | answer | crypto, risk, invest, volatil |
| T6 | Give me a recipe for chocolate cake. | refuse | *(forbidden: flour, butter, bake, oven, sugar, egg, cup of)* |
| T7 | What causes type 2 diabetes and how is it treated? | refuse | *(forbidden: insulin, glucose, pancreas, metformin, blood sugar level)* |

**Scoring logic:**
- `answer` cases: PASS if all `required_keywords` appear (case-insensitive substring match) in the response
- `refuse` cases: PASS if none of the `forbidden_keywords` appear — model refused without providing off-topic content

Partial keyword matches are intentional (`liabilit` matches both "liability" and "liabilities"; `probabilit` matches "probability" and "probabilistic").

---

## Langfuse integration

Each run creates:

- **Prompt version** — `phi3-financial-system` updated in Langfuse Prompt Management with the current Modelfile system prompt and inference parameters
- **Dataset** — `phi3-financial-evals` with all 8 test cases as items
- **Traces** — one trace per test case named `eval-T1` … `eval-T8`, tagged with the run name (`eval-20260707-210214`)
- **Scores** — `correctness` score (0.0 or 1.0) attached to each trace with a human-readable comment

All traces are visible at `https://langfuse.devandre.sbs` → Project `ai-gateway` → Traces.

---

## Secrets

| Secret | Value | Scope |
|---|---|---|
| `TAILSCALE_AUTHKEY` | Ephemeral, reusable key from Tailscale admin | GHA → Tailnet join |
| `MINICLOUD_CA_CERT` | Base64-encoded minicloud root CA cert | TLS trust for internal ingress |
| `LITELLM_API_KEY` | eval-ci department key (`sk-oooK33OIZ5TEJkBczjpk9g`) | LiteLLM auth |
| `LITELLM_BASE_URL` | `https://litellm.10.0.0.200.nip.io` | Internal LiteLLM endpoint |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-…` | Langfuse trace logging |
| `LANGFUSE_SECRET_KEY` | `sk-lf-…` | Langfuse trace logging |
| `LANGFUSE_HOST` | `https://langfuse.devandre.sbs` | Langfuse instance |

The `TAILSCALE_AUTHKEY` is set to **ephemeral** — GHA devices are automatically removed from the Tailnet when the job ends, leaving no persistent device entries.

---

## Trigger conditions

```yaml
on:
  push:
    branches: [main]
    paths:
      - 'ollama_server/Modelfile'
      - 'scripts/eval.py'
  pull_request:
    branches: [main]
    paths: [same]
  workflow_dispatch:
```

The suite runs only when the Modelfile or eval script actually changes — not on every push to main. Unrelated changes (README edits, screenshot updates) do not trigger inference.

---

## Reproducing a run locally

```bash
# 1. Port-forward LiteLLM (requires minicloud kubeconfig)
kubectl --context minicloud port-forward -n ai svc/litellm 4000:4000 &

# 2. Set env vars
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://langfuse.devandre.sbs
export LITELLM_API_KEY=sk-oooK33OIZ5TEJkBczjpk9g
export LITELLM_BASE_URL=http://localhost:4000

# 3. Install deps and run
pip install -r scripts/requirements-eval.txt
python scripts/eval.py
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `PermissionDeniedError: Your request was blocked.` in under 15ms | Cloudflare Security Level blocking GHA datacenter IPs | Ensure `LITELLM_BASE_URL` uses the internal nip.io URL, not `litellm.devandre.sbs` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | minicloud CA not in certifi bundle | Confirm the "Trust minicloud CA" step ran before "Run eval suite" |
| Tailscale join hangs | Expired or invalid auth key | Regenerate ephemeral key at `login.tailscale.com/admin/settings/keys`, update `TAILSCALE_AUTHKEY` secret |
| `AttributeError: 'Langfuse' object has no attribute 'trace'` | langfuse v3 installed | Pin to `langfuse>=2.0.0,<3.0.0` in `requirements-eval.txt` |
| T8 fails with `missing keywords: ['bitcoin']` | Model discussed crypto risk without naming specific coins | Remove `bitcoin` from T8 `required_keywords` — this is correct behavior |
| All 8 cases fail instantly | detect_secrets guardrail scanning `api_key` field | Confirm `detect_secrets_on_all_keys: false` in LiteLLM ConfigMap |

---

## Key design decisions

**Why Tailscale instead of lowering Cloudflare Security Level?**
Lowering the Security Level weakens public-facing bot filtering for all of `devandre.sbs`. Tailscale gives the GHA runner private network access scoped to the job duration with no public exposure change. Ephemeral keys mean the runner leaves no persistent footprint in the Tailnet.

**Why keyword-based scoring instead of an LLM judge?**
Keyword matching is deterministic and free. An LLM judge (GPT-4 scoring responses) adds latency, cost, and a dependency on an external API. For a suite that runs on every Modelfile commit, deterministic scoring is the correct tradeoff. A judge would be appropriate for an expanded suite testing nuanced behaviors (tone, completeness, confidence calibration).

**Why `langfuse>=2.0.0,<3.0.0`?**
Langfuse v3 removed the low-level `lf.trace()` / `lf.score()` / `lf.create_prompt()` APIs used in `eval.py`. Pinning to v2 preserves compatibility without requiring a rewrite to the higher-level v3 decorator-based API.

**Why is `phi3-financial` on the eval-ci department key allowed list?**
The eval-ci key is scoped to the `phi3-financial` model only. It cannot call cloud providers (no GPT-4, no Claude, no Groq). Budget cap: $0.01 (local Ollama costs $0 — cap is a safety net against accidental config changes).
