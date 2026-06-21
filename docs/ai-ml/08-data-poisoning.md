---
id: data-poisoning
title: Data Poisoning Defence
sidebar_position: 8
---

# Data Poisoning Defence

Prompt injection (see [Prompt Injection](prompt-injection)) manipulates the model at inference time via the input. Data poisoning is a different attack: corrupting the Qdrant knowledge base so the model gives systematically wrong answers — to every user who retrieves that data, indefinitely, with no injection patterns to detect.

**The core problem:** every existing quality control (Ragas faithfulness, citation check, LLM-as-judge) measures model output against retrieved context. If the context is poisoned, all controls are poisoned with it. A document stating the wrong franchise amount scores faithfulness=1.0, passes the citation check, and looks correct in every Langfuse dashboard.

---

## Attack Vectors

### 1. Factual corruption

Upload a document with wrong policy terms. No injection patterns, no imperative sentences — just incorrect facts stated in normal document language:

```
[Appears to be a legitimate policy wording document — passes all injection scans]

"La franchise applicable en cas de dégât des eaux est de 2 500 €."
[Actual franchise in every legitimate policy document: 150 €]
```

Every claims adjuster who asks about water damage excesses receives `€2,500`. Ragas faithfulness = 1.0. Citation check passes. LLM-as-judge correctness = 0.9. All dashboards look healthy.

### 2. Retrieval manipulation

A document crafted to be semantically close to many common queries — not because it is relevant, but because it is designed to fool the `nomic-embed-text` embedding model. The attacker's document gets retrieved for `"what is the indemnity for..."` regardless of context, injecting wrong content into every claims query.

### 3. Feedback poisoning

The human feedback loop (issue #43) wires 👍/👎 into Langfuse as quality scores. Coordinated accounts systematically click 👍 on wrong answers. Ragas scores are low, LLM-as-judge scores are low — but `human_feedback` is high and suppresses alerts. Over time this degrades the golden datasets and raises quality thresholds to accept wrong answers.

### 4. Bulk ingestion spike

An attacker with document upload access bulk-ingests hundreds of subtly wrong documents overnight, shifting the retrieval landscape before anyone notices. Every query the next morning returns poisoned context.

---

## Risk by Department

| Department | Risk | Most likely vector |
|---|---|---|
| Sinistres | **CRITICAL** | Factual corruption of policy terms → wrong indemnity advice |
| Finance | **CRITICAL** | Wrong IFRS17 / Solvabilité II interpretations |
| Juridique | **CRITICAL** | Invented article references in legal docs |
| Souscription | **HIGH** | Wrong underwriting criteria → mispriced risk |
| Actuariat | **HIGH** | Corrupted statistical assumptions → bad pricing models |
| Réassurance | **HIGH** | Wrong treaty terms → uncovered exposure |
| IT | **LOW** | Wrong procedure docs → inconvenience only |

---

## Defence Architecture

```text
DOCUMENT INGESTION (before Qdrant indexing)
├── Injection scan (issue #46 — existing)
├── Collection write permission check (dept-scoped)
├── Bulk ingestion rate limit (50 docs/hour via Redis)
├── Cross-document consistency check
│   (new factual claims vs existing chunks on same topic)
└── Chunk provenance metadata attached to every indexed chunk
    (uploaded_by, doc_hash, uploaded_at, page_number, source_doc)

QUERY PIPELINE
└── RAG sources logged to Langfuse on every response
    (rag-sources-used event: doc_id, uploaded_by, doc_hash per chunk)

FEEDBACK VALIDATION (extends issue #43 feedback-bridge)
├── Flag: 👍 on response where judge_correctness < 0.60
└── Flag: 5+ accounts like same response within 10 minutes

WEEKLY INTEGRITY SCAN (Sunday 03:00 UTC CronJob)
├── Full Qdrant scan across all 10 collections
├── Injection pattern check on every chunk
├── Provenance gap check (chunks missing metadata)
└── Results → Langfuse event + Grafana alert if flagged > 0

INCIDENT RESPONSE
└── Document removal by doc_hash (surgical — no other chunks affected)
```

---

## Layer 1 — Chunk Provenance

### What it does

Every chunk indexed into Qdrant carries a provenance payload. This enables a complete chain of custody from any response back to the person who uploaded the source document.

```
Langfuse trace (RAG response)
  └── event: rag-sources-used
        └── sources[0]:
              doc_id:       "claims-docs/a3f7b91c2d..."
              source_doc:   "expert-assessment-claim-892.pdf"
              page_number:  4
              uploaded_by:  "adjuster.martin@hdiseguros.fr"
              uploaded_at:  "2026-06-21T09:14:32Z"
              doc_hash:     "a3f7b91c2d4e5f6..."
```

**Audit query for any suspicious response:**

```
Langfuse → Traces → open trace → Events → rag-sources-used
→ sources[].uploaded_by     who contributed to this response
→ sources[].doc_hash        fingerprint to find all chunks from same document
→ sources[].uploaded_at     when the document entered the knowledge base
```

### Duplicate detection

The same document cannot be indexed twice. At ingestion time, `safe_ingest()` queries Qdrant for existing chunks with the same `doc_hash`. If found, the ingestion is skipped with a log message — no silent double-indexing.

---

## Layer 2 — Collection Write Permissions

### Permission matrix

Upload access is scoped by department and enforced at the LiteLLM hook layer before `safe_ingest()` is called.

| Collection | Authorised departments |
|---|---|
| `claims-docs` | direction-sinistres, platform-team |
| `finance-docs` | direction-finance, direction-actuariat, platform-team |
| `legal-docs` | direction-juridique, platform-team |
| `underwriting-docs` | direction-souscription, platform-team |
| `reinsurance-docs` | direction-réassurance, platform-team |
| `actuarial-docs` | direction-actuariat, direction-finance, platform-team |
| `audit-docs` | direction-audit, platform-team |
| `it-docs` | direction-it, platform-team |
| `hr-docs` | direction-rh, platform-team |
| `commercial-docs` | direction-commercial, platform-team |
| `general-docs` | any authenticated user |

### Response to an unauthorised upload attempt

```
HTTP 403:
"La direction direction-it n'est pas autorisée à ingérer des documents
 dans la collection claims-docs.
 Contactez l'équipe plateforme pour obtenir l'accès."
```

Event `collection-write-denied` logged to Langfuse with department, collection, and API key hash.

### Bulk ingestion rate limit

More than 50 documents per hour from the same department triggers a rate limit and an alert. Normal document upload behaviour does not approach this threshold — it indicates either automated tooling or a poisoning attempt.

```
HTTP 429:
"Limite d'ingestion dépassée (50 docs/heure).
 Contactez l'équipe plateforme pour les ingestions en masse."
```

---

## Layer 3 — Cross-Document Consistency Check

### What it does

When a new document is ingested, factual sentences are extracted and embedded. Each is compared against existing chunks in the same collection covering the same topic. If the same topic returns a different claimed value (high topic similarity but low claim similarity), a `document-consistency-conflict` WARNING is logged.

### Factual sentences detected

```python
# Patterns that identify factual claims worth cross-checking:
"La franchise applicable est de 150 €"           → extracted
"Le délai de déclaration est de 5 jours ouvrés"  → extracted
"Article L113-2 du Code des assurances"          → extracted
"Couvert jusqu'à hauteur de 50 000 €"            → extracted
```

### What happens on detection

```
New document: expert-update-franchise-2026.pdf
  Factual sentence: "La franchise dégât des eaux est de 2 500 €"
  Query existing collection → finds 5 chunks stating "franchise: 150 €"
  Topic similarity: 0.91 (same topic — water damage franchise)
  Claim similarity: 0.41 (different value stated)

Result: document-consistency-conflict WARNING in Langfuse
  metadata:
    new_sentence:      "La franchise dégât des eaux est de 2 500 €"
    existing_sentence: "La franchise applicable en cas de dégât des eaux est de 150 €"
    existing_doc:      "policy-wording-mrh-v12.pdf"
    existing_uploaded_by: "team.platform@hdiseguros.fr"
    topic_similarity:  0.91
    claim_similarity:  0.41
```

The document is **not blocked** — it may represent a legitimate policy update. A domain expert reviews the conflict and either approves the new document or rejects it. For `finance-docs` and `legal-docs` the behaviour can be set to blocking (quarantine until reviewed).

---

## Layer 4 — Feedback Anomaly Detection

### Pattern 1 — Thumbs-up on a low-quality response

When a user gives 👍 to a response that the LLM-as-judge scored below 0.60 on correctness, the `feedback-bridge` (issue #43) flags it. This catches individual accounts confirming wrong answers — possibly unwitting (user didn't read carefully) or deliberate (feedback poisoning).

```
Event: feedback-quality-mismatch (WARNING)
  human_rating:   positive
  judge_score:    0.43
  user:           adjuster.x@hdiseguros.fr
  interpretation: User rated positive a response the judge scored < 0.60
```

### Pattern 2 — Coordinated positive feedback

Five or more distinct accounts give 👍 to the same response within a 10-minute window. Normal behaviour does not produce this pattern — it indicates coordinated manipulation.

```
Event: coordinated-positive-feedback (ERROR)
  trace_id:    "abc123..."
  like_count:  6
  window_secs: 600
  action:      possible-feedback-poisoning
```

Counter resets after 10 minutes. A single popular response that receives likes over hours is not flagged — only simultaneous bursts.

---

## Layer 5 — Weekly Integrity Scan

### What it scans

Every Sunday at 03:00 UTC a CronJob scans all chunks across all 10 collections:

| Check | What it catches |
|---|---|
| Injection patterns | Documents ingested before issue #46 was deployed that contain instruction-like content |
| Provenance gaps | Chunks missing `uploaded_by`, `doc_hash`, or `uploaded_at` (ingested before this issue) |

Results are written to a single Langfuse event `weekly-integrity-scan-complete` with:
- Total chunks scanned
- Flagged chunk count and details (document, uploader, pattern matched)
- Provenance gap count

### Triggering a manual scan

```bash
kubectl create job --from=cronjob/qdrant-integrity-scan integrity-scan-$(date +%Y%m%d) -n ai
kubectl logs -n ai job/integrity-scan-$(date +%Y%m%d) -f
```

### Reviewing scan results

```
Langfuse → Events → filter: name = "weekly-integrity-scan-complete"
→ metadata.flagged_chunks > 0 → see metadata.flagged_details for chunk list
→ metadata.no_provenance_chunks > 0 → chunks needing backfill
```

---

## Incident Response — Removing a Poisoned Document

When a poisoned document is confirmed (via Langfuse event or domain expert review):

### Step 1 — Find the doc_hash

```
Langfuse → Events → name = "indirect-injection-in-document" or "document-consistency-conflict"
→ metadata.doc_hash = "a3f7b91c2d4e5f6..."
```

### Step 2 — Delete all chunks with that hash

```bash
DOC_HASH="a3f7b91c2d4e5f6..."
COLLECTION="claims-docs"

kubectl exec -n ai deployment/qdrant -- /bin/sh -c "
  curl -s -X POST http://localhost:6333/collections/${COLLECTION}/points/delete \
    -H 'Content-Type: application/json' \
    -d '{\"filter\": {\"must\": [{\"key\": \"doc_hash\", \"match\": {\"value\": \"${DOC_HASH}\"}}]}}'
"
```

### Step 3 — Verify deletion

```bash
kubectl exec -n ai deployment/qdrant -- /bin/sh -c "
  curl -s -X POST http://localhost:6333/collections/${COLLECTION}/points/count \
    -H 'Content-Type: application/json' \
    -d '{\"filter\": {\"must\": [{\"key\": \"doc_hash\", \"match\": {\"value\": \"${DOC_HASH}\"}}]}}'
"
# → {"result": {"count": 0}}
```

### Step 4 — Audit the uploader's other documents

```
Langfuse → Events → filter: name = "document-ingested", metadata.uploaded_by = "<user>"
→ review all doc_hash values they uploaded
→ re-ingest any documents that need verification
```

### Step 5 — Revoke upload access if attack confirmed

```bash
# Revoke the user's virtual key in LiteLLM admin
curl -X DELETE http://litellm.ai.svc:4000/key/delete \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"keys": ["<virtual-key>"]}'
```

Deletion is surgical — `doc_hash` uniquely identifies the poisoned document's chunks without affecting any other content in the collection.

---

## Langfuse Event Reference

| Event name | Level | When fired |
|---|---|---|
| `document-ingested` | INFO | Every successful ingestion — records uploader + hash |
| `indirect-injection-in-document` | ERROR | Injection pattern found at ingestion — document quarantined |
| `document-consistency-conflict` | WARNING | New document contradicts existing chunk on same topic |
| `collection-write-denied` | WARNING | Department not authorised to write to collection |
| `bulk-ingestion-rate-exceeded` | ERROR | > 50 documents in 1 hour from same department |
| `rag-sources-used` | INFO | Every RAG response — provenance of each contributing chunk |
| `feedback-quality-mismatch` | WARNING | 👍 on response where judge_correctness < 0.60 |
| `coordinated-positive-feedback` | ERROR | 5+ accounts like same response within 10 minutes |
| `weekly-integrity-scan-complete` | INFO / ERROR | Weekly CronJob result — ERROR if flagged_chunks > 0 |

---

## Grafana Alerting

| Alert | Condition | Severity |
|---|---|---|
| `DataPoisoningChunkFlagged` | Injection found in document at ingestion | Critical, fires immediately |
| `IntegrityScanFlagged` | Weekly scan finds suspicious chunks in Qdrant | Critical, fires immediately |
| `FeedbackPoisoningDetected` | Coordinated positive feedback detected | Warning, fires immediately |
| `BulkIngestionSpike` | > 50 docs/hour from one department | Warning, fires immediately |

---

## Operational Checks

```bash
# Documents ingested today (with uploader)
# → Langfuse → Events → filter: name = "document-ingested" → metadata.uploaded_by

# Check consistency conflicts this week
# → Langfuse → Events → filter: name = "document-consistency-conflict"

# Verify integrity scan ran last Sunday
kubectl get jobs -n ai | grep integrity-scan
kubectl logs -n ai job/integrity-scan-<date> | tail -5

# Check collection chunk counts per department
kubectl exec -n ai deployment/qdrant -- /bin/sh -c "
  for coll in claims-docs finance-docs legal-docs underwriting-docs; do
    echo -n \"\$coll: \"
    curl -s http://localhost:6333/collections/\$coll | jq '.result.points_count'
  done
"

# Check bulk ingestion rate counters in Redis
kubectl exec -n ai deployment/redis -- \
  redis-cli KEYS "ingestion_rate:*" | xargs -I{} sh -c 'echo -n "{}: "; redis-cli GET {}'
```

---

## What These Controls Do Not Cover

| Gap | Reason | Path |
|---|---|---|
| Embedding model adversarial examples | Crafted documents that fool `nomic-embed-text` at a mathematical level require ML-specific defences beyond pattern matching | Deferred; monitor retrieval score distributions for anomalies |
| Insider threat with platform-team role | Platform team has write access to all collections | Covered by Authentik RBAC audit logging (issue #33) + controller audit logs |
| Slow drift poisoning | A single incorrect document ingested months ago may not trigger consistency checks if it predates the authoritative version | Weekly integrity scan + provenance audit catches this once controls are live |
| Feedback poisoning below the 5-account threshold | Single account consistently giving 👍 to wrong answers | Correlate human_feedback with judge_correctness in monthly ACPR report (issue #45) |
