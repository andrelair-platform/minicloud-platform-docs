---
id: custom-images
title: Custom-Built Images — Inventory & Upgrade Guide
sidebar_label: Custom Images
---

# Custom-Built Images — Inventory & Upgrade Guide

The platform runs several open-source tools that required patching,
custom Python services built from scratch, and one website. Each is a
custom container image pushed to Harbor. This page documents every
custom image, why it was built, where its source lives, and how to
upgrade it.

---

## The problem this solves

When a custom image has no source repo, three things break:

1. **You can't find it.** The only trace is an image tag in a manifest
   file. If the tag is a short SHA, it tells you nothing about what is
   inside.
2. **You can't upgrade it.** There is no Dockerfile to edit. You have to
   reverse-engineer what was changed from the running container.
3. **You can't recover it.** If Harbor loses the image and your Mac
   drive fails, the image is gone. No source means no rebuild.

Every custom image now has its own GitHub repo with a CI pipeline. A
code change triggers a build automatically. The upgrade path is always:
edit source → commit → push → CI does the rest.

---

## Inventory

### Custom services (written from scratch)

| Image | Repo | Harbor tag pattern | Used by |
|---|---|---|---|
| `markitdown-proxy` | [minicloud-markitdown-proxy](https://github.com/andrelair-platform/minicloud-markitdown-proxy) | `library/markitdown-proxy:<sha>-amd64` | Open WebUI (DOCLING_SERVER_URL), rag-ingest |
| `rag-ingest` | [minicloud-rag-ingest](https://github.com/andrelair-platform/minicloud-rag-ingest) | `library/rag-ingest:<sha>-amd64` | Document ingestion pipeline |

### Patched open-source images (upstream + fixes)

| Image | Repo | Harbor tag pattern | Why patched |
|---|---|---|---|
| `postgresql-noavx512` | [minicloud-postgresql-noavx512](https://github.com/andrelair-platform/minicloud-postgresql-noavx512) | `library/postgresql-noavx512:<version>-noavx512` | pgvector 0.8.4 AVX-512 SIGILL on i7-8565U/i7-10510U |
| `litellm-custom` | [minicloud-litellm-custom](https://github.com/andrelair-platform/minicloud-litellm-custom) | `library/litellm:<version>` | Prisma non-root fix + libatomic + google-generativeai |
| `backstage` | [minicloud-backstage](https://github.com/andrelair-platform/minicloud-backstage) | `library/backstage:<sha>-amd64` | Custom plugins + Authentik OIDC wiring |

### Open-source images used as-is (no patch)

These are tracked here for completeness. They use upstream images
directly — no custom build, no Harbor copy.

| Image | Source | Used by |
|---|---|---|
| `ghcr.io/docling-project/docling-serve-cpu:v1.26.0` | Docling project | markitdown-proxy routing, Open WebUI |
| `ghcr.io/open-webui/open-webui:0.9.4` | Open WebUI project | AI chat + init containers |

---

## Custom services

### markitdown-proxy

**What it does:** A FastAPI service that mimics the Docling
`/v1/convert/file` API. Open WebUI points `DOCLING_SERVER_URL` here.
The proxy routes requests based on file extension:

- `.pdf`, images → forwarded to Docling (layout analysis + OCR)
- `.docx`, `.xlsx`, `.pptx`, `.html`, `.txt`, `.md` → converted locally
  with the `markitdown[all]` Python library

**Why it exists:** Open WebUI needs one `DOCLING_SERVER_URL`. Docling
is a heavy GPU-optional container that handles PDFs well but cannot
convert Office files. This proxy adds Office support transparently
without changing Open WebUI config.

**Source:**
```
minicloud-markitdown-proxy/
├── Dockerfile       ← python:3.12-slim + fastapi + markitdown[all]
├── main.py          ← FastAPI app, routing logic
└── .github/workflows/ci.yml
```

**Manifest:** `minicloud-gitops/manifests/ai/10-markitdown-proxy.yaml`

---

### rag-ingest

**What it does:** A FastAPI service that implements the full RAG
ingestion pipeline in-cluster:

1. Accept file upload (PDF, DOCX, XLSX, PPTX, HTML, MD, TXT)
2. Convert via markitdown-proxy (same routing as above)
3. Split on French insurance structural boundaries (article/section
   headings detected by regex)
4. Embed each chunk with `bge-m3` (1024-dim, 100+ languages) via Ollama
5. INSERT directly into `ragdb` (pgvector) with rich metadata
   (`document_type`, `article`, `section`, `source`, `collection`)

**Why it exists:** Without it, ingestion required Python tools installed
on the Mac, a port-forward to the Ollama service, and manual SQL. This
service makes ingestion a single `curl -F file=@doc.pdf` from anywhere.

**API:**
```
POST /ingest   file, collection, source, doc_type
GET  /health
GET  /ready
```

**`doc_type` values:** `policy`, `endorsement`, `annexe`, `regulatory`,
`tariff`, `internal`

**Source:**
```
minicloud-rag-ingest/
├── Dockerfile       ← python:3.12-slim + fastapi + psycopg2-binary
├── main.py          ← FastAPI app, chunking, embedding, DB insert
└── .github/workflows/ci.yml
```

**Manifest:** `minicloud-gitops/manifests/ai/11-rag-ingest.yaml`

**Ingest a document:**
```bash
kubectl --context minicloud port-forward -n ai svc/rag-ingest 8001:8001 &
curl -s -X POST http://localhost:8001/ingest \
  -F "file=@/path/to/document.pdf" \
  -F "collection=<OPEN_WEBUI_KNOWLEDGE_BASE_UUID>" \
  -F "source=Contrat RC Pro 2026" \
  -F "doc_type=policy" | python3 -m json.tool
kill %1
```

---

## Patched open-source images

### postgresql-noavx512

**What it patches:** pgvector 0.8.4 inside Bitnami PostgreSQL 18.4.0.

**Why:** The upstream pgvector 0.8.4 build includes EVEX-encoded
(AVX-512) instructions in the HNSW index update code path. All four
cluster CPUs (i7-8565U, i7-10510U — Whiskey Lake / Comet Lake) lack
AVX-512 support. Every HNSW INSERT triggered a `SIGILL` fault, making
RAG document uploads fail silently.

**Fix:** The Dockerfile recompiles `vector.so` from source with
`-mno-avx512f -mno-avx512bw -mno-avx512vl -mno-avx512dq`, forcing GCC
to use only SSE4/AVX2 code paths. The resulting `vector.so` replaces
the one in the Bitnami image.

**Performance (measured):**
- HNSW index scan: 0.31 ms
- GIN FTS scan: 2.71 ms
- INSERT + HNSW update: 6.8 ms/row
- Embedding (bge-m3 via Ollama): 393 ms (dominates)

**How to upgrade when Bitnami releases a new PostgreSQL version:**

1. Edit `Dockerfile` in `minicloud-postgresql-noavx512` — change the
   `FROM` tag in both `AS builder` and the final stage.
2. Check whether the new pgvector version still has AVX-512 paths:
   ```bash
   objdump -d vector.so | grep -c 'zmm\|evex'
   ```
   If count is 0, the upstream fixed it — you can switch back to the
   standard image and delete this repo.
3. Commit and push. CI rebuilds and pushes to Harbor.
4. Update `harbor.10.0.0.200.nip.io/library/postgresql:` tag in
   `minicloud-gitops/helm-values/postgresql-ai-values.yaml`.

**Source:**
```
minicloud-postgresql-noavx512/
├── Dockerfile       ← multi-stage: recompile vector.so, copy into base
└── .github/workflows/ci.yml
```

---

### litellm-custom

**What it patches:** `ghcr.io/berriai/litellm-database:main-latest`

**Why — three fixes in one image:**

1. **Prisma non-root permissions:** The base image downloads Prisma
   engine binaries to `/root/.cache` (mode 700). When running as UID
   1000 in Kubernetes, `Path.exists()` on those paths raises
   `PermissionError` before any env var can override it. Fix:
   `chmod -R 755 /root /root/.cache`.

2. **libatomic missing:** The Node.js binary that prisma-client-py
   downloads at runtime to run Prisma CLI migrations requires
   `libatomic.so.1`. It is absent from the Alpine base. Fix:
   `apk add --no-cache libatomic`.

3. **google-generativeai missing:** The Gemini provider in LiteLLM
   requires this package. It is not in the base venv. Fix: bootstrap
   pip and install it.

**How to upgrade when LiteLLM releases a new version:**

1. Edit `Dockerfile` in `minicloud-litellm-custom` — change the
   `LITELLM_VERSION` ARG to the new version.
2. Commit and push. CI builds and pushes to Harbor, then bumps the
   image tag in `minicloud-gitops/manifests/ai/01-litellm-deployment.yaml`.
3. Verify the three fixes still apply — check if Prisma, libatomic, and
   google-generativeai issues are resolved upstream. If they are, remove
   the corresponding `RUN` layers.

**Source:**
```
minicloud-litellm-custom/
├── Dockerfile       ← ARG LITELLM_VERSION + 3 fix layers
└── .github/workflows/ci.yml
```

---

## CI pipeline (all four repos)

All four repos share the same CI pattern, triggered on every push to
`main`:

```
push to main
  │
  ├── docker/build-push-action → harbor.devandre.sbs/library/<name>:<tag>
  │
  ├── cosign sign (keyless, GitHub OIDC → Sigstore Fulcio)
  │
  └── clone minicloud-gitops → sed bump image tag → signed commit → push
            └── ArgoCD auto-syncs within 3 minutes
```

**Required GitHub secrets (set on each repo):**

| Secret | Value |
|---|---|
| `HARBOR_USER` | `admin` |
| `HARBOR_PASSWORD` | Harbor admin password |
| `GPG_PRIVATE_KEY` | Armored GPG private key (FD6D39D681DEFA34) |
| `GITOPS_TOKEN` | GitHub PAT with `repo` + `workflow` scopes |

---

## Open WebUI — runtime patches (no image rebuild)

Two modifications to Open WebUI are applied at pod start via init
containers, without rebuilding the image. These are documented here
because they represent custom logic that must be maintained.

### CA bundle injection (`inject-minicloud-ca`)

**What:** Concatenates the system CA bundle with the minicloud
self-signed CA certificate into `/ca-bundle/bundle.crt`. The main
container reads it via `SSL_CERT_FILE=/ca-bundle/bundle.crt`.

**Why:** Open WebUI's Python HTTP client cannot verify the minicloud CA
when calling Authentik token/JWKS/userinfo endpoints, causing
`SSL: CERTIFICATE_VERIFY_FAILED`. The `OAUTH_TLS_VERIFY=false` env var
does not exist in Open WebUI 0.9.4 — the only fix is injecting the CA.

**Where:** Helm values `open-webui-values.yaml` → `volumeMounts.initContainer`

**To upgrade:** If the Open WebUI image is upgraded and the CA
injection stops working, check whether `SSL_CERT_FILE` is still
respected in the new version's Python runtime.

### French BM25 patch (`patch-bm25-french`)

**What:** An init container that patches Open WebUI's `BM25Retriever`
at pod start to use a French NLTK Snowball stemmer and French stop-word
filter instead of the default whitespace tokenizer.

**Why:** The default tokenizer treats `sinistres` and `sinistre` as
different tokens — BM25 scores drop for French insurance vocabulary.
The stemmer normalises both to `sinistr`, `réassurance`/`réassurer`
to `réassur`, etc.

**Where:** The patch script lives in ConfigMap `bm25-french-patchscript`
in the `ai` namespace.
`minicloud-gitops/manifests/ai/09-bm25-french-patchscript.yaml`

**To upgrade:** When Open WebUI is upgraded, the patched file path
(`open_webui/utils.py`) may change. Verify the init container exits
with code 0 after upgrade:
```bash
kubectl logs -n ai open-webui-0 -c patch-bm25-french
```
If the patch fails, update the file path in the ConfigMap.

---

## Where each piece of custom logic lives — quick reference

| Custom logic | Location | How to find it |
|---|---|---|
| markitdown-proxy app code | `minicloud-markitdown-proxy/main.py` | GitHub repo |
| rag-ingest app code | `minicloud-rag-ingest/main.py` | GitHub repo |
| pgvector AVX-512 fix | `minicloud-postgresql-noavx512/Dockerfile` | GitHub repo |
| LiteLLM Prisma fix | `minicloud-litellm-custom/Dockerfile` | GitHub repo |
| Backstage customisation | `minicloud-backstage/` | GitHub repo |
| BM25 French stemmer | `manifests/ai/09-bm25-french-patchscript.yaml` | minicloud-gitops |
| Open WebUI CA injection | `helm-values/open-webui-values.yaml` initContainer section | minicloud-gitops |
| ktayl-solution-web | `ktayl-solution-web/` | GitHub repo |
| platform-demo (Go service) | `platform-demo/` | GitHub repo |

---

## Adding a new custom image

1. Create a new repo under `andrelair-platform/minicloud-<name>`.
2. Add `Dockerfile` + source code + `.github/workflows/ci.yml` (copy
   the pattern from any of the four repos above).
3. Set the four required secrets on the new repo.
4. Add a manifest in `minicloud-gitops/manifests/` referencing the
   Harbor image.
5. Add a component entry to `minicloud-gitops/catalog-info.yaml`.
6. Add the catalog URL to `helm-values/backstage-values.yaml`.
