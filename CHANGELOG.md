# Changelog

All notable changes to JobScout will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Multi-User Auth + Company Priority + Search Autocomplete (2026-06-24)

**Multi-user Supabase auth:**
- `backend/middleware/supabase_auth.py` — `require_auth` Flask decorator: HS256 JWT verification against `SUPABASE_JWT_SECRET`; existing `API_SECRET` scraper bearer path preserved and checked first; sets `flask.g.user_id` and `flask.g.email`.
- `backend/storage/migrate_add_user_id.py` — idempotent SQLite migration: `user_id TEXT NOT NULL DEFAULT 'legacy'` added to `user_profile`, `applications`, `resume_versions`; `priority_companies`, `priority_mode`, `score_weights` columns added to `user_profile`; UNIQUE INDEX on `user_profile(user_id)`. Auto-runs on server startup.
- `backend/storage/profile_manager.py` — all 6 functions now accept `user_id: str = "legacy"`; auto-creates row for new users; priority fields serialized/deserialized as JSON.
- `backend/routes/profile_routes.py` — `_profile_auth()` hybrid helper (JWT first, legacy cookie/PIN fallback); both GET and POST scope by `user_id`.
- `backend/routes/company_request_routes.py` — `POST /api/companies/request` files GitHub Issues via `GITHUB_TOKEN` for unknown company additions.
- `frontend/src/lib/supabase.js` — Supabase client singleton with `currentAccessToken` module-level var.
- `frontend/src/lib/api.js` — `authHeaders()` prefers Supabase JWT Bearer, falls back to legacy `vault_token`.
- `frontend/src/components/LoginPage.jsx` — GitHub + Google OAuth + email magic link; redirects to `/job-scout/` on success.
- App.jsx auth gate: shows spinner during session load, renders LoginPage when `!user`.

**Company priority panel:**
- `frontend/src/components/ScoreWeightDials.jsx` — 4 labeled range sliders (Skills, Role Fit, Logistics, Company Tier); live % share display; persisted to profile.
- `frontend/src/components/CompanyPriorityPanel.jsx` — @dnd-kit drag-to-reorder list; Score Boost / Hard Sort mode toggle; GitHub Issue auto-filing for unknown companies; embeds ScoreWeightDials; 300ms debounced save.
- App.jsx priority scoring: `_boosted_score` (rank multipliers ×1.5→×1.05) and `_priority_group` (0=first, 999=none) injected into `enriched` useMemo; both `fj` sort blocks use `_priority_group` first, then `_boosted_score`.

**Search autocomplete:**
- `frontend/src/components/CompanyAutocomplete.jsx` — prefix+substring ranked suggestions (max 8), avatar bubbles, tier badges, "+ Add to priority list" last row, keyboard nav (Arrow/Enter/Escape), outside-click close.
- `frontend/src/tabs/JobsTab.jsx` — raw `<input>` replaced with CompanyAutocomplete; CompanyPriorityPanel added as first child of expanded filters section.

### Fixed
- `getSession()` missing `.catch()` — permanent spinner on missing Supabase env vars. Added `.catch(() => setAuthLoading(false))`.
- `GET /api/profile` always returned the `'legacy'` row regardless of logged-in user. GET handler now calls `_profile_auth()` and passes `user_id` to `get_profile()`.

### Added — Manual Triggers Reliability Sprint (2026-05-15)
- POST /api/admin/purge-stale and POST /api/admin/clear-cache destructive admin endpoints with scrape-in-progress guard (#23).
- POST /api/admin/reextract-skills and POST /api/admin/vault-reindex non-destructive admin endpoints (#24).
- Concurrency guard on POST /api/scrape (returns 409 when scrape active) + progress-bar UI + background scrape thread reports via shared broker (#20).
- Admin Blueprint scaffold (routes/admin_routes.py) + GET /api/admin/doctor health-check endpoint with 6 probes (#22).
- Thread-safe scrape status broker (`core/scrape_status.py`) and `GET /api/scrape/status` endpoint for live progress polling (#19).
- Dashboard Monitor tab now shows live per-company scrape progress (current company, completed/total, jobs found, ETA) while a scrape is running (#19).

### Changed
- Consolidated `run_scrape()` from main.py + server.py into single `core/scrape_orchestrator.py` (#21). `delay` is now read from `SCRAPE_DELAY` env var; `--delay` CLI flag preserved as alias.

### Fixed
- `run_scrape()` TypeError on `POST /api/scrape` — caller signature aligned (#19).
