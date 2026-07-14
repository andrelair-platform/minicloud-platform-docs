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
                    │   │   10 GiB local-path PVC  │  │
                    │   │   (model weights, NVMe)  │  │
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
| Models | **qwen3.5:4b, phi4-mini, deepseek-r1:7b, moondream, llava-phi3, llama3.2:1b, phi3-financial** (upgraded 2026-07-05 from initial llama3.2:3b) | CPU-optimal 4–7B Q4_K_M range. Vision models (moondream, llava-phi3) added for OCR/image analysis. See [Inference Optimization](inference-optimization) for rationale. |
| Inference TPS | **~10–35 tokens/sec** depending on model | llama3.2:1b: ~30 t/s · phi4-mini: ~15 t/s · qwen3.5:4b: ~12 t/s · deepseek-r1:7b: ~8 t/s |
| Ollama API exposure | **Cluster-internal only** (`http://ollama.ai.svc:11434`) | Unauthenticated LLM = abuse vector if exposed. Open WebUI is the gatekeeper. |
| Ollama persistence | 10 GiB **local-path** PVC at `/root/.ollama` on fast-heron (Phase 66) | Model weights are static re-downloadable assets — local NVMe avoids Longhorn replication overhead. No HA: if fast-heron is down, re-pull on restart. |
| Open WebUI install | Helm chart `open-webui/open-webui` v14.4.0 (app 0.9.4) | Mature chart with sane defaults |
| Open WebUI database | SQLite on Longhorn (1 GiB) | Postgres is overkill for single-user demo. SQLite handles RAG embeddings + chat history + user accounts fine. |
| Open WebUI auth | First-user-becomes-admin (Open WebUI default) | Acceptable: TLS Ingress is internal-only via private nip.io hostname |
| Open WebUI memory | **1.5 GiB limit** (initial 512 MiB OOMKilled the pod) | Open WebUI bundles sentence-transformers + embedding models for RAG; startup needs 700-900 MiB before any traffic |
| TLS | cert-manager `chat-tls` Certificate, Phase 15 root CA | Same pattern as every other Ingress |
| Image source | Both `ollama/ollama:0.23.2` (**pinned 2026-06-15**, was `:latest`) and `ghcr.io/open-webui/open-webui:0.9.4` pulled through Phase 16 Harbor proxy cache | Validates Sovereign Registry pattern again |

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
| **SSO for Open WebUI** | First-user-admin works for single-operator | Authentik SSO deployed (Phase 23) |

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
  # Pinned 2026-06-15 — see "Image tag pinning" section
  tag: "0.23.2"

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

nodeSelector:
  kubernetes.io/hostname: fast-heron   # added Phase 66

persistentVolume:
  enabled: true
  storageClass: local-path   # changed from longhorn in Phase 66
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

## Image tag pinning (2026-06-15)

Ollama was originally installed with `image.tag: latest` — a rolling reference to whatever upstream `ollama/ollama` had most recently published. During the 2026-06-15 platform-wide `:latest` audit (one of only two `:latest` references found cluster-wide), this was pinned.

**Change in `ollama-values.yaml`:**

```diff
 image:
   registry: docker.io
   repository: ollama/ollama
-  tag: latest
+  tag: "0.23.2"
```

Applied with:

```bash
helm repo add ollama https://otwld.github.io/ollama-helm/   # if not already added
helm upgrade ollama ollama/ollama --version 1.56.0 -n ai -f ollama-values.yaml
```

The chart version (`1.56.0`) was explicitly pinned too — same logic, no surprise upgrades.

**Why `0.23.2` specifically:**

| Requirement | How `0.23.2` meets it |
|---|---|
| Matches exactly what was running and validated | `kubectl exec deploy/ollama -- ollama -v` reported `0.23.2` at audit time |
| Llama3.2:3b model + Open WebUI integration proven at this version | 35+ days of continuous use at this exact version, ~13 TPS sustained |
| Upstream is at `0.30.x` — why not upgrade? | **Pin + upgrade in one move is anti-pattern.** A pin freezes known-good state; an upgrade is a separate deliberate change. Bundling them defeats the purpose of either. |

**Where the pinned values file lives:**

Mirrored to [`minicloud-ansible/helm-values/ollama-values.yaml`](https://github.com/andrelair-platform/minicloud-ansible/blob/main/helm-values/ollama-values.yaml) so it survives a controller wipe. Same pattern as `backstage-values.yaml`. Ollama is not in `minicloud-gitops` (direct Helm install, not yet ArgoCD-managed).

**Cluster-wide audit pattern:**

```bash
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: {range .spec.containers[*]}{.image}{"\n"}{end}{end}' | grep ':latest$'
```

Empty output = cluster is fully pinned. Full incident story (including the more dramatic Backstage `NotImplementedError` overlay symptom that surfaced the same anti-pattern) is in [the Phase 18 doc](../developer-platform/01-backstage.md#image-tag-pinning-2026-06-15).

---

## Phase 66 — Storage & Placement Update (2026-06-25, #64)

After Phase 63 (cluster hardening) and Phase 65 (Vault KMS), a follow-up improvement pinned Ollama to `fast-heron` and migrated its PVC from Longhorn to `local-path`.

### Rationale

| Issue | Impact |
|---|---|
| Ollama scheduled on any node | Model weights (2 GiB) would need to be re-pulled if the pod landed on a node where Longhorn hadn't yet attached the volume, causing 90–120s attachment delays on first inference |
| Longhorn replication for model weights | Model weights are static, re-downloadable assets — Longhorn's 3× replication wastes ~6 GiB of NVMe space and adds cross-node network traffic on every pod start |

`local-path` gives zero-latency local NVMe reads. The tradeoff is no high-availability: if `fast-heron` goes down, Ollama is unavailable until the node comes back. This is acceptable for a demo AI workload — model weights can be re-pulled in ~30s from the Ollama registry.

### What changed in `ollama-values.yaml`

```diff
+nodeSelector:
+  kubernetes.io/hostname: fast-heron
+
 persistentVolume:
   enabled: true
-  storageClass: longhorn
+  storageClass: local-path
   size: 10Gi
   accessModes:
     - ReadWriteOnce
```

### Migration procedure

```bash
# 1. Copy updated values to controller (controller dir is not a git clone)
scp ~/Developer/cloudplateform/minicloud-ansible/helm-values/ollama-values.yaml \
  controller:/home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/ollama-values.yaml

# 2. Scale down so PVC can be deleted cleanly
kubectl scale deployment ollama -n ai --replicas=0

# 3. Delete old Longhorn PVC
kubectl delete pvc ollama -n ai

# 4. Upgrade — creates new local-path PVC
helm upgrade ollama ollama/ollama --namespace ai \
  --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/ollama-values.yaml

# 5. Wait for pod ready then re-pull model
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=ollama -n ai --timeout=90s
kubectl exec -n ai deployment/ollama -- ollama pull llama3.2:3b

# 6. Verify
kubectl get pvc ollama -n ai
# NAME    STATUS  VOLUME                                   STORAGECLASS
# ollama  Bound   pvc-a2c782db-9c2f-4d81-baf9-9bef03ec5d29  local-path
kubectl get pod -n ai -l app.kubernetes.io/name=ollama -o wide
# NODE: fast-heron
kubectl exec -n ai deployment/ollama -- ollama list
# llama3.2:3b  a80c4f17acd5  2.0 GB
```

### Key gotcha: controller values directory is not a git repo

`/home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/` is a standalone directory on the controller, **not** a git clone. Running `git pull` there returns `fatal: not a git repository`. Whenever `ollama-values.yaml` (or any Helm values file) is updated in `minicloud-ansible` on the Mac, the file must be **scp'd** to the controller before running `helm upgrade` — otherwise the upgrade uses the old file silently and applies the wrong values.

---

## Done When

```text
✔ 2 pods Running in ai namespace (ollama + open-webui-0)
✔ ollama PVC is local-path (not longhorn)
✔ open-webui PVC is Longhorn (intentional — chat history is stateful)
✔ Ollama pod scheduled on fast-heron (nodeSelector)
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
