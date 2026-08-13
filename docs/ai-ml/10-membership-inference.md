---
id: membership-inference
title: Membership Inference Defence
sidebar_position: 10
---

# Membership Inference Defence

Membership inference attacks determine whether a specific record exists in a system's knowledge base. In a RAG platform, this means probing whether a particular claim file, policy document, or personal record is indexed in Qdrant — without ever accessing Qdrant directly.

---

## Classical Membership Inference — Low Risk

Classical membership inference determines whether a specific data sample was in a model's **training set** by probing output confidence or perplexity. Researchers can distinguish "the model memorised this text" from "the model hasn't seen this before."

This is low risk here for the same reason as model inversion (see [Model Inversion](model-inversion)): `llama3.2:1b/3b` were trained on public web data. No ktayl-solution documents are in that training set.

This changes if fine-tuning ever happens — the fine-tuning gate in issue #48 blocks that path until a membership inference test is explicitly documented and closed.

---

## The Real Risk — RAG Membership Probing

An attacker with a valid virtual key can determine whether a specific document is indexed in Qdrant by crafting queries that would only be answerable if that record were present:

```
"Quel est le montant d'indemnisation du sinistre référence FR-2024-00892?"
→ Model answers with specific amount  → document IS in Qdrant
→ "Je n'ai pas trouvé d'informations" → document is NOT in Qdrant
```

Each probe is a single query — far more surgical than knowledge base enumeration (issue #48). The enumeration detector does not catch this because it measures topic diversity, not identifier presence.

### Three probe patterns

**Pattern 1 — Direct identifier probe**

The attacker supplies a structured business identifier and measures response specificity:

```
"Quel est le montant pour le sinistre FR-2024-00892?"
"Quelle est la franchise pour la police MRH-2024-11547?"
"Quels sont les détails du dossier SIN-2023-004512?"
```

**Pattern 2 — Corroborative probe**

The attacker already knows partial details (from a leaked document, a former employee, or public records) and probes to confirm the rest or verify a hypothesis:

```
"Confirme que la franchise pour la police MRH-2024-11547 est de 150 €."
→ Model confirms → policy indexed, franchise is 150 €
→ Model contradicts with different amount → policy indexed, actual franchise revealed
→ "No documents found" → policy not indexed
```

All three outcomes are membership signals.

**Pattern 3 — Personal data existence probe**

The attacker (or a legitimate data subject exercising GDPR rights) asks whether the system holds their personal data:

```
"Quelles informations avez-vous sur M. Jean Dupont, né le 14/03/1978 à Lyon?"
"Est-ce que mes données sont dans votre système?"
"Do you have a file on me?"
```

Whether answered "yes" or "no", the model is making a membership determination about personal data — a data processing decision that belongs to the Data Protection Officer, not to the AI.

---

## What's Already In Your Stack

| Control | What it covers |
|---|---|
| Presidio PII masking (issue #37) | Strips names, dates of birth, national IDs from prompts — partially covers pattern 3 |
| Enumeration detection (issue #48) | Catches bulk probing across many topics; single-query probing bypasses it |
| Collection ACL (issue #47) | Scopes which departments can query which collections — limits blast radius of a compromised key |
| Response abstraction (issue #48) | Reduces specificity of answers — partial mitigation against pattern 2 |
| Virtual key routing (issue #34) | Department-scoped access — IT key cannot probe `claims-docs` |

The retrieval grounding gate (issue #44) inadvertently worsens pattern 1: `"Aucun document trouvé (score 0.21 < 0.35)"` is a clean negative membership signal with quantified confidence.

---

## Defence Architecture

```text
PRE-CALL (extends RetrievalGroundingHook + PromptInjectionHook)
├── Identifier stripping
│   Claim refs, policy numbers, plates, addresses → placeholders
│   before query reaches Qdrant
│   → membership-probe-identifiers-stripped WARNING in Langfuse
│
└── GDPR Art. 15 routing
    Access request patterns detected → HTTP 451
    → DPO email + 30-day deadline returned
    → AI never answers membership questions about personal data
    → gdpr-access-request-detected INFO in Langfuse

RETRIEVAL GATE (fix to RetrievalGroundingHook, issue #44)
└── Neutral error message — similarity score removed from response
    Score logged internally; never returned to caller
    "Je n'ai pas trouvé d'informations suffisantes"
    (same message at score 0.05 and score 0.34)
```

---

## Layer 1 — Identifier Stripping

### What it does

Structured business identifiers are replaced with typed placeholders **before** the query reaches Qdrant. The retrieval system never sees the specific reference, so it cannot match a specific record. The model answers generically based on policy type, not based on a specific file.

### Identifiers stripped

| Type | Example | Placeholder |
|---|---|---|
| Claim reference | `FR-2024-00892`, `SIN-2023-004512` | `[RÉFÉRENCE SINISTRE]` |
| Policy number | `MRH-2024-11547`, `AUTO-2023-998877` | `[NUMÉRO POLICE]` |
| Broker / intermediary code | `CRT12345`, `INT-AB7890` | `[CODE COURTIER]` |
| Vehicle registration | `AB-123-CD` | `[IMMATRICULATION]` |
| Exact street address | `15 rue de la Paix` | `[ADRESSE]` |

Presidio already handles: names, dates of birth, national IDs (NIR), IBANs, phone numbers. Identifier stripping extends Presidio's pipeline for business-specific tokens that are not PII in the GDPR sense but are membership probe tokens in the RAG sense.

### What the user experiences

```
User query:    "Quel est le montant pour le sinistre FR-2024-00892?"
Sent to Qdrant: "Quel est le montant pour le [RÉFÉRENCE SINISTRE]?"
Model response: "Les montants d'indemnisation pour un sinistre dégât des eaux
                 dépendent des conditions générales de votre contrat. La franchise
                 standard est de 150 € et le plafond est..."
```

The user gets a general answer about claim amounts. No membership information is revealed. A legitimate adjuster working claim FR-2024-00892 should retrieve the file directly from the claims management system, not ask the AI assistant for its specific amounts.

### Langfuse event

`membership-probe-identifiers-stripped` (WARNING) fires whenever identifiers are stripped. Metadata includes the count and categories of identifiers removed — not the actual values, which are already stripped.

---

## Layer 2 — Neutral Error Message

### The problem with the current message

The retrieval grounding gate (issue #44) returns:

```
"Aucun document pertinent trouvé (score de similarité 0.21 < 0.35)"
```

The numeric score is a graded membership signal:
- Score 0.05 → very clearly not indexed
- Score 0.21 → not indexed but closer
- Score 0.34 → almost at threshold — document may be indexed but query didn't match well
- Score 0.45 → above threshold → different response path (document found)

An attacker running the same probe with slight query variations can map the similarity landscape and infer partial membership information even below the threshold.

### Fix

Remove the score from the user-visible message. Log it internally only.

**Before:**
```
"Aucun document pertinent trouvé (score de similarité 0.21 < 0.35).
 Veuillez reformuler ou contacter votre référent Sinistres."
```

**After:**
```
"Je n'ai pas pu trouver d'informations suffisantes pour répondre
 à cette question. Veuillez reformuler ou contacter votre référent Sinistres."
```

Score 0.05 and score 0.34 produce identical responses. The score is still recorded in the Langfuse `retrieval_gate_blocked` event for operational use.

---

## Layer 3 — GDPR Art. 15 Routing

### Legal context

GDPR Article 15 grants data subjects the right to know whether their personal data is being processed and to access it. If a user asks "do you have information about me?", the correct response is a legal one — not a technical one.

The AI answering this question directly creates two problems:
- **If it says "yes"**: it has just confirmed processing of personal data, triggering full Art. 15 obligations the AI cannot fulfil (it cannot provide a copy, explain the purpose, list third-party recipients)
- **If it says "no"**: it may be wrong (documents are indexed under different identifiers), and a false denial of data processing is a GDPR violation

Neither answer is safe. The only correct response is to route to the DPO.

### Patterns detected

```
French:
  "avez-vous des informations sur moi?"
  "mes données figurent-elles dans votre système?"
  "que savez-vous sur moi?"
  "je veux accéder à mes données" / "droit d'accès"

English:
  "do you have information about me?"
  "is my data stored in your system?"
  "right of access" / "GDPR article 15"
  "do you have a file on me?"
```

### Response

```
HTTP 451 Unavailable For Legal Reasons

"Pour exercer votre droit d'accès aux données personnelles (GDPR Art. 15),
 veuillez contacter notre Délégué à la Protection des Données :
 dpo@hdiseguros.fr — délai de réponse : 30 jours conformément au RGPD."
```

**HTTP 451** is the correct status code for legally-mandated refusals (defined in RFC 7725). It communicates that this is a legal restriction, not a technical error, and is more informative than 403 or 400 for this use case.

The `gdpr-access-request-detected` INFO event is logged to Langfuse with the matched pattern and department. These events should be reviewed monthly — a data subject who escalates to the DPO without having received a response within 30 days creates a compliance incident.

---

## Langfuse Event Reference

| Event name | Level | When fired |
|---|---|---|
| `membership-probe-identifiers-stripped` | WARNING | Claim ref, policy number, plate, or address stripped from query |
| `gdpr-access-request-detected` | INFO | GDPR Art. 15 access request pattern matched → routed to DPO |

---

## Operational Checks

```bash
# Membership probe attempts today (identifier stripping events)
# → Langfuse → Events → filter: name = "membership-probe-identifiers-stripped"

# GDPR access requests this month (should be reviewed for DPO follow-up)
# → Langfuse → Events → filter: name = "gdpr-access-request-detected"
# → confirm DPO has responded within 30 days for each

# Verify neutral error message is active (no score in response)
kubectl exec -n ai deployment/litellm -- \
  curl -s -X POST http://localhost:4000/chat/completions \
    -H "Authorization: Bearer $TEST_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "claims-assistant", "messages": [{"role": "user",
         "content": "xyz123 completely unrelated query"}]}' \
  | jq '.error.message'
# → should NOT contain "score de similarité" or any numeric value
```

---

## What These Controls Do Not Cover

| Gap | Reason | Path |
|---|---|---|
| Timing-based membership inference | Response latency differs when Qdrant finds vs does not find a match — measurable with enough probes | Add artificial jitter (5–50ms random delay) to retrieval gate responses as v2 |
| Partial identifier probing (attacker has only first 4 digits of claim ref) | Stripping requires a full pattern match; partial refs may not be caught | Extend patterns with fuzzy matching on numeric sequences in context of claim/policy words |
| Fine-tuned model membership inference | Not applicable today | Fine-tuning gate (issue #48) blocks this until membership inference test is documented |

---

## Relationship to Other Controls

```
issue #37 Presidio      → strips PII (names, DOB, NIR, IBAN)
issue #49 this issue    → strips business identifiers (claim refs, policy numbers)
                          together: no personal or business identifier reaches Qdrant

issue #44 retrieval gate   → blocks low-similarity queries
issue #49 neutral message  → removes score from error response
                             together: no membership signal in either positive or negative gate outcome

issue #46 injection hook   → blocks malicious prompt patterns
issue #49 GDPR routing     → redirects legal access requests
                             together: PromptInjectionHook handles both attack and legal dimensions
```
