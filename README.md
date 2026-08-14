# JobScout

Ingestion pipeline that keeps 130+ company career endpoints across 6 ATS APIs polled, parsed, and normalized into SQLite without manual babysitting. Tier 1 companies (24 of them) poll every 5 minutes, the full sweep runs hourly, and every source fails in isolation: one schema change degrades one company to zero rows, not the sweep. Job postings are what it ingests. The engineering problem is 130+ third-party schemas that change without notice, on a $0/month compute budget.

---

## How it stays alive

### Tiered polling

Tier 1 (24 companies) every 5 minutes from a Render background thread. Full sweep hourly. A GitHub Actions fallback sweep runs 9x/day and exports `api-data.json` for the dashboard. Night skip 12am to 5:30am CST, because ATS platforms publish during business hours. That cuts roughly a quarter of the compute for zero data loss.

### Failure isolation

`scrape_with_retry` in `scrapers/utils.py` retries each source 3 times with exponential backoff (2s, 4s) and never raises. A broken scraper logs and returns an empty list. With 130+ sources, per-source failure containment matters more than per-source completeness.

### Date and salary parsing

The posted-date extractor handles 4 formats (ISO, US MM/DD/YYYY, relative "5 days ago", same-day) with bounds checks, so "10000 days ago" inside a salary string cannot produce a 1970 date. The salary extractor covers 5 pattern families, annualizes hourly rates at 2080 hours, and rejects any number with a non-salary qualifier ("signing bonus", "equity grant", "401(k) match") in the 30 characters before it. That filter exists because "$25,000 to $50,000 signing bonus" was polluting the salary column.

### Progress broker

A single thread-safe singleton (`core/scrape_status.py`) reports scrape state for both the 5-minute cron and manual triggers. A 10-minute watchdog marks dead runs finished. Destructive admin operations (`VACUUM`, stale-job purge) check the broker and return 409 instead of fighting SQLite lock contention with scrape writes.

### The $0 budget

Render free tier plus GitHub Actions free tier. About 1,080 of 2,000 free Action minutes a month. A 14-minute keepalive ping defeats Render's 15-minute sleep. Polling at 1.5s instead of SSE, because long-lived connections through Render's proxy are not worth the keepalive complexity. Total cost: $0/month.

---

## What I'd fix

- **The read-path auth bug.** After multi-user auth shipped, `GET /api/profile` called `get_profile()` without extracting `user_id`. Writes went to the correct row. Reads returned the shared `legacy` row, so every logged-in user saw default state on every refresh. Caught in whole-branch review, not per-task review. Read paths need the same scoping audit as write paths.
- **Config drift, fixed structurally.** The CLI took a `delay` argument while the server read a hardcoded `SCRAPE_DELAY`, and the two drifted apart. Now one env var, one read path, and one canonical `run_scrape()` signature shared by CLI and Flask server.
- **Score-weight sliders are stored, not wired.** `ScoreWeightDials` persists 4 weights to the backend, but ranking still uses fixed multipliers (1.5 down to 1.05). Either wire `normalizeWeights` into the scoring formula or delete the sliders. Right now the UI promises something it does not do.
- **A missing `.catch()` hung the whole app.** `supabase.auth.getSession().then(...)` had no `.catch()`, so a missing `VITE_SUPABASE_URL` rejected the promise and the loading spinner never cleared. Every `.then()` that gates UI state now carries a `.catch()`.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  RENDER (FREE)                       │
│  Flask + background thread                           │
│  ├── Every 5 min:  Tier 1 (24 companies)             │
│  ├── Every 60 min: All tiers (full sweep)            │
│  ├── Night skip:   12am-5:30am CST paused            │
│  ├── Alerts:       Discord + Telegram on match       │
│  └── SQLite (WAL): jobs + profile + resume versions  │
│                                                      │
│  API: /api/data  /api/health  /api/scrape            │
│       /api/scrape/status  /api/profile               │
│       /api/resume/versions  /api/applications        │
│       /api/admin/doctor|purge-stale|clear-cache|     │
│       reextract-skills|vault-reindex                 │
└──────────────────────┬──────────────────────────────┘
                       │ primary source (~5 min fresh)
┌──────────────────────▼──────────────────────────────┐
│             REACT DASHBOARD (GitHub Pages)           │
│  Jobs: ranked search, filters, pagination            │
│  Analytics: ATS pie, salary bar, 30-day trend        │
│  Tracker: resume versions, application history       │
│  Monitor: health, manual triggers, run history       │
└──────────────────────▲──────────────────────────────┘
                       │ fallback (~2 hr fresh)
┌──────────────────────┴──────────────────────────────┐
│              GITHUB ACTIONS (FREE)                   │
│  ├── 9x/day scrape (skip 12am-5:30am CST)            │
│  ├── Export api-data.json, commit, deploy Pages      │
│  └── Budget: ~1,080 min/month of 2,000 free          │
└──────────────────────────────────────────────────────┘
```

Design constraints behind this shape (single gunicorn worker, SQLite WAL single-writer assumption, polling over SSE, singleton broker) are recorded in [`specs/README.md`](specs/README.md).

---

## ATS coverage

| ATS | Companies | API |
|-----|-----------|-----|
| Greenhouse | 87 | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` |
| Ashby | 11 | `api.ashbyhq.com/posting-api/job-board/{slug}` |
| Workday | 7 | `{slug}.wd1.myworkdayjobs.com/wday/cxs/{slug}/{board}/jobs` |
| Lever | 4 | `api.lever.co/v0/postings/{slug}` |
| SmartRecruiters | 4 | `api.smartrecruiters.com/v1/companies/{slug}/postings` |
| BambooHR | 3 | `{slug}.bamboohr.com/careers/list` |

Workday needs a slug, an instance (`wd1`, `wd5`), and a board path. The other five need one slug each. Adding a company is one dict in `backend/config/companies.py`.

---

## Run it

```bash
cd backend
pip install -r requirements.txt
python main.py --fast    # Tier 1 only (~30 sec)
python main.py           # All 130+ companies (~3 min)
python main.py --stats   # Check results
```

Deploy: `render.yaml` is a one-click Render blueprint. The dashboard deploys to GitHub Pages from the Actions workflow. Point it at your Render URL from the dashboard settings panel (stored in localStorage, no rebuild). Alerts fire when company is in `DREAM_COMPANIES`, the title matches `DREAM_ROLE_KEYWORDS`, and `relevance_score >= DREAM_ALERT_SCORE` (default 0.70), via Discord webhook or Telegram bot, both free.

Maintenance endpoints (`/api/admin/*`, Bearer auth): `doctor` (6-probe health check), `purge-stale`, `clear-cache` (VACUUM), `reextract-skills`, `vault-reindex`. Destructive ones return 409 while a scrape is running.

---

## Layout

```
backend/
├── config/          companies.py (130+ companies, 6 ATS), profile.py (skills/locations)
├── scrapers/        one module per ATS + utils.py (dates, salaries, retry)
├── core/            relevance.py, scrape_orchestrator.py, scrape_status.py (broker)
├── routes/          vault_routes.py, admin_routes.py, profile_routes.py
├── storage/         db.py (SQLite WAL), profile_manager.py, resume_vault.py (TF-IDF)
├── alerts/          notifier.py (Discord + Telegram)
├── server.py        Flask API + background scraper + night skip
└── main.py          CLI used by Actions and local runs
frontend/src/        React dashboard on GitHub Pages
.github/workflows/   9x/day scrape + Pages deploy
```

---

## License

MIT
