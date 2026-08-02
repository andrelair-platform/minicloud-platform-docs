---
id: deep-research-agent
title: Deep Research Agent — CrewAI Multi-Agent Runtime
sidebar_label: Deep Research Agent
---

# Deep Research Agent — CrewAI Multi-Agent Runtime

**Phase complete:** 2026-08-02  
**GitOps:** `services/minicloud-crew-agent/` + `manifests/ai/29-crew-agent-runtime.yaml`  
**Image:** `harbor.10.0.0.200.nip.io/library/minicloud-crew-agent:1.0.1`

A three-agent CrewAI crew deployed as an OpenAI-compatible FastAPI service and registered as `deep-research-agent` in LiteLLM. It complements the single-loop [Research Agent](research-agent) by adding a structured synthesis and regulatory validation stage before returning an answer.

---

## When to use each agent

| Agent | Model ID | Best for |
|---|---|---|
| Research Agent | `research-agent` | Quick lookups, factual questions, document retrieval |
| Deep Research Agent | `deep-research-agent` | Regulatory analysis, compliance questions, advisory tasks needing synthesis + validation |

**Latency:** `research-agent` responds in 5–15 s. `deep-research-agent` takes 30–120 s (three agents × up to 8 LLM iterations each).

---

## Architecture

```
Open WebUI
    │  model: "deep-research-agent"
    ▼
LiteLLM Gateway (:4000)
    │  routes openai/deep-research-agent → minicloud-crew-agent:8081/v1
    ▼
minicloud-crew-agent (:8081)        ← FastAPI + CrewAI
    │
    ├── Agent 1: Research Specialist (mistral-small, max_iter=8)
    │       ├── [tool] rag_search ──► rag-ingest:8001/query
    │       └── [tool] web_search ──► DuckDuckGo (ddgs)
    │
    ├── Agent 2: Financial Analyst (mistral-large, max_iter=4)
    │       └── [no tools] — synthesises Agent 1 output into structured answer
    │
    └── Agent 3: Compliance Validator (mistral-large, max_iter=8)
            └── [tool] rag_search — cross-checks every regulatory claim
```

The crew runs **sequentially**: Research → Analysis → Compliance. Each agent receives the output of prior agents as context. The final response is the Compliance Validator's validated, corrected answer.

---

## Service

```yaml
# manifests/ai/29-crew-agent-runtime.yaml
image: harbor.10.0.0.200.nip.io/library/minicloud-crew-agent:1.0.1
env:
  LITELLM_BASE_URL: http://litellm.ai.svc.cluster.local:4000
  LITELLM_API_KEY:  secretKeyRef litellm-credentials/master-key
  RAG_INGEST_URL:   http://rag-ingest.ai.svc.cluster.local:8001
  CREW_SMALL_MODEL: mistral-small   # Researcher
  CREW_LARGE_MODEL: mistral-large   # Analyst + Compliance Validator
  CREW_MAX_ITER:    "8"
resources:
  requests: 200m / 512Mi
  limits:   1000m / 1Gi
```

Endpoints:

| Path | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |
| `/v1/models` | GET | Returns `deep-research-agent` in OpenAI model list format |
| `/v1/chat/completions` | POST | Runs the three-agent crew |

---

## Agents

### Agent 1 — Research Specialist

Uses `mistral-small` (fast, low cost) to maximise retrieval iterations within budget.

**Goal:** Find accurate, comprehensive information using available tools. Prefer internal knowledge base over web when both are available. Cite every source as `[N]`.

**Tools:** `rag_search`, `web_search`

### Agent 2 — Financial Analyst

Uses `mistral-large` for synthesis quality. Has no tools — it reasons purely from Agent 1's output.

**Goal:** Synthesise research into a structured answer: executive summary → key facts → regulatory context → practical implications. Preserve all `[N]` citations verbatim.

**Context:** receives Agent 1 output.

### Agent 3 — Compliance Validator

Uses `mistral-large` with `rag_search` access to verify regulatory claims.

**Goal:** Identify every regulatory reference (ACPR, AMF, Solvency II, MiFID II, GDPR…), cross-check each against the knowledge base, correct errors, and return the final validated answer. Appends a `Compliance note:` section if corrections were made.

**Context:** receives both Agent 1 and Agent 2 outputs.

---

## Implementation details

### LLM routing

CrewAI ≥ 0.80 uses its own `crewai.LLM` class internally. The model string must include an `openai/` provider prefix so the embedded litellm client knows to use OpenAI-compatible format against the proxy:

```python
from crewai import LLM

def _llm(model: str) -> LLM:
    return LLM(
        model=f"openai/{model}",           # e.g. "openai/mistral-small"
        base_url=f"{LITELLM_BASE_URL}/v1", # LiteLLM proxy maps virtual → real provider
        api_key=LITELLM_API_KEY,
        temperature=0.1,
        max_retries=2,
    )
```

### Async execution

CrewAI's `crew.kickoff()` is blocking. It runs on FastAPI's event loop thread pool via `run_in_executor` to avoid blocking other requests:

```python
async def run(question: str) -> str:
    crew, inputs = _build_crew(question)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: crew.kickoff(inputs=inputs)
    )
    return str(result)
```

### Task templating

Tasks use `{question}` as a template variable filled at kickoff time, so each request creates a fresh Crew with a dynamically-scoped task description:

```python
research_task = Task(
    description="Research the following question...\n\nQuestion: {question}",
    ...
)
crew.kickoff(inputs={"question": user_question})
```

---

## LiteLLM registration

```yaml
# manifests/ai/00-litellm-configmap.yaml
- model_name: deep-research-agent
  litellm_params:
    model: openai/deep-research-agent
    api_base: http://minicloud-crew-agent.ai.svc.cluster.local:8081/v1
    api_key: none
```

---

## Ingress

Internal-only ingress at `crew-agent.10.0.0.200.nip.io`. Not exposed via Cloudflare tunnel — external consumers go through LiteLLM.

`proxy-read-timeout: 600` (vs 300 for research-agent) to accommodate three agents × 8 iterations × Mistral API latency.

---

## Build and release

```bash
cd ~/Developer/cloudplateform/minicloud-gitops/services/minicloud-crew-agent
docker buildx build --platform linux/amd64 \
  -t harbor.10.0.0.200.nip.io/library/minicloud-crew-agent:<VERSION> \
  --push .

# Update the image tag:
# manifests/ai/29-crew-agent-runtime.yaml → image: ...minicloud-crew-agent:<VERSION>
# Open a PR → merge → ArgoCD rolls out
```

**Release history:**
- `1.0.0` — initial release
- `1.0.1` — fix: switch to `crewai.LLM` with `openai/` prefix (CrewAI ≥ 0.80 LLM routing fix)

---

## Troubleshooting

**`LLM Provider NOT provided` error in crew-agent logs**  
Model name missing `openai/` prefix. Ensure `_llm()` uses `model=f"openai/{model}"`.

**Crew returns partial/truncated response**  
`max_tokens` in the calling request is too low. The compliance validator's output can be 400–600 tokens. Use at least `max_tokens: 1000` when calling `deep-research-agent` directly.

**Crew times out (504 from ingress)**  
Three agents × 8 iterations = up to 24 LiteLLM calls. If Mistral API is slow, reduce `CREW_MAX_ITER` in the Deployment env or use `CREW_SMALL_MODEL: mistral-small` for the analyst too.

**deep-research-agent not visible in Open WebUI model selector**  
```bash
kubectl port-forward -n ai svc/litellm 4001:4000 &
curl http://localhost:4001/v1/models | python3 -m json.tool | grep deep-research
```
