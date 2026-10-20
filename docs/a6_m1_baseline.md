# A6-M1 integration baseline

Validated on 2026-10-19 in the New Repo on branch `M1-yuzirui`, HEAD `286fb5d` (`Merge pull request #32 from LiiiKiii/M5`). The working tree already contained the agents-list and briefing integration edits when this A6 batch began. A6 changed the root `README.md` and added this report; it preserved those uncommitted edits. No Git history operation or Original Repo access was performed.

## Execution results

All backend commands used `.venv\Scripts\python.exe`. Test and migration subprocesses received `ADMIN_DATABASE_URL=sqlite+aiosqlite:///<temporary-directory>/admin.db` before importing the app. Pytest also received `TIKTOKEN_CACHE_DIR=<repo>/.venv/tiktoken_cache`. No production database or paid LLM provider was contacted.

| Check | Result | Evidence |
| --- | --- | --- |
| Python dev dependencies | **PASS** | Installed the repository's `pytest>=9,<10` and `pytest-asyncio>=1.3,<2` into `.venv`; installed `uvicorn` there to verify the documented ASGI command. |
| Full offline unittest discovery | **PASS** | `python -m unittest discover -s tests -p "test_*.py" -q`: 312 tests, 0 failures or errors. |
| Focused knowledge/PDF pytest | **PASS** | `python -m pytest tests/test_knowledge_retrieval.py tests/admin/test_knowledge_router.py tests/admin/services/pdf -q`: 34 passed. |
| Focused API/auth/planning pytest | **PASS** | `python -m pytest tests/test_api_endpoints.py tests/test_final_a4_integration.py tests/test_auth_dependencies.py tests/test_auth_router.py tests/test_planning_api.py tests/test_insurance_tools.py -q`: 36 passed, 10 subtests passed. |
| Full pytest discovery | **PASS** | `python -m pytest tests -q`: 346 passed, 69 subtests passed. This overlaps the focused runs. |
| Database migration | **PASS** | `python -m alembic upgrade head` against a fresh temporary SQLite database advanced revisions `0001` through `0004`; `alembic_version` contained `0004`. |
| App initialization | **PASS** | Entered `api.server.app`'s actual lifespan with a temporary SQLite database, then called `GET /api/health` through `httpx.ASGITransport`: HTTP 200, `{"status":"ok","agent_loop":"running"}`. `python -m uvicorn --version` ran successfully. A listening network server was not started. |
| Frontend dependency install, lint, typecheck, build | **BLOCKED** | `node`, `npm`, `pnpm`, and `corepack` are unavailable in this environment. `web/pnpm-lock.yaml` exists, but no lockfile install or compiled frontend check was possible. |
| Production database, real LLM, browser end to end | **NOT TESTED** | Excluded from this offline validation. |

The first focused pytest run had 29 passes and five PDF chunker failures because `tiktoken` attempted to download the public `cl100k_base` data through a blocked sandbox connection. The data was then cached in ignored `.venv/tiktoken_cache`, and both the focused and full pytest suites passed. This was an environment prerequisite, not an application-code fix.

## Interface and security review

| Area | Status | Finding |
| --- | --- | --- |
| Runtime and tools | **PASS for covered paths** | Runtime lifecycle, tool calling, provider retry, and WebSocket tests pass in the full suite. The app lifespan check exercised initialization and clean shutdown without a provider call. |
| Reasoning and pending data | **PASS for covered paths** | Existing gap-analysis, feasibility, run-rate, data-layer, and planning tests pass. Calculations and seed business rules were not changed in A6. |
| Attribution | **BLOCKED for full runtime parity** | `improvement_advice.py` lazily imports `nanobot.agent.tools.insurance.reasoning_layer.attribution_gap`, which is absent. Its tests inject a deterministic substitute, so passing planning tests do not prove the real attribution path. |
| Authentication and tenant isolation | **PASS for tested routes** | Real JWT/RBAC API tests reject anonymous agents-list access and scope active user IDs to the caller's tenant. Briefing tests reject anonymous and spoofed agent IDs, foreign message reads/writes, non-admin management access, and non-superadmin ingestion. Target and competition read tests isolate tenants, including a shared agent ID. |
| Knowledge and PDF | **PASS for covered paths** | File retrieval, FTS5 lookup, upload boundaries, tenant scoping, and PDF processing pass in the focused 34-test suite. |
| Briefing and planning | **PASS for mounted/covered paths** | The existing briefing router is included once from `api.server.create_app` under its declared `/api/briefing/...` paths with `require_briefing_access` at mount time. Planning and briefing API tests pass. No LLM-generated briefing was exercised. |
| Database | **PASS for fresh temporary SQLite** | Alembic reaches `0004`; app startup initializes current tables and the FTS5 index in a disposable database. Upgrade behavior against existing data was not tested. |
| Target Management frontend interface | **PASS by code inspection; runtime BLOCKED** | `web/src/app/admin/targets/page.tsx` calls `adminApi.agents.list()`. The client requests `/api/agents-list` through `apiFetch`, attaches the admin Bearer token, and retries after a 401 refresh. The API returns `{"ok":true,"data":[{"agent_id":"..."}]}` from active users in the authenticated tenant. No TypeScript build or browser check ran. |

OpenAPI inspection found `GET /api/agents-list` and 13 distinct briefing path templates under `/api/briefing`. Existing briefing handlers retain their own HTTP methods and response bodies; the mount adds authentication and access control. The frontend's agent-facing calls to `/api/performance`, `/api/targets`, and `/api/chat-sessions` have no corresponding mounted paths, while the admin management endpoints use separate `/api/admin/...` contracts. The current health response exposes `status` and `agent_loop`, not an Original `service` field. These are integration limits, not failures of the suites above.

## Release disposition

**Backend baseline: PASS with documented gaps. Frontend build validation: BLOCKED. Full Original parity: NOT ESTABLISHED.** Before claiming browser or end-to-end readiness, run `pnpm install --frozen-lockfile` and `pnpm check` from `web/` on a machine with Node.js 20+ and pnpm 9, then resolve any reported errors. The missing attribution module, persistent chat-session API, and agent-facing business routes need their designated owners' contracts and integration work. The current A6 batch made no changes to those components.

Recommended commit message for the complete working tree after review: `fix(m1): restore agent list and briefing integration`. No commit or push was performed.
