---
id: ollama
title: Phase 20 — Ollama
sidebar_position: 1
---

# Ollama — Run LLMs Locally on Your Cluster

Ollama lets you run large language models (LLaMA 3, Mistral, Phi-3, Gemma, etc.) as an API endpoint directly on your cluster. No OpenAI account, no API costs, no data leaving your network.

---

## Why Run LLMs on Bare-Metal

```text
✔ Zero API cost (models run locally)
✔ Data never leaves your infrastructure
✔ No rate limits
✔ Use in CI pipelines, internal tools, SaaS apps
✔ 24 cores + 48 GiB RAM is enough for 7B–13B parameter models
```

---

## What You Can Run

| Model | Parameters | RAM Required | Quality |
|---|---|---|---|
| Phi-3 Mini | 3.8B | ~4 GiB | Fast, good for coding |
| Mistral 7B | 7B | ~6 GiB | Excellent general purpose |
| LLaMA 3 8B | 8B | ~7 GiB | Best open-source general |
| LLaMA 3 70B | 70B | ~48 GiB | GPT-4 level (needs all 3 nodes) |
| Gemma 2 9B | 9B | ~8 GiB | Strong reasoning |
| CodeLlama 13B | 13B | ~10 GiB | Code generation |

Your cluster (48 GiB total) can run multiple 7B–13B models simultaneously across nodes.

---

## Deploy Ollama in k3s

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      containers:
        - name: ollama
          image: ollama/ollama:latest
          ports:
            - containerPort: 11434
          resources:
            requests:
              memory: "8Gi"
              cpu: "4"
            limits:
              memory: "16Gi"
              cpu: "8"
          volumeMounts:
            - name: ollama-data
              mountPath: /root/.ollama
      volumes:
        - name: ollama-data
          persistentVolumeClaim:
            claimName: ollama-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-pvc
  namespace: ai
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 50Gi
---
apiVersion: v1
kind: Service
metadata:
  name: ollama
  namespace: ai
spec:
  type: LoadBalancer
  selector:
    app: ollama
  ports:
    - port: 11434
      targetPort: 11434
```

```bash
kubectl create namespace ai
kubectl apply -f ollama.yaml
```

---

## Pull and Run a Model

```bash
# Get a shell in the pod
kubectl exec -n ai -it deploy/ollama -- /bin/bash

# Pull a model
ollama pull mistral
ollama pull llama3

# List models
ollama list

# Chat (interactive)
ollama run mistral
```

---

## Use the REST API

Ollama exposes an OpenAI-compatible API:

```bash
# From inside the cluster or via Tailscale/MetalLB
curl http://10.0.0.200:11434/api/generate \
  -d '{
    "model": "mistral",
    "prompt": "Explain Kubernetes in 3 sentences",
    "stream": false
  }'
```

---

## OpenAI-Compatible Endpoint

Use Ollama as a drop-in replacement for OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://10.0.0.200:11434/v1",
    api_key="ollama"   # any string works
)

response = client.chat.completions.create(
    model="mistral",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

---

## Deploy Open-WebUI (Chat Interface)

A full ChatGPT-like browser UI connected to your Ollama instance:

```bash
kubectl apply -n ai -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: open-webui
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: open-webui
  template:
    metadata:
      labels:
        app: open-webui
    spec:
      containers:
        - name: open-webui
          image: ghcr.io/open-webui/open-webui:main
          ports:
            - containerPort: 8080
          env:
            - name: OLLAMA_BASE_URL
              value: http://ollama:11434
---
apiVersion: v1
kind: Service
metadata:
  name: open-webui
  namespace: ai
spec:
  type: LoadBalancer
  selector:
    app: open-webui
  ports:
    - port: 80
      targetPort: 8080
EOF
```

Access at `http://10.0.0.201` — your private ChatGPT.

---

## Done When

```text
✔ Ollama pod Running with persistent storage
✔ At least one model pulled (mistral or llama3)
✔ REST API responding on MetalLB IP
✔ Open-WebUI accessible in browser
✔ Python client connecting successfully
```
