# Insurance Performance Intelligence Copilot

A Hybrid Intelligent Reasoning System for insurance agents' performance gap diagnosis and action planning.

## Overview

Insurance agents operate in a target-driven environment and need to monitor performance targets, competition progress, pending policies, and customer follow-up opportunities.

This project progressively combines data-driven diagnosis, deterministic business-rule reasoning, knowledge retrieval, action planning, and natural-language interaction. Each migration stage contains only the components introduced by that point in the development cycle.

## Project Status

Current migration stage:

**A4 — Existing Tests and Baseline Acceptance**

A4 validates the smallest usable administration path for the M3 knowledge subsystem. Administrators can authenticate, manage tenant-scoped knowledge bases, upload PDF documents for OCR and indexing, inspect generated chunks, and import project-local text documents through English administration tools. The round adds repeatable baseline tests for knowledge retrieval, upload boundaries, and the PDF document-processing pipeline.

The stage also retains the A3 integration delivered by the other workstreams: M3 daily briefing and compliance services, plus M4 planning endpoints and the interface contract for later candidate prioritisation.

Unrelated administration areas such as user management, tenant management, model configuration, audit dashboards, usage analytics, channels, and general database tools are intentionally excluded from this stage.

### A0 Deliverables Retained

- base repository structure, development configuration, and project conventions;
- initial mock data and business configuration;
- four competition rule documents;
- MDRT and COT qualification rules;
- insurance sales scripts.

### A1 Deliverables Retained

- message bus, provider, configuration, and minimal agent runtime foundations;
- SQLAlchemy models for knowledge bases, documents, and document chunks;
- `SearchKnowledgeBaseTool` for SQLite FTS5 keyword lookup with a SQL `LIKE` fallback.

### A2 M3 Deliverables Retained

- `SearchCompetitionRulesTool` for competition and qualification material;
- `SearchBestPracticeTool` for sales and performance practices;
- `SearchSalesScriptsTool` for customer-facing guidance;
- the extended Markdown knowledge corpus under `data/knowledge/`;
- tenant-aware knowledge CRUD and the PDF processing services that later administration stages can expose.

The file-based tools use deterministic English keyword and section matching. They do not use embeddings or vector similarity.

### A3 M3 Deliverables Retained

- `api/routers/briefing.py` with tenant-aware inbox ingestion, daily briefing, acknowledgement, message-state, settings, warmup, and administrative message endpoints;
- `api/briefing/llm_generator.py` with an English briefing prompt, OpenAI-compatible and Anthropic adapters, structured action-item extraction, and a deterministic fallback;
- `api/briefing/compliance.py` with rule-based training and practice warnings that remain visible when LLM generation is unavailable;
- `api/briefing/scheduler.py` with tenant-scoped briefing warmup only;
- inbox, daily briefing, briefing settings, user, role, permission, and model-configuration persistence models;
- a stage-scoped model-configuration bridge for selecting the enabled default LLM;
- database registration and package metadata required by the API package.

The completed project's unrelated upload-cleanup job remains outside the A3 M3 scheduler.

### A3 M4 Deliverables Retained

- `api/routers/planning.py` exposes the existing chase-plan and improvement-advice tools through validated planning endpoints;
- the planning router is mounted by the shared FastAPI application without changing either tool's calculations or priority rules;
- the chase-plan tool consumes the current competition data-layer contract directly instead of importing the completed prototype's former enrichment module;
- `docs/coursework/prioritization-interface.md` defines the future candidate input, ranked output, ownership, deterministic tie-breaking, and validation boundary;
- no customer scoring, Top-K selection, optimisation endpoint, or new ranking algorithm is introduced in A3.

### A4 M3 Deliverables

#### Authentication and API integration

- `admin/services/auth_service.py` for password hashing and signed access and refresh tokens;
- `admin/dependencies.py` for bearer-token validation, tenant identity, and role enforcement;
- `admin/routers/auth.py` for login, refresh, logout, and current-user operations;
- a stage-scoped admin router registry that mounts only authentication and knowledge management;
- application-lifespan database initialisation and cleanup in `api/server.py`;
- idempotent A4 seed data for knowledge permissions, admin roles, and the first administrator.

#### Knowledge administration

- a protected administration page for creating and deleting knowledge bases;
- document listing, status display, chunk preview, and deletion;
- tenant-scoped PDF upload with filename sanitisation, a 20 MB limit, background OCR, token-aware chunking, and SQLite FTS5 indexing;
- English `admin_list_knowledge` and `admin_kb_import` tools;
- project-local text import for `.md`, `.txt`, and `.csv` sources with workspace path validation and FTS5 indexing.

#### Stage-scoped frontend

- `/admin/login` for administrator authentication;
- `/admin/knowledge` for knowledge-base and document management;
- a minimal A4 navigation shell that exposes only the knowledge area;
- an API client with token refresh and role-aware controls.

#### M3 tests and baseline acceptance

- file-based retrieval tests for competition rules, best practices, and sales scripts;
- SQLite FTS5 acceptance coverage for administrator-managed knowledge chunks;
- tenant-isolation and PDF upload validation tests for the knowledge administration router;
- unit tests for PDF rasterisation, OCR extraction, layout recovery, Markdown chunking, indexing, and end-to-end document status transitions;
- isolated temporary databases, files, and mocked OCR adapters so the baseline does not require production data or external services.

## Knowledge Corpus

The version-controlled corpus contains:

| Category | Documents |
| -------- | --------- |
| Competition rules | `competition_starlight.md`, `competition_elite_challenge.md`, `competition_quarterly_sprint.md`, `competition_rookie_king.md` |
| Qualification rules | `mdrt_rules.md`, `cot_rules.md` |
| Sales guidance | `sales_scripts.md`, `best_practices.md`, `action_guidelines.md` |
| Historical competition circulars | Markdown documents under `data/knowledge/competitions/` |

Files in `data/knowledge/` remain version-controlled source assets. They are not automatically inserted into the database. Use `admin_kb_import` for supported text sources, or upload a PDF through the administration page.

## Administration API

The A4 server mounts the following routes under `/api/admin`:

| Area | Routes |
| ---- | ------ |
| Authentication | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Knowledge bases | list, create, read, update, and delete under `/knowledge-bases` |
| Documents | list, register, upload, delete, and inspect chunks under `/knowledge-bases/{kb_id}/documents` |

Knowledge routes enforce role and tenant boundaries. `readonly` users can inspect data, `agent_manager` users can create and import content, and `admin` or `super_admin` users can delete content.

### PDF ingestion pipeline

1. `PdfRasterizer` converts PDF pages into images.
2. `OcrExtractor` extracts text through RapidOCR.
3. `LayoutRecoverer` reconstructs page-level Markdown.
4. `MarkdownChunker` creates overlapping token-bounded chunks.
5. `KnowledgeIndexer` stores chunks and maintains SQLite FTS5 rows.
6. `DocumentProcessor` records indexed or failed status for the administration page.

Uploaded runtime files are stored outside version control.

## Development Environment

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x with `aiosqlite`
- JSON Web Tokens signed with `python-jose`
- PyMuPDF and RapidOCR ONNX Runtime
- `tiktoken` for token-aware chunking
- Next.js 16 and React 19 for the administration page

Install the Python project and its test dependencies with:

```powershell
python -m pip install -e ".[dev]"
```

Configure A4 authentication in `.env` before starting the server or creating the first administrator:

```text
ADMIN_SECRET_KEY=<random-signing-secret-of-at-least-32-bytes>
ADMIN_DEFAULT_PASSWORD=<initial-admin-password>
```

Never commit real secrets. Create the database records and initial `admin` account with:

```powershell
python -m admin.seeds
```

Start the backend and frontend with the project's existing development commands. The administration page is available at `/admin/login` after both services are running.

## Test and Baseline Acceptance

Run the A4 M3 acceptance scope with:

```powershell
python -m pytest tests/test_knowledge_retrieval.py tests/admin/test_knowledge_router.py tests/admin/services/pdf -q
```

The acceptance scope covers the following baseline:

| Area | Baseline evidence |
| ---- | ----------------- |
| File knowledge retrieval | English queries return matched content with source references |
| Database knowledge retrieval | SQLite FTS5 returns indexed chunks and preserves document provenance |
| Upload boundary | Tenant isolation, PDF-only input, and the 20 MB size limit are enforced |
| Document processing | Rasterisation, OCR, layout recovery, chunking, indexing, and failure states are tested |

These tests exercise only features already available by A4. They do not introduce vector search, retrieval scoring datasets, production OCR benchmarks, or later-stage end-to-end workflows.

## A4 Boundary

This round does not introduce the completed project's remaining admin pages, full agent-side admin orchestration, vector retrieval, retrieval evaluation datasets, final deployment configuration, or end-to-end production hardening. Those components and their tests must be migrated in their designated later stages.
