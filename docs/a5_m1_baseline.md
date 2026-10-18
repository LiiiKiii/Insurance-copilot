# A5-M1 test baseline

Tested on 2026-10-19 in the New Repo, branch `M1-yuzirui` at `ed1128a`. The working tree was clean before this batch. The Original Repo was not accessed; its supplied **A5-M1 Original Test Contract Report** was the only Original reference. No test was copied directly from Original source.

## Environment and execution

- Windows, Python 3.12.10 from `.venv\Scripts\python.exe`. `pyproject.toml` requires Python >=3.11 and does not configure pytest; pytest is not installed in this virtual environment. The New Repo uses `unittest` discovery.
- All tests in this batch ran offline. New API tests use an `httpx` ASGI transport, real JWT validation, and a temporary SQLite database through `get_db` override. They do not enter application lifespan or use the workspace admin database. Provider tests use a scripted provider and mocked retry sleeps.

| Suite | Exact command (from repository root) | Passed | Failed | Skipped |
|---|---|---:|---:|---:|
| Initial full baseline | `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | 281 | 0 | 0 |
| API | `.venv\Scripts\python.exe -m unittest tests/test_api_endpoints.py tests/test_api_server.py tests/test_planning_api.py -q` | 15 | 0 | 0 |
| Reasoning | `.venv\Scripts\python.exe -m unittest tests/test_gap_analysis.py tests/test_feasibility.py tests/test_run_rate.py tests/test_reasoning_tools.py tests/test_reasoning_tool_calling.py -q` | 61 | 0 | 0 |
| Skill/tool available subset | `.venv\Scripts\python.exe -m unittest tests/test_tool_registry.py -q` | 9 | 0 | 0 |
| Session/agent available subset | `.venv\Scripts\python.exe -m unittest tests/test_agent_tool_calling.py tests/test_provider_retry.py -q` | 8 | 0 | 0 |
| Security integration | `.venv\Scripts\python.exe -m unittest tests/test_auth_dependencies.py tests/test_auth_router.py tests/test_websocket_auth_audit.py tests/test_final_a4_integration.py -q` | 25 | 0 | 0 |
| Final full regression | `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q` | 292 | 0 | 0 |

The grouped suites overlap the full regression; their counts must not be added. Other existing full-suite tests cover admin configuration, audit, encryption, WebSocket, compliance, runtime Apply, and planning. No test was skipped or marked xfail. All planned tests for modules that do not exist were **not run**, rather than counted as passed or skipped.

During development, one draft tool test failed because its assertion expected a shortened enum error string; the validator returned the full permitted-value list. This was a **test adaptation issue**, corrected without changing production code or relaxing the enum check. An initial grouped-suite invocation from `tests/` could not find the relative `.venv` executable; rerunning from the repository root succeeded. Neither was a final regression failure.

## Added coverage and reused tests

- `tests/test_api_endpoints.py` is newly authored for the New Repo. It verifies `/api/health`, target request validation and read-only role rejection, real JWT authentication, and target/competition isolation between two tenants, including a shared agent ID. Original report references: `tests/test_api_endpoints.py:39-306` and `api/routers/business.py:33-614`. The New Repo's admin routes are different contracts, so this is an adaptation, not a direct port.
- `tests/test_tool_registry.py` extends existing New Repo coverage for nested arrays/objects, required fields, enums, ranges, string length, nullable values, safe casting, undeclared fields, and boolean rejection as a number. Original report reference: `tests/test_tool_validation.py:44-403`.
- `tests/test_provider_retry.py` is newly authored for transient retry backoff, non-transient errors, cancellation, and generation settings. Original report reference: `tests/test_provider_retry.py:27-216`.
- Reused unchanged: `test_gap_analysis.py`, `test_feasibility.py`, `test_run_rate.py`, `test_reasoning_tools.py`, `test_reasoning_tool_calling.py`, `test_agent_tool_calling.py`, `test_compliance.py`, `test_auth_dependencies.py`, `test_auth_router.py`, `test_websocket_auth_audit.py`, and `test_final_a4_integration.py`. They cover the implemented reasoning rules, tool-call continuation and pairing, compliance, JWT/RBAC, and WebSocket tenant checks. No M1 implementation defect required a production code fix in this batch.

## Original-to-New differences and deferred dependencies

| Original report contract | New Repo finding / impact |
|---|---|
| `GET /api/health` returns `status` and `service` | New endpoint returns `status` and `agent_loop`; the changed response is asserted as implemented. Clients expecting `service` need migration work. |
| `GET /api/performance`, `/api/competitions`, `/api/agent-info`, `/api/dashboard`, `/api/proactive-alerts`, `/api/all-competitions`, `/api/targets` | These Original business routes are not mounted. `/api/admin/targets/` and `/api/admin/competitions/` are authenticated tenant-scoped administration routes, not replacements for the Original agent-facing read contracts. Exact business API parity remains deferred. |
| `compute_gap_analysis`, `compute_feasibility`, `compute_run_rate` | Implemented and covered; New `compute_run_rate` accepts an `as_of_date` for deterministic testing and rejects nonpositive targets. |
| `compute_attribution_gap`, `enrich_competitions`, `SkillRegistry` | No corresponding module is present. Their Original behavior was not tested here or treated as implemented. `improvement_advice.py` still has a lazy import of `attribution_gap`, so that path needs integration attention. |
| `SessionManager`, session history/JSONL, HTTP `/api/chat-sessions` | Not present. AgentLoop's current `process_direct()` explicitly reserves and ignores `session_key`; persistent conversation and ownership contracts remain deferred. Existing tool-call message pairing is covered in memory only. |
| MessageTool suppression and the Original agent runtime | The New Repo's A1 AgentLoop has no MessageTool or persistent conversation path. It does have bounded tool-call continuation, covered by existing tests. |
| Original ToolRegistry error strings | New Repo returns generic errors to avoid leaking parameter and exception details; nested validation is now tested without weakening this security behavior. |
| Data/team tests using `data/db/admin.db` and fixed agent IDs | No portable M2 seed fixture or agent-facing data API contract was established in this batch. These tests were not run against the workspace database. |

Original source files were unavailable, so report descriptions could not be migrated line-for-line or used to prove full Original parity. Future A5/A6 work needs the agent-facing business routes, attribution/enrichment and SkillRegistry modules, a portable data/team fixture, and session persistence with owner/tenant authorization. The most immediate integration risk is code that calls the missing attribution module; the health response and agent-facing route differences also affect clients expecting the Original shape.

Commit readiness: **READY WITH DOCUMENTED LIMITATIONS** for the implemented New Repo baseline. This is not a claim of full Original parity.
