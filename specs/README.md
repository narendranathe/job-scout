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

## Open Issues and Next Work

**Open issues (post-sprint):**
- **#18** — PRD: Manual Triggers Reliability Sprint. All 6 children merged. **Manually close after this commit lands** (no PR references the PRD directly).
- **#1** — `[Feature] Automatic application tracking via email parsing + extension events` (older backlog, separate sprint).
- **#2, #3, #4** — Older Relevance #1, #2, #3 issues (older work; verify if shipped, close if so).

**Recommended next priorities:**
1. **Vault UI integration** — the resume vault has 8 live endpoints + 95 indexed PDFs but no dashboard frontend. First slice: wire `POST /api/vault/best-match` into job cards so clicking a job surfaces the best-matching resume.
2. **Wave-3 cleanup** — close #18, audit #2/#3/#4 status, file a 1-line follow-up if `db_admin.py` or any sprint module needs hardening based on first-week production use.
3. **AutoApply AI integration** — separate repo (`autoapply-ai`); see `CLAUDE.md` for the end-to-end vision (Chrome extension reads form fields, FastAPI backend generates answers via multi-LLM pipeline, JobScout vault picks the right resume).

## How To Work in This Repo

## How To Work in This Repo

- Read `README.md` first for user-facing behavior and contribution flow.
- Read this `specs/README.md` before implementation.
- Update this file before `compact` and at session end.

## Session Checkpoints

