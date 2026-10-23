# A6-M1 integration baseline

> The 2026-10-19 baseline and first 2026-10-22 addendum below are historical. The final incident addendum at the end reflects merged M2/M4 HEAD `8af1813` and supersedes the earlier scripted recommendation-flow status.

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

## 2026-10-22 final-evaluation addendum

The checkout was clean at `b3f608a` before this M1 batch. The five requirements were checked against this HEAD with isolated SQLite fixtures and a scripted provider. The Original Repo, shared database, and paid providers were not used.

| Requirement | Status | Result |
| --- | --- | --- |
| 1. Evaluation scenario | **PASS** | `tests/test_m1_evaluation_scenario.py` creates and reads consistent business rows, then calls the existing `compute_gap_analysis`. Values and limits are below. |
| 2. Candidate filtering | **BLOCKED for authoritative eligibility** | The M4 filter passes its focused tests for supplied flags, but neither HTTP nor Agent tools derive permission/compliance flags from trusted candidate records. Upstream provenance needs M2/M4 integration. |
| 3. Relevance labels | **PASS for proposed rubric; BLOCKED for adoption** | The existing synthetic fixture contains grades 0–3 and evaluation code consumes them; M4 has not fixed a general labeling rule or adjudication method. |
| 4. Chat-to-Agent | **PASS for scripted offline flow; real model NOT TESTED** | A JWT-authenticated `/ws/chat` request reached the real `AgentLoop`; the scripted provider selected `prioritize_followups`, the registered tool returned a filtered ranking, and the second scripted provider response became the final answer. This is not autonomous model selection. |
| 5. Tool list and audit | **PASS for registered tools and tested audit path** | The 13 tools listed below are in `RuntimeState.tool_registry`. The tested tool call now persists name, call ID, dispatch outcome, session/turn IDs, and the final response. It stores no tool arguments or result payload in tool-call audit fields. |

### Scenario and authoritative field sources

The isolated scenario fixes the clock at 2026-10-22. `admin.models.competition.Competition` has `COMP-1` with target `HKD 170,000` and deadline `2026-12-31`; `CompetitionEntry` for `AGT001` has current `HKD 100,000` and stored nominal gap `HKD 70,000`. `AgentPerformanceMetrics` for the same agent and period has current `HKD 100,000`, target `HKD 170,000`, and pending premium `HKD 14,000`. `data_layer._db.load_competitions_from_db` reads the active entry and derives displayed target as `current_value + gap` when both exist (here `100,000 + 70,000 = 170,000`), otherwise it uses `Competition.target_value`; it does not recompute the stored gap. It calculates `70` days to the deadline. `_db.load_performance_row` selects the latest `period_end` row for the agent. The authenticated WebSocket uses `User.username` as the allowed `agent_id` and rejects another agent ID.

`reasoning_layer.gap_analysis.compute_gap_analysis` allocates the shared pending pool to positive HKD/USD competition gaps in earliest-deadline order. In this one-competition fixture, `70,000 - min(70,000, 14,000) = HKD 56,000` is returned as `actual_gap` with `pending_deduction=14,000`. This is the implemented open-gap calculation, not independent underwriting verification of the pending amount or validation that a stored entry gap equals target minus current. Non-monetary gaps receive no pending deduction. The M4 synthetic ranking fixture is separate: it supplies `AGT001`, USD `open_gap=100,000`, deadline `2026-12-31`, and candidate records; it supplies no target or current performance source.

### Filtering and relevance evidence

`planning_layer.prioritization._exclusion_reason` checks candidate object, nonblank/unique ID, `eligible`, `permission_allowed`, `compliance_allowed`, nonnegative finite expected contribution, urgency/actionability in `[0,1]`, and business fit in `[0,1]` (default `0.5`), in that order. A zero objective gap excludes all candidates first. `prioritize_followups` then normalizes weights, scores eligible records, sorts by score, urgency, contribution, and ID, and takes `top_k`. The current default for each of the three permission/eligibility flags is `True`. `POST /api/planning/prioritization` and `/ws/chat` bind the top-level agent ID to the authenticated username, but supplied candidate flags and evidence are not independently checked against tenant-owned M2 records. `excluded_candidates` returns excluded IDs and reasons; they do not enter `recommendations`, yet an untrusted supplied ID can appear in that exclusion list and the provider-visible tool result.

The existing `data/evaluation/prioritization_synthetic.json` already assigns `POL-B=3`, `POL-C=3`, `POL-D=2`, `POL-A=1`, and `POL-E=0`; `POL-X` is a hard compliance exclusion and has no relevance grade. Proposed wording: **3** follow up first (B/C), **2** worthwhile after highest priorities (D), **1** low priority (A), **0** do not recommend (E). These are reproducible fixture examples, not an approved general rule or score thresholds. Hard permission, compliance, and eligibility exclusions must be applied before graded evaluation. The current scorer still returns grade-0 `POL-E` as a recommendation because labels are evaluation data, not scorer inputs; M4 must confirm whether grade 0 remains a soft judgment or becomes a hard exclusion. With this fixture, ranking is B/C/D/A/E, `POL-X` is excluded, and Precision@3/NDCG@3 are `1.0/1.0` versus the expected-contribution baseline's `0.666667/0.319818`.

### Agent tools and persistent evidence

`api.state.RuntimeState` uses `reasoning_layer.composition.build_reasoning_registry`; `ToolRegistry.get_definitions` exposes the following names and schemas to the provider. Registration is verified at runtime, including `prioritize_followups`.

| Tool | Implementation |
| --- | --- |
| `get_performance_snapshot` | `insurance/data_layer/performance.py` |
| `get_competition_status` | `insurance/data_layer/competition.py` |
| `get_pending_policies` | `insurance/data_layer/pending.py` |
| `get_attribution_analysis` | `insurance/data_layer/attribution.py` |
| `calculate_run_rate`, `assess_gap_feasibility` | `insurance/reasoning_layer/tools.py` |
| `search_competition_rules` | `insurance/knowledge_layer/competition_rules.py` |
| `search_best_practice` | `insurance/knowledge_layer/best_practice.py` |
| `search_sales_scripts` | `insurance/knowledge_layer/sales_scripts.py` |
| `search_knowledge_base` | `insurance/knowledge_layer/search_kb.py` |
| `generate_chase_plan` | `insurance/planning_layer/chase_plan.py` |
| `generate_improvement_advice` | `insurance/planning_layer/improvement_advice.py` |
| `prioritize_followups` | `insurance/planning_layer/prioritization.py` |

All 13 tools are registered and advertised to the provider. Data-layer and database-backed knowledge tools require relevant stored records; file-backed knowledge tools require their local corpus; planning tools require their declared inputs. Registration alone does not establish that every tool can complete in a particular deployment.

The scripted WebSocket test used a real authenticated user in an isolated database. Provider call 1 offered the tool schema and returned call ID `priority-call-1`; the actual tool result ranked B/C/D/A/E and excluded `POL-X` (`compliance_excluded`) and `POL-P` (`permission_denied`). Provider call 2 received the paired tool result and returned the final answer. `AgentLoop` now emits per-turn `tool_events`; `api.ws.chat` persists `AiAuditLog.tools_called=["prioritize_followups"]`, `FlowLog` steps `user_input`, `llm_call`, `tool_call`, `response`, and `ChatMessage.metadata_json` with the tool event. The tool flow metadata contains call ID, status `completed`, and `turn:evaluation`; the audit rows share the generated `ws:` session ID, with user/tenant attribution on `AiAuditLog`. A separate test verifies a model-supplied foreign `agent_id` is denied before tool execution. `completed` means the tool returned through `ToolRegistry`, not that every business assertion inside a returned JSON payload passed. Runtime logger messages alone are not persistent audit records; no token-usage record is produced by this path.

### Focused tests and handoff

The focused command (repository root, with `ADMIN_DATABASE_URL` set to a temporary SQLite path before imports) was `python -m unittest tests.test_m1_evaluation_scenario tests.test_gap_analysis tests.test_data_layer_tools tests.test_websocket_auth_audit tests.test_websocket_chat tests.test_reasoning_tool_calling tests.test_agent_tool_calling tests.test_tool_registry tests.test_prioritization tests.test_prioritization_evaluation tests.test_planning_api -q`: **78 tests, PASS**. The first draft integration assertion selected the wrong history slice; it was corrected to select the assistant tool-call and tool-result records by role. Existing mock WebSocket tests now patch chat-history persistence so they do not touch an uninitialised database.

M2 must provide tenant/owner-scoped candidate preparation and evidence for expected contribution and permission decisions. M4 must confirm hard eligibility/compliance semantics, label-0 treatment, a general 0–3 annotation rubric, and whether exclusion IDs belong in model-visible output. M5 must confirm the UI's use of `/api/chat-sessions` and structured recommendations. A real model-driven selection and production-data evaluation remain **NOT TESTED**.

## 2026-10-22 M5 live E2E incident and merged M2/M4 integration

M5 observed live model calls to `prioritize_followups` with `missing_candidate_id`, `invalid_expected_contribution`, and `invalid_urgency`, followed by tool-call budget exhaustion. This is a reported live **FAIL**; no paid provider was called in this batch, so a repaired live E2E is **NOT TESTED**. The earlier scripted WebSocket success above demonstrated plumbing with hand-built valid arguments and does not establish autonomous model success. The security boundary is now fail closed, and that earlier test has been replaced with a denial-and-audit test.

| Area | Current status | Evidence |
| --- | --- | --- |
| M2 candidate preparation | **PASS for offline coursework; BLOCKED for runtime** | `scripts/build_m2_candidate_dataset.py` deterministically produces ten scenarios, 100 synthetic raw records, and 60 eligible records from `data/mock`. `tests/test_m2_candidate_dataset.py` checks the lineage and M4 compatibility. The generator is not a tenant-aware runtime service or an authorized customer source. |
| M4 ranking | **PASS for supplied valid fixture; BLOCKED for model-facing schema** | The M2 scenario passes `ToolRegistry` execution with five recommendations. The ranker remains unchanged. |
| Agent candidate authorization | **BLOCKED** | `AgentPolicy`, `AgentClient`, and `AgentPerformanceMetrics` are keyed by `agent_id` without a tenant key; the current runtime has no joined tenant/owner candidate lookup or authoritative candidate-level permission/compliance decision. Binding the WebSocket agent ID to JWT username alone cannot prove row ownership across tenants. |
| WebSocket recommendation cards | **BLOCKED pending trusted result and M5 agreement** | The server sends `type=response` with `content`, `session_id`, and `turn_id`. M5 has an `action_plan` `ChatResult` card type, but `useWebSocket.ts` does not read a response `result` field. No structured recommendation is emitted from an unverified model payload. Ordinary text responses retain their existing shape. |
| M1 safety and audit | **PASS for tested paths** | `AgentLoop` omits `prioritize_followups` from all model-visible tool lists and rejects a call even if the provider emits it. It does not replay model-supplied candidate arguments or request another provider completion. WebSocket audit persists the attempted tool name, call ID, and `candidate_source_unavailable` status without candidate IDs. |

### Tool schema diagnosis and M4 patch request

`RuntimeState` registers `PrioritizeFollowupsTool` through `build_reasoning_registry`, and `ToolRegistry.get_definitions()` exposes `tool.parameters`. The current provider schema requires top-level `agent_id`, `objective.open_gap`, and `candidates`, yet declares each candidate only as `{"type":"object"}`. The generic `Tool.cast_params`/`validate_params` therefore accepts an object missing its ID or containing numeric strings in score fields. `_exclusion_reason` then requires a nonblank string `candidate_id`, finite nonnegative numeric `expected_contribution`, and numeric `urgency` and `actionability` in `[0,1]`. A local probe got generic validator `[]` and ranker exclusions `missing_candidate_id`, `invalid_expected_contribution`, `invalid_urgency` for those exact cases. These item exclusions are returned inside a completed tool result, so the earlier `completed` audit status did not prove useful recommendations.

The exact minimal M4-owned schema patch is to replace `candidates.items={"type":"object"}` with an object declaring `candidate_id: string (minLength 1)`, `expected_contribution: number (minimum 0)`, `urgency: number (minimum 0, maximum 1)`, and `actionability: number (minimum 0, maximum 1)`, with all four required. Declare optional `business_fit: number (0..1)` and `eligible`, `permission_allowed`, `compliance_allowed` as booleans. Keep the existing top-level objective and candidate array. M4 should align any further nested constraints/weights schema with its runtime rules and decide whether the three access flags may default to true for trusted callers. Schema repair helps model formatting; it cannot establish ownership or authorize candidate records, and M1 will not re-advertise this tool to a model until that source exists.

The checked-in M2 five-result scenario serializes to 4,223–4,289 characters, above the former `ToolRegistry` 4,000-character output limit. M1 raised the default to 5,000 for these existing fixtures. Results above the configured limit now return a safe `result_too_large` status/message instead of truncated invalid JSON. This is an output-size boundary change; the tool-call iteration budget and M4 score/validation rules are unchanged.

### Trusted source and gap semantics

Existing pending-policy retrieval returns policy IDs, premiums, status, submission date, and approval-day estimates for an agent. M2's coursework generator derives eligibility from pending positive-premium status or explicit client follow-up/renewal tags; expected contribution from policy premium × conversion rate or client premium × retention rate; urgency/actionability from due dates, status, and tags; and compliance from the training gate. These are reproducible **coursework rules on synthetic records**, not a production authorization contract. A runtime adapter needs an authenticated tenant and agent ownership join, trusted records and applicable eligibility/compliance decisions, conversion/retention units and missing-value rules, stable currency, and a documented candidate evidence/ID redaction policy. It must filter unauthorized rows before calling M4 or sending any result to a provider. Current code does not provide that adapter; M1 did not invent it.

For terminology pending M2/M4 agreement: the **verified gap** should use an authorized target and observed current performance (`max(target-current,0)`) without counting pending policies as achieved. A **projected gap** may subtract a documented, eligible pending contribution from that verified gap. M2's synthetic `objective.open_gap` is target minus current in USD and does not subtract pending. The A2 `compute_gap_analysis` function deducts full stored pending premium from a monetary nominal competition gap and calls the result `actual_gap`; this is a planning estimate, not proof of issued business. M2's contribution estimate uses conversion/retention rates, so the two deductions must not be mixed or double counted. The earlier M1 HKD scenario and the current M2/M4 USD fixtures also need an explicit currency match before integration.

### Proposed M5 response extension

After a trusted adapter and successful validated M4 tool output exist, retain the current WebSocket response fields and add an optional `result` matching M5's existing `ChatResult` union: `{"kind":"action_plan","title":"Follow-up priorities","actions":[{"priority":"P0","action":"<tool recommended_action>"}]}`. Map only `priority_level` and `recommended_action` from completed, parsed, server-validated M4 recommendations; never parse a model-written final answer for cards. Omit `result` on ordinary chat, errors, or blocked calls. M5 must add `result?: ChatResult` to `InboundWsEvent` and copy it onto the assistant `ChatMessage`; its current hook drops such a field. Title/summary wording and any richer candidate-card fields need M5 agreement. No new WebSocket event type is proposed or emitted now.

### Current validation and release decision

Focused command (repository root, with `ADMIN_DATABASE_URL` set to temporary SQLite before imports and `TIKTOKEN_CACHE_DIR` set locally): `python -m unittest tests.test_m1_prioritization_contract tests.test_m2_candidate_dataset tests.test_m1_evaluation_scenario tests.test_gap_analysis tests.test_data_layer_tools tests.test_websocket_auth_audit tests.test_websocket_chat tests.test_reasoning_tool_calling tests.test_agent_tool_calling tests.test_tool_registry tests.test_prioritization tests.test_prioritization_evaluation tests.test_planning_api -q`: **89 tests PASS**. Full `python -m unittest discover -s tests -p "test_*.py" -q`: **345 tests PASS**. The local schema probe output is recorded above; no live provider or production database was used.

**M1 safety change: reviewable for commit; final recommendation-flow baseline acceptance: BLOCKED.** The fail-closed guard and ordinary chat path pass offline, but M2/M4 must supply an authorized runtime candidate contract and M4 must repair the nested schema. M5 must agree on and consume the optional structured result. A scripted provider cannot close the live E2E failure; repeat the live test only after these dependencies land.

## 2026-10-22 coursework recommendation integration (supersedes the preceding runtime status)

Baseline: `M1-yuzirui` at `ea570ab`. The earlier M1 changes above were present but uncommitted when this integration began. M2 v3 and the M4 schema repair are now in this checkout. The `data/evaluation/m2_candidate_annotations_v3.json` human annotation file was not changed. No Git history operation, shared database, Original Repo access, or paid provider call was used.

| Area | Status | Verified result |
| --- | --- | --- |
| M2 v3 source | **PASS for coursework fixtures** | `m2-coursework-candidates-v3` contains 10 scenarios, 100 source-linked synthetic candidates, 60 passing all three gates, snapshot date `2026-05-31`, and USD objectives. The adapter reads this versioned file and `data/mock/policies.json` and `clients.json` without regenerating scores. |
| M4 contract | **PASS for fixture calls** | The registered `prioritize_followups` schema now declares required nested candidate ID, expected contribution, urgency, and actionability, plus optional business fit and Boolean gates. The unchanged M4 ranker executes the server-prepared payload and returns deterministic recommendations. |
| Authenticated scripted Chat-to-Agent | **PASS** | A real JWT-authenticated WebSocket turn offers a no-argument `prioritize_followups` facade to a scripted provider. Server code prepares the candidate payload, dispatches to the registered M4 tool, validates its output, and the second scripted completion supplies natural-language answer text. |
| Tenant, agent, and data isolation | **PASS for tested demo path** | Current gate: the JWT user must be active in the enabled seeded `default` Tenant with the expected ID and `agent_manager` role; both `M1_COURSEWORK_DEMO_TENANT_ID` and `M1_COURSEWORK_DEMO_AGENT_ID` must match. WebSocket `agent_id` must equal the authenticated username; a unique M2 scenario must match that agent. Candidate scenario, owner, synthetic tenant provenance label, currency, ID, mock source record, origin markers, and gate decision evidence are checked. Any mismatch hides the facade. Forged model arguments are denied. |
| Structured response | **PASS for backend scripted path; browser NOT TESTED** | A validated completed tool call adds an optional `result` to the existing `type=response` WebSocket frame. Ordinary chat and denied calls have no result. M5's current `useWebSocket.ts` validates and copies inbound `result` into the assistant message. Browser rendering has not been tested in this M1 batch. |
| Audit | **PASS for isolated scripted path** | Tool name, call ID, status, session/turn correlation, user and tenant attribution, FlowLog steps, and final answer persist in the test database. Tool arguments and candidate lists are not put into tool-call audit fields. |
| Autonomous live provider | **NOT TESTED** | A scripted provider proves dispatch and validation, not that a real model will select the facade or write a useful final answer. The earlier live malformed-argument incident remains historical **FAIL** until repeated successfully. |
| Production candidate lookup | **BLOCKED** | This explicit synthetic coursework adapter is not a live tenant-owned customer lookup. Production requires an authoritative tenant/agent/candidate ownership and compliance contract from M2/M4. |

### M1 adapter and security boundary

`nanobot.agent.coursework_demo.CourseworkCandidateSource.prepare` runs only when `api.ws._coursework_demo_scope` maps the authenticated JWT principal to the explicitly configured demo Tenant. It requires the scenario `SCN-<username>` and validates the stored USD objective (`open_gap = max(target - current, 0)`) without changing M2 values. It checks every candidate against its mock source record and decision evidence, including rows that will be excluded. It removes all rows failing eligibility, permission, or compliance before calling M4. Thus M4 sees only authorized fixture rows and its `excluded_candidates` must be empty; excluded IDs never enter the provider-visible tool result or card. If config, scope, source, or provenance fails, the model never sees this tool. This path is limited to `channel=websocket` and does not change other Agent tools or M4's scoring rules. The May 31 snapshot must be presented as historical coursework data, not live customer state.

For a supported turn, `AgentLoop` replaces only the model-facing schema for `prioritize_followups` with `{"type":"object","properties":{},"additionalProperties":false}`. The model sends `{}` and cannot supply an agent, scenario, candidate, flag, score, or currency. M1 dispatches the prepared server payload through `ToolRegistry.execute_with_status`; it does not raise the four-iteration tool budget. Calls with any model arguments are rejected before dispatch. A completed ranker's agent/objective/counts, authorized IDs, order, actions, evidence, and score bounds are checked before the card is constructed. Other tool schemas and agent binding remain as before. The 5,000-character registry output boundary and safe `result_too_large` response from the prior M1 batch remain in force.

### WebSocket result and M5 handoff

The backend sends the normal `type=response`, `content`, `session_id`, and `turn_id` fields. On validated recommendations it also sends:

```json
{
  "result": {
    "kind": "action_plan",
    "title": "Coursework follow-up priorities",
    "source": "m2-coursework-candidates-v3",
    "scenario_id": "SCN-AGT00690",
    "as_of_date": "2026-05-31",
    "tool_call_id": "priority-call-1",
    "actions": [{
      "rank": 1, "candidate_id": "<authorized candidate ID>", "priority": "P0",
      "action": "<M4 recommended_action>", "timing": "<M4 recommended_timing>",
      "evidence": {}, "priority_score": 0, "score_components": {}
    }]
  }
}
```

The placeholders show the field contract; actual actions and scores come from the checked-in M2 source and M4 result. `tool_call_id` must match a completed `prioritize_followups` event from this turn. M5 now accepts and validates inbound `result` and copies it into the assistant `ChatMessage`. A live demo must still show the dated source and verify text and card display in the UI.

### Verification and remaining acceptance

Focused coursework, contract, authenticated WebSocket, Agent, ordinary chat, and M2 source tests: `python -m unittest tests.test_coursework_demo tests.test_m1_prioritization_contract tests.test_websocket_auth_audit tests.test_agent_tool_calling tests.test_websocket_chat tests.test_m2_candidate_dataset -q` — **53 PASS**. These include cross-tenant, wrong Tenant slug, wrong agent/scenario, malformed record, forged tool arguments, excluded-ID secrecy, ordinary chat, and audit checks. Full offline `python -m unittest discover -s tests -p "test_*.py" -q`, with a disposable SQLite `ADMIN_DATABASE_URL` and local tiktoken cache: **365 PASS** after correcting one stale M2 test assumption. The first run failed only because `test_annotation_tool_updates_only_selected_human_slot` expected the other annotator's ranking to be empty, while the committed human file now has a ranking. The test now compares the other slot before and after the edit; the annotation data was not changed. `git diff --check` passes. The tests use scripted responses and local files only.

**M1 coursework integration: reviewable for commit/PR after the final offline suite. Full browser/live acceptance: NOT TESTED.** To run M5's live E2E, use the isolated demo setup documented in README, set both M1 demo opt-in variables to the printed IDs, and authenticate the matching seeded scenario agent. Use `/ws/chat` with the JWT and matching `agent_id`; request follow-up prioritization, then inspect the `type=response` text, `result` card, source date, `tool_call_id`, FlowLog, and AiAuditLog. Run against the isolated demo database with an explicitly approved provider. A production candidate path remains separate and blocked on authoritative M2/M4 ownership/compliance contracts.

## 2026-10-23 M1 currency and demo-setup correction

This section records the 2026-10-23 state before the default-tenant correction below. It superseded older A6 claims that every registered tool was offered to every Agent turn or that M5 dropped the WebSocket card. M5's current hook validates and copies the optional `action_plan` result. Browser rendering and autonomous live-model selection remain **NOT TESTED**; the coursework adapter is not a production customer retrieval service.

`compute_gap_analysis` previously used HKD when a competition omitted `unit` and applied one untyped pending-premium pool to both HKD and USD gaps. The stored `AgentPerformanceMetrics.pending_premium_current` and M2 coursework source are USD. The function now requires each competition unit, assumes USD for that stored pending input, and deducts only from matching USD gaps. A caller with genuinely HKD pending premium must pass `pending_unit="HKD"`; this preserves explicit HKD calculations without converting currencies. Unknown three-letter currency codes and missing units fail clearly. Existing nonmonetary units such as `policies`, `%`, and `sessions` receive no premium deduction. `compute_feasibility` now defaults to USD, matching its Agent tool schema, and accepts only USD, HKD, or `policies`; explicit HKD and policy-count branches keep their existing formulas. The M4 chase-plan implementation and its ranking weights were not changed.

The `nominal_gap` is the stored competition gap. The field named `actual_gap` remains `nominal_gap` minus the same-currency **full pending premium** and is a planning estimate, not a verified open gap or issued business. A verified open gap would require an agreed target/current source and should not count pending policies as achieved. This batch does not invent approval rates, alter M2 contribution estimates, or redesign the gap formula; M2/M4 must agree on any future verified/projected gap contract.

At this historical stage, `python -m scripts.setup_m1_coursework_demo --agent-id AGT00690` created a separate `coursework-demo` tenant and login. The workflow was replaced by the default-tenant validation described below. Earlier smoke results in this section apply to that superseded implementation.

Focused command (temporary SQLite `ADMIN_DATABASE_URL`, local tiktoken cache): `python -m unittest tests.test_gap_analysis tests.test_feasibility tests.test_chase_plan tests.test_m1_evaluation_scenario tests.test_reasoning_tools tests.test_m1_coursework_setup tests.test_coursework_demo tests.test_agent_tool_calling tests.test_tool_registry tests.test_websocket_auth_audit tests.test_websocket_chat -q` — **121 PASS**. Full offline `python -m unittest discover -s tests -p "test_*.py" -q` under the same isolation — **385 PASS**. A final direct gap-analysis check after tightening malformed currency spelling — **20 PASS**. `git diff --check` passes. No paid provider or browser E2E was run. The old sections above remain as dated evidence of earlier integration stages.

## 2026-10-23 M1 default-tenant coursework integration

The current M1 gate uses the seeded `default` tenant, ID `00000000-0000-0000-0000-000000000001`. M2's `coursework-demo` candidate tenant marker remains checked as synthetic source provenance; it does not identify a database tenant. A JWT must resolve to an active, non-superadmin user in the enabled default tenant with exactly the seeded `agent_manager` role. Both `M1_COURSEWORK_DEMO_TENANT_ID` and `M1_COURSEWORK_DEMO_AGENT_ID` must explicitly match the tenant and that one JWT username. WebSocket `agent_id` must match the JWT username. The server chooses `SCN-<username>` and verifies M2 source records, currency, ownership, eligibility, permission, and compliance before M4 sees candidates. Other users in the same default tenant cannot receive the coursework facade. This is synthetic coursework behavior, not production candidate authorization.

The dedicated `data/demo/m1_coursework.db` setup order is: configure the isolated URL and seed secrets, migrate with `python -m alembic upgrade head`, run `python -m admin.seeds`, validate with `python -m scripts.setup_m1_coursework_demo --agent-id AGT00690`, configure both printed M1 opt-in values, then start the backend. The M1 command refuses another database URL or missing/outdated migration and only reads existing seed data. It rejects missing, disabled, ambiguous, foreign-tenant, or privileged accounts and never changes passwords or roles. See README for PowerShell commands.

Isolated SQLite smoke: migrations reached `0007`; `admin.seeds` created one default tenant and 50 agent logins; the M1 validator passed twice for `AGT00690`; M3 built-in knowledge sync found that tenant and indexed 16 local Markdown files into three knowledge bases with 39 chunks. SQLite indexing did not call an embedding provider. Focused M1 setup, adapter, and WebSocket command: **33 PASS**. Full offline backend `python -m unittest discover -s tests -p 'test_*.py' -q` with a disposable SQLite URL and local tiktoken cache: **390 PASS**. A chat-session fixture now has fixed message timestamps because its default timestamps could tie and random UUID ordering reversed the expected roles in two full runs. Browser rendering and live-provider selection: **NOT TESTED**. The isolated smoke database was removed after validation.
