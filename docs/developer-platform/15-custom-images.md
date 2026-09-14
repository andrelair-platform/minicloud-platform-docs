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

## When does a vendor app get its own repo? (the Backstage pattern)

A natural question: *"we have `minicloud-backstage`; should every end-user vendor app (GLPI, ERPNext,
etc.) get a repo too?"* The honest answer from the evidence is: **the discriminator is not
"end-user-facing," it's "is there a custom artifact to own"** — either a **custom image/build** *or*
**custom application code / config-as-code / business logic** worth versioning. Both need a repo
(`Dockerfile`/source + CI) to be findable, upgradable, recoverable — and both *are* the visible
**work evidence** for a portfolio/cert. A **pure stock chart** driven only by a values file has no such
artifact → no repo.

Look at what actually has a repo vs not:

| App | End-user-facing? | Custom artifact to own? | Has a repo? |
|---|---|---|---|
| Backstage | yes | **yes** — custom plugins, `yarn build` | ✅ `minicloud-backstage` |
| Open WebUI | yes | **yes** — `Dockerfile` (CA cert, French BM25) | ✅ `minicloud-open-webui` |
| OnlyOffice | yes | **yes** — `Dockerfile` (CA cert, `NODE_EXTRA_CA_CERTS`) | ✅ `minicloud-onlyoffice` |
| **ERPNext** | yes | **yes** — custom image (Factur-X + pypdf) **and** custom Frappe apps (`erpnext_dsn`, `erpnext_facturx`, `erpnext_sepa`) + tests | ✅ **`minicloud-erpnext`** |
| Grafana / Vault / Harbor / Loki / NATS | yes (mostly) | **no** — stock chart + values only | ❌ none — just `helm-values/` + `apps/` |

Grafana, Vault and Harbor are all end-user-facing, yet run **stock upstream images configured only via
`helm-values/`** — no custom artifact → **no repo**. ERPNext looks like "just config" from the cluster,
but it carries **real custom work** (a Factur-X e-invoicing image *and* French DSN/SEPA/Factur-X Frappe
apps with tests) → it rightly has `minicloud-erpnext`. That custom business logic is exactly the kind of
thing a repo makes **referenceable and demonstrable**.

### The rule

```
Is there a custom artifact to own?
  (a) a custom image/build — baked plugins, CA trust, a patch, compiled-from-source
  (b) custom app code / config-as-code / business logic — a Frappe app, custom
      DocTypes, migrations, generators, tests
        │
   ┌────┴────┐
  YES        NO
   │          │
   ▼          ▼
 own repo   NO repo —
 (Dockerfile/  just helm-values/<app>-values.yaml
  source + CI)  + an apps/ Application pointing at
 + helm-values/ the stock upstream chart
 + apps/
```

The deployment config **always** stays in gitops (`helm-values/` + `manifests/` + `apps/`) regardless —
the repo owns the *artifact/code*, gitops owns *how it's deployed*.

**So for GLPI:** it typically needs a custom image (internal-CA trust, ITIL plugins, PHP config) **and**
carries config-as-code → it correctly has a home repo (`ktayl-itsm`) owning the **Dockerfile + app
config**, with deployment in gitops (`helm-values/` + `manifests/ktayl-itsm/` + `apps/`). A future
vendor app that runs a **stock community chart unchanged with no custom code** gets **no repo** — only
`helm-values/` + `apps/`. The guard against sprawl is *"is there a real artifact/code to hold?"*, not
"is it user-facing" — that's what keeps ~90 workloads from becoming ~90 repos while still giving every
piece of genuine custom work its own referenceable home.

---

## CA trust: bake vs runtime (the `trust-manager` decision)

Most of the platform's "patched" images exist for **one reason: to trust the internal `minicloud-ca`**
(so the app can verify TLS to other internal services). That is a *config* need, not a real artifact —
and there are two ways to meet it:

| Approach | Repo needed? | CA rotation | Trade-off |
|---|---|---|---|
| **Bake CA into a custom image** (`ARG CA_CERT` → `update-ca-certificates`) | ✅ yes (Dockerfile + CI) | **rebuild + repush every image** | self-contained + scannable, and doubles as work evidence — but a repo to maintain and a rotation rebuilds everything |
| **Inject CA at runtime** (mount a ConfigMap + `NODE_EXTRA_CA_CERTS`) | ❌ no — `helm-values/` + `manifests/` only | **update one file, restart pods** | lighter, stock image, no repo — relies on the chart supporting a volume/env mount |

### Recommendation

**For CA trust alone, prefer runtime injection — and do it cluster-wide with `trust-manager`.** CA
certs rotate; baking forces a rebuild of *every* image on each rotation, and couples a deploy-time infra
detail into a build artifact (the same anti-pattern as baking `NEXT_PUBLIC_*`). Runtime injection keeps
you on the **stock vendor image** (no repo), and rotation becomes "update one file."

`trust-manager` (a cert-manager sub-project) distributes the CA to **every namespace** automatically as
a ConfigMap + Secret `minicloud-ca-bundle` (key `ca.crt`). A new app then just:

```yaml
# pod spec (via the chart's values)
volumes:
  - name: ca
    configMap:
      name: minicloud-ca-bundle
volumeMounts:
  - name: ca
    mountPath: /etc/ssl/certs/minicloud-ca.crt
    subPath: ca.crt
    readOnly: true
env:
  # Node apps; others just use the mounted file via the OS trust store
  - name: NODE_EXTRA_CA_CERTS
    value: /etc/ssl/certs/minicloud-ca.crt
```

**Bake a custom image only for a real artifact** — added binaries/plugins/code, a specific unpatched
CVE, or an app that genuinely can't read a mounted CA. **CVE hygiene** is better handled by Renovate
(auto-bump to the vendor's latest patched tag) + Trivy scanning than by an `apt upgrade` layer (which is
non-reproducible — note the `apt-mark hold` workarounds in the baked images).

**Status:** ✅ **live and verified.** `trust-manager` + the `minicloud-ca-bundle` Bundle are wired in
gitops (`apps/platform/trust-manager.yaml`, `helm-values/minicloud-1/trust-manager-values.yaml`,
`manifests/cert-manager-config/02-trust-bundle-minicloud-ca.yaml`) — the CA ConfigMap **and** Secret are
distributed across **all ~73 namespaces**. Go-forward: **new apps use the runtime mount below**; the
existing baked images (OnlyOffice, Open WebUI, Backstage) stay as-is (consistency > churn) and can
migrate opportunistically.

### How it works, day-to-day (the lifecycle, jargon-free)

**The core problem.** Your internal services talk to each other over TLS, but they use a **private**
certificate authority (`minicloud-ca`) that stock software doesn't know about. By default, a stock
container image (Node.js, Python, curl…) hitting an internal URL signed by your CA throws an
*untrusted certificate* error.

**The old way — baking.** You wrote a `Dockerfile`, used `ARG CA_CERT`, copied the private cert into the
image's OS trust store, and built it. The pain: every CA rotation/expiry meant **rebuild the image →
push to the registry → bump the manifest → redeploy** — and you maintained a whole GitHub repo just for
that image wrapper.

**The new way — runtime injection via `trust-manager`.** Instead of hiding the cert *inside* the image
at build time, you hand it to the container **when it starts**. Think of `trust-manager` as an automated
postal worker for the cluster:

1. **The source** — `minicloud-ca` lives centrally in the cluster (the cert-manager Vault issuer).
2. **The robot (`trust-manager`)** — it watches a `Bundle` resource. It grabs the `minicloud-ca`
   certificate and **mirrors it into a clean `ConfigMap` named `minicloud-ca-bundle` in *every*
   namespace** (plus a Secret of the same name). If the CA ever updates, the robot re-mirrors it to
   every namespace automatically.
3. **The application** — no custom Dockerfile, no private repo. You run the **stock upstream image**
   (e.g. `onlyoffice/documentserver`) and tell Kubernetes two things in the Helm chart / deployment YAML:
   - **Mount** the `minicloud-ca-bundle` ConfigMap into the pod as a file (e.g. at
     `/etc/ssl/certs/minicloud-ca.crt`).
   - **Set an env var** pointing the runtime at that file — `NODE_EXTRA_CA_CERTS=/etc/ssl/certs/minicloud-ca.crt`
     for Node apps (equivalent flags for other runtimes, or drop it into the OS trust dir).

   (See the copy-paste pod snippet earlier in this section.)

**What this means going forward:**
- **New apps** → use the vendor's stock image directly; just add the volume mount + env var for the CA
  bundle. **Zero Dockerfiles, zero build pipelines, zero repo.**
- **Certificate rotation** → `trust-manager` updates every ConfigMap; apps pick up the new cert on
  their next pod restart. **No code changes, no image rebuilds.**

**Wiring gotcha (learned in the spike):** the `Bundle` CR is **cluster-scoped**, so it must be in the
ArgoCD AppProject `clusterResourceWhitelist` (`trust.cert-manager.io/Bundle`) — otherwise ArgoCD
rejects it as "synchronization tasks are not valid" and nothing distributes. Same class as the
PriorityClass whitelist gotcha.

---

## AI / MCP integration is separate from the image (and its repo)

A common confusion: *"if I retire an app's image repo, can I still expose it to AI / MCP?"* **Yes —
they are two independent layers.**

```
LAYER 1 — running the app (the container)
  How the IMAGE is built (CA trust, CVE patches). Retire the baked image →
  run the STOCK vendor image + runtime CA (trust-manager). The app's HTTP API is UNCHANGED.
                    │  the app's HTTP API (over the network)
                    ▼
LAYER 2 — exposing it to AI / MCP (a separate component you write)
  An MCP server / copilot tool that CALLS that API ("convert this PDF",
  "generate a report from a template", "extract text"). A CLIENT of the app —
  it does NOT live inside the app's image.
```

The app's API belongs to the app **regardless of how its image is built** — a stock image and a baked
image expose the *same* endpoints. So:

| Thing | Needs a repo? | Which repo |
|---|---|---|
| **Running the vendor app** | ❌ no (if the baked image is retired) | none — stock image + `helm-values/` + `apps/` |
| **AI/MCP-enabling it** | ✅ yes — it's custom code | a **different, new** repo (or a tool module inside the consuming product), **not** the app's image repo |

**Example — OnlyOffice.** Its editor/Conversion/Document-Builder APIs + plugin SDK are always
available over the network. An "OnlyOffice → copilot" tool (e.g. *generate a policy PDF*, *convert a
broker submission*) is a **Layer-2** component that lives with the **AI Ops Copilot** (#19) — or a
standalone MCP server — and calls OnlyOffice's API. You can retire `minicloud-onlyoffice` (the image
wrapper) and the AI integration is entirely unaffected, because it was never in that repo. **Running an
app and AI-enabling an app are decoupled.**

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
