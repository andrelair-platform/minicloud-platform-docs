---
id: ollama
title: Phase 19 — Ollama + Open WebUI (self-hosted AI)
sidebar_position: 1
---

# Phase 19 — Self-Hosted AI: Ollama + Open WebUI

The minicloud cluster gets its own LLM endpoint. **Ollama** runs the
inference engine (Llama 3.2 3B on CPU); **Open WebUI** wraps it with a
ChatGPT-style frontend. Together they deliver a tangible, useful AI
service — accessible at `https://chat.10.0.0.200.nip.io` — that runs
entirely on your bare-metal cluster with zero external API calls.

The original Phase 19 plan was "Ollama + MLflow + Kubeflow." We
**deliberately scoped down to Ollama only** — same pattern as Phase 11
(OpenTofu shipped, Crossplane deferred), Phase 13 (GitHub Actions
shipped, GitLab deferred), Phase 16 (Harbor proxy cache shipped,
n8n/Temporal/Airflow deferred), Phase 18 (Backstage catalog shipped,
plugins/templates/SSO deferred). MLflow and Kubeflow have no
operational use case on a single-operator cluster with no active ML
pipelines; deferring them keeps the cluster usable for actual workloads.

---

## Architecture: why two components

```text
                    ┌─────────────────────────────────┐
   Browser          │   ai namespace                  │
       │  HTTPS     │                                 │
       │  + first-  │   ┌──────────────────────────┐  │
       │  user-     │   │ Open WebUI (StatefulSet) │  │
       │  becomes-  │   │   Python web server      │  │
       │  admin     │   │   ~825 MiB steady-state  │  │
       ▼            │   │   1 GiB Longhorn PVC     │  │
  cert-manager TLS  │   │   (SQLite + RAG          │  │
  + NGINX Ingress ─▶│   │    embeddings)           │  │
                    │   └─────────┬────────────────┘  │
                    │             │ HTTP              │
                    │             │ http://ollama:    │
                    │             │   11434            │
                    │             ▼                    │
                    │   ┌──────────────────────────┐  │
                    │   │ Ollama (Deployment)      │  │
                    │   │   inference engine       │  │
                    │   │   ~2.6 GiB RAM (model    │  │
                    │   │     hot in memory)       │  │
                    │   │   10 GiB Longhorn PVC    │  │
                    │   │   (model weights)        │  │
                    │   │   port 11434 (cluster-   │  │
                    │   │     internal only)       │  │
                    │   └──────────────────────────┘  │
                    └─────────────────────────────────┘
```

**Ollama is the engine; Open WebUI is the steering wheel.** Without
Open WebUI, all you have is a `curl`-able API — the architecturally
correct thing for backends to consume, but useless for human chat.
Open WebUI provides chat history, markdown rendering, multi-model
switching, and (built-in) RAG document upload.

**Why Ollama isn't exposed via Ingress:** unauthenticated LLM endpoints
are a real abuse vector — anyone reaching them can spam your CPU with
prompts. Open WebUI sits in front with auth. Ollama stays cluster-
internal.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Ollama install | Helm chart `otwld/ollama` v1.56.0 (app 0.23.2) | Standard install, configurable via Helm values |
| GPU | **None — CPU-only** | No NVIDIA GPUs on the ThinkPads. CPU works for 3B-7B models at usable speeds. |
| Model | **`llama3.2:3b`** (~2 GiB on disk + RAM) | Sweet spot for CPU on ThinkPads. Larger models (7B+) are 2-3x slower, marginal quality gain at this size. |
| Inference TPS | **~13 tokens/sec** sustained on CPU | Measured in the cold-start test. Roughly 10 words/sec — twice the human reading speed. |
| Ollama API exposure | **Cluster-internal only** (`http://ollama.ai.svc:11434`) | Unauthenticated LLM = abuse vector if exposed. Open WebUI is the gatekeeper. |
| Ollama persistence | 10 GiB Longhorn PVC at `/root/.ollama` | Model survives pod restarts; room for a 7B follow-up if added later |
| Open WebUI install | Helm chart `open-webui/open-webui` v14.4.0 (app 0.9.4) | Mature chart with sane defaults |
| Open WebUI database | SQLite on Longhorn (1 GiB) | Postgres is overkill for single-user demo. SQLite handles RAG embeddings + chat history + user accounts fine. |
| Open WebUI auth | First-user-becomes-admin (Open WebUI default) | Acceptable: TLS Ingress is internal-only via private nip.io hostname |
| Open WebUI memory | **1.5 GiB limit** (initial 512 MiB OOMKilled the pod) | Open WebUI bundles sentence-transformers + embedding models for RAG; startup needs 700-900 MiB before any traffic |
| TLS | cert-manager `chat-tls` Certificate, Phase 15 root CA | Same pattern as every other Ingress |
| Image source | Both `ollama/ollama:latest` and `ghcr.io/open-webui/open-webui:0.9.4` pulled through Phase 16 Harbor proxy cache | Validates Sovereign Registry pattern again |

---

## What's deliberately deferred

Same scope-reduction pattern as every prior phase:

| Component | Why deferred | Future home |
|---|---|---|
| **MLflow** | No active ML training workload to track | Future ML-pipeline phase when there's real model training |
| **Kubeflow** | 8-12 GiB RAM + Istio service-mesh dependency + days of setup; no pipelines to run | Future phase only if/when scale/use-case justifies it |
| **GPU support** | Hardware constraint (no NVIDIA on ThinkPads) | If/when a GPU node joins the cluster |
| **External API exposure for Ollama** | Security: unauthenticated LLM = abuse vector | Future "API gateway + auth" phase if a legitimate external consumer arrives |
| **Multiple models loaded simultaneously** | RAM budget says one model at a time | Pull on demand |
| **SSO for Open WebUI** | First-user-admin works for single-operator | Future Keycloak phase |

---

## Pre-flight

```bash
helm repo add otwld https://helm.otwld.com
helm repo add open-webui https://helm.openwebui.com
helm repo update
```

---

## Install Ollama

`ollama-values.yaml`:

```yaml
image:
  registry: docker.io
  repository: ollama/ollama
  tag: latest

ollama:
  port: 11434
  gpu:
    enabled: false   # CPU-only on ThinkPads

service:
  type: ClusterIP
  port: 11434

resources:
  requests: { cpu: "1",   memory: 2Gi }
  limits:   { cpu: "4",   memory: 8Gi }

persistentVolume:
  enabled: true
  storageClass: longhorn
  size: 10Gi
  accessModes: [ReadWriteOnce]
```

```bash
kubectl create namespace ai
helm install ollama otwld/ollama -n ai -f ollama-values.yaml --wait --timeout 5m

# Pull the model (~2 GiB; takes 30-90s through Phase 16 Harbor proxy)
kubectl exec -n ai deploy/ollama -- ollama pull llama3.2:3b

# Verify
kubectl exec -n ai deploy/ollama -- ollama list
# NAME           ID              SIZE      MODIFIED
# llama3.2:3b    a80c4f17acd5    2.0 GB    Less than a minute ago
```

> **Note on the Ollama model registry:** Ollama pulls models from
> `registry.ollama.ai`, not a standard OCI registry. The Phase 16
> Harbor proxy cache doesn't intercept this — model pulls go direct.
> This is acceptable: model pulls are infrequent (once per model) and
> the model weights are persisted to Longhorn after the first pull.

---

## Test Ollama API + measure TPS

```bash
kubectl run ollama-test --rm -i --restart=Never -n ai --quiet \
  --image=curlimages/curl:latest --image-pull-policy=IfNotPresent \
  -- curl -sf http://ollama:11434/api/generate \
       -d '{"model":"llama3.2:3b","prompt":"What is Kubernetes in one sentence?","stream":false}' \
  | jq '{
    eval_count,
    eval_duration_s: (.eval_duration / 1e9),
    tokens_per_second: (.eval_count / (.eval_duration / 1e9))
  }'
```

Expected on cold-start (first prompt after pod starts):

| Metric | Value |
|---|---|
| Wall-clock total | ~12 s |
| `load_duration_s` (model into RAM) | 1.9 s |
| `prompt_eval_duration_s` | 1.0 s |
| `eval_duration_s` | 1.7 s |
| **Tokens/sec (sustained)** | **~13** |

Subsequent prompts within the `keep_alive` window (5 min default) skip
the load step. 13 TPS = roughly 10 words/sec (about 2x human reading
speed). Genuinely usable.

After model load, Ollama pod memory stabilizes around **2.6 GiB**.

---

## Install Open WebUI

`open-webui-values.yaml`:

```yaml
# Disable the chart's bundled Ollama subchart — we have our own.
ollama:
  enabled: false

# Point at the existing Ollama Service via cluster DNS.
ollamaUrls:
  - http://ollama.ai.svc:11434

# Disable plugins/sidecars not needed for Phase 19.
pipelines:    { enabled: false }
tika:         { enabled: false }
websocket:    { enabled: false }
redis-cluster: { enabled: false }

resources:
  requests:
    cpu: 100m
    memory: 512Mi
  limits:
    cpu: 1000m
    # 512 MiB OOMKills the pod during init (Open WebUI loads
    # sentence-transformers + embedding models for RAG before serving
    # any traffic). 1.5 GiB is the right floor.
    memory: 1500Mi

persistence:
  enabled: true
  size: 1Gi
  storageClass: longhorn
  accessModes: [ReadWriteOnce]

ingress:
  enabled: false   # we add our own with cert-manager TLS

service:
  type: ClusterIP
  port: 80
  containerPort: 8080

extraEnvVars:
  - { name: WEBUI_NAME, value: "minicloud chat" }
  - { name: WEBUI_URL,  value: "https://chat.10.0.0.200.nip.io" }
```

```bash
helm install open-webui open-webui/open-webui -n ai \
  -f open-webui-values.yaml --wait --timeout 5m

kubectl get pods -n ai
# ollama-...                  1/1 Running
# open-webui-0                1/1 Running

kubectl get pvc -n ai
# ollama         10Gi
# open-webui     1Gi
```

---

## TLS Ingress

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: chat-tls
  namespace: ai
spec:
  secretName: chat-tls
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
  dnsNames: [chat.10.0.0.200.nip.io]
  duration: 2160h
  renewBefore: 720h
  privateKey: { algorithm: ECDSA, size: 256 }
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: chat
  namespace: ai
  annotations:
    nginx.org/redirect-to-https: "true"
    # Generous body size for RAG document uploads
    nginx.org/client-max-body-size: "10m"
    # NB: do NOT add nginx.org/websocket-services here — see Gotchas
spec:
  ingressClassName: nginx
  tls:
    - hosts: [chat.10.0.0.200.nip.io]
      secretName: chat-tls
  rules:
    - host: chat.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: open-webui
                port: { number: 80 }
```

---

## Two real install gotchas

### 1. Open WebUI OOMKilled at 512 MiB

Open WebUI bundles sentence-transformers + embedding models for RAG.
Initial memory budget of 512 MiB seemed generous for a "small Python
web server" but the bundled ML runtime needs 700-900 MiB before serving
any traffic. The pod silently CrashLoopBackOff with `exitCode: 137,
reason: OOMKilled` on the very first init. Bumping limit to 1.5 GiB
fixes it; observed steady-state ~825 MiB.

### 2. F5 NGINX `nginx.org/websocket-services` annotation breaks routing

I initially added `nginx.org/websocket-services: "open-webui"` thinking
WebSocket-aware routing was needed for the streaming chat. The F5 NGINX
controller misinterprets this and forwards traffic to
`http://127.0.0.1:8181/` (a phantom internal target). Result: 502 Bad
Gateway on every request.

Fix: remove the annotation. WebSocket upgrade is handled automatically
by NGINX without the `websocket-services` directive.

```bash
kubectl patch ingress chat -n ai --type=json \
  -p='[{"op":"remove","path":"/metadata/annotations/nginx.org~1websocket-services"}]'
```

---

## End-to-end verification

```bash
# Open WebUI HTTPS reachable
curl -sI --cacert ~/minicloud-ca.crt -m 5 https://chat.10.0.0.200.nip.io/
# HTTP/1.1 200 OK
# Server: nginx/1.29.7

# HTTP redirects to HTTPS
curl -sI -m 5 http://chat.10.0.0.200.nip.io/
# HTTP/1.1 301 Moved Permanently

# HTML title
curl -s --cacert ~/minicloud-ca.crt https://chat.10.0.0.200.nip.io/ \
  | grep -oE "<title>[^<]+</title>"
# <title>Open WebUI</title>
```

In the browser:

1. Open `https://chat.10.0.0.200.nip.io`
2. Click "Get started" → first user becomes admin (signup)
3. Send a prompt: "Hello, who are you?"
4. Response streams in within ~5-10 seconds at ~13 tokens/sec

---

## Memory pressure monitoring

Phase 17's reviewer flagged this:

> When the model is "hot" in RAM, the Ollama pod will sit close to its
> 4GB request. Keep an eye on `kubectl top pods -n ai`.

Real numbers:

```bash
$ kubectl top pod -n ai
NAME                 CPU(cores)   MEMORY(bytes)
ollama-...           814m         2630Mi      # model loaded + actively answering
open-webui-0         11m          825Mi       # idle
```

Total `ai` namespace footprint at idle: ~3.5 GiB out of the cluster's
~48 GiB. Comfortable.

If you load a 7B model alongside the 3B, expect ~6.5 GiB additional
usage. Pull on demand:

```bash
kubectl exec -n ai deploy/ollama -- ollama pull mistral:7b
```

---

## Done When

```text
✔ 2 pods Running in ai namespace (ollama + open-webui-0)
✔ 2 PVCs Bound on Longhorn (10 GiB ollama, 1 GiB open-webui)
✔ ollama list shows llama3.2:3b loaded
✔ Cert + Ingress for chat.10.0.0.200.nip.io serves 200 over HTTPS
✔ Browser signup works; first prompt returns a coherent response
✔ Ollama-reported eval rate ≥ 10 tokens/sec
✔ Homer has a "Chat" tile under Apps
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Self-hosted LLM inference on bare-metal CPU** | The fastest-growing portfolio piece in 2026. "I run my own AI" without API costs is a recruiter-recognizable headline. |
| **Frontend/backend separation: Ollama + Open WebUI** | Same pattern as every production AI deployment — inference engine separated from user-facing UI by an authenticated boundary |
| **Cluster-internal API exposure pattern** | Unauthenticated LLM endpoints exposed publicly are a real abuse vector. Keeping Ollama internal and routing through an authenticated Open WebUI is the production-correct shape. |
| **Memory budget tuning** | OOMKilled-then-debug-then-bump cycle is real production work. The 512→1500 MiB jump for Open WebUI is the kind of empirical sizing every shop does on first install. |
| **F5 NGINX annotation gotcha discovery** | Incorrect annotations silently misroute traffic. Reading ingress controller logs to find `127.0.0.1:8181` upstream is real Day-2 debugging. |
| **Tokens/sec measurement** | Reading `eval_count / eval_duration` from Ollama's API response is the canonical way to measure inference performance. Same shape as `tokens_per_second` in vLLM, llama.cpp, etc. |
| **Senior scope reduction** | Choosing Ollama only over Ollama + MLflow + Kubeflow is the same skill as every prior deferral (Crossplane, GitLab, Vault, Backstage plugins). |
| **Honest "we don't have GPUs" framing** | Naming the constraint (CPU-only ThinkPads) and choosing a model size that works there (3B) is more credible than pretending CPU inference is "the same as GPU." |
