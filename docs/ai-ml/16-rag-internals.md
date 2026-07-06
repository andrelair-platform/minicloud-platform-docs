---
id: rag-internals
title: RAG Internals — Indexes, Search Algorithms & Merging Strategies
sidebar_label: RAG Internals
---

# RAG Internals — Indexes, Search Algorithms & Merging Strategies

**Context:** Conceptual reference for the retrieval stack used in the minicloud RAG pipeline. Covers HNSW, IVFFlat, GIN, BM25, RRF, and why each was chosen over its alternatives.

---

## Why vector dimensions are a durable architectural decision

When you upload a document, the RAG system converts every text chunk into a **vector** — a list of numbers representing the meaning of that text in high-dimensional space. Semantically similar texts produce geometrically close vectors.

With bge-m3, every chunk becomes 1024 floats:
```
[0.023, -0.451, 0.887, ..., 0.112]   ← 1024 numbers
```

The constraint: **both ingestion and query-time must use the exact same embedding model**.

- The pgvector column is declared as `vector(1024)` — a fixed-size type. Inserting a 768-dim vector is a type error.
- Two different models do not just produce different sizes — they produce **incompatible coordinate spaces**. A value at dimension 312 from nomic-embed-text means something entirely different from the same position in bge-m3. Mixing them silently returns wrong results.
- Changing models requires wiping all stored vectors, dropping and recreating the index, and re-ingesting every document.

This happened in Phase E (2026-07-06): nomic-embed-text (768-dim) → bge-m3 (1024-dim). The migration required:

```sql
TRUNCATE document_chunk;
ALTER TABLE document_chunk DROP COLUMN vector;
ALTER TABLE document_chunk ADD COLUMN vector vector(1024);
DROP INDEX IF EXISTS document_chunk_vector_idx;
CREATE INDEX ON document_chunk USING hnsw (vector vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

All existing documents had to be re-ingested from scratch. **Embedding model choice is in the same category as "which database engine" — not a config toggle.**

---

## HNSW — the vector similarity index

### What it is

**HNSW = Hierarchical Navigable Small World**

Finding the nearest vectors to a query by brute force — computing distance to every row — is too slow at scale. HNSW is a graph-based data structure for fast approximate nearest-neighbor search.

Think of it as a highway system built over your data:

- **Top layer**: very few nodes, long-range shortcuts (motorways)
- **Middle layers**: moderate density, regional connections
- **Bottom layer**: every chunk connected to its closest neighbors (local streets)

When you search, you enter at the top, take large jumps toward your query vector, then descend to finer layers for precision. You reach approximate nearest neighbors in `O(log n)` steps instead of scanning all `n` rows.

In pgvector:
```sql
CREATE INDEX ON document_chunk USING hnsw (vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

- `m = 16`: each node connects to 16 neighbors per layer — more connections = better recall, more memory
- `ef_construction = 64`: search width during index build — higher = better index quality, slower build
- `vector_cosine_ops`: use cosine distance (angle between vectors) rather than Euclidean distance — better for normalized embedding vectors

### Why HNSW was chosen for this platform

Two reasons: one forced, one chosen.

**Forced — IVFFlat crashed on this hardware.**
pgvector 0.8.4 compiles IVFFlat with AVX-512 SIMD instructions. The cluster CPUs (i7-8565U, i7-10510U) lack AVX-512. Every IVFFlat INSERT triggered `SIGILL` (illegal instruction). The fix was a custom `postgresql:18.4.0-noavx512` image recompiling `vector.so` with `-mno-avx512f/bw/vl/dq`. HNSW did not have the same SIMD issue in this pgvector version.

**Chosen — the workload fits HNSW better.**

| Property | IVFFlat | HNSW | Why it matters here |
|---|---|---|---|
| Build requirement | Needs data first (k-means training) | Incremental (updates on INSERT) | Documents ingested one at a time |
| Recall | ~85–95% | ~95–99% | With only 3 chunks reaching LLM, missed neighbors are real quality failures |
| Memory | Lower | Higher | Corpus is thousands of chunks, not millions — memory cost is irrelevant |
| Tuning | `lists` + `probes` (per query) | `m` + `ef_construction` (once at build) | Zero ongoing maintenance required |

IVFFlat only wins when you have tens of millions of rows and RAM is genuinely constrained. Neither condition applies here.

### Measured latency (this cluster)

| Operation | Time |
|---|---|
| HNSW vector scan | 0.31 ms |
| GIN full-text scan | 2.71 ms |
| INSERT + HNSW index update | 6.8 ms/row |
| bge-m3 embedding (Ollama) | 393 ms |
| Ollama inference | 2–8 s (dominates end-to-end) |

---

## All vector index types

### pgvector built-ins

| Index | Algorithm | When to use |
|---|---|---|
| **HNSW** | Graph traversal | Default choice: incremental inserts, under 10M rows, recall matters |
| **IVFFlat** | k-means cluster partitioning | Batch-loaded, over 10M rows, memory constrained, can tolerate lower recall |
| **Flat (none)** | Brute force | Under ~50k rows, or when 100% exact recall is required |

### Beyond pgvector

Once you outgrow pgvector, purpose-built systems exist:

**Faiss (Facebook AI Similarity Search)**
A C++/Python library offering more index types:
- **PQ (Product Quantization)**: compresses vectors 4–16× — trades recall for memory. Used at 100M+ vectors when they won't fit in RAM.
- **IVFPQ**: combines IVFFlat partitioning with PQ compression — the standard at billion-scale.
- **ScaNN**: Google's variant, lets you specify the exact recall/latency trade-off you need.

Use Faiss when you need precise control over the memory/speed/recall trade-off in an ML pipeline, not a database.

**Qdrant / Weaviate / Milvus / Pinecone**
Dedicated vector databases. All use HNSW internally but add horizontal scaling, payload filtering, distributed sharding, and native sparse+dense hybrid search. Choose one of these when:
- You need to search within a subset (`doc_type = "policy"`) without raw SQL
- Corpus exceeds tens of millions of vectors
- Vector search is the primary workload, not a feature bolted onto a relational DB

For this platform, pgvector is correct: the data already lives in PostgreSQL, the corpus is small, and adding a separate stateful service would add operational overhead for no benefit at current scale.

### Decision tree

```
How many vectors?
├── < 100k          → HNSW or flat (don't over-engineer)
├── 100k – 10M      → HNSW (pgvector is fine)
├── 10M – 100M      → IVFFlat or HNSW with memory budget in mind
├── 100M – 1B       → IVFPQ (Faiss) or Qdrant/Milvus
└── over 1B         → Dedicated distributed system

Incremental inserts (live ingestion)?
└── Yes → HNSW always (IVFFlat needs a rebuild)

Need 100% recall?
└── Yes → Flat (brute force, no index)

Already in PostgreSQL + small team?
└── Yes → pgvector HNSW, don't add a separate service
```

---

## GIN — the full-text keyword index

### What it is

**GIN = Generalized Inverted Index**

GIN has nothing to do with vector similarity. It is a PostgreSQL index for **keyword search** — finding documents that contain specific words.

It builds an inverted map: for every word (or stem) in your documents, it stores the list of rows that contain it:

```
"sinistre"    → [row 3, row 7, row 42, row 891]
"réassurance" → [row 7, row 15, row 203]
"franchise"   → [row 3, row 15, row 44, ...]
```

When you query `"sinistre"`, PostgreSQL looks up that word in the map and retrieves exactly those rows — no scanning, no distance computation.

In ragdb:
```sql
CREATE INDEX ON document_chunk USING gin (to_tsvector('french', text));
```

The `'french'` dictionary applies stemming before indexing — "sinistres", "sinistre", "sinistré" all reduce to `sinistr`, so any form finds all forms. It also removes stop words ("le", "la", "de", "et").

The index was rebuilt with `'french'` during the bge-m3 migration (was `'simple'`). With `'simple'`, "sinistres" and "sinistre" are different tokens — queries would miss inflected forms.

### HNSW vs GIN — what each finds

| Query | HNSW finds | GIN finds |
|---|---|---|
| "accidents de voiture" | Chunks semantically about car accidents, even if different words used | Chunks containing the literal words "accidents", "voiture" |
| "Article 12" | Chunks topically similar to Article 12 | Chunks containing exactly "Article" and "12" |
| Synonym: query "dommage", doc says "sinistre" | Finds it (same semantic space) | Misses it (different word) |
| Exact clause lookup | May miss if phrasing differs | Finds it reliably |

This is why both indexes exist together — they cover each other's blind spots.

### When to use GIN (general PostgreSQL use cases)

**Full-text search on documents:**
```sql
SELECT * FROM contracts
WHERE to_tsvector('french', body) @@ to_tsquery('french', 'franchise & responsabilité');
```

**JSONB containment queries:**
```sql
SELECT * FROM document_chunk WHERE vmetadata @> '{"doc_type": "policy"}';
```
GIN indexes JSONB keys and values — without it, this is a full table scan.

**Array containment:**
```sql
SELECT * FROM claims WHERE tags @> ARRAY['fire', 'flood'];
```

**When NOT to use GIN:**
- Frequent writes — GIN is expensive to update (consider GiST for write-heavy tables)
- Equality checks (`WHERE name = 'Jean'`) — use B-tree
- Numeric ranges (`WHERE price BETWEEN 100 AND 500`) — use B-tree

---

## BM25 — keyword relevance ranking

### What it is

**BM25 = Best Match 25** (the 25th variant the researchers tried before the formula worked)

BM25 is a ranking formula that answers: given a query, which documents match best and in what order? It is the algorithm behind most search engines (Elasticsearch, Solr, early Google).

### The core intuitions

**Term frequency saturates.** A document mentioning "sinistre" once is probably relevant. One mentioning it 10 times is more relevant — but not 10× more. BM25 applies a saturation curve so each additional mention contributes less.

**Long documents are penalized.** A 10,000-word document mentioning "sinistre" 5 times is less focused on it than a 200-word clause mentioning it 5 times. BM25 normalizes by document length.

### The formula

For a query term `t` in document `d`:

```
score(t, d) = IDF(t) × tf × (k1 + 1) / (tf + k1 × (1 − b + b × doc_len/avg_doc_len))
```

| Component | What it does |
|---|---|
| IDF (Inverse Document Frequency) | Rare words score higher — "sinistre" in 10/1000 docs beats "contrat" in 900/1000 |
| TF saturation (k1 ≈ 1.5) | Going from 1→2 mentions roughly doubles score; 10→11 adds almost nothing |
| Length normalization (b = 0.75) | Full normalization (b=1) heavily penalizes long docs; b=0.75 is the empirical standard |

### BM25 vs TF-IDF

TF-IDF is the simpler predecessor. BM25 = "TF-IDF done right":

| | TF-IDF | BM25 |
|---|---|---|
| Term frequency | Linear, unbounded | Saturating curve |
| Length normalization | Crude or absent | Built in, tunable |
| Practical performance | Decent | Consistently better |

### What BM25 cannot do

BM25 is purely lexical — no understanding of meaning:
- Query "dommage" → misses documents about "sinistre" (same concept, different word)
- Query "voiture" → misses "automobile", "véhicule"

This is the gap that HNSW vector search fills. They are complementary, not competing.

### The French BM25 patch (Phase D)

The `rank_bm25` Python library used in Open WebUI tokenizes on whitespace only — "sinistres" and "sinistre" are treated as different tokens, so a query for one misses documents using the other.

Fix: an init container patches `utils.py` at pod start, injecting an NLTK Snowball French stemmer that reduces both to `sinistr` before BM25 scoring — matching the behavior of the GIN index's `'french'` dictionary.

---

## RRF — merging two ranked lists

### The problem

BM25 and HNSW produce scores that are fundamentally incomparable:
- BM25 returns `3.47`, `2.91`, `1.83` — a weighted keyword relevance score
- HNSW returns `0.923`, `0.887`, `0.741` — cosine similarity from 0 to 1

You cannot add them together. They live on different scales with different meanings.

### The RRF formula

**RRF = Reciprocal Rank Fusion**

It ignores the scores entirely and uses only rank positions:

```
RRF_score(chunk) = 1/(k + rank_in_BM25) + 1/(k + rank_in_HNSW)
```

`k = 60` (empirically found constant that dampens the advantage of rank #1).

Example with four chunks:

| Chunk | BM25 rank | HNSW rank | RRF score |
|---|---|---|---|
| Article 12 — franchise | 1 | 3 | 1/61 + 1/63 = 0.0321 |
| Article 7 — sinistre | 3 | 1 | 1/63 + 1/61 = 0.0321 |
| Préambule général | 2 | 2 | 1/62 + 1/62 = **0.0323** |
| Clause obscure | 1 | 50 | 1/61 + 1/110 = 0.0255 |

The chunk ranked well by **both** systems wins. A #1 in BM25 but #50 in HNSW loses to a #2 in both — consistency across retrieval methods is a stronger signal than dominance in one.

### Why k=60

Without k (i.e. k=0), rank #1 scores `1/1 = 1.0` and rank #2 scores `1/2 = 0.5` — a steep cliff. With k=60, rank #1 scores `1/61 ≈ 0.0164` and rank #2 scores `1/62 ≈ 0.0161` — a gentle slope. k=60 was found empirically to work well across many datasets and has become the standard default.

### RRF vs other merging strategies

| Strategy | Score-dependent | Requires tuning | Requires training data | Handles scale mismatch | Used here |
|---|---|---|---|---|---|
| Weighted sum | Yes | Yes (α, β weights) | No | No | No |
| Score normalization + weighted sum | Yes | Yes | No | Partial | No |
| CombMNZ | Yes | Partial | No | Partial | No |
| Learning to Rank (LTR) | Yes | Yes | Yes (relevance labels) | Yes | No |
| **RRF** | **No** | **No** | **No** | **Yes** | **Yes** |
| Cross-encoder re-ranking | N/A | No | No (pretrained) | N/A | Yes (after RRF) |

**Why not weighted sum?** Requires normalizing BM25 and HNSW scores to a common scale. Min-max normalization is sensitive to outliers — one anomalous BM25 score compresses everything else near zero. Also requires tuning α and β per domain, which means continuously re-tuning as the corpus grows.

**Why not Learning to Rank?** LTR is the most powerful approach — a trained model learns the optimal combination from human-labeled relevance data. But you need labeled training data: documents humans marked as relevant or not. No such data exists for this platform. LTR without training data is a random model.

**Why cross-encoder after RRF?** The cross-encoder reads the query and each candidate chunk together and produces a single relevance score — it models query-document interaction directly, far more accurately than either BM25 or HNSW alone. The cost is high: it must run inference on each candidate. Running it over thousands of candidates would be too slow. So the pipeline uses RRF to coarsely merge and narrow to 10, then cross-encoder to precisely re-rank to 3.

### Full retrieval pipeline

```
User query: "quelle est la franchise en cas de sinistre?"
    │
    ├── BM25 (rank_bm25, French-stemmed, runs in Open WebUI pod)
    │     ranks TOP_K=10 chunks by keyword match
    │     #1 Article 12 — franchise
    │     #2 Article 3 — définitions
    │     #3 Article 7 — sinistre
    │
    └── HNSW (pgvector, cosine similarity)
          query embedded → bge-m3 → 1024-dim vector
          cosine search → TOP_K=10 nearest chunks
          #1 Article 7 — sinistre
          #2 Article 12 — franchise
          #3 Clause 4 — indemnisation
    │
    └── RRF merges both ranked lists (k=60)
          → single ranked list, score = sum of reciprocal ranks
          #1 Article 12 — franchise  (high in both)
          #2 Article 7 — sinistre    (high in both)
          #3 Clause 4 — indemnisation
    │
    └── Cross-encoder re-ranker (ms-marco-MiniLM-L-6-v2, in-process)
          reads query + each chunk together
          re-scores top 10 → picks TOP_K_RERANKER=3
    │
    └── 3 chunks injected into LLM context → answer with citations
```

---

## How the components relate

```
┌─────────────────────────────────────────────────────────┐
│                    ragdb (PostgreSQL)                    │
│                                                         │
│  document_chunk table                                   │
│  ├── vector vector(1024)  ← HNSW index (semantic)      │
│  └── text text            ← GIN index  (keyword)        │
└─────────────────────────────────────────────────────────┘
         │                          │
    cosine search               @@ tsvector query
    (approximate,               (exact, stemmed,
     fast, semantic)             keyword match)
         │                          │
         └──────────── RRF ─────────┘
                        │
               cross-encoder re-rank
                        │
                   top 3 chunks
                        │
                 LLM answer
```

Each layer compensates for a different weakness:
- **HNSW** finds semantic neighbors — misses when exact phrasing matters
- **GIN/BM25** finds exact keywords — misses synonyms and paraphrases
- **RRF** merges without score normalization — robust to scale differences
- **Cross-encoder** re-ranks with full query-document context — most accurate, applied last to a small set
