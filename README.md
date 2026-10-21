# Insurance Performance Intelligence Copilot

A Hybrid Intelligent Reasoning System for insurance agents' performance gap diagnosis and action planning.

## Overview

Insurance agents operate in a target-driven environment and need to monitor performance targets, competition progress, pending policies, and customer follow-up opportunities.

This project progressively combines data-driven diagnosis, deterministic business-rule reasoning, knowledge retrieval, action planning, and natural-language interaction. Each migration stage contains only the components introduced by that point in the development cycle.

## Project Status

Current migration stage:

**A6 — Final Integration Validation and Baseline Freeze**

A5 established repeatable acceptance coverage for knowledge retrieval, upload boundaries, PDF processing, and planning. A6 validates the merged project and freezes the accepted baseline. The current validation confirms the knowledge-retrieval boundary and the deterministic planning behavior while preserving their documented limitations.

No new M3 runtime code is introduced in A6 because the required knowledge models, retrieval tools, administration routes, ingestion pipeline, corpus, and acceptance tests were migrated in A0 through A5.

A6 adds no new administration features. It validates the code already present in the merged repository and retains the A3 integration delivered by the other workstreams: M3 daily briefing and compliance services, plus M4 planning endpoints and the interface contract for candidate prioritisation.

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

### A4 M4 Deliverables

- the existing English action templates are seeded as the non-public
  `planning.action_templates` system configuration;
- super administrators can manage the templates through the protected system
  configuration API already introduced in A4;
- the chase-plan tool consumes the managed value without changing its weekly
  target calculations or priority rules;
- the version-controlled JSON file and built-in English templates remain safe
  fallbacks when the administration database is unavailable or invalid.

### A5 M3 Deliverables Retained

#### Tests and baseline acceptance

- file-based retrieval tests for competition rules, best practices, and sales scripts;
- SQLite FTS5 acceptance coverage for administrator-managed knowledge chunks;
- tenant-isolation and PDF upload validation tests for the knowledge administration router;
- unit tests for PDF rasterisation, OCR extraction, layout recovery, Markdown chunking, indexing, and end-to-end document status transitions;
- isolated temporary databases, files, and mocked OCR adapters so the baseline does not require production data or external services.

### A5 M4 Deliverables Retained

#### Planning-tool baseline acceptance

- chase-plan coverage for pending-premium deduction, equal weekly targets, urgent competition selection, managed-template fallback, and stable errors;
- planning API coverage for route registration, validated chase-plan inputs, improvement-advice Top-N forwarding, and invalid tool payloads;
- deterministic tests that isolate database access and business calculations;
- no customer scoring, ranking, Top-K selection, or optimisation algorithm was added by the test round.

### A6 M3 Baseline Freeze

- confirmed that competition rules, qualification rules, best practices, and sales scripts are searchable through the existing English file-retrieval tools;
- confirmed that administrator-managed chunks are searchable through SQLite FTS5 with the SQL `LIKE` fallback retained for compatible deployments;
- confirmed that retrieval responses preserve source references for Markdown assets and database-backed documents;
- confirmed that the version-controlled knowledge corpus, tenant-aware administration routes, import tool, and PDF ingestion pipeline are present in the final staged repository;
- retained the A5 automated acceptance scope without modifying the validated M3 implementation;
- recorded the final M3 capabilities and known retrieval boundaries in this README.

### M4 Prioritisation and Planning

- the chase-plan tool deducts pending premium, selects an urgent open
  competition, divides the remaining gap into weekly targets, and attaches
  configured action-template text;
- the improvement-advice tool calculates attribution gaps at runtime and maps
  the highest-priority weaknesses to deterministic P0/P1/P2 guidance;
- `prioritize_followups` filters ineligible, unauthorised, non-compliant, and
  invalid candidates before applying an explainable weighted score;
- eligible candidates are ranked with deterministic tie-breaking and returned
  as Top-K recommendations with score components, priority levels, actions,
  timing, evidence, and ranking reasons;
- `POST /api/planning/prioritization` exposes the ranking contract through the
  authenticated planning API without querying or changing M2-owned data;
- Precision@K and NDCG@K utilities compare the weighted ranking with an
  expected-contribution-only baseline using a tracked synthetic fixture;
- the synthetic evaluation validates the implementation pipeline only and is
  not evidence of production effectiveness or improved sales outcomes; and
- the default Agent runtime tool registry remains unchanged, so enabling
  automatic LLM access to `prioritize_followups` remains an explicit integration
  decision.

## Knowledge Corpus

The version-controlled corpus contains:

| Category | Documents |
| -------- | --------- |
| Competition rules | `competition_starlight.md`, `competition_elite_challenge.md`, `competition_quarterly_sprint.md`, `competition_rookie_king.md` |
| Performance standards | `mdrt_rules.md` (written premium excellence), `cot_rules.md` (portfolio quality excellence); legacy filenames are retained for compatibility |
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

Create a virtual environment and install the Python project, its test dependencies, and an ASGI server with:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" uvicorn
```

Copy `.env.example` to `.env` and configure authentication before starting the server or creating the first administrator. Set `ADMIN_DATABASE_URL` to a database intended for this instance; if omitted, the application uses `data/db/admin.db`. Keep `.env` out of version control.

```text
ADMIN_SECRET_KEY=<random-signing-secret-of-at-least-32-bytes>
ADMIN_DEFAULT_PASSWORD=<initial-admin-password>
AGENT_DEFAULT_PASSWORD=<initial-password-for-seeded-agent-accounts>
ADMIN_ENCRYPTION_KEY=<Fernet-key-for-encrypted-provider-credentials>
```

`ADMIN_ENCRYPTION_KEY` is required when encrypted provider credentials are stored or read. Generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and keep the value private.

Apply the tracked migrations to a new development database, then create the initial `admin` account and seed data:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m admin.seeds
```

Start the backend from the repository root, then start the frontend in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.server:app --reload
```

```powershell
cd web
pnpm install --frozen-lockfile
pnpm dev
```

The frontend requires Node.js 20+ and pnpm 9. It proxies `/api/*` and `/ws/*` to `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). Open `http://localhost:3000/admin/login`. For local chat WebSockets, set `WS_ALLOWED_ORIGINS=http://localhost:3000` in the backend environment.

## Test and Baseline Acceptance

Run the complete backend suites from the repository root with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q
.\.venv\Scripts\python.exe -m pytest tests -q
```

For frontend checks, run `pnpm install --frozen-lockfile` followed by `pnpm lint` from `web/`. Set `ADMIN_DATABASE_URL` to a disposable SQLite database for integration runs; never point tests at a production database. The PDF chunker tests need the public `cl100k_base` tokenizer data cached by `tiktoken` on first use.

Run the focused A6 M3 acceptance scope with:

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

These tests exercise the M3 features introduced through A4 and retained in the frozen baseline. They do not introduce vector search, retrieval scoring datasets, or production OCR benchmarks.

Run the A6 M4 planning acceptance scope with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chase_plan.py tests/test_insurance_tools.py tests/test_planning_api.py -q
```

The 19-test acceptance scope executes the current chase-plan logic with
isolated business data and action templates, verifies the improvement-advice
template contract against deterministic attribution results, and checks route
registration, validated request forwarding, and stable invalid-payload
handling. The detailed result and functional boundary are recorded in
`docs/a6_m4_planning_baseline.md`.

Run the current M4 prioritisation and attribution regression scope with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_attribution_gap.py tests/test_planning_api.py tests/test_prioritization.py tests/test_prioritization_evaluation.py -q
```

Run the reproducible ranking experiment with:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_prioritization.py
```

The implementation details, current ownership boundary, synthetic-data notice,
and baseline comparison are recorded in
`docs/coursework/m4_prioritization_experiment.md`.

## A6 Baseline Freeze

A6 is the final migration round. The M3 baseline is considered complete for the
implemented product scope: deterministic English file retrieval, SQLite FTS5
database retrieval with a SQL fallback, source citation, tenant-aware knowledge
administration, local text import, PDF ingestion, and automated acceptance
coverage.

The current M4 implementation combines the deterministic chase-plan and
improvement-advice tools with a separate prioritisation module for explainable
candidate filtering, weighted ranking, Top-K recommendation, and offline
ranking metrics. It must not be represented as a trained
conversion-probability model or as proof of production business impact.

Vector or embedding retrieval, a production labelled ranking dataset,
production OCR benchmarking, automatic M2 candidate-data ingestion, M5
recommendation rendering, and broader production hardening remain outside the
currently integrated baseline.
