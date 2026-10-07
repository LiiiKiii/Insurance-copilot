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

**A2 — Business Reasoning and Knowledge**

A2 adds domain-specific data access, deterministic reasoning, planning modules, and the M3 business knowledge layer on top of the A1 platform and data foundations.

The source modules in this stage remain separately testable building blocks. Registration in the agent runtime, application-wide API mounting, frontend integration, and end-to-end answer generation are introduced only when their corresponding integration stages are reached.

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

### A2 M3 Deliverables

The M3 contribution introduces three specialised file-based knowledge tools:

| Tool | Source | Purpose |
| ---- | ------ | ------- |
| `SearchCompetitionRulesTool` | competition summaries, qualification rules, and historical competition circulars | Retrieve competition and honour-standard excerpts with source filenames |
| `SearchBestPracticeTool` | `best_practices.md` | Retrieve sales practices for case size, conversion, competition sprints, MDRT progress, and existing-client opportunities |
| `SearchSalesScriptsTool` | `sales_scripts.md` | Retrieve scripts for objection handling, needs analysis, referrals, upselling, and closing |

The knowledge layer package also exports the A1 `SearchKnowledgeBaseTool` so the four retrieval tools share one package boundary.

## Knowledge Corpus

The A2 corpus consists of the A0 documents plus the following additions:

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

## Integration Status

The A2 M3 source boundary includes the specialised retrieval tools, expanded knowledge corpus, knowledge router, and its PDF ingestion services.

The following shared prerequisites must be supplied by the platform integration before the router is executable:

- FastAPI application and router mounting;
- `admin.dependencies` authentication and role dependencies;
- user and tenant identity models;
- initialized knowledge tables and database session factories;
- stage-appropriate package dependencies.

The current minimal AgentLoop does not register or execute the A2 knowledge tools. That registration belongs to the later agent-integration stage.

Tool results contain source filenames or database source metadata. Answer-level citation composition, citation correctness measurement, relevance-labelled evaluation data, and Recall@K/Precision@K evaluation are not yet implemented.

## Development Environment

- Python 3.11+
- SQLAlchemy 2.x with `aiosqlite`
- FastAPI for the knowledge management router
- PyMuPDF for PDF rasterisation
- RapidOCR ONNX Runtime for OCR
- `tiktoken` for token-aware chunking

Install the local project and its declared dependencies with:

```powershell
python -m pip install -e .
```

Environment-specific configuration is managed through environment variables and `.env` where supported. Local secrets, runtime databases, uploaded documents, and generated indexes must not be committed.

## Development

The knowledge modules can be validated independently from the final application flow:

- run file-based searches against the version-controlled knowledge corpus;
- initialize temporary knowledge tables and test database keyword lookup;
- test PDF rasterisation, OCR adaptation, layout recovery, chunking, processing, and indexing with isolated fixtures;
- verify tenant and role enforcement when the shared admin dependencies are available.

Application-wide tool orchestration, answer generation, knowledge management UI, source-citation evaluation, vector retrieval, and end-to-end deployment remain subsequent-stage work.
