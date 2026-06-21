---
id: model-inversion
title: Model Inversion & Knowledge Base Extraction Defence
sidebar_position: 9
---

# Model Inversion & Knowledge Base Extraction Defence

This page covers an important distinction: classical model inversion is **low risk** for this stack, but two closely related attacks are real and require active controls.

---

## Classical Model Inversion — Why It's Low Risk Here

Classical model inversion attacks query a model repeatedly to reconstruct its training data from its weights — extracting memorised private text that the model saw during training. This is well-documented against large language models where researchers extracted verbatim training samples via specific prompting.

**This is low risk for this specific deployment because:**

`llama3.2:1b` and `llama3.2:3b` are pre-trained base models from Meta, trained on public web data. HDI Seguros policy documents, claim records, underwriting criteria, and financial data **are not in that training set** — they are confidential internal documents that never reached the public internet. There is nothing to extract from the model weights that relates to HDI Seguros business.

The assessment changes completely if models are ever fine-tuned on internal documents. See the [Fine-Tuning Gate](#fine-tuning-gate) section — this is a hard prerequisite before any fine-tuning phase.

---

## The Two Real Attacks for RAG Systems

### Attack 1 — Knowledge Base Enumeration

An attacker with a valid virtual key systematically queries the system to reconstruct the entire Qdrant knowledge base without ever accessing Qdrant directly:

```
"What is the franchise for water damage?"           → extracts €150
"What is the franchise for fire damage?"            → extracts €500
"What is the indemnity limit for property damage?"  → extracts €500,000
"What are the exclusions for clause 1?"             → extracts clause text
"What are the exclusions for clause 2?"             → extracts clause text
...200 queries later: full policy wording reconstructed
```

Each individual query is legitimate. Only the systematic pattern across many distinct topics reveals the attack. This requires no technical exploit — just a valid API key and a structured list of questions.

**Risk in insurance:** entire policy wordings, pricing structures, underwriting criteria, and claims procedures could be exfiltrated by a competitor, a disgruntled employee, or a compromised broker account. All of this is confidential commercial and regulatory information.

### Attack 2 — Embedding Reconstruction

`nomic-embed-text` embeddings (768-dimensional vectors) are stored in Qdrant alongside the original chunk text. Research (Vec2Text, 2023) has demonstrated that embedding vectors can be inverted to reconstruct the original text with meaningful accuracy for sentence-length inputs (~40–60% fidelity).

If Qdrant storage is compromised, an attacker with the raw embedding vectors could partially recover policy document text without having the documents themselves.

**Risk level in this stack:** lower than enumeration, because Qdrant is internal-only — it has no Ingress, is accessible only via Tailscale and Cilium NetworkPolicy, and requires a network-level compromise first. Mitigated by Longhorn LUKS encryption at rest.

---

## What's Already In Your Stack

| Control | What it covers |
|---|---|
| Virtual key routing (issue #34) | Department-scoped read access — IT key cannot query `claims-docs` |
| Per-key query rate limits (issue #34) | Slows enumeration — limited requests per minute |
| DataSovereigntyHook (issue #42) | Responses never leave your infrastructure |
| Tailscale + UFW | Qdrant unreachable from internet |
| Cilium NetworkPolicy | Pod-level network isolation within cluster |

Virtual key routing already gives partial enumeration resistance — a compromised `direction-it` key can only enumerate the IT collection, not claims or finance. The blast radius of any single compromised key is scoped to one department's document set.

---

## Defence Architecture

```text
PRE-CALL (EnumerationDetectionHook)
└── Track unique query topic fingerprints per API key per hour
    → warning at 60 distinct topics
    → block + CRITICAL event at 80 distinct topics

POST-CALL (verbatim reproduction check)
└── SequenceMatcher: response vs retrieved chunks
    → > 60% verbatim overlap → abstraction_compliance = 0 + WARNING

SYSTEM PROMPT (high-stakes departments)
└── Abstraction constraint appended to claims/finance/legal/underwriting prompts
    "Ne jamais reproduire textuellement plus de deux phrases consécutives"

STORAGE (Qdrant PVC)
└── Longhorn LUKS encryption at rest
    → embedding vectors + chunk text encrypted on disk
    → key managed by Vault (issue #15)

FINE-TUNING GATE
└── GitHub Actions workflow blocks fine-tuning unless safety checklist closed
```

---

## Layer 1 — Enumeration Detection

### How it works

Each query is fingerprinted by its first six normalised words. Redis HyperLogLog tracks the cardinality of unique fingerprints per API key per hour — the count of distinct topics, not the count of queries.

| Fingerprint A | `"what is the franchise for water"` |
|---|---|
| Fingerprint B | `"what is the franchise for fire"` |
| Fingerprint C | `"what is the indemnity limit for"` |

Three distinct topics. The same question asked 80 times counts as one topic — normal repeated clarifications do not trigger the detector.

### Thresholds

| Threshold | Action |
|---|---|
| 60 unique topics / hour | `enumeration-warning` WARNING event in Langfuse — monitoring escalated, request not blocked |
| 80 unique topics / hour | `enumeration-detected` ERROR event + HTTP 429 — request blocked, Grafana alert fires |

Counter resets after 1 hour. A power user who legitimately asks many different questions will approach 60 but is unlikely to exceed 80 in a single hour of normal work — the threshold is calibrated to systematic machine-speed querying, not human browsing.

### Reviewing an enumeration alert

```
Langfuse → Events → filter: name = "enumeration-detected"
→ metadata.key_hash      identifies the API key
→ metadata.unique_topics count at time of block
→ metadata.department    which collection was being enumerated
```

Cross-reference with Langfuse Traces to see the full query sequence for that key hash:

```
Langfuse → Traces → filter by time window → sort by created_at
→ look for short factual questions with systematic topic progression
```

If enumeration is confirmed, revoke the key:

```bash
curl -X DELETE http://litellm.ai.svc:4000/key/delete \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"keys": ["<virtual-key>"]}'
```

---

## Layer 2 — Response Abstraction

### System prompt constraint

All high-stakes department system prompts (claims, finance, legal, underwriting, audit) include:

```
RÈGLE SUPPLÉMENTAIRE — REPRODUCTION TEXTUELLE:
Ne jamais reproduire textuellement plus de deux phrases consécutives d'un document source.
Synthétise, reformule et explique — ne copie pas le texte brut du document.
Si l'utilisateur demande explicitement une citation textuelle, indique:
"Je ne peux pas reproduire le texte intégral. Référez-vous au document [source] page [X]."
```

This makes enumeration harder — the attacker gets a paraphrase, not the exact policy wording. Combined with the citation requirement from issue #44, the attacker knows which document to request but cannot reconstruct its text from model responses alone.

### Post-call verbatim detection

After every response, the `abstraction_compliance` score is computed using `SequenceMatcher` between the response text and each retrieved chunk:

| Score | Meaning |
|---|---|
| 1 | Response is a genuine synthesis — no verbatim copying detected |
| 0 | Response is > 60% verbatim overlap with a source chunk — flagged |

A score of 0 fires a `verbatim-reproduction-detected` WARNING in Langfuse. This is non-blocking — it surfaces cases where the model ignored the abstraction constraint for human review and system prompt tuning.

---

## Layer 3 — Qdrant PVC Encryption at Rest

### Why

Qdrant stores two sensitive artefacts on disk: the original chunk text (policy document excerpts) and the `nomic-embed-text` embedding vectors. Without encryption, a compromised node, a stolen disk, or a Longhorn snapshot exfiltration exposes both in plaintext. The embedding vectors can be partially inverted to recover text even without the chunk payload.

### Implementation — Longhorn LUKS

Longhorn's built-in encryption support uses LUKS (Linux Unified Key Setup) at the volume level. The encryption key is stored in a Kubernetes Secret populated by the External Secrets Operator from Vault (issue #15) — never hardcoded.

```yaml
# StorageClass: longhorn-encrypted
parameters:
  encrypted: "true"
  CRYPTO_KEY_CIPHER: "aes-xts-plain64"
  CRYPTO_KEY_HASH: "sha256"
  CRYPTO_KEY_SIZE: "256"
  CRYPTO_PBKDF: "argon2i"
```

Qdrant's PVC uses `storageClassName: longhorn-encrypted`. The encryption is transparent to Qdrant — no application changes required.

### Verifying encryption is active

```bash
# On the node hosting the Qdrant PVC (check which node via kubectl)
ssh set-hog "lsblk -o NAME,TYPE,FSTYPE | grep crypto"
# → shows a crypto_LUKS device backing the volume

# From Mac via controller:
kubectl get pvc -n ai
# → qdrant-storage   Bound   longhorn-encrypted   10Gi
```

### Migration from unencrypted PVC

```bash
# 1. Scale down Qdrant
kubectl scale deployment qdrant -n ai --replicas=0

# 2. Snapshot existing PVC via Longhorn UI
#    → Longhorn UI → Volumes → qdrant-storage → Create Snapshot

# 3. Restore snapshot into a new PVC using longhorn-encrypted StorageClass
#    → Longhorn UI → Snapshots → Restore → StorageClass: longhorn-encrypted

# 4. Update Qdrant Helm values
ssh controller "/home/ktayl/.local/bin/helm upgrade qdrant qdrant/qdrant \
  --namespace ai \
  --values /home/ktayl/minicloud-ktaylorganisation/ansible/helm-values/qdrant-values.yaml \
  --wait"

# 5. Scale back up and verify
kubectl scale deployment qdrant -n ai --replicas=1
kubectl rollout status deployment/qdrant -n ai

# 6. Verify collection counts match pre-migration
kubectl exec -n ai deployment/qdrant -- \
  curl -s http://localhost:6333/collections | jq '.result.collections[].name'
```

---

## Fine-Tuning Gate

If fine-tuning of `llama3.2` on internal HDI Seguros documents is ever considered, the following safety checklist must be completed and documented in a closed GitHub issue before the fine-tuning workflow can run:

| Item | Why |
|---|---|
| Differential privacy training (DP-SGD, ε ≤ 8) | Limits how much any single training example can influence model weights — caps memorisation |
| Training data PII scan + removal (Presidio batch) | No names, IBANs, policy numbers, or national IDs in training set |
| Membership inference attack test | Verify the fine-tuned model cannot confirm whether a specific document was in training data |
| Model inversion attack test (Carlini et al. protocol) | Verify the model does not reproduce verbatim training text under systematic prompting |
| Output filter blocking verbatim training data reproduction | Last-resort post-call filter if the above controls are insufficient |
| Legal review | Fine-tuning on policyholder documents may create GDPR Art. 22 obligations or IP issues |

A GitHub Actions workflow (`finetuning-gate.yml`) enforces this — the fine-tuning run fails unless the checklist issue is closed. This gate cannot be bypassed without modifying the workflow, which itself requires a PR review.

**Current status:** fine-tuning is not planned. Base models (`llama3.2:1b/3b`) are used as-is. The gate exists to prevent the checklist being skipped when fine-tuning is eventually evaluated.

---

## Grafana Alerting

| Alert | Condition | Severity |
|---|---|---|
| `KnowledgeBaseEnumerationDetected` | API key reaches 80 unique topics / hour | Critical, fires immediately |
| `EnumerationWarning` | API key reaches 60 unique topics / hour | Warning, fires immediately |
| `VerbatimReproductionSpike` | > 15% of responses have `abstraction_compliance = 0` over 1 hour | Warning, fires after 15 min |

---

## Operational Checks

```bash
# Check enumeration counters in Redis (any key near threshold)
kubectl exec -n ai deployment/redis -- \
  redis-cli KEYS "enum_topics:*" | xargs -I{} sh -c \
  'echo -n "{} topics: "; redis-cli PFCOUNT {}'

# Check verbatim reproduction rate (last 24h)
# → Langfuse → Scores → abstraction_compliance → filter value = 0

# Check enumeration events today
# → Langfuse → Events → filter: name = "enumeration-detected" OR "enumeration-warning"

# Verify Qdrant PVC is on encrypted StorageClass
kubectl get pvc -n ai -o custom-columns=\
'NAME:.metadata.name,STORAGECLASS:.spec.storageClassName,STATUS:.status.phase'

# Confirm LUKS device active on Qdrant node
kubectl get pod -n ai -l app=qdrant -o wide    # find node
ssh <qdrant-node> "lsblk -o NAME,TYPE,FSTYPE | grep -i luks"
```

---

## What These Controls Do Not Cover

| Gap | Reason | Path |
|---|---|---|
| Adversarial embedding queries (Vec2Text-style attack on live Qdrant API) | Qdrant API is internal-only; requires cluster access first | Covered by Tailscale + Cilium NetworkPolicy |
| Enumeration below 80 topics/hour | A patient attacker queries 79 topics/hour indefinitely | Longer-window detection (24h sliding window) as v2 enhancement |
| Fine-tuned model memorisation | Not applicable today — no fine-tuning planned | Fine-tuning gate blocks this path until safety checklist is complete |
| Model extraction / surrogate model training | Requires thousands of API calls with outputs; rate limits slow this significantly | Existing per-key rate limits from issue #34 |
