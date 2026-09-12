---
id: annotation-workflow
title: Human Annotation & Golden-Set Curation
sidebar_label: Annotation Workflow
---

# Human Annotation & Golden-Set Curation

> How the platform runs a human-in-the-loop annotation loop **without adding
> infrastructure** — using **Langfuse** (already deployed) instead of Argilla.
> Backlog: **#313** (LLMOps layer 7, data management). Companion to the
> [LLMOps Stack Assessment](https://andrelair-platform.github.io/minicloud-platform-docs/docs/ai-ml/llmops-stack-assessment).

## Decision — Langfuse, not Argilla

Argilla v2 requires **ElasticSearch (~1–2 GB JVM RAM) + PostgreSQL + Redis**.
There is no ES/OpenSearch in the cluster, and the cluster is **CPU-only with
tight quotas** — adding an ES stack for an occasional annotation tool is
disproportionate (see [Compute Constraints](https://andrelair-platform.github.io/minicloud-platform-docs/docs/ai-ml/compute-constraints)
and the "no app just to install it" principle).

**Langfuse v3.201.1 (already running) provides the same human-in-the-loop
primitives natively** — Annotation Queues, Score Configs, manual Scores on traces
— with **zero new infrastructure and zero extra RAM**. It closes the layer-7
annotation gap while staying sovereign and lean.

## Capabilities (verified in the live DB)

Langfuse tables present: `annotation_queues`, `annotation_queue_items`,
`score_configs`, `scores` — the full annotation feature set is available.

| Need | Langfuse feature |
|---|---|
| Review model outputs | **Annotation Queue** — route selected traces to a human review queue |
| Structured labels | **Score Configs** — define categorical/numeric score dimensions (e.g. `helpful`, `faithful`, `pii_safe`) |
| Manual scoring | **Scores** on any trace/observation |
| Build golden sets | **Datasets** — promote reviewed traces into a dataset, export as golden set |

## Workflow — from traces to golden set

```
LiteLLM calls ──(success_callback: langfuse)──► Langfuse traces
                                                     │
                                    1. filter interesting/failing traces
                                                     ▼
                                    2. add to an Annotation Queue
                                                     ▼
                                    3. human review → apply Scores
                                       (define Score Configs first)
                                                     ▼
                                    4. promote good examples → a Dataset
                                                     ▼
                                    5. export the Dataset → golden set JSON
                                                     ▼
                             feeds the Ragas eval (manifests/ai/16-rag-eval-job)
```

### Step-by-step (Langfuse UI — `https://langfuse.devandre.sbs`, Authentik SSO)

1. **Define Score Configs** (Project Settings → Scores): e.g. `faithfulness`
   (numeric 0-1), `pii_safe` (boolean), `answer_quality` (categorical
   good/ok/bad).
2. **Create an Annotation Queue** (Annotation → Queues): name it (e.g.
   `rag-golden-review`) and attach the score configs.
3. **Add traces to the queue**: from the Traces view, filter (e.g. low
   `online_faithfulness`, or a given session/model), select → *Add to
   annotation queue*.
4. **Annotate**: work the queue, apply scores, mark good/bad examples.
5. **Promote to a Dataset**: add the well-scored traces to a Langfuse
   **Dataset** (input + expected output).
6. **Export** the dataset (UI export or public API) → drop into the Ragas eval
   dataset (`manifests/ai/18-rag-eval-dataset-configmap.yaml`) to grow the
   golden set the CI gate scores against.

## Closing the loop

This connects the existing pieces into a quality flywheel:

```
Ragas eval (CI gate) → surfaces weak answers
        → Langfuse annotation queue (human review)
        → curated golden set
        → back into the Ragas eval dataset  (loop)
```

Plus the online drift CronJob (`17-rag-eval-cronjob`) posts `online_faithfulness`
scores continuously → the annotation queue can be fed from real drift, not just
CI failures.

## If a real volume need emerges later

If annotation volume ever outgrows Langfuse (large labelling campaigns, multiple
annotators, dataset-versioning at scale), revisit **Argilla** — but only then,
with the ES cost justified by the workload. Until then, Langfuse is the right,
lean choice.
