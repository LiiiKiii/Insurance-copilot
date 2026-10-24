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
- the current offline evaluation compares the weighted ranking with an
  expected-contribution-only baseline at K=1, 3, and 5 across 10 tracked M2
  scenarios, and includes fixed weight-sensitivity profiles;
- the evaluation uses synthetic case-level data and AI-assisted adjudication
  of two independent human rankings, so it is not evidence of production
  effectiveness or improved sales outcomes; and
- `prioritize_followups` is registered. For an authenticated, configured
  coursework demo agent, the model sees a no-argument facade; M1 prepares and
  validates M2 v3 candidates server-side before invoking the unchanged M4
  ranker. Other scopes remain fail closed. This synthetic adapter is not a
  production candidate retrieval service, and live autonomous LLM E2E has not
  been verified.

## Insurance workflow Skills (M1)

The five Python Skills in `nanobot/agent/skills/insurance/` select answer workflows for single-target gaps, performance diagnosis, feasibility, weekly planning, and underperformance analysis. A Skill matches the raw question and supplies instructions; a Tool supplies data or runs a calculation. Skills do not execute business logic. `SkillRegistry` matches Chinese phrases and scoped English phrases deterministically, orders matches by priority `5, 10, 20, 30, 40`, and selects at most two. No match leaves the normal chat flow intact.

On an authenticated `/ws/chat` turn, the server verifies the JWT and that the requested `agent_id` equals the signed-in username. `AgentLoop` checks the Tool definitions and required parameter schemas before it adds server-owned workflow guidance to the system message. The user's original text stays in the user message and chat history; a client-written `[SKILL GUIDANCE]` tag cannot become trusted guidance. The existing ToolRegistry, agent binding, tenant checks, four-iteration limit, audit, and optional structured response remain in effect. There is no separate HTTP chat Skill path.

Examples: “我离 MDRT 还差多少？”, “请做业绩诊断”, “目标还来得及吗？”, “请拆解我的目标做每周计划”, “业绩为什么没达标？”; “What's my MDRT gap?”, “Analyze my performance gap.”, “Can I still achieve my target?”, “Create a weekly target plan.”, “Why am I underperforming?”. Skills refer only to currently registered Tools. The old `calc_gap_analysis`, `calc_run_rate`, `calc_feasibility`, `calc_attribution_gap`, `get_period_comparison`, and `get_ranking` Tool names are unavailable; prompts either use compatible New Repo Tools or omit those claims. Pending-adjusted chase-plan gaps are planning estimates, not verified open gaps. Feasibility guidance uses the current USD premium baseline only; it does not assess HKD or policy-count goals with that baseline.

Offline scripted-provider tests cover selection, integration, authorization, audit, and fallback. Real LLM Tool selection and answer quality still require an approved isolated end-to-end run. Generic Markdown `SKILL.md` loading and proactive alerts are **DEFERRED**.

## Knowledge Corpus

The version-controlled corpus contains:

| Category | Documents |
| -------- | --------- |
| Competition rules | `competition_starlight.md`, `competition_elite_challenge.md`, `competition_quarterly_sprint.md`, `competition_rookie_king.md` |
| Performance standards | `mdrt_rules.md` (MDRT/COT/TOT qualification and FYC/FYP milestones), `cot_rules.md` (COT qualification, benefits, and achievement paths) |
| Sales guidance | `sales_scripts.md`, `best_practices.md`, `action_guidelines.md` |
| Historical competition circulars | Markdown documents under `data/knowledge/competitions/` |

Files in `data/knowledge/` remain version-controlled source assets. With `BUILTIN_KNOWLEDGE_AUTO_SYNC=1` (the default), the API startup synchronizes the three built-in knowledge groups into the database; other supported text sources can be imported with `admin_kb_import`, and PDFs can be uploaded through the administration page.

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

### Isolated M1 coursework demo

Use a **separate** SQLite database for this synthetic demo. The setup command
refuses any other database target. Run migrations and `admin.seeds` there first;
the seed creates the `default` tenant and agent logins used by M2 business data
and M3 built-in knowledge. The M1 command only validates an existing enabled
default tenant and scenario-matching seeded agent. It does not create accounts,
reset passwords, or change roles. Configure `ADMIN_DEFAULT_PASSWORD` and
`AGENT_DEFAULT_PASSWORD` as described above before the first seed run.

```powershell
New-Item -ItemType Directory -Force data/demo | Out-Null
$demoDb = (Join-Path (Get-Location) 'data/demo/m1_coursework.db').Replace('\', '/')
$env:ADMIN_DATABASE_URL = 'sqlite+aiosqlite:///' + $demoDb
.\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Demo database migration failed' }
.\.venv\Scripts\python.exe -m admin.seeds
if ($LASTEXITCODE -ne 0) { throw 'Demo database seed failed' }
.\.venv\Scripts\python.exe -m scripts.setup_m1_coursework_demo --agent-id AGT00690
if ($LASTEXITCODE -ne 0) { throw 'Demo agent validation failed' }
.\.venv\Scripts\python.exe -m scripts.sync_builtin_knowledge
if ($LASTEXITCODE -ne 0) { throw 'Demo knowledge sync failed' }
```

Set both `M1_COURSEWORK_DEMO_TENANT_ID` and `M1_COURSEWORK_DEMO_AGENT_ID` in the
backend environment to the IDs printed by the setup command, and use the same isolated `ADMIN_DATABASE_URL` when
starting the backend. Keep `ADMIN_SECRET_KEY` configured as described above.
Log in as `AGT00690` with the seeded agent password. A repeat setup only reads
the existing tenant, user, and role. The knowledge sync uses local Markdown
and does not request embeddings on SQLite.
The dataset's `coursework-demo` tenant label records synthetic source provenance;
it is not the database tenant. This demo does not authorize production customer
candidate retrieval.
The dataset is a dated `2026-05-31` coursework snapshot, not live customer
data. The WebSocket result card is supported by the current M5 hook; a browser
or live-provider E2E has not been established by the offline tests.

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
.\.venv\Scripts\python.exe scripts/select_m4_horizon_weights.py `
  --output data/evaluation/m4_horizon_weight_selection_v3.json

.\.venv\Scripts\python.exe scripts/evaluate_prioritization.py `
  --scenarios data/evaluation/m2_candidate_scenarios_v4.json `
  --annotations data/evaluation/m2_candidate_annotations_v4.json `
  --output data/evaluation/m4_prioritization_results_v4.json
```

The first command performs deterministic leave-one-scenario-out weight
selection over the 10 horizon-aligned v4 scenarios, requiring every one of the
four score factors to retain at least 0.05 weight. The second evaluates the
selected horizon-weighted ranker at `K = 1, 3`, compares it with the raw
expected-contribution baseline, and runs fixed sensitivity profiles. `K = 5`
is recorded as not applicable because the formal candidate sets contain only
three or four items; out-of-horizon candidates are never used as padding. The
final results, fold allocation, provenance, limitations, and baseline
comparison are recorded in
`docs/coursework/m4_horizon_prioritization_v4_results.md`. The earlier v3
experiment remains in `docs/coursework/m4_prioritization_experiment.md` for
reproducibility and is not the final coursework result.

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

Production-labelled ranking data, online outcome validation, production OCR
benchmarking, and broader production hardening remain outside the currently
integrated baseline.
