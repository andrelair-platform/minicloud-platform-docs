---
id: open-webui
title: Open WebUI — AI Chat Interface
sidebar_label: Open WebUI (AI Chat)
---

# Open WebUI — AI Chat Interface

Self-hosted ChatGPT-equivalent for the ktayl-solution IS. Connects all users (employees, underwriters, claims handlers) to the LiteLLM gateway — providing access to vLLM-hosted local models and cloud providers behind a unified chat interface.

## Access

| URL | Audience |
|---|---|
| https://chat.devandre.sbs | Public (Cloudflare Tunnel) |
| https://chat.10.0.0.200.nip.io | Internal (Tailscale only) |

Login: Authentik OIDC SSO.

## Deployment

| Parameter | Value |
|---|---|
| Namespace | `ai` |
| Managed by | ArgoCD (`litellm` app) |
| Image | Custom — `minicloud-open-webui` |
| Manifest path | `manifests/ai/` in minicloud-gitops |
| Storage | Longhorn PVC (conversation history) |
| Auth | Authentik OIDC |

The custom image (`minicloud-open-webui`) adds:
- minicloud CA certificate trusted at TLS level
- French BM25 tokenizer for French-language RAG search

```bash
kubectl --context minicloud get pods -n ai -l app=open-webui
kubectl --context minicloud get ingress -n ai chat
```

## Custom image source

```bash
cd ~/Developer/cloudplateform/minicloud-open-webui
# Build locally (injects CA cert at build time):
docker build --build-arg CA_CERT="$(cat ~/minicloud-ca.crt)" .
```

CI pushes signed images to `harbor.10.0.0.200.nip.io/library/minicloud-open-webui`.

## Model routing via LiteLLM

Open WebUI connects to LiteLLM at `https://litellm.devandre.sbs`. Model selection in the UI corresponds to LiteLLM route names:

| UI model name | Backend |
|---|---|
| `mistral-7b` | vLLM on-cluster (ai namespace) |
| `phi3-mini` | vLLM on-cluster |
| `gpt-4o` | Azure OpenAI (€10/month cap) |
| `claude-3-haiku` | Anthropic API (€10/month cap) |

## RAG pipeline integration

Open WebUI connects to the on-cluster RAG pipeline for document-grounded answers:

```
User question (Open WebUI)
    ↓
LiteLLM gateway
    ↓  embed query
Qdrant (policy-docs, incident-reports collections)
    ↓  retrieve top-k chunks
LLM (vLLM / cloud)
    ↓  grounded answer
Open WebUI (with citations)
```

Collections available to users:
- `policy-docs` — insurance product terms and conditions
- `incident-reports` — historical claims reports (anonymised)
- `regulatory` — ACPR/EIOPA guidance documents

## IS use cases

| User | Use case |
|---|---|
| Claims handler | "What does policy clause 12.3 say about water damage?" |
| Underwriter | "Summarise the risk profile for this prospect sector" |
| HR | "Draft a DDA-compliant training reminder email" |
| Developer | "Explain this Spring Boot stack trace" |

## Related components

- [LiteLLM AI Gateway](ai-gateway) — model routing + cost controls
- [RAG Pipeline](rag-pipeline) — document retrieval
- [Langfuse](langfuse) — conversation traces and cost tracking
- [minicloud-crew-agent](https://github.com/andrelair-platform/minicloud-ops) — multi-agent workflows
