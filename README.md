# Insurance Performance Intelligence Copilot

A Hybrid Intelligent Reasoning System for insurance agents' performance gap diagnosis and action planning.

## Overview

Insurance agents operate in a target-driven environment and need to monitor performance targets, competition progress, pending policies, and customer follow-up opportunities.

This project aims to build an intelligent decision-support system that helps insurance agents and supervisors:

- identify performance gaps;
- understand relevant contributing factors;
- assess whether remaining targets are achievable;
- retrieve relevant business knowledge and guidance;
- prioritise appropriate follow-up actions.

The system progressively integrates data-driven diagnosis, deterministic business-rule reasoning, knowledge retrieval, optimisation-based planning, and natural-language interaction.

## Project Status

Current migration stage:

**A3 — API, Sessions, and System Integration**

A3 begins the integration of the independently developed A2 modules through API and runtime boundaries. The M3 contribution exposes daily briefing operations, converts business notifications into English knowledge-guided prompts, and keeps compliance warnings deterministic and separate from LLM output. The M4 contribution exposes the existing template-based planning tools through a focused business API and fixes the interface contract for future candidate prioritisation without implementing the later ranking model.

Chat-session orchestration and application-wide server composition are shared integration responsibilities and are not included in this M3 baseline.

### A0 Deliverables Retained

- base repository structure, development configuration, and project conventions;
- initial mock data and business configuration;
- four competition rule documents;
- MDRT and COT qualification rules;
- insurance sales scripts.

### A1 Deliverables Retained

- message bus, provider, configuration, and minimal agent runtime foundations;
- SQLAlchemy models for knowledge bases, documents, and document chunks;
- `SearchKnowledgeBaseTool` for database-backed keyword lookup using SQLite FTS5 with a SQL `LIKE` fallback.

### A2 M3 Deliverables Retained

The M3 contribution includes three specialised file-based knowledge tools:

| Tool | Source | Purpose |
| ---- | ------ | ------- |
| `SearchCompetitionRulesTool` | competition summaries, qualification rules, and historical competition circulars | Retrieve competition and honour-standard excerpts with source filenames |
| `SearchBestPracticeTool` | `best_practices.md` | Retrieve sales practices for case size, conversion, competition sprints, MDRT progress, and existing-client opportunities |
| `SearchSalesScriptsTool` | `sales_scripts.md` | Retrieve scripts for objection handling, needs analysis, referrals, upselling, and closing |

The knowledge layer package also exports the A1 `SearchKnowledgeBaseTool` so the four retrieval tools share one package boundary.

### A3 M3 Deliverables

- `api/routers/briefing.py` with tenant-aware inbox ingestion, daily briefing, acknowledgement, message-state, settings, warmup, and administrative message endpoints;
- `api/briefing/llm_generator.py` with an English briefing prompt, OpenAI-compatible and Anthropic adapters, structured action-item extraction, and a deterministic fallback;
- `api/briefing/compliance.py` with rule-based training and practice warnings that remain visible when LLM generation is unavailable;
- `api/briefing/scheduler.py` with tenant-scoped briefing warmup only;
- inbox, daily briefing, briefing settings, user, role, permission, and model configuration persistence models;
- a stage-scoped model configuration bridge for selecting the enabled default LLM;
- database registration and package metadata required by the new API package.

The completed project's unrelated upload-cleanup job is deliberately excluded from the A3 M3 scheduler. Chat uploads, frontend views, and full application bootstrap remain outside this round.

### A3 M4 Deliverables

- `api/routers/planning.py` exposes the existing chase-plan and improvement-advice tools through validated planning endpoints;
- the planning router is mounted by the shared FastAPI application without changing either tool's calculations or priority rules;
- the chase-plan tool now consumes the current competition data-layer contract directly instead of importing the completed prototype's former enrichment module;
- `docs/coursework/prioritization-interface.md` defines the future candidate input, ranked output, ownership, deterministic tie-breaking, and validation boundary;
- no customer scoring, Top-K selection, optimisation endpoint, or new ranking algorithm is introduced in A3.

## Knowledge Corpus

The retained corpus consists of the A0 documents plus the following A2 additions:

| Category | Documents |
| -------- | --------- |
| Best practices and action guidance | `best_practices.md`, `action_guidelines.md` |
| Historical competition circulars | `competitions/AG24050.md`, `AG25011.md`, `AG25030.md`, `AG25035.md`, `AG25044.md`, `AG25099.md`, `AG25129.md`, `AG25138.md` |

The specialised tools read Markdown files directly from `data/knowledge/`. They perform deterministic keyword and section matching; they do not use embeddings or vector similarity.

The database-backed `SearchKnowledgeBaseTool` remains separate. Markdown files are not automatically inserted into the `documents` and `document_chunks` tables merely by being present in the repository.

## Knowledge Management API

`admin/routers/knowledge.py` defines tenant-aware operations for:

- listing, creating, reading, updating, and deleting knowledge bases;
- listing and registering documents;
- deleting documents and their chunks;
- listing stored document chunks;
- uploading a document and scheduling background ingestion.

The router depends on the shared admin authentication and database layers. It must be mounted by the platform API before these routes become available over HTTP.

### Document Ingestion

The upload route uses the knowledge-specific services under `admin/services/pdf/`:

1. `PdfRasterizer` converts PDF pages into images.
2. `OcrExtractor` extracts text lines through RapidOCR.
3. `LayoutRecoverer` reconstructs page-level Markdown.
4. `MarkdownChunker` creates overlapping token-bounded chunks.
5. `KnowledgeIndexer` stores chunks and maintains the SQLite FTS5 index.
6. `DocumentProcessor` coordinates the pipeline and updates document status.

Uploaded runtime files are stored outside version control. Repository knowledge documents remain version-controlled source assets.

## Daily Briefing API

`api/routers/briefing.py` defines the M3 API boundary for turning structured customer notifications into a prioritised daily briefing.

| Area | Routes |
| ---- | ------ |
| Inbox ingestion | `POST /api/briefing/inbox/ingest` |
| Daily briefing | `GET /api/briefing/today/summary`, `GET /api/briefing/today`, `POST /api/briefing/today/regenerate`, `POST /api/briefing/today/acknowledge` |
| Message state | `GET /api/briefing/messages/{message_id}`, `POST /api/briefing/messages/{message_id}/read`, `POST /api/briefing/messages/{message_id}/handled` |
| Tenant administration | Briefing settings, manual warmup, agent listing, and message CRUD under `/api/briefing/admin/` |

The generator groups notifications into P0, P1, and P2 sections. Its English prompt requests a top-three action list, complete notification context, concrete next steps, and a suggested customer-facing script. The parser extracts a short structured action preview from the generated Markdown. If no usable model configuration or API key exists, a deterministic English summary is returned instead.

Compliance checks do not rely on the language model. They read the latest agent performance record and return structured training or practice warnings beside the briefing response.

The scheduler polls tenant briefing settings and can pre-generate eligible agents' briefings at the configured Asia/Shanghai time. It is supplied as an integration module but is not started automatically by this migration round.

## Integration Status

The A3 M3 source boundary includes the A2 knowledge components plus the briefing router, briefing services, persistence models, model selection bridge, and scheduler.

The following shared integration work remains outside this contribution:

- mounting the briefing and knowledge routers in the shared FastAPI application;
- starting and stopping the briefing scheduler from the application lifespan;
- connecting shared authentication and chat-session context to the briefing routes;
- registering knowledge tools in the final agent runtime;
- integrating frontend briefing views and notification channels;
- evaluating retrieval and citation quality with labelled Recall@K and Precision@K data.

No full server bootstrap, chat-session implementation, frontend module, or deployment configuration is introduced in this M3 baseline.

## Development Environment

- Python 3.11+
- SQLAlchemy 2.x with `aiosqlite`
- FastAPI for the knowledge and briefing routers
- OpenAI-compatible and Anthropic clients for optional briefing generation
- APScheduler for configurable briefing warmup
- PyMuPDF for PDF rasterisation
- RapidOCR ONNX Runtime for OCR
- `tiktoken` for token-aware chunking

Install the local project and its declared dependencies with:

```powershell
python -m pip install -e .
```

Environment-specific configuration is managed through environment variables and `.env` where supported. Local secrets, runtime databases, uploaded documents, and generated indexes must not be committed.

## Development

The A3 modules can be validated independently from the final application flow:

- run file-based searches against the version-controlled knowledge corpus;
- initialize temporary knowledge tables and test database keyword lookup;
- test PDF rasterisation, OCR adaptation, layout recovery, chunking, processing, and indexing with isolated fixtures;
- verify tenant and role enforcement when the shared admin dependencies are available;
- build an English prompt from representative P0, P1, and P2 messages;
- verify deterministic briefing output with no configured LLM key;
- exercise briefing storage, acknowledgement, compliance warnings, and warmup scheduling against a temporary database.

Application-wide server composition, chat-session orchestration, frontend integration, source-citation evaluation, vector retrieval, and end-to-end deployment remain subsequent-stage work.
