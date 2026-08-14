# minicloud Copilot

**EPIC:** [#260](https://github.com/andrelair-platform/platform-backlog/issues/260) · **Status:** 📋 Backlog (5 connectors) · **Sprint:** TBD

minicloud Copilot is the self-hosted equivalent of Microsoft 365 Copilot. Every data source and AI component already exists on the platform — these 5 connectors wire them together so that AI assistance is embedded in the daily tools employees already use (email, chat, meetings, documents, search).

---

## Stack mapping — minicloud vs M365 Copilot

| M365 Copilot capability | minicloud equivalent | Status |
|---|---|---|
| Outlook — email summarization, triage | Stalwart mail + n8n + LiteLLM | 📋 #261 |
| Teams — meeting notes, action items | Jitsi + Whisper + LiteLLM + Nextcloud | 📋 #262 |
| SharePoint / OneDrive grounding | Nextcloud webhook → RAG → Qdrant | 📋 #263 |
| Copilot Chat in Teams | Matrix @ai bot → LiteLLM → Element | 📋 #264 |
| Enterprise Search | Unified RAG in Open WebUI (Qdrant backend) | 📋 #265 |
| AI gateway | LiteLLM | ✅ live |
| AI observability | Langfuse | ✅ live |
| Document conversion | markitdown-proxy | ✅ live |
| Vector search | Qdrant | ✅ live |
| Automation | n8n + minicloud-crew-agent | ✅ live |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        minicloud Copilot                            │
│                                                                     │
│  Data Sources              Connectors           AI Layer            │
│  ──────────                ──────────           ────────            │
│  Stalwart IMAP ──→ n8n ──────────────────────→ LiteLLM             │
│  Nextcloud files ──→ markitdown-proxy → RAG ──→   │                │
│  Jitsi recording ──→ Whisper ────────────────→    │                │
│  ERPNext API ────────────────────────────────→    │                │
│  Matrix history ─────────────────────────────→    ↓                │
│                                              Qdrant (vector DB)     │
│                                                   │                │
│                                              Open WebUI             │
│                                         (Enterprise Search)         │
│                                                   │                │
│                                              Langfuse (traces)      │
└─────────────────────────────────────────────────────────────────────┘
```

All connectors write to the same Qdrant instance. Open WebUI becomes the unified Enterprise Search interface — no separate search tool needed.

---

## Connector 1 — Email AI ([#261](https://github.com/andrelair-platform/platform-backlog/issues/261))

**Stalwart IMAP → n8n → LiteLLM → Matrix + ERPNext + SMTP**

| Step | Component | Detail |
|---|---|---|
| Trigger | n8n IMAP node | Polls shared mailboxes (sinistres@, courtiers@, production@) every 2 min |
| Classification | LiteLLM | Urgency P1/P2/P3 + type (déclaration / résiliation / avenant / autre) |
| Extraction | LiteLLM | Insured name, policy number, date of loss, 3-sentence summary |
| Alert | Matrix webhook | Posted to `#sinistres:` room; P1 triggers @room |
| CRM creation | ERPNext REST API | Lead/Opportunity with extracted fields |
| Acknowledgement | SMTP via Stalwart | Auto-reply with SLA: P1=4h / P2=24h / P3=48h |
| Draft assist | LiteLLM | Reply draft saved to Stalwart Drafts (human sends) |

**Value for insurance IS:** Eliminates manual triage of sinistres@ — every claim email is classified, logged in ERPNext, and acknowledged within 5 minutes.

---

## Connector 2 — Meeting Notes ([#262](https://github.com/andrelair-platform/platform-backlog/issues/262))

**Jitsi → Whisper → LiteLLM → Nextcloud + Matrix**

| Step | Component | Detail |
|---|---|---|
| Recording | Jibri (to deploy) | Saves .mp4 to Nextcloud `Meetings/recordings/` |
| Trigger | n8n WebDAV poll | Detects new recording file |
| Transcription | Whisper large-v3 | OpenAI-compatible endpoint in `ai` namespace |
| Summarization | LiteLLM | Structured output: participants, decisions, action items, summary |
| Storage | Nextcloud | Notes saved to `Meetings/notes/<date>-<room>.md` |
| Notification | Matrix | Summary posted to corresponding Matrix room |

**Action item format:** `- [ ] @owner: task description (due: YYYY-MM-DD)`

---

## Connector 3 — Document Grounding ([#263](https://github.com/andrelair-platform/platform-backlog/issues/263))

**Nextcloud webhook → markitdown-proxy → rag-ingest → Qdrant**

This is the fastest connector to ship — no new containers, just wiring existing services.

**Collection mapping:**

| Nextcloud folder | Qdrant collection | doc_type |
|---|---|---|
| /Company/Policies/ | company-policies | policy |
| /Company/Procedures/ | company-procedures | internal |
| /Company/Sinistres/ | sinistres | claim |
| /Company/Contracts/ | contracts | contract |

**Trigger:** Nextcloud Flow app fires webhook on file create/update/delete → n8n → `rag-ingest` service.

---

## Connector 4 — Chat AI Assistant ([#264](https://github.com/andrelair-platform/platform-backlog/issues/264))

**Matrix @ai bot → LiteLLM → Element Web**

Deployed as **maubot** in `chat` namespace. Users mention `@ai` in any Element room.

| Command | Action |
|---|---|
| `@ai <question>` | AI reply with last 10 messages as context |
| `@ai /search <query>` | RAG search across all Qdrant collections → top 3 sources |
| `@ai /summarize` | Summarize last 20 messages in the room |
| `@ai /action-items` | Extract action items from last 20 messages |

For document questions (message contains `?` + policy keywords) → RAG lookup first → LiteLLM with retrieved context.

---

## Connector 5 — Enterprise Search UI ([#265](https://github.com/andrelair-platform/platform-backlog/issues/265))

**Open WebUI + Qdrant → unified search across all 4 data sources**

Open WebUI is reconfigured to use the shared Qdrant instance (`VECTOR_DB=qdrant`) instead of its default Chroma. Five Knowledge Bases are pre-configured:

| Knowledge Base | Collections | Access |
|---|---|---|
| 📧 Emails | emails | management |
| 📁 Company Documents | company-policies, procedures, contracts | all |
| 🎥 Meeting Notes | meeting-transcripts | all |
| 💬 Chat History | matrix-history | collab |
| 🔍 All Sources | all collections (re-ranked) | management |

**Hybrid search:** BM25 keyword + dense vector, French BM25 tokenizer already in the `minicloud-open-webui` custom image.

**Source citation:** every response includes filename + collection + chunk score.

---

## Build order

| Step | Issue | Effort | Depends on |
|---|---|---|---|
| 1 | Email AI (#261) | ~3 days (n8n workflow + LiteLLM prompt) | nothing |
| 2 | Document grounding (#263) | ~1 day (webhook + existing rag-ingest) | nothing |
| 3 | Chat AI (#264) | ~2 days (maubot deploy + plugin) | nothing |
| 4 | Meeting notes (#262) | ~4 days (Jibri + Whisper + n8n) | Jibri |
| 5 | Enterprise Search (#265) | ~2 days (Open WebUI config + KB setup) | #261 #262 #263 |

Total estimate: **~12 days** for full minicloud Copilot. No new infrastructure except Jibri (Jitsi recording) and Whisper (both lightweight).

---

## Observability

Every LLM call in all 5 connectors flows through LiteLLM → traced in Langfuse with:
- `tags`: connector name (`email-ai`, `meeting-notes`, etc.)
- `metadata`: source document / email subject / room name
- `session_id`: tied to the source event for full trace

A Grafana dashboard `minicloud-copilot-v1` will show: calls per connector / p95 latency / classification distribution.
