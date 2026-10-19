# A5-M5 frontend baseline

Tested on 2026-10-19 in the New Repo, branch `M5` on top of main `48de515`. Scope: static checks of `web/` and an end-to-end smoke test of the frontend against the backend. The Original Repo has no frontend automated tests and its CI (`.github/workflows/ci.yml`) runs Python tests only, so there was no frontend test suite to migrate.

## Environment

- Windows 11, Node.js 20.20.2, pnpm 9.15.9
- Next.js 16.1.7, React 19.2.3, TypeScript 5.9.3, ESLint 9.39.4, Tailwind CSS 4.2.2
- Backend: Python 3.12, `uvicorn api.server:app --port 8000`, SQLite database seeded with `python -m admin.seeds`. Local secrets live in the untracked `.env`.

## Static checks

`web/package.json` gains two scripts: `typecheck` (`tsc --noEmit`) and `check`, which runs lint, build and typecheck in that order. Build runs before typecheck so that the route types under `.next/types` are generated first.

| Check | Command (from `web/`) | Result |
|---|---|---|
| Install | `pnpm install --frozen-lockfile` | Pass |
| Lint | `pnpm lint` | Pass: 0 errors, 6 warnings |
| Build | `pnpm build` | Pass: 14 routes, all prerendered as static |
| Type check | `pnpm typecheck` | Pass: 0 errors |
| All | `pnpm check` | Pass, about 56 s from a clean `.next` |

A stale `.next/` directory from an earlier `pnpm dev` can make `typecheck` report errors in `.next/types/validator.ts`. Deleting `.next` and rerunning resolves it; it is not a source error.

### Lint warnings kept as-is

All six warnings come from code migrated unchanged from the Original Repo. They are documented rather than fixed, following the stage A rule of minimal code changes.

| File | Line | Rule | Note |
|---|---|---|---|
| `components/ChatInterface.tsx` | 152 | `react-hooks/exhaustive-deps` | `refreshBriefingSummary` missing from deps |
| `components/ChatInterface.tsx` | 449 | `@typescript-eslint/no-unused-expressions` | short-circuit expression used as a statement |
| `components/ChatInterface.tsx` | 559 | `@typescript-eslint/no-unused-expressions` | same pattern |
| `components/DailyBriefingModal.tsx` | 12 | `@typescript-eslint/no-unused-vars` | unused type import `BriefingActionItem` |
| `components/DailyBriefingModal.tsx` | 130 | `@typescript-eslint/no-unused-vars` | unused function `jumpToMessage` |
| `components/chat/UploadPill.tsx` | 69 | `react-hooks/exhaustive-deps` | `state` missing from deps |

## Defects found and fixed in this round

The smoke test found three integration defects between the migrated frontend and the A4 backend. Each is fixed in its own commit.

| Commit | Defect | Fix |
|---|---|---|
| `fix: send websocket auth handshake` | The A4 backend requires `{"type": "auth", "token": ...}` as the first WebSocket frame and replies `auth_ok`. The migrated client sent nothing, so after login the socket was closed and the chat stayed Offline. | `lib/useWebSocket.ts` skips connecting without a token, sends the auth frame on open and reports `connected` only after `auth_ok`. |
| `fix: preserve trailing slashes in API proxy` | Admin list and create calls such as `/api/admin/users/` were redirected by Next.js to the slash-less path; FastAPI then redirected back with an absolute URL on port 8000, which the browser blocked as cross-origin. Admin lists did not load and saves spun forever. | `next.config.ts` sets `skipTrailingSlashRedirect` and adds a rewrite that keeps the trailing slash. |
| `fix: send only accepted fields when saving users` | The users API forbids unknown fields. The page sent `is_active` on create and `username` on update, so both returned 422. | The users page sends `username` only on create and `is_active` only on update. Payloads of the targets, models and config pages were checked against the backend schemas and need no change. |

The A4 round reported the admin endpoints as reachable based on `curl -L`. That check followed redirects and does not enforce CORS, so it missed the trailing-slash defect. Browser-level testing is required for proxy behaviour.

### Configuration

The browser WebSocket goes through the Next.js proxy, so the backend sees the frontend origin. It must be allowed in the backend environment, otherwise the socket is rejected with 403:

```bash
WS_ALLOWED_ORIGINS=http://localhost:3000
```

Open the app at `http://localhost:3000`. The LAN address printed by `pnpm dev` has a different origin and needs its own entry. The variable is not yet listed in `.env.example`.

## Smoke test

### Without login (both servers running)

| # | Step | Expected | Result |
|---|---|---|---|
| 1 | Open each route: `/`, `/login`, `/targets`, `/admin`, `/admin/login` and the 8 admin pages | HTTP 200 | Pass |
| 2 | Open an unknown path | HTTP 404 | Pass |
| 3 | Open `/` without a session | Redirect to `/login` | Pass |
| 4 | Open `/admin/users` without a session | Redirect to `/admin/login` | Pass |
| 5 | Check `<html lang>`, page title and visible text | `en`, English title, no Chinese | Pass |
| 6 | Call each admin API used by the pages through the frontend proxy, without following redirects | 401 (present and protected) | Pass after the trailing-slash fix |
| 7 | Open a chat page without a token | No WebSocket connection attempted | Pass |
| 8 | Open a chat page with an invalid token | Auth frame sent, socket closed by backend, UI shows Offline | Pass |

### Signed in (manual, in a browser)

| # | Step | Expected | Result |
|---|---|---|---|
| 9 | Sign in at `/login` | Redirect to `/`, chat page loads | Pass |
| 10 | Check the chat header status | Connected | Pass after the WebSocket fix |
| 11 | Send a question, e.g. "How far am I from MDRT?" | Reply or a readable error; no reconnect loop | Pass |
| 12 | Switch the Competitions / Honors / Performance tabs | Tabs switch; empty states where APIs are missing | Pass |
| 13 | Open `/targets` | Targets page loads | Pass |
| 14 | Mobile width (375 px): open the menu drawer and data panel | Layout works | Pass |
| 15 | Sign out | Back to `/login` | Pass |
| 16 | Sign in at `/admin/login` as `admin` | Admin console loads; sidebar shows 8 pages | Pass |
| 17 | Users: list, create, edit, delete a test user | All succeed | Pass after the trailing-slash and users fixes |
| 18 | Competitions: list. Targets: list, create, edit, delete | All succeed | **Partial.** Competitions list passes; the page is read-only by design, as in the Original Repo. Targets is **blocked** by the missing `/api/agents-list`: the page groups targets by that agent list, so no targets are shown, and create sends an empty `agent_id` (422). |
| 19 | Models and System config: list and edit | All succeed | Pass |
| 20 | Audit log: requests, AI audit and errors tabs | Lists load | Pass |
| 21 | Knowledge base: list and upload a document | Succeeds | Pass |
| 22 | Briefing settings | Page loads | **Blocked** by the unregistered briefing router (404) |

## Known issues (not fixed in this round)

| Issue | Impact | Owner |
|---|---|---|
| `/api/agents-list` is missing | Admin targets page shows no targets and cannot create one (test 18) | Backend (M1/M2) |
| Briefing router not registered in `api/server.py` | Briefing settings and the daily briefing modal fail (test 22) | Backend (M3/M1) |
| `/api/agent-info`, `/api/competitions`, `/api/performance`, `/api/proactive-alerts`, `/api/chat-sessions` are missing | Sidebar profile, Honors and Performance tabs, alert banner and chat history stay empty | Backend |
| Access tokens expire after 15 minutes and the frontend never calls `/api/admin/auth/refresh` | The chat drops to Offline after 15 minutes until the user signs in again | Frontend (M5), candidate for stage B |
| "Configure API" dialog calls `/api/config/apply`, `/api/config/test` and `/api/feature-models` without the bearer token | Saving or testing an LLM key from the dialog returns 401; configure the key in `.env` instead | Frontend (M5), candidate for stage B |
| `WS_ALLOWED_ORIGINS` missing from `.env.example` | Fresh setups cannot open the chat socket | Backend (M1) |

## Not migrated

`docs/qa/mobile/` in the Original Repo (about 57 MB of screenshots, Lighthouse reports and a performance trace) records the original author's manual mobile QA of the Chinese UI. It does not apply to this repository and is not copied.
