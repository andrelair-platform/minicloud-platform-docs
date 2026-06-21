---
id: hallucination-controls
title: Hallucination Prevention & Detection
sidebar_position: 5
---

# Hallucination Prevention & Detection

Hallucination is the AI platform's highest-severity reliability risk. A model that invents a claim amount, a non-existent policy clause, or a fabricated French insurance regulation causes direct business harm — wrong payments, contract disputes, compliance failures.

This page covers the three-layer control architecture implemented for the HDI Seguros platform.

---

## Risk Classification

Not every department carries the same hallucination risk. Controls are applied proportionally:

| Department | Risk | Why |
|---|---|---|
| Sinistres | **CRITICAL** | Invented indemnity amounts → wrong payment to claimant |
| Finance | **CRITICAL** | Fabricated ratios or provisions → financial misstatement |
| Juridique | **CRITICAL** | Non-existent article cited → contract dispute or compliance failure |
| Souscription | **HIGH** | Wrong coverage terms quoted → customer sold wrong product |
| Actuariat | **HIGH** | Invented statistical assumptions → bad pricing |
| Audit | **HIGH** | Fabricated findings → audit report integrity |
| Réassurance | **HIGH** | Wrong treaty terms → uncovered exposure |
| Commercial | **MEDIUM** | Wrong product info → sales error |
| IT / Transformation / RH | **LOW** | Easily verified or low-consequence |

High-stakes departments (Sinistres, Finance, Juridique, Souscription, Actuariat, Audit, Réassurance) receive all three control layers. Low-stakes departments receive Layer 1 only.

---

## Architecture Overview

```text
User query (Open WebUI)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  LAYER 1 — RETRIEVAL GROUNDING GATE                       │
│  Qdrant similarity score < 0.35 → refuse (400)            │
│  "Aucun document pertinent trouvé"                         │
└───────────────────────┬───────────────────────────────────┘
                        │ similarity ≥ 0.35
                        ▼
┌───────────────────────────────────────────────────────────┐
│  LAYER 2 — DEPARTMENT SYSTEM PROMPT                       │
│  Model constrained: cite sources, say "I don't know"      │
│  High-stakes depts → llama3.2:3b (dedicated model alias)  │
└───────────────────────┬───────────────────────────────────┘
                        │
                        ▼
              Ollama (inference)
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│  LAYER 3 — CITATION CHECK HOOK (post-call)                │
│  Scans for specific claims (€, %, articles, clauses)      │
│  No citation found → Langfuse WARNING + queue for review  │
│  Self-eval confidence = 1 → prepend French warning        │
└───────────────────────┬───────────────────────────────────┘
                        │
                        ▼
              Response to user
```

All three layers run inside LiteLLM as `CustomLogger` hooks — no additional network hops, no latency impact on the main inference path.

---

## Layer 1 — Retrieval Grounding Gate

### What it does

When Open WebUI queries Qdrant, it receives a maximum cosine similarity score alongside the retrieved chunks. This score is passed through to LiteLLM in the request metadata. If the score falls below **0.35** — meaning no document in the vector store closely matches the query — the call is refused before Ollama is invoked.

```
similarity < 0.35  →  HTTP 400
                       "Aucun document pertinent trouvé pour votre question
                        (score de similarité 0.21 < 0.35).
                        Veuillez reformuler ou contacter votre référent Sinistres."
```

### Why 0.35

Cosine similarity on `nomic-embed-text` embeddings (768 dimensions):

| Score range | Meaning |
|---|---|
| > 0.75 | High semantic match — document directly answers the query |
| 0.50–0.75 | Related content — model can likely answer with grounding |
| 0.35–0.50 | Weak match — context may be tangential |
| < 0.35 | No relevant document — model will hallucinate if allowed to proceed |

0.35 is the empirically safe floor before free hallucination starts. It can be tuned per department once traffic data is available in Langfuse.

### Why this is the most important control

A model that never reaches Ollama without a grounding document cannot hallucinate on that query. Layers 2 and 3 reduce hallucination probability; Layer 1 eliminates it for the "no context" case entirely.

---

## Layer 2 — Department System Prompts

### What it does

Each high-stakes department is mapped to a dedicated LiteLLM model alias with a system prompt that imposes hard constraints on the model's behavior.

### Claims (Sinistres)

```
Tu es un assistant spécialisé pour la direction sinistres de HDI Seguros France.

RÈGLES ABSOLUES:
1. Réponds UNIQUEMENT à partir des documents fournis dans le contexte.
2. Si le contexte ne contient pas l'information demandée, réponds exactement:
   "Cette information ne figure pas dans mes documents. Merci de contacter
    votre référent sinistres."
3. N'invente JAMAIS: montants d'indemnisation, délais réglementaires,
   références d'articles, clauses contractuelles, noms de garanties.
4. Pour toute valeur chiffrée (montant, délai, pourcentage), indique
   toujours le document source.
5. En cas de doute sur l'interprétation d'une clause, dis-le explicitement.
```

### Finance

```
RÈGLES ABSOLUES:
1. Réponds uniquement à partir du contexte documentaire fourni.
2. Toute donnée chiffrée (montant, ratio, provision, taux) doit être
   accompagnée de sa source.
3. Ne jamais déduire ou extrapoler des montants financiers non
   explicitement présents dans le contexte.
4. Pour les normes IFRS17, Solvabilité II ou règles fiscales: cite
   l'article exact — sinon indique que tu n'as pas cette information.
```

### Juridique

```
RÈGLES ABSOLUES:
1. Tu n'es PAS un conseil juridique — précise-le si on te demande
   une opinion de droit.
2. Cite uniquement les textes explicitement présents dans les documents.
3. Ne jamais paraphraser un article de loi sans l'avoir dans ton contexte.
4. Signale toujours si la législation a pu évoluer depuis la date du
   document source.
```

### Model alias routing

The LiteLLM router maps each department's virtual key to its model alias:

| Department | Model alias | Base model |
|---|---|---|
| Sinistres, Souscription | `claims-assistant` | `llama3.2:3b` |
| Finance, Actuariat, Audit, Réassurance | `finance-assistant` | `llama3.2:3b` |
| Juridique | `legal-assistant` | `llama3.2:3b` |
| IT, RH, Commercial, Transformation | `general-assistant` | `llama3.2:1b` |

High-stakes departments always use `llama3.2:3b` — the 3B model is measurably more conservative and citation-aware than the 1B model on insurance-domain queries.

---

## Layer 3 — Citation Check Hook

### What it does

After Ollama returns a response, the `RetrievalGroundingHook` post-call handler scans the text for **specific factual claims** and checks whether those claims are accompanied by a **source citation**.

### Specific claim patterns detected

```python
r"\d[\d\s]*[.,]\d{2}\s*€"           # monetary: 12 500,00 €
r"\d+\s*%"                           # percentages: 85 %
r"article\s+[lra]\s*[\d\-]+"        # French law: Article L111-1
r"clause\s+\d+"                      # contract clauses
r"(délai|deadline)\s+(de\s+)?\d+\s*(jour|mois|an)"   # time limits
r"(couvert|garanti|exclu)\s+(jusqu|à hauteur|pour)"   # coverage assertions
```

### Citation markers accepted

`selon`, `d'après`, `source`, `document`, `article`, `clause`, `contrat`, `police`, `avenant`, `annexe`, `référence`, `voir`, `cf.`, `conformément`

### Outcomes

| Situation | Action |
|---|---|
| Specific claim + citation present | `citation_compliance = 1` score logged to Langfuse |
| Specific claim, no citation | `citation_compliance = 0` + `uncited-specific-claim` WARNING event → annotation queue |
| No specific claim | No citation check (not needed) |
| Department not in high-stakes list | Hook skipped entirely |

The citation check is **non-blocking** — it never rejects a response. It surfaces the trace for human review so domain experts can verify the claim and, if wrong, add the correct version to the Langfuse golden dataset (see issue [#43](https://github.com/andrelair-platform/platform-backlog/issues/43) — evaluation framework).

### Self-evaluation confidence

When a specific claim is detected in a high-stakes response, a lightweight secondary call to `llama3.2:1b` asks the model to rate its own confidence (1–3). If the model reports confidence 1 ("I invented this"), the response is prepended with:

```
⚠️ Je ne dispose pas de documents suffisants pour répondre avec certitude
   à cette question. Veuillez vérifier auprès de votre référent métier.
```

This visible warning is the last-resort signal to the user that the answer should not be acted on without verification.

---

## What Gets Logged to Langfuse

Every hallucination-related event is a first-class Langfuse object:

| Event / Score name | Type | Value | When |
|---|---|---|---|
| `retrieval_gate_blocked` | Event (INFO) | — | Similarity < 0.35 → call refused |
| `citation_compliance` | Score | 0 or 1 | Specific claim detected in high-stakes response |
| `uncited-specific-claim` | Event (WARNING) | — | claim found, no citation → annotation queue |
| `low_self_confidence` | Event (WARNING) | — | Self-eval confidence = 1 |
| `human_feedback` | Score | 1 or −1 | User 👍/👎 in Open WebUI (issue #43 evaluation framework) |

Filter in Langfuse: **Traces → Filter by score `citation_compliance = 0`** to see all uncited claims in the last 7 days.

---

## Grafana — Hallucination Risk Panel

The AI Observability dashboard includes a hallucination risk panel:

```
Panel: Hallucination Risk by Department (24h)
├── Heatmap:  ragas_faithfulness per department
├── Bar:      uncited_specific_claim_total per department
├── Line:     retrieval_gate_refused_total per department
└── Gauge:    avg citation_compliance per department
```

**Alert rule:** `uncited_specific_claim` for `finance` or `juridique` > 5 events in 1 hour → Alertmanager fires.

---

## What These Controls Do Not Cover

| Gap | Why | Mitigation path |
|---|---|---|
| Factual accuracy against external ground truth | Citation check verifies *whether* a source was cited, not *whether the source is correct* | Langfuse golden datasets per dept (#43) |
| Temporal hallucination (outdated training data) | System prompt instructs model to flag document dates — doesn't eliminate | Document metadata: include effective date in every ingested chunk |
| Cross-document contradiction | Two retrieved docs disagree — model may pick the wrong one | Deferred; requires multi-document consistency check |
| Hallucination in image/multimodal input | Platform is text-only | Out of scope |

---

## Operational Checks

```bash
# Check how many calls the retrieval gate blocked today
kubectl logs -n ai deployment/litellm --since=24h \
  | grep "retrieval_gate_blocked" | wc -l

# Check uncited-claim events in Langfuse (last 24h)
# → Langfuse UI → Traces → Filter: event.name = "uncited-specific-claim"

# Check citation_compliance score distribution
# → Langfuse UI → Scores → citation_compliance → group by department

# Verify hooks are loaded at LiteLLM startup
kubectl logs -n ai deployment/litellm | grep -E "RetrievalGroundingHook|loaded"
```
