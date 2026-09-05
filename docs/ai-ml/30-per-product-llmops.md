---
id: per-product-llmops
title: Per-Product LLMOps — reusable standard
sidebar_label: Per-Product LLMOps (standard)
---

# Per-Product LLMOps — reusable standard

## Overview

The [AI Gateway](./12-ai-gateway.md) already gives **platform-wide** LLM observability:
every call routed through LiteLLM is auto-traced into a single global
[Langfuse](./14-langfuse.md) project (`ai-gateway`). That answers *"what is the
platform's LLM traffic doing?"* but not *"what is **this product's** RAG feature
doing, end to end?"* — a gateway trace is one model call, not the
`retrieval → rerank → generation` flow a product owner cares about.

This page defines the **repeatable golden path** for giving any custom product its
own **product-scoped** LLMOps: a dedicated Langfuse project with app-level traces
(`Trace → span → generation`, keyed by `session_id`/`user_id`), on top of — not
instead of — the gateway's automatic per-call traces. Reference implementation:
**retrieva** (`retrieva` Langfuse project, live 2026-09-05).

:::note Two layers, one Langfuse
**Gateway layer** (automatic): LiteLLM `success_callback:[langfuse,prometheus]` →
the global `ai-gateway` project. Nothing to do per product.
**App layer** (this standard): the product's backend emits its own trace tree to a
**dedicated project** via the Langfuse core SDK. This is what makes a RAG feature
auditable as a *feature*, not just a stream of model calls.
:::

## Architecture

```
                       ┌─────────────────────────── product backend (e.g. retrieva) ───────────────────────────┐
  user question ──────▶│  RAGService.askWithConversation()                                                      │
                       │     startTrace(name, sessionId=convId, userId, tags)  ── config/tracing.js (core SDK)  │
                       │        ├─ span "retrieval"   (query rephrase → vector search → rerank)                 │
                       │        └─ generation "answer"(model, input, output)  ──┐                               │
                       └───────────────────────────────────────────────────────┼───────────────────────────────┘
   LLM calls inside the flow still go through the AI Gateway ──▶ LiteLLM ────────┘ (also auto-traced → ai-gateway project)
                                                                     │
   app trace tree (this standard) ─── Langfuse SDK POST /api/public/ingestion ──▶ langfuse-web ──▶ Redis/MinIO
                                                                     │                                    │
                                                                     ▼                                    ▼
                                                            (dedicated project)                    langfuse-worker
                                                             e.g. "retrieva"  ◀──── ClickHouse ◀──────────┘
```

Credentials, network and config all flow through existing platform mechanisms
(Vault → ESO → k8s Secret; two-sided NetworkPolicy; per-overlay env).

## The 6-step golden path (per product)

### 1. Create the dedicated Langfuse project (UI)

Create the project in the Langfuse UI under the `minicloud-platform` org and copy
its `pk-lf-…` / `sk-lf-…` keys.

:::warning The provisioning API is Enterprise-gated
`POST /api/admin/projects` (and the org/project bootstrap API) returns
`403 {"error":"This feature is not available on your current plan."}` on the OSS
build — `ADMIN_API_KEY` only unlocks it on Langfuse EE. **Do not** wire an
`ADMIN_API_KEY` to script project creation on OSS; create the project by hand in
the UI, once, and store the keys (next step).
:::

### 2. Store the keys in Vault (reusable)

One path per product, distinct from the product's per-env secret paths:

```bash
# write needs the Vault ROOT token
vault kv put secret/platform/langfuse/<product> public-key=pk-lf-… secret-key=sk-lf-…
```

The **same project keys are used for dev and prod** — traces from both
environments land in one product view, kept distinguishable by Langfuse's native
**`environment`** attribute (see the box below). (Keys live at
`secret/platform/langfuse/<product>`, *not* under the per-env
`platform/<product>` / `platform/<product>-dev` paths.)

:::tip One project, dev + prod — the `environment` attribute
You **don't** (and often *can't*, on OSS with a project cap) create one Langfuse
project per environment. Use the **single shared project** and set Langfuse's
first-class **`environment`** attribute per environment — the UI then gives you an
**Environment filter/scope** (and per-environment dashboards) over the one project.

Because the image is **env-agnostic** (the same artifact runs dev & prod — a Kargo
prerequisite — and `NODE_ENV=production` in *both*), the environment **cannot** come
from inside the image. It must be a **per-overlay env var**:

```yaml
# base/<backend>.yaml         → default for prod
- { name: LANGFUSE_TRACING_ENVIRONMENT, value: "production" }
# minicloud-1/dev/backend-patch.yaml → dev overlay overrides it (merged by env name)
- { name: LANGFUSE_TRACING_ENVIRONMENT, value: "development" }
```

The backend passes it to the SDK: `new Langfuse({ environment })` (the SDK also
auto-reads `LANGFUSE_TRACING_ENVIRONMENT`). Value must match
`^(?!langfuse)[a-z0-9-_]+$`. As belt-and-suspenders (older UIs), the reference
module also adds an `env:<value>` **tag** and `metadata.environment` to every
trace, so you can filter by tag if the Environment scope isn't available. Same
pattern for `session_id`/`user_id` grouping — all within the one project.
:::

### 3. ESO → the product's k8s Secret

Add two keys to the product's `ExternalSecret` — in **base** (prod) and in the
**dev overlay patch** (both read the shared project path):

```yaml
# services/<product>/base/externalsecret.yaml  AND  minicloud-1/dev/externalsecret-patch.yaml
- secretKey: langfuse-public-key
  remoteRef: { key: platform/langfuse/<product>, property: public-key }
- secretKey: langfuse-secret-key
  remoteRef: { key: platform/langfuse/<product>, property: secret-key }
```

:::warning ESO SSA no-op when adding keys
Adding new `.spec.data` keys to an existing `ExternalSecret` can silently no-op
under ArgoCD ServerSideApply (field-ownership): the sync "Succeeds" but the new
keys never render into the target Secret. **Fix:** after the app has synced the
new spec, `kubectl delete externalsecret <name> -n <ns>` → ArgoCD recreates it
fresh and all keys render. Running pods keep their already-injected env.
:::

### 4. Backend env — in-cluster Langfuse URL + keys

```yaml
# services/<product>/base/<backend>.yaml
- { name: LANGFUSE_BASE_URL, value: "http://langfuse-web.langfuse.svc.cluster.local:3000" }
- { name: LANGFUSE_TRACING_ENVIRONMENT, value: "production" }   # dev overlay overrides to "development"
- name: LANGFUSE_PUBLIC_KEY
  valueFrom: { secretKeyRef: { name: <product>-secrets, key: langfuse-public-key } }
- name: LANGFUSE_SECRET_KEY
  valueFrom: { secretKeyRef: { name: <product>-secrets, key: langfuse-secret-key } }
```

Use the **in-cluster service URL** (`langfuse-web.langfuse.svc…:3000`), not the
public `langfuse.devandre.sbs` — it matches the egress NetworkPolicy, needs no
TLS/hairpin, and keeps trace traffic on-cluster.

### 5. Two-sided NetworkPolicy (both ends must allow it)

A default-deny on either side drops the traffic silently, so **both** rules are
required:

- **Egress** (product side): allow the backend → `langfuse` ns `:3000`. The
  backend-egress policy is **label-scoped** — the emitting pod must carry the
  label the policy selects (e.g. `app: <product>-backend`), or its egress is
  dropped even with the rule present.
- **Ingress** (langfuse side): add the product's namespaces to the
  `allow-app-tracing` ingress NetworkPolicy in
  `manifests/langfuse-base/03-networkpolicies.yaml` (podSelector
  `app.kubernetes.io/name: langfuse`, port 3000). LiteLLM (`ai` ns) is covered by
  a separate `allow-litellm-tracing` rule; app products need this one.

### 6. App-level tracing via the core SDK

Add a small `config/tracing.js` (or equivalent) that owns Langfuse init and hands
back a **null-safe** trace handle, then instrument the RAG flow.

:::warning LangChain v1 forces the core SDK (not the callback handler)
`langfuse-langchain`'s peer dep is `langchain <0.4.0`. A product on **LangChain
v1** (`@langchain/core ^1.x`) cannot use the `CallbackHandler` — use the **core
`langfuse` SDK** (`langfuse.trace()` → `.span()` / `.generation()` → `.end()` →
`flushAsync()`) and build the span hierarchy manually. This is the retrieva
pattern.
:::

Key properties of the reference module:

- **Init is dynamic + guarded** (`await import('langfuse')` inside try/catch) so a
  missing optional dep or bad key never breaks module load — tracing just disables
  itself (`isLangfuseEnabled()` → false, spans become no-ops).
- **`startTrace({name, sessionId, userId, input, tags, metadata})`** returns a
  handle exposing `span()`, `generation()`, `update()`, `flush()` — all no-ops
  when disabled, so call sites never need `if (enabled)` guards.
- Instrument the flow: one trace per request, a `retrieval` **span** around
  search+rerank, an `answer` **generation** around the LLM call, then
  `trace.update({output}); trace.flush()`. Use `sessionId = conversationId` so
  Langfuse groups a conversation, and `userId` for per-user analytics.
- **npm workspaces double-lock trap:** in a monorepo (`workspaces:[backend,…]`),
  the CI test job installs from the **root** `package-lock.json` while Docker
  builds from `backend/package-lock.json`. A new dep (`langfuse`) must be in
  `backend/package.json` **and both** lockfiles, or CI (`Cannot find package`) or
  the image will break.

### 7. Prompt Management (decoupled, label-routed) — mandatory

Managed prompts live in the **dedicated Langfuse project**, not hardcoded in Git —
so product/domain experts tweak them in the UI and roll out/back with **zero
redeploy**, and every LLM call links to the exact prompt version.

- **Decoupled deployment + Git fallback (no SPOF):** store system prompts / few-shot /
  output schemas in Langfuse; keep the Git copy as the **seed + runtime fallback**.
  Resolve Langfuse-first; if it's disabled/unreachable/absent, fall back to the
  committed template. Prompt management must never take the app down.
- **Dynamic label routing (one project, dev + prod):** pull by **label**, not a pinned
  version, via a per-overlay **`LANGFUSE_PROMPT_LABEL`** (prod=`production`,
  dev=`latest`; `canary` optional). Relabelling a version rolls out/back instantly.
- **Mustache + typing:** template vars are `{{var}}`, compiled with `prompt.compile(vars)`;
  declare the variable list in the prompt `config`. Keep the message **structure**
  (history + user turn) in code and render the managed system text as a **literal**
  message so compiled content isn't re-parsed by the chain framework.
- **Trace-linked attribution:** pass the resolved Langfuse prompt object as `prompt`
  on the generation → each answer links its prompt **version** (A/B + regression).
- **Playground:** non-devs tweak templates + params against real trace data in the UI.

```js
// resolve (label-routed) → compile → build chain → link version
const p = await getLangfusePrompt('retrieva-rag-system', { label: process.env.LANGFUSE_PROMPT_LABEL });
const systemText = p ? p.compile({ context, responseInstruction })       // Langfuse (Mustache)
                     : renderGitFallback({ context, responseInstruction }); // never a SPOF
answerGen.update({ prompt: p });   // trace-linked prompt-version attribution
```

Seed a prompt once via the SDK (`langfuse.createPrompt({ name, type:'text', prompt,
labels:['production'], config:{variables:[…]} })` — the newest version also gets
`latest`). Reference: retrieva `config/promptManager.js` + `prompts/ragPrompt.js`
(prompt `retrieva-rag-system`).

## Operate / verify / audit

```bash
# keys from Vault (read via root token on controller)
D=$(curl -sk --cacert ~/minicloud-ca.crt -H "X-Vault-Token: $(cat ~/.vault-root-token)" \
     https://vault.devandre.sbs/v1/secret/data/platform/langfuse/<product>)
PK=$(echo "$D" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["data"]["public-key"])')
SK=$(echo "$D" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["data"]["secret-key"])')

# list the product's traces (proves read + project mapping)
curl -sk --cacert ~/minicloud-ca.crt -u "$PK:$SK" \
  "https://langfuse.devandre.sbs/api/public/traces?limit=10"

# emit a trace from the real backend runtime (proves write + egress + ingress)
#   node --input-type=module, import('/app/config/tracing.js'), startTrace→span→generation→flush
```

**A 207 from `/api/public/ingestion` only means *queued*.** In Langfuse v3 the web
tier accepts to Redis/MinIO and the **worker** writes to ClickHouse. If traces are
accepted (207/201) but never appear in the read API, the failure is downstream —
check the worker logs and ClickHouse, not the app. See the incident note below.

:::danger ClickHouse system logs fill the PVC → all traces dropped (2026-09-05)
Langfuse's ClickHouse ships internal telemetry tables (`system.trace_log`, the
sampling profiler, plus `text_log`/`metric_log`/…) with **no TTL**. On this
platform `system.trace_log` reached **25 GiB** (1.06 B rows) on the 30 Gi PVC →
100% full → ClickHouse returned `code 243 NOT_ENOUGH_SPACE` on every insert and
the worker **dropped every trace** (LiteLLM + app-level) after max retries. The
real Langfuse data was ~2 MiB.

**The fix has two halves — a config half and a live half:**

- **Config (`clickhouse.extraOverrides`): disable the sampling query profiler** that
  feeds `system.trace_log` (25 GiB, >80% of the fill) — a settings profile, so no
  engine conflict:
  ```xml
  <clickhouse><profiles><default>
    <query_profiler_real_time_period_ns>0</query_profiler_real_time_period_ns>
    <query_profiler_cpu_time_period_ns>0</query_profiler_cpu_time_period_ns>
  </default></profiles></clickhouse>
  ```
- **Live: `ALTER TABLE system.<log> MODIFY TTL event_date + INTERVAL 3 DAY`** for the
  remaining smaller logs (text_log/metric_log/…). This persists on the PVC across
  restarts, so it's the durable bound for those.

**Do NOT** try to disable/bound these logs with `<trace_log remove="1"/>`,
`<trace_log><enabled>false</enabled></trace_log>`, or a `<trace_log><ttl>…</ttl></trace_log>`
sub-element in config. All three are wrong: the first two are no-ops (the logs are ON
by ClickHouse **compiled-in default**, so removing the config node just falls back to
the enabled default), and a **`<ttl>` sub-element crashes ClickHouse on startup**
(`BAD_ARGUMENTS code 36: TTL should be specified inside 'engine'`) because the bitnami
base config already defines each log's `<engine>` — that took CH into CrashLoopBackOff
platform-wide. `MODIFY TTL` works *live* (the table already exists) but the same TTL in
*config* does not.

**Emergency cleanup of a 100%-full ClickHouse:** `TRUNCATE` itself fails (it needs
to reserve 1 MiB) — use `DROP TABLE system.trace_log SYNC`, which unlinks parts
directly and breaks the deadlock (system tables recreate on restart).
:::

## Status

| Product | Langfuse project | Vault path | Live |
|---|---|---|---|
| retrieva | `retrieva` | `secret/platform/langfuse/retrieva` | ✅ 2026-09-05 (dev) |

Next products follow the 6 steps above — the only per-product manual step is
creating the project + copying keys (step 1); everything else is
copy-and-rename from the retrieva overlays.
