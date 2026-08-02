---
id: research-agent
title: Research Agent — LangGraph ReAct Runtime
sidebar_label: Research Agent
---

# Research Agent — LangGraph ReAct Runtime

**Phase complete:** 2026-08-02  
**GitOps:** `services/minicloud-agent/` + `manifests/ai/26-agent-runtime.yaml`  
**Image:** `harbor.10.0.0.200.nip.io/library/minicloud-agent:1.0.1`

A LangGraph ReAct agent deployed as an OpenAI-compatible FastAPI service and registered as a selectable model (`research-agent`) in LiteLLM. Users in Open WebUI pick "research-agent" exactly as they would any other model — the agent loop is transparent.

---

## Architecture

```
Open WebUI
    │  model: "research-agent"
    ▼
LiteLLM Gateway (:4000)
    │  routes openai/research-agent → minicloud-agent:8080/v1
    ▼
minicloud-agent (:8080)          ← FastAPI + LangGraph
    │
    ├── create_react_agent
    │       │
    │       ├── [tool] rag_search ──► rag-ingest:8001/query
    │       │                         pgvector + bge-m3 + BM25
    │       │
    │       └── [tool] web_search ──► DuckDuckGo (ddgs)
    │                                 public internet via egress NP
    │
    └── model calls ──► LiteLLM ──► mistral-small (default)
```

The agent uses the **ReAct pattern** (Reason → Act → Observe → Reason…): for each user message, the LLM decides whether to call a tool, observes the result, and loops until it has enough information to answer — up to `AGENT_MAX_ITERATIONS=6` reasoning steps.

---

## Service

```yaml
# manifests/ai/26-agent-runtime.yaml
image: harbor.10.0.0.200.nip.io/library/minicloud-agent:1.0.1
env:
  LITELLM_BASE_URL: http://litellm.ai.svc.cluster.local:4000
  LITELLM_API_KEY:  secretKeyRef litellm-credentials/master-key
  RAG_INGEST_URL:   http://rag-ingest.ai.svc.cluster.local:8001
  AGENT_DEFAULT_MODEL: mistral-small
  AGENT_MAX_ITERATIONS: "6"
resources:
  requests: 100m / 256Mi
  limits:   500m / 512Mi
```

Endpoints:

| Path | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |
| `/v1/models` | GET | Returns `research-agent` in OpenAI model list format |
| `/v1/chat/completions` | POST | Runs the agent loop; supports `stream: true/false` |

---

## Tools

### `rag_search(query, collection="")`

Queries the internal knowledge base via `POST /query` on the rag-ingest service. Returns the top-5 chunks with source citations.

```python
payload = {"query": query, "top_k": 5}
# optional: payload["collection"] = collection_uuid
response = await client.post(f"{RAG_INGEST_URL}/query", json=payload)
chunks = response.json().get("results", [])
# → "[1] Source: Solvency II directive\n<text excerpt>"
```

The agent is prompted to prefer `rag_search` over `web_search` for internal documents.

### `web_search(query)`

Searches the public web via the `ddgs` library (DuckDuckGo). Returns the top-5 results with title, URL, and snippet.

Internet egress is enabled via a dedicated NetworkPolicy (`allow-agent-internet-egress` in `manifests/ai/04-networkpolicies-cloud-egress.yaml`) that allows the `minicloud-agent` pod to reach TCP port 443.

---

## System prompt

```
You are a research assistant for a financial and insurance advisory platform.

When answering:
1. Search the internal knowledge base first with rag_search
2. If internal results are insufficient, search the web with web_search
3. Always cite your sources: use [1], [2], etc. referencing the Source fields
4. If both searches return nothing useful, say so clearly — do not guess

Be concise, factual, and cite all claims.
```

---

## LiteLLM registration

The agent is registered as a model in `manifests/ai/00-litellm-configmap.yaml`:

```yaml
model_list:
  - model_name: research-agent
    litellm_params:
      model: openai/research-agent
      api_base: http://minicloud-agent.ai.svc.cluster.local:8080/v1
      api_key: none
```

LiteLLM forwards any `model: research-agent` request to the agent's `/v1/chat/completions` endpoint. The agent returns standard OpenAI chat completion JSON, so LiteLLM treats it identically to any other provider.

---

## Streaming

The agent collects the full response from the LangGraph loop, then streams it back in 40-character SSE chunks if the client requested `stream: true`:

```python
async def _sse_stream(request_id, model, content):
    for i in range(0, len(content), 40):
        yield f"data: {json.dumps({'choices': [{'delta': {'content': content[i:i+40]}}]})}\n\n"
    yield "data: [DONE]\n\n"
```

This means the Open WebUI typing effect works naturally — characters appear progressively even though the agent reasoning is done before streaming starts.

---

## Ingress

The agent has an internal-only ingress at `agent.10.0.0.200.nip.io` (no Cloudflare tunnel). It is not intended for direct access — all traffic routes via LiteLLM. The ingress exists for developer debugging (`/docs` Swagger UI, direct `/v1/chat/completions` tests).

`proxy-read-timeout: 300` is set on the ingress to accommodate long agent reasoning loops.

---

## Build and release

```bash
# Build and push a new release:
cd ~/Developer/cloudplateform/minicloud-gitops/services/minicloud-agent
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker buildx build \
  --platform linux/amd64 \
  -t harbor.10.0.0.200.nip.io/library/minicloud-agent:<VERSION> \
  --push .

# Update the image tag in the manifest:
# manifests/ai/26-agent-runtime.yaml → image: ...minicloud-agent:<VERSION>
# Open a PR → merge → ArgoCD rolls out automatically
```

Tag `1.0.0` was the initial release. Tag `1.0.1` updated `duckduckgo-search` to the renamed `ddgs` package.

---

## Troubleshooting

**Agent returns "unable to retrieve specific information"**  
The RAG knowledge base may be empty for that topic. Ingest documents via the rag-ingest pipeline, or the web search may have hit DuckDuckGo rate limits. Check pod logs:

```bash
kubectl logs -n ai -l app=minicloud-agent --tail=30
```

**Agent times out (504 from ingress)**  
The default agent loop allows 6 iterations × 2 tool calls = up to 12 LiteLLM round-trips. Reduce `AGENT_MAX_ITERATIONS` in the Deployment env if needed, or increase the ingress `proxy-read-timeout`.

**research-agent not visible in Open WebUI model selector**  
Check LiteLLM has loaded the config:

```bash
kubectl port-forward -n ai svc/litellm 4001:4000 &
curl http://localhost:4001/v1/models | python3 -m json.tool | grep research
```
