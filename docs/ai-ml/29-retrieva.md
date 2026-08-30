---
title: Retrieva — Governed RAG (DORA third-party ICT risk)
sidebar_label: Retrieva (RAG)
---

# Retrieva — Governed RAG on the platform

> Enterprise RAG application for **DORA third-party ICT risk** (vendor
> questionnaires, DORA compliance assessments), deployed on minicloud as the
> reference [AI platform golden-path](./28-ai-platform-golden-path.md) consumer:
> it *plugs into* the shared LLMOps stack instead of rebuilding it.

**Repo:** [andrelair-platform/retrieva](https://github.com/andrelair-platform/retrieva) ·
**Live (prod):** https://retrieva.online

## What it is

Retrieva is a Next.js (frontend) + Express (backend) application with MongoDB,
Redis/BullMQ and Qdrant. On minicloud it does **not** run its own LLM or
embedding stack — it points at the governed **LiteLLM gateway** and a shared
**Qdrant**, inheriting EU-residency, PII masking, budgets, observability and
audit for free. It owns only its business logic.

## Architecture (on minicloud)

```
Browser ── HTTPS ──> Cloudflare edge ──> cloudflared (HA, k8s) ──> ingress-nginx
                                                                      │  host-routing
                                              /  ──────────────> retrieva-frontend :3000
                                              /api, /socket.io ─> retrieva-backend  :3007
retrieva-backend ──> MongoDB (own)  ──> Redis/BullMQ (own)
                └──> LiteLLM gateway (ai ns) ──> EU cloud (prod) | free tier (dev)
                └──> Qdrant (ai ns, own collection)
```

| Component | Detail |
|---|---|
| Frontend | Next.js 16, `NEXT_PUBLIC_*` baked at build → per-environment image |
| Backend | Express 5, uid 1001, `:3007`, `/health` |
| Datastores | MongoDB 7 + Redis/Valkey (one set per environment) |
| Vectors | shared Qdrant (`retrieva` / `retrieva-dev` collections) |
| LLM/embeddings | via LiteLLM (Azure-passthrough) — never a provider SDK directly |

## Public exposure chain (prod)

`retrieva.online` is an **own apex domain** (registrar NameCheap) migrated onto
the platform's Cloudflare account and served through the existing minicloud
tunnel:

1. Zone added to Cloudflare → nameservers switched at the registrar.
2. A proxied `CNAME @` → the tunnel; a `retrieva.online` block in the cloudflared
   HA ConfigMap routes it to `ingress-nginx` (`originServerName: retrieva.online`).
3. A k8s Ingress does host + path routing; TLS terminates at Cloudflare's edge
   (Universal SSL), with an internal **minicloud-ca** cert on the tunnel hop
   (the Vault PKI role must allow the domain — `allowed_domains` + bare-domain).

## Two environments, two AI tiers

The **golden-path 2-env model** (dev + prod) with the cost/residency split
enforced by the gateway, not by app config:

| | prod (`retrieva.online`) | dev (`retrieva-dev.10.0.0.200.nip.io`) |
|---|---|---|
| Exposure | public (Cloudflare tunnel) | internal (Tailscale + CA) |
| LiteLLM team | `retrieva` — `[onprem, eu]` | `retrieva-dev` — EU + free models |
| Generation | **AWS Bedrock / Azure OpenAI (EU)** | **free tier — Ollama Cloud** |
| Embeddings | mistral-embed (EU) | mistral-embed (EU, negligible cost) |
| Vault path | `secret/platform/retrieva` | `secret/platform/retrieva-dev` |

Cloud (paid, EU-resident) providers are reachable **only** by the prod team;
dev maximises the free tier. Apps select the model by deployment name; the team
RBAC enforces which tiers each environment can reach.

## Governance enforced by the network

The RAG backend runs behind an **egress NetworkPolicy** (`backend-egress-governed`):
it may egress **only** to DNS, the LiteLLM gateway + Qdrant (ai namespace) and
its own Mongo/Redis. Any direct call to an external LLM provider
(`ollama.com`, `api.groq.com`, `api.openai.com`, …) is dropped at L3/L4 — so
EU-residency / PII / audit governance holds even if the application code is
misconfigured. Verified: `fetch('https://ollama.com')` from the backend =
blocked; `fetch('http://litellm.ai.svc:4000')` = 200.

## How to verify

```bash
# prod public
curl -sI https://retrieva.online/                    # 200, valid edge TLS
# dev internal (Tailscale + CA)
curl --cacert ~/minicloud-ca.crt \
  --resolve retrieva-dev.10.0.0.200.nip.io:443:10.0.0.200 \
  -sI https://retrieva-dev.10.0.0.200.nip.io/         # 200
# governed LLM path (from the backend pod, via LiteLLM)
kubectl -n retrieva exec deploy/retrieva-backend -- \
  node -e '/* POST /openai/deployments/tier-premium/chat/completions */'
```

## Compliance mapping

- **DORA third-party ICT risk** — the business capability itself; audit trail via
  Langfuse per-call + the [model governance matrix](./12-ai-gateway.md).
- **EU residency** — prod on Bedrock (eu-west-1) + Azure (Sweden), enforced by
  team RBAC + the egress allowlist.
- **GDPR / AI-Act** — Presidio PII masking + LlamaGuard at the gateway, inherited.

## Status

Prod live at `retrieva.online`; dev live internally. Both **Synced/Healthy**.
Full detail (data model, API, runbooks) lives in the repo.
