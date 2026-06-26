# Engineering Memory

This file is the persistent project context for agents and maintainers.


## Repo Context Index

<!-- AUTO:REPO_CONTEXT_START -->
### Canonical Context Sources

- User-facing overview: `README.md`
- Engineering memory: `specs/README.md`
- Glossary: `UBIQUITOUS_LANGUAGE.md`
- Branch snapshot: `main`
- Last commit: `data: 170 jobs Â· Mar 05 23:24 UTC [skip ci]`

### Repo Summary

- Zero-cost, real-time job scraper + intelligent React dashboard built for data engineers and ML professionals. Monitors 130+ companies across 6 ATS platforms, sends dream-job alerts via Discord and Telegram (free forever), and builds a semantic memory of every resume version and company you've ever applied to. ┌─────────────────────────────────────────────────────┐
<!-- AUTO:REPO_CONTEXT_END -->

## Architecture and Design Constraints

- **Render free tier**: single gunicorn worker, no persistent disk beyond ephemeral container, sleeps after 15 min idle (mitigated by 14-min GitHub Actions keepalive).
- **SQLite WAL mode** for the jobs/applications DB — single-writer assumption holds. Background scrape thread + manual trigger share one DB via the orchestrator; concurrency guard prevents double-writers.
- **Zero new runtime deps** for the Manual Triggers sprint — `threading.RLock`, stdlib `shutil.disk_usage`, no SSE/WebSocket libraries.
- **All admin operations honor `API_SECRET` Bearer auth** — same pattern as `/api/scrape`. No new auth surface.
- **Non-goals**: mode picker in dashboard (always-fast), real `gh workflow run` integration (stays as external link), SSE streaming (polling at 1.5s is sufficient), splitting `server.py` into per-concern modules.

## Built So Far

**Discovery layer (live):**
- 130+ companies scraped across 6 ATS platforms (Greenhouse, Lever, Ashby, SmartRecruiters, BambooHR, Workday) every 5 min on Render + every 2 hr on GitHub Actions.
- Multi-signal relevance engine + TF-IDF resume booster + per-tier alert thresholds + Playwright extension for locked APIs.
- Discord + Telegram dream-job alerts (free forever).

**Manual Triggers Reliability Sprint — 2026-05-15 (PRD #18, all 6 children shipped):**
- **Thread-safe scrape status broker** (`core/scrape_status.py`) — singleton with `start/tick/finish/snapshot/is_running` + 10-min stale-run watchdog.
- **Consolidated `run_scrape()`** into `core/scrape_orchestrator.py` — single canonical signature `run_scrape(conn, *, mode='fast', status_broker=None)`. CLI and Flask server both import from here. `delay` moved from arg to `SCRAPE_DELAY` env var.
- **Live progress UI** — `GET /api/scrape/status` returns the broker snapshot; frontend polls every 1.5s; renders a progress bar with current company, X/Y companies, jobs found, ETA.
- **Concurrency guard** — `POST /api/scrape` returns `409` with snapshot if a scrape is already running. The 5-min cron thread also reports through the broker, so manual users see its progress in real time.
- **Admin Blueprint** (`routes/admin_routes.py`) with 5 endpoints, all under `/api/admin/`:
  - `GET /doctor` — 6-probe health-check (DB, scrapers, recent run, env, vault, disk).
  - `POST /purge-stale` — deletes inactive jobs older than N hours (default 96). 409 during active scrape.
  - `POST /clear-cache` — VACUUM the SQLite DB. 409 during active scrape.
  - `POST /reextract-skills` — re-runs skill extraction over `resume_versions` rows.
  - `POST /vault-reindex` — rebuilds the in-memory TF-IDF matrix from `resume_vault/text/`.
- **6-card Manual Triggers panel** in `frontend/src/App.jsx` Monitor tab — scrape + 5 admin ops + GitHub Actions link.
- **pytest coverage** — first real test suite in the repo: `test_scrape_status.py`, `test_scrape_orchestrator.py`, `test_admin_routes.py` (covering broker thread-safety, orchestrator regression, doctor aggregation, purge/clear-cache during scrape guard).

**Resume vault layer (live, ❌ no dashboard UI yet):**
- 95 PDF resume vault + filename parser (150+ naming patterns) + TF-IDF cosine-similarity engine.
- 8 vault endpoints under `/api/vault/`. Frontend integration deferred (see Open Issues).

## Design Decisions

- **Broker as singleton, not request-scoped** — Render runs a single gunicorn worker; the background scrape thread and Flask handlers all share the same process. A module-level `broker = StatusBroker()` is the simplest correct shape. If we ever go multi-worker, we'd need to externalize state (Redis or DB column).
- **10-min watchdog inside `is_running()`** rather than a separate cleanup thread — keeps the broker fully synchronous and stdlib-only. Cost: an extra wall-clock check per `is_running()` call (negligible).
- **Polling over SSE** — 1.5s polling is cheap on Render's free tier and avoids the keepalive complexity of long-lived connections behind their proxy. Each `/api/scrape/status` call is <50ms.
- **`SCRAPE_DELAY` env var, not function arg** — eliminated the original bug (drift between CLI `delay` and server hardcoded `SCRAPE_DELAY`). One env var, one read path, one canonical signature.
- **Admin Blueprint mirrors `vault_routes.py`** — same pattern, same auth, same response JSON shape. New endpoints feel like the existing surface.
- **Destructive admin ops check `broker.is_running()` and return 409** — prevents `VACUUM`/`DELETE` lock contention with the scrape's `UPDATE` traffic. Non-destructive ops (re-extract, reindex) don't need the guard.
- **Self-critique gate on every PR** — 3 parallel Agent calls (Sanity / Production / Architecture) before commit. Caught real issues during the sprint (e.g., daemon thread leak, missing min() clamp). Repeated across all 6 children.

## What Worked

- **Vertical-slice decomposition** (PDD → `/prd-to-issues`) — 6 thin end-to-end slices on 2 parallel tracks beat 5 horizontal layers. Tracers (#19, #22) de-risked the architecture before fan-out (#20, #21, #23, #24) all merged with only additive `CHANGELOG.md` + `App.jsx` conflicts.
- **Parallel RemoteTrigger fleet** — two tracers fired simultaneously (#19 + #22), then four Wave-2 issues fanned out in parallel. Self-critique baked into each prompt prevented agents from shipping unreviewed code.
- **Conflict pattern was always additive** — every cross-PR conflict in this sprint was an "add a line to a Markdown list" or "add a new admin card to the same JSX panel". Resolving with `--force-with-lease` after each merge worked cleanly.
- **Test surface added per slice** — first pytest suite in the repo arrived as a side effect of the sprint, not as a separate "add tests" issue. Each child PR carried its own tests.

## What Failed or Was Reverted

- **PR #14 + #17 (relevance overhaul scoring + UI signals, 2026-05-15 earlier)** — auto-close trailers were missed, causing issues #7/#10/#11 to stay open after their PRs merged. **Lesson:** when bundling multiple issues in one PR, use the literal `Closes #N, Closes #M, Closes #O` syntax on separate lines in the PR body, not a single combined phrase. (Manually closed during cleanup.)
- **Force-push pre-action hook blocked the rebase workflow** initially during the Manual Triggers sprint. Resolved by user-authorized `--force-with-lease`. **Lesson:** for PR-branch rebases (own branches, no shared collaborators), `--force-with-lease` is the safe-force variant and should be allowlisted in the hook.

**Multi-User Auth + Company Priority + Search Autocomplete Sprint — 2026-06-24 (12 tasks, all shipped):**

- **Supabase hybrid auth** (`backend/middleware/supabase_auth.py`) — `require_auth` decorator: HS256 JWT verification against `SUPABASE_JWT_SECRET`. Existing `API_SECRET` Bearer path checked *first* so scrapers are unaffected. Sets `flask.g.user_id` (from JWT `sub` claim) and `flask.g.email`. `check_auth()` counterpart for `before_request` hooks.
- **Idempotent DB migration** (`backend/storage/migrate_add_user_id.py`) — adds `user_id TEXT NOT NULL DEFAULT 'legacy'` to `user_profile`, `applications`, `resume_versions`; adds `priority_companies`, `priority_mode`, `score_weights` TEXT columns to `user_profile`; creates `UNIQUE INDEX` on `user_profile(user_id)`. Each column addition guarded by `PRAGMA table_info` check — safe to re-run. Auto-runs at server startup via `server.py`.
- **Multi-user profile_manager** (`backend/storage/profile_manager.py`) — all 6 functions accept `user_id: str = "legacy"`; `get_profile` auto-creates row for new users; `priority_companies` and `score_weights` serialized as JSON strings in SQLite, deserialized on read.
- **Auth-scoped profile routes** (`backend/routes/profile_routes.py`) — `_profile_auth()` hybrid helper: tries JWT first (`flask.g.user_id`), falls back to legacy cookie/PIN for dev-mode. Both GET and POST handlers now scope by `user_id`.
- **Company request endpoint** (`backend/routes/company_request_routes.py`) — `POST /api/companies/request` files a GitHub Issue via `GITHUB_TOKEN` env var for unknown companies. Catches `HTTPError`, `URLError`, `OSError`.
- **Supabase frontend client** (`frontend/src/lib/supabase.js`) — singleton with `currentAccessToken` module-level var; updated on `onAuthStateChange`. `authHeaders()` in `api.js` now prefers JWT Bearer, falls back to legacy `vault_token`.
- **LoginPage** (`frontend/src/components/LoginPage.jsx`) — GitHub/Google OAuth + email magic link. `redirectTo = window.location.origin + '/job-scout/'`. Auth gate: App.jsx shows spinner during `authLoading`, renders LoginPage when `!user`.
- **ScoreWeightDials** (`frontend/src/components/ScoreWeightDials.jsx`) — 4 labeled range sliders (Skills 53%, Role Fit 25%, Logistics 22%, Company Tier 8%); live % display; stored and persisted but *not yet wired to scoring* (intentional deferral — see Open Issues).
- **CompanyPriorityPanel** (`frontend/src/components/CompanyPriorityPanel.jsx`) — @dnd-kit sortable list; Score Boost / Hard Sort mode toggle; "+ Add company" calls `POST /api/companies/request` for unknown companies; embeds ScoreWeightDials; debounced (300ms) save to `/api/profile`.
- **Priority scoring in App.jsx** — `getCompanyMultiplier` (rank1=×1.5 … rank6+=×1.05) and `getPriorityGroup` (0=first, 999=none) injected into `enriched` useMemo as `_boosted_score` and `_priority_group`. Both fj sort blocks check `_priority_group` before `_boosted_score`.
- **CompanyAutocomplete** (`frontend/src/components/CompanyAutocomplete.jsx`) — prefix matches first, then substring, sorted by `job_count` desc, max 8; avatar bubbles (deterministic color); tier badges; "+ Add to priority list" last row; ArrowDown/Up/Escape/Enter keyboard nav; outside-click close.
- **JobsTab integration** (`frontend/src/tabs/JobsTab.jsx`) — raw `<input>` replaced with `<CompanyAutocomplete>`; `<CompanyPriorityPanel>` added as first child of expanded filters section.

## Design Decisions

- **Broker as singleton, not request-scoped** — Render runs a single gunicorn worker; the background scrape thread and Flask handlers all share the same process. A module-level `broker = StatusBroker()` is the simplest correct shape. If we ever go multi-worker, we'd need to externalize state (Redis or DB column).
- **10-min watchdog inside `is_running()`** rather than a separate cleanup thread — keeps the broker fully synchronous and stdlib-only. Cost: an extra wall-clock check per `is_running()` call (negligible).
- **Polling over SSE** — 1.5s polling is cheap on Render's free tier and avoids the keepalive complexity of long-lived connections behind their proxy. Each `/api/scrape/status` call is <50ms.
- **`SCRAPE_DELAY` env var, not function arg** — eliminated the original bug (drift between CLI `delay` and server hardcoded `SCRAPE_DELAY`). One env var, one read path, one canonical signature.
- **Admin Blueprint mirrors `vault_routes.py`** — same pattern, same auth, same response JSON shape. New endpoints feel like the existing surface.
- **Destructive admin ops check `broker.is_running()` and return 409** — prevents `VACUUM`/`DELETE` lock contention with the scrape's `UPDATE` traffic. Non-destructive ops (re-extract, reindex) don't need the guard.
- **Self-critique gate on every PR** — 3 parallel Agent calls (Sanity / Production / Architecture) before commit. Caught real issues during the sprint (e.g., daemon thread leak, missing min() clamp). Repeated across all 6 children.
- **Supabase HS256 (not RS256/JWKS)** — Supabase supports both. HS256 with `SUPABASE_JWT_SECRET` is simpler (no HTTP call to Supabase on every request, no key rotation complexity). Acceptable for single-owner personal deploy; switch to JWKS if the app becomes multi-tenant with strict security requirements.
- **API_SECRET bearer path checked FIRST in require_auth** — scrapers call `/api/scrape` with `API_SECRET`. If JWT check ran first, scrapers would get 401 every time. Order: API_SECRET → JWT → 401.
- **user_id DEFAULT 'legacy' in SQLite** — backward-compat: existing rows (pre-migration) and any caller that doesn't provide auth gets `'legacy'`. Single-owner deployments work unchanged. Multi-user isolation is opt-in via Supabase login.
- **auth.js exports preserved, not replaced** — App.jsx imports `shouldShowLogin`, `deriveMode`, `setCsrf` from `auth.js`. If we had replaced the file, App.jsx would break. Solution: append `export { supabase } from './supabase'` at the end of the existing file without touching anything else.
- **Score weights deferred** — `scoreWeights` state is stored, displayed, and persisted to backend but has no effect on ranking. `getCompanyMultiplier` uses fixed rank-order multipliers (1.5→1.05). Wiring weights into a custom scoring formula is a future task once the UX is validated.
- **onOpenAddSearch stub** — the "+ Add company" button inside CompanyPriorityPanel fires `onOpenAddSearch(() => {})`. Companies can still be added via the autocomplete dropdown's "+ Add to priority list" row. The stub is intentional: the panel's internal add path includes the GitHub issue-filing flow; the autocomplete path is a quick-add that bypasses it. A proper modal connecting the two flows is deferred.

## What Worked

- **Vertical-slice decomposition** (PDD → `/prd-to-issues`) — 6 thin end-to-end slices on 2 parallel tracks beat 5 horizontal layers. Tracers (#19, #22) de-risked the architecture before fan-out (#20, #21, #23, #24) all merged with only additive `CHANGELOG.md` + `App.jsx` conflicts.
- **Parallel RemoteTrigger fleet** — two tracers fired simultaneously (#19 + #22), then four Wave-2 issues fanned out in parallel. Self-critique baked into each prompt prevented agents from shipping unreviewed code.
- **Conflict pattern was always additive** — every cross-PR conflict in this sprint was an "add a line to a Markdown list" or "add a new admin card to the same JSX panel". Resolving with `--force-with-lease` after each merge worked cleanly.
- **Test surface added per slice** — first pytest suite in the repo arrived as a side effect of the sprint, not as a separate "add tests" issue. Each child PR carried its own tests.
- **Subagent-Driven Development for auth+priority sprint** — 12 tasks across 3 features, each dispatched as a fresh implementer subagent + task reviewer. The review loop caught 3 real issues before they reached the final review: missing `URLError/OSError` catch in company_request_routes, broad mock patch target in tests, and `priority_companies` return type mismatch (backend returns list; frontend must handle both list and JSON string).
- **Brief-file handoffs over context pasting** — each implementer got a self-contained brief file (exact code to write, exact line numbers to edit). No cross-task context pollution. The final 12-task branch had zero merge conflicts despite touching the same App.jsx and profile_routes.py across multiple tasks.

## What Failed or Was Reverted

- **PR #14 + #17 (relevance overhaul scoring + UI signals, 2026-05-15 earlier)** — auto-close trailers were missed, causing issues #7/#10/#11 to stay open after their PRs merged. **Lesson:** when bundling multiple issues in one PR, use the literal `Closes #N, Closes #M, Closes #O` syntax on separate lines in the PR body, not a single combined phrase. (Manually closed during cleanup.)
- **Force-push pre-action hook blocked the rebase workflow** initially during the Manual Triggers sprint. Resolved by user-authorized `--force-with-lease`. **Lesson:** for PR-branch rebases (own branches, no shared collaborators), `--force-with-lease` is the safe-force variant and should be allowlisted in the hook.
- **auth.js replace plan abandoned mid-task** — the original plan said to replace `auth.js` entirely with a Supabase-only version. Task 7 implementer caught that App.jsx imports `shouldShowLogin`, `deriveMode`, `setCsrf` from `auth.js` (line 28). Replacing the file would have silently broken App.jsx at runtime. **Lesson:** before replacing a module, always grep for all import sites across the codebase — not just the file being replaced.
- **GET /api/profile always returned "legacy" row** — the GET handler was calling `get_profile()` without extracting `user_id` from auth context. Writes went to the correct user row; reads always returned the shared `legacy` row. Every user who logged in would see the default state after every page refresh. Caught in the final whole-branch review (not in per-task review). Fixed in `ae57def`. **Lesson:** read paths need the same user-scoping audit as write paths — it's easy to add auth to POST but forget GET.
- **getSession() missing .catch()** — `supabase.auth.getSession().then(...)` had no `.catch()`. A missing `VITE_SUPABASE_URL` env var would cause the promise to reject and `setAuthLoading(false)` to never fire, showing a permanent spinner. Caught in final review. Fixed with `.catch(() => setAuthLoading(false))` in `ae57def`. **Lesson:** every `.then()` chain that gates UI state needs a `.catch()` to handle misconfiguration gracefully.

## Open Issues and Next Work

**Post-auth-priority-autocomplete sprint (open):**
- **Score weights not wired to scoring** — `scoreWeights` state is stored, persisted, and displayed via ScoreWeightDials but has no effect on `_boosted_score`. `getCompanyMultiplier` uses fixed rank multipliers. Wire `normalizeWeights` into a custom scoring formula or remove the sliders.
- **onOpenAddSearch stub** — the "+ Add company" button inside CompanyPriorityPanel fires `() => {}`. Build a modal/search overlay that opens CompanyAutocomplete in "add to priority" mode.
- **LinkedIn OAuth not configured** — LoginPage has a LinkedIn button but the Supabase provider is not enabled. Either enable it (requires LinkedIn Developer App) or remove the button.
- **No test coverage for SUPABASE_JWT_SECRET missing path** — `require_auth` returns 500 if `SUPABASE_JWT_SECRET` is not set. No test covers this branch.
- **vault_routes 500→401 masking** — when `SUPABASE_JWT_SECRET` is missing, `check_auth()` returns a 500 response but `vault_routes` before_request discards it and returns 401. Makes server misconfiguration invisible to the caller.

**Pre-existing open issues:**
- **#1** — `[Feature] Automatic application tracking via email parsing + extension events` (older backlog, separate sprint).
- **#2, #3, #4** — Older Relevance #1, #2, #3 issues (older work; verify if shipped, close if so).

**Recommended next priorities:**
1. **Wire score weights into scoring** — `normalizeWeights` is already defined; multiply each score component by the corresponding normalized weight before summing into `_display_score`.
2. **CompanyPriorityPanel add-company modal** — connect `onOpenAddSearch` to an overlay that uses CompanyAutocomplete; unify the two "add to priority" paths.
3. **AutoApply AI integration** — separate repo (`autoapply-ai`); see `CLAUDE.md` for the end-to-end vision.

## How To Work in This Repo

## How To Work in This Repo

- Read `README.md` first for user-facing behavior and contribution flow.
- Read this `specs/README.md` before implementation.
- Update this file before `compact` and at session end.

## Session Checkpoints

