# CLAUDE.md — JobScout Project Context

> Single source of truth for Claude Code (CLI) sessions.
> Read this FIRST. It reflects the actual state of the local codebase
> as of March 2025, verified against the running Render server.

---

## Project Identity

- **Name:** JobScout — Personal Job Discovery Platform
- **Repo:** https://github.com/narendranathe/job-scout
- **Owner:** Narendranath Edara (narendranathe)
- **Current version:** 3.2 (full vault loop live: scrape → score → best-match → download → track)
- **Languages:** Python ~49% / JavaScript ~50% / YAML ~1%
- **Total cost:** $0/month (Render free + GitHub Actions free + GitHub Pages free)
- **Live jobs tracked:** 500+ (grows continuously as Render scrapes)

---

## What This Project Does

A production-grade, zero-cost **end-to-end job hunt automation platform** for Data Engineers and ML Engineers. The system covers the full lifecycle:

1. **Discover** — Scrape 153 company career pages across 6 ATS platforms every 5 minutes
2. **Score** — Rate every job against your resume using multi-signal relevance + TF-IDF scoring
3. **Match** — Find the best resume (from 95+ tailored PDFs) for each specific job description
4. **Alert** — Instant Discord/Telegram notifications when dream roles appear
5. **Track** — Application status management with resume version history per company
6. **Apply** — *(In progress)* Auto-fill job applications using multi-LLM pipeline, Chrome extension, and stored work history

**Origin:** Inspired by the "Job Hunt Agent" concept — an automated system that scrapes jobs, rates them against your resume using AI, and sends personalized daily recommendations with resume improvement suggestions. JobScout is the production implementation, evolving from pure discovery into a full **AutoApply AI** system that handles the apply step itself.

**End-state vision:** See a dream job → JobScout picks the best resume → Chrome extension opens the application portal → multi-LLM pipeline reads the questions → auto-fills answers from your stored work history → you review and submit. Zero repetitive typing.

---

## Current Status — What's DONE vs PENDING

```
┌─────────────────────────────────────────┬──────────────────────┐
│               Layer                     │        Status        │
├─────────────────────────────────────────┼──────────────────────┤
│ Scraping 153 companies (6 ATS)          │ ✅ Live              │
│ Hourly GitHub Actions cron              │ ✅ Running           │
│ Flask API + all base endpoints          │ ✅ Live on Render    │
│ Resume vault backend (9 endpoints)      │ ✅ Live + auth-gated │
│ 95 PDFs + 73 texts in local vault       │ ✅ Imported          │
│ Application tracker + Pipeline kanban   │ ✅ Built (9 tabs)    │
│ Discord + Telegram alerts               │ ✅ Live              │
│ Vault UI in dashboard                   │ ✅ Built             │
│ Best-match on job cards                 │ ✅ Wired             │
│ Resume-Match % chip on every card       │ ✅ Wired (lazy-fetch)│
│ Resume upload UI                        │ ✅ Built (10 MB cap) │
│ Compare two resume versions             │ ✅ Built (TF-IDF)    │
│ Default-resume selector                 │ ✅ Built             │
│ PDF download from job card              │ ✅ Built             │
│ In-app server-setup panel               │ ✅ Built (v3.2)      │
│ Self-describing root endpoint           │ ✅ Built (v3.2)      │
│ pytest suite                            │ ✅ 197 tests passing │
├─────────────────────────────────────────┼──────────────────────┤
│ AutoApply: Chrome extension             │ ❌ Designed, not built│
│ AutoApply: Multi-LLM answer pipeline    │ ❌ Designed, not built│
│ AutoApply: Work history profile store   │ ❌ Designed, not built│
│ AutoApply: Portal form auto-fill        │ ❌ Designed, not built│
│ AutoApply: Pop-up application tracker   │ ❌ Designed, not built│
├─────────────────────────────────────────┼──────────────────────┤
│ App.jsx split into modules              │ ✅ Done (1805 LOC + 22 files)│
│ server.py split into modules            │ ✅ Done (184 LOC + 7 files)│
│ Standardize on one PDF library          │ ✅ Done (pypdf)        │
└─────────────────────────────────────────┴──────────────────────┘
```

### The Real Next Step (AutoApply AI)

The JobScout discovery-and-recommendation loop is **functionally complete**:
see job → vault picks best resume → click downloads PDF → status tracked.

The genuinely-missing layer is the apply step itself — the AutoApply AI
system (designed, partially built in a separate repo). Within this repo
the previously-listed tech debt is now fully cleared (see commit history
for the May 2026 refactor series):

- App.jsx split into per-tab modules — was 3886 LOC, now 1805 LOC orchestrator
  + 22 focused files across lib/, components/, tabs/ (PRs #69–85)
- server.py split into route modules — was 905 LOC, now 184 LOC orchestrator
  + 7 focused files across core/ and routes/ (PRs #60–67)
- pdfplumber retired, pypdf is the single PDF library (PR #58)

Feature work on the dashboard side is mostly polish at this point.
The user-visible features that CLAUDE.md previously labeled "not built"
were all wired up months ago — including the "Resume Match: 87%" chip
on every card, the best-match button, the vault tab, the compare UI,
and the default-resume selector. Search App.jsx for `jobFitByJob`,
`fetchBestMatch`, `setAsDefaultResume`, `VaultRow`, and
`uploadVaultPdf` to find them.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  RENDER (FREE TIER)                   │
│  Flask (server.py — 184 lines + 7 modules) + BG Thread │
│  ├── Every 5 min:  Tier 0+1 (58 dream companies)     │
│  ├── Every 60 min: All tiers (full 153-company sweep) │
│  ├── Night skip:   12am–5:30am CST (06:00–11:30 UTC) │
│  ├── Dream alerts: Discord + Telegram on new match    │
│  └── SQLite DB (WAL mode):                            │
│       ├── jobs (scraped + scored, dedup by external_id)│
│       ├── applications (tracker w/ status tracking)   │
│       ├── resume_versions (per-company tailored)      │
│       ├── user_profile (preferences + PIN hash)       │
│       └── scrape_runs (audit log)                     │
│                                                       │
│  Resume Vault:                                        │
│       ├── resume_vault/pdf/   (PDF storage, gitignored)│
│       └── resume_vault/text/  (extracted text cache)   │
│                                                       │
│  Flask API on port 10000 via gunicorn                 │
│  vault_routes.py Blueprint registered in server.py    │
└──────────────────────┬───────────────────────────────┘
                       │ live data (~5 min fresh)
┌──────────────────────▼───────────────────────────────┐
│       REACT DASHBOARD (GitHub Pages)                  │
│       App.jsx — 1805 lines + 22 modules               │
│  ├── Dual-source: live Render API → static fallback   │
│  ├── 9 Tabs: Jobs, Rare, Analytics, Companies, Trends,│
│  │           Tracker, Vault, Pipeline, Monitor        │
│  ├── Ranked search (10-tier scoring algorithm)        │
│  ├── Dream company badges, ATS platform icons         │
│  ├── Application tracker (localStorage + API sync)    │
│  ├── Mobile responsive (768px / 480px breakpoints)    │
│  ├── Dark/light theme toggle                          │
│  └── ✅ Full vault UI: tab + chips + best-match + DL│
└──────────────────────▲───────────────────────────────┘
                       │ fallback (~2 hr fresh)
┌──────────────────────┴───────────────────────────────┐
│           GITHUB ACTIONS (FREE TIER)                  │
│  ├── Hourly scrape at :20 (skip quiet hours)          │
│  ├── Export api-data.json → commit → deploy Pages     │
│  ├── Keepalive: ping Render every 14 min (biz hours)  │
│  └── Budget: ~1,080 min/month (limit: 2,000)         │
└───────────────────────────────────────────────────────┘
```

---

## File Structure

```
job-scout/
├── backend/
│   ├── config/
│   │   ├── companies.py           # 109 companies, 3 tiers, 6 ATS platforms
│   │   └── profile.py             # Static skills & preferences (fallback)
│   ├── scrapers/
│   │   ├── greenhouse.py          # ~87 companies
│   │   ├── lever.py               # ~4 companies
│   │   ├── ashby.py               # ~11 companies
│   │   ├── smartrecruiters.py     # ~4 companies
│   │   ├── bamboohr.py            # ~3 companies
│   │   └── workday.py             # ~15 finance/enterprise companies (POST API)
│   ├── core/
│   │   └── relevance.py           # Multi-signal scoring engine (0–1.0)
│   ├── storage/
│   │   ├── db.py                  # SQLite: jobs, applications, resume_versions, scrape_runs
│   │   ├── profile_manager.py     # Profile + resume + PIN + skill extraction (100+ patterns)
│   │   └── resume_vault.py        # PDF vault + TF-IDF engine + bulk import + filename parser
│   ├── alerts/
│   │   └── notifier.py            # Discord + Telegram dream-job alerts
│   ├── routes/
│   │   ├── vault_routes.py        # Flask Blueprint — 9 vault endpoints
│   │   └── __init__.py
│   ├── server.py                  # 847 lines — Flask API + background scraper + night skip
│   ├── main.py                    # CLI for GitHub Actions + local testing
│   ├── export_data.py             # DB → api-data.json bridge
│   ├── vault_cli.py               # CLI for resume vault operations
│   ├── resume_vault/              # ← vault storage (gitignored)
│   │   ├── pdf/                   # 95 PDFs (Narendranath_{Company}_{Role}.pdf)
│   │   └── text/                  # 73 extracted text files
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # 3882 lines — full React dashboard, 9 tabs
│   │   └── main.jsx
│   ├── public/
│   │   └── api-data.json          # Static fallback (Actions updates hourly)
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .github/workflows/
│   ├── scrape-and-deploy.yml      # Hourly scrape + quiet hours + Pages deploy
│   └── keepalive.yml              # Ping Render every 14 min (business hours)
├── Dockerfile                     # Render deployment
├── render.yaml                    # One-click Render blueprint
├── resume.md                      # Resume content (tracked)
├── CLAUDE.md                      # This file
#  Gitignored (private, intentionally):
#    resume-personal.md, resume-projects.md, resume_narendranath.tex,
#    resumes/, backend/resume_vault/
├── .gitignore
└── README.md
```

---

## Database Schema (SQLite — jobscout.db)

```sql
-- Core job data (deduplicated by external_id)
jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE NOT NULL,
    title, company, location, department, description, url, ats,
    is_remote INTEGER, posted_at TEXT,
    salary_min INTEGER, salary_max INTEGER,
    relevance_score REAL,         -- 0.0–1.0, computed by relevance.py
    matched_skills TEXT,           -- JSON array
    sponsorship INTEGER,           -- H1B detection flag
    first_seen_at TEXT, last_seen_at TEXT, is_active INTEGER
)

-- Application tracker
applications (
    id, external_id TEXT NOT NULL,
    title, company, url,
    status TEXT DEFAULT 'saved',   -- saved | applied | interview | offer | rejected
    relevance_score, salary_min, salary_max, location,
    notes TEXT, resume_version TEXT,
    saved_at TEXT, applied_at TEXT, updated_at TEXT
)

-- Resume versions (tailored per company/role)
resume_versions (
    id, version_key TEXT UNIQUE NOT NULL,   -- "_DE", "_GS", "standard"
    display_name TEXT,
    resume_text TEXT,
    extracted_skills TEXT DEFAULT '[]',
    target_roles TEXT DEFAULT '[]',
    target_companies TEXT DEFAULT '[]',
    notes TEXT, created_at TEXT, updated_at TEXT
)

-- User profile (single row)
user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pin_hash TEXT,                  -- pbkdf2_hmac for dashboard PIN
    resume_text TEXT,
    extracted_skills TEXT DEFAULT '[]',
    custom_skills TEXT DEFAULT '[]',
    preferred_locations TEXT DEFAULT '[]',
    dream_companies TEXT DEFAULT '[]',
    dream_role_keywords TEXT DEFAULT '[]',
    created_at TEXT, updated_at TEXT
)

-- Scrape audit log
scrape_runs (
    id, started_at, finished_at,
    companies_scraped, jobs_found, new_jobs, updated_jobs, errors,
    status TEXT DEFAULT 'running'
)
```

---

## API Endpoints (ALL LIVE on Render)

### Core
| Method | Path | Description |
|--------|------|-------------|
| GET | `/ping` | Keepalive (prevents Render sleep) |
| GET | `/api/data` | Full JSON export for dashboard |
| GET | `/api/health` | Server uptime, cycle count, error rate |
| GET | `/api/stats` | Quick DB stats |
| POST | `/api/scrape` | Manual trigger (optional Bearer auth) |

### Profile & Resume
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/profile` | Get/update user profile |
| GET/POST | `/api/resume` | Get/upload resume text → extract skills |
| POST | `/api/verify-pin` | Check dashboard PIN |
| POST | `/api/set-pin` | Set/change PIN |
| GET | `/api/resume/versions` | List all resume versions |
| POST | `/api/resume/versions` | Save/update a version |
| POST | `/api/resume/versions/upload` | PDF upload → extract text → save |
| GET | `/api/resume/versions/compare?a=X&b=Y` | Skill overlap comparison |
| GET/DELETE | `/api/resume/versions/<key>` | Get/delete specific version |

### Application Tracker
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/applications` | List/save applications |
| DELETE | `/api/applications/<ext_id>` | Remove from tracker |
| GET | `/api/applications/company/<name>` | Full history for a company |
| GET | `/api/applications/export` | Export all as JSON backup |

### Resume Vault (9 endpoints — ✅ live, ✅ wired into dashboard)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/vault/upload` | Upload PDF to vault, extract text, register |
| GET | `/api/vault/list` | List all vault files with metadata |
| POST | `/api/vault/import` | Bulk import from local directory |
| POST | `/api/vault/compare` | TF-IDF cosine similarity between two versions |
| POST | `/api/vault/job-fit` | Resume vs job description fit score |
| POST | `/api/vault/best-match` | Rank ALL resumes against a JD → best fit |
| GET | `/api/vault/stats` | Vault summary (counts, size, companies) |
| GET/DELETE | `/api/vault/version/<key>` | Get/delete specific version |
| GET | `/api/vault/version/<key>/pdf` | Stream the actual PDF bytes for inline view/download |

---

## Scraper Registry

Each module exports `scrape(company: dict) -> Generator[dict]`.
Every yielded dict must contain: `external_id`, `title`, `company`, `location`, `description`, `url`, `ats`.

| Module | ATS | API Pattern | Companies |
|--------|-----|-------------|-----------|
| `greenhouse.py` | Greenhouse | `GET boards-api.greenhouse.io/v1/boards/{slug}/jobs` | ~87 |
| `lever.py` | Lever | `GET api.lever.co/v0/postings/{slug}` | ~4 |
| `ashby.py` | Ashby | `GET api.ashbyhq.com/posting-api/job-board/{slug}` | ~11 |
| `smartrecruiters.py` | SmartRecruiters | `GET api.smartrecruiters.com/v1/companies/{slug}/postings` | ~4 |
| `bamboohr.py` | BambooHR | `GET {slug}.bamboohr.com/careers/list` | ~3 |
| `workday.py` | Workday | `POST {host}/wday/cxs/{slug}/{board}/jobs` | ~15 |

### Tier system (companies.py — 147 total companies across 4 tiers)
- **Tier 0 (28 companies):** Top-of-mind dream companies — scraped every cycle alongside Tier 1
- **Tier 1 (30 companies):** Anthropic, OpenAI, Stripe, Databricks, Snowflake, Netflix, Spotify, Discord, Goldman Sachs, JP Morgan, etc. — every cycle (~5 min)
- **Tier 2 (59 companies):** Figma, Notion, Airbnb, Pinterest, DoorDash, etc. — every 2nd cycle
- **Tier 3 (30 companies):** Visa, KPMG, Bosch, etc. — every 4th cycle
- `get_batch(cycle_number)` returns the correct companies for each cycle

---

## Relevance Engine (core/relevance.py)

Scores each job 0.0–1.0 using weighted signals from `config/profile.py`:

| Signal | Weight | Values |
|--------|--------|--------|
| Core skills match | 40% | python, sql, spark, kafka, airflow, etl, azure, aws, databricks, fabric |
| Secondary skills match | 20% | docker, k8s, terraform, dbt, snowflake, pytorch, mlflow, etc. |
| Title relevance | 15% | "data engineer"→15%, "ml engineer"→14%, "analytics eng"→12%, "platform eng"→8% |
| Location preference | 10% | remote, dallas, tx, texas, austin |
| Experience level | 10% | senior, staff, lead, principal, "4+ years" etc. |
| Sponsorship signal | 5% | +5% for H1B-positive keywords, -5% for "no sponsorship" |

Pre-filter: `is_relevant_title()` rejects titles matching `EXCLUDE_TITLE_KEYWORDS` (recruiter, intern, director, etc.) before scoring.

---

## Resume Vault Engine (storage/resume_vault.py)

### Filename Parser
Handles 150+ real resume files from `C:\Users\naren\OneDrive\Desktop\Resume Easy`:

```
Narendranath_{Company}.pdf              → bloomberg
Narendranath_{Company}_{Role}.pdf       → gs_data (Goldman Sachs, Data Engineer)
Narendranath_Edara_{Company}_{Role}.docx → goldman_sachs_ai_quant_engineer
Naren_{Role}_{Company}.docx             → affirm_de (role-first pattern)
```

**Company aliases:** gs→Goldman Sachs, ms→Morgan Stanley, capitalone→Capital One, jpmc→JPMorgan Chase, sf→Salesforce, att→AT&T, meta→Meta, bofa→Bank of America

**Role aliases:** de→Data Engineer, ml→ML Engineer, ai→AI Engineer, ae→Analytics Engineer, ds→Data Scientist, sde→Software Engineer, dq→Data Quality, quant→Quant Strategist

### TF-IDF Cosine Similarity (pure Python, no sklearn)
- Tokenizer with 100+ stopwords removed
- Smooth IDF: `log((N+1)/(df+1)) + 1`
- Sparse vector cosine similarity (dot product / magnitudes)
- Interpretation thresholds: ≥90% near identical, ≥75% very similar, ≥55% moderately similar, ≥35% different, <35% very different

### Resume vs JD Fit Scoring
- Combined score: 60% skill_match + 40% tfidf_similarity
- `find_best_resume_for_job(job_description)` ranks all 95 versions, returns sorted best-first
- Skill gap analysis: matched, missing, and extra skills per resume

### Vault CLI
```bash
cd backend
python vault_cli.py import "C:\Users\naren\OneDrive\Desktop\Resume Easy"
python vault_cli.py list
python vault_cli.py stats
python vault_cli.py compare gs_data meta_ml
python vault_cli.py job-fit gs_data "We need Python, SQL, Spark..."
python vault_cli.py best-match "Senior Data Engineer with Spark, Kafka..."
python vault_cli.py parse "Narendranath_GS_data.pdf"
```

---

## AutoApply AI — Automated Application System

This is the next major phase: closing the loop from **job discovery → automated application submission**.
The AutoApply AI project (separate repo, Fly.io live) integrates directly with JobScout's vault and scoring infrastructure.

### End-to-End Flow

```
JOBSCOUT DASHBOARD (existing)
  See job → vault picks best resume → click "Auto-Apply"
       │
CHROME EXTENSION
  ├── Detects ATS portal (Greenhouse, Lever, Workday, etc.)
  ├── Reads form fields: name, email, resume upload, work history, free-text questions
  ├── Sends form schema + JD to FastAPI backend
  └── Receives auto-generated answers → fills form fields
       │
FASTAPI BACKEND
  ├── Work History Profile Store (PostgreSQL)
  │   ├── Companies worked at + roles + date ranges
  │   ├── Bullet-point descriptions + technologies + team sizes + metrics
  │   ├── Education, certifications, awards
  │   └── Personal details (name, email, phone, LinkedIn, GitHub)
  │
  ├── Multi-LLM Answer Pipeline
  │   ├── Factual ("First name", "Years of Python") → direct lookup, NO LLM
  │   ├── Short-answer ("Why this company?") → Claude/GPT
  │   ├── Behavioral ("Describe a challenge") → Claude + STAR + matching bullet
  │   ├── Technical ("SQL experience level") → skill matching
  │   └── Cover letter → Claude with JD + resume context
  │
  ├── Resume Selection (vault integration)
  │   ├── POST /api/vault/best-match → picks best resume for JD
  │   └── Auto-attaches correct PDF for upload field
  │
  ├── Application Tracker Sync
  │   ├── Records every application to JobScout's /api/applications
  │   └── Shows "applied here before" in popup
  │
  └── Redis Session Cache
       └── Cache "Why do you want to work here?" templates, customize per company
```

### Integration Points (JobScout → AutoApply)
| JobScout Component | AutoApply Uses It For |
|--------------------|-----------------------|
| `/api/vault/best-match` | Picks right resume PDF for upload field |
| `/api/vault/job-fit` | Shows match % in popup before applying |
| `/api/applications` | Records application after submission |
| `/api/applications/company/<n>` | "Applied here before" in popup |
| `resume_vault/pdf/` | Actual PDF attached to application |
| `profile_manager.py` skill extraction | Maps skills to portal checkboxes/dropdowns |
| Relevance engine scores | Prioritizes which jobs to auto-apply first |

### AutoApply AI — Current State (separate repo)
- **API live:** `https://autoapply-ai-api.fly.dev`
- **Stack:** FastAPI + PostgreSQL/Supabase + Redis/Upstash + Chrome MV3 Extension
- **LLM chain:** Anthropic → OpenAI → Kimi → Ollama → keyword fallback
- **Chrome options page:** LLM token input (Anthropic/OpenAI/Kimi/Ollama) + Clerk auth + API URL
- **Extension sidepanel:** ApplyMode + JobScout multi-job view (JobScout features inside extension)
- **floatingPanel.ts:** Created but NOT wired to vite.config.ts or manifest.json yet
- **End-to-end autofill:** NOT validated on a real ATS page yet

### What's Built vs What's Designed
| Component | Status |
|-----------|--------|
| Resume vault (95 PDFs, TF-IDF, best-match API) | ✅ Built (JobScout) |
| Application tracker (status, company history) | ✅ Built (JobScout) |
| LLM provider chain (Anthropic → Ollama) | ✅ Built (AutoApply AI) |
| GitHub vault (versions/applications/private) | ✅ Built (AutoApply AI) |
| Chrome extension (options, sidepanel, worker) | ⚠ Partial — not e2e tested |
| floatingPanel.ts autofill | ❌ Not wired up |
| Work history profile store (PostgreSQL) | ❌ Designed only |
| Multi-LLM routing per question type | ❌ Designed only |
| Portal form field detection (DOM parsing) | ❌ Designed only |
| Redis answer cache | ❌ Designed only |

---

## Alert System (alerts/notifier.py)

Fires when ALL conditions match on a NEW job:
1. Company is in `DREAM_COMPANIES` list
2. Role title contains a `DREAM_ROLE_KEYWORDS` entry
3. `relevance_score >= 0.70`

**Channels:** Discord webhook + Telegram Bot (both free forever)

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXX/YYY
TELEGRAM_BOT_TOKEN=1234567890:AAF...
TELEGRAM_CHAT_ID=987654321
```

---

## Dashboard (frontend/src/App.jsx — 1805 lines + 22 modules)

React 18 + Vite + Recharts. Single-file component.

### 9 Tabs
1. **Jobs** — Ranked search, multi-filter, job cards with logos, relevance bars, skills pills, H1B badge, expandable descriptions, "Applied here" badge, **Resume Match % chip** (auto-fetched from default vault resume, color + icon coded), **"📄 Find Best Resume" button** (ranks all vault resumes against the JD, top-N drawer with PDF download), **status pills** that sync to the application tracker
2. **Rare** — Subset of Jobs filtered to roles requiring rare/in-demand skills (counts surface in the tab label)
3. **Analytics** — ATS distribution pie, salary range bar, 30-day posting trend
4. **Companies** — Logo grid with job counts and sample roles
5. **Trends** — Posting timeline, top companies by volume
6. **Tracker** — Application status board, resume version manager, localStorage + API sync
7. **Vault** — Stats panel, upload form, compare two versions (TF-IDF + skill diff), browse/search/sort all PDFs, set default resume, delete versions — all wired to live `/api/vault/*` endpoints
8. **Pipeline** — Kanban of applications by stage (Saved → Applied → Phone → Offer → Rejected)
9. **Monitor** — Server health, pipeline status, manual scrape trigger

### Ranked Search Algorithm (10 tiers)
1. Exact title match → 100
2. Title starts with query → 90
3. Title contains exact phrase → 80
4. All query words in title → 70
5. Company name match (alias-aware) → 60
6. Skills match → 50
7. Location match → 40
8. Description contains query → 30
9. Partial word match in title → 20
10. Partial match in description → 10

---

## Implementation History

| Version | Key changes |
|---------|------------|
| v1.0 | Greenhouse scraper, SQLite, Flask, basic React |
| v2.0 | 100+ companies, 5 ATS, tiered scheduling, GitHub Actions, relevance engine |
| v2.5 | Workday (7 finance cos), alerts (Slack/Twilio→Discord/Telegram), mobile, 10-tier search, night skip, ProfileManager |
| v3.0 | Discord+Telegram free forever, application tracker, PIN security, 6-tab dashboard, 13 new API endpoints |
| v3.1 | Resume vault (resume_vault.py 844 lines), vault Blueprint (9 endpoints live), bulk import 95 PDFs, vault CLI |
| v3.2 | In-app server-setup panel (SetupPanel) + self-describing root endpoint — no more `.env` / DevTools setup, root `/` now auto-discovers routes |

---

## What Worked / What Didn't

**Worked:** Public ATS APIs stable · SQLite WAL for concurrent read/write · Discord free forever · Dual-source hook (live API → static JSON) · TF-IDF pure Python · Filename parser for 150+ naming patterns

**Didn't work / required fixes:**
- Slack (paid after 30d) → Discord
- Twilio → Telegram
- Workday URL variations (wd1/wd5/oraclecloud) — had to detect and branch
- Night schedule timezone math — CST→UTC was off 1hr, fixed to: `360 <= utc_mins < 690`
- GitHub Actions budget — hourly=2880min (over 2000 limit) → 9×/day=1080min
- server.py import order — vault_bp must go AFTER `app = Flask(__name__)`
- pdfplumber vs pypdf — two PDF libs in use, should standardize

---

## Key Design Decisions

| Decision | Why |
|----------|-----|
| Batch (5-min) over streaming | Jobs post hourly — streaming = 10x cost for zero benefit |
| SQLite over Postgres (JobScout) | Single-writer, zero-config, WAL handles concurrency, $0 |
| Postgres for work history (AutoApply) | Relational — company→role→bullets needs foreign keys |
| TF-IDF over embeddings | Pure Python, no ML deps, fast for 95 docs |
| Discord/Telegram over Slack | Free forever vs 30-day trial |
| GitHub Actions over Airflow | No infra to manage, free tier sufficient |
| React SPA on GitHub Pages | Static hosting = $0 |
| Chrome extension over Selenium | Real browser session — sees cookies, works with 2FA |
| Redis for answer cache | Cache question templates, customize per company, save LLM calls |
| Privacy-first (local data) | All personal data local/self-hosted |
| FastAPI over Flask (AutoApply) | Async for concurrent LLM calls |
| Multi-LLM routing | Factual=no LLM, behavioral=Claude, short=GPT — route by type to minimize cost |

---

## Technical Debt

1. AutoApply end-to-end loop never validated on a real ATS page
2. Work history not in a queryable database yet
3. No portal form field mapping per ATS (each has different DOM)

Resolved (no longer debt):
- ~~App.jsx 3886-LOC monolith~~ — split into 1805-LOC orchestrator + 22 focused
  files across `lib/`, `components/`, `tabs/`. (PRs #69-85, May 2026)
- ~~server.py 905-LOC monolith~~ — split into 184-LOC orchestrator + 7 focused
  files across `core/` and `routes/`. (PRs #60-67, May 2026)
- ~~Vault has no dashboard UI~~ — full tab + best-match + chip + upload + compare all wired
- ~~No pytest suite~~ — 17 test files, 219 passing tests covering vault hardening,
  relevance, scrape orchestrator, applications API, admin routes, profile manager,
  the new JD-payload cap (#41), the unified DELETE behavior (#44),
  the pypdf consolidation (#58), and Workday URL-triple validation (#59)
- ~~Untracked resume files at repo root~~ — `resume.md` was always tracked;
  `resume-projects.md`, `resume_narendranath.tex`, `resume-personal.md` are
  gitignored on purpose (private content, never intended to commit)
- ~~pdfplumber + pypdf coexistence~~ — pdfplumber retired; pypdf is the single
  PDF library, with a regression test (`test_pdfplumber_no_longer_imported_anywhere`)
  pinning the decision
- ~~Workday coverage only 9 companies~~ — bumped to 15 (Adobe, Cisco, Mastercard,
  Charles Schwab, BNY Mellon, State Street added). Plus 3 new test guards
  (URL-triple completeness, valid wd_instance subdomain, no duplicate names).

---

## Environment Variables

```bash
# Render (required)
PORT=10000

# Server (optional)
DB_PATH=./jobscout.db
FAST_INTERVAL=300
SCRAPE_DELAY=0.3
API_SECRET=your_secret

# Vault storage backend (see storage/vault_backend.py)
# Defaults to "local" — writes to backend/resume_vault/.
# On Render free tier (ephemeral disk), set to "r2" and provide R2 creds.
VAULT_BACKEND=local                                    # or "r2"
RESUME_VAULT_PATH=./backend/resume_vault                # only when VAULT_BACKEND=local
R2_ACCOUNT_ID=<cloudflare account>                     # required when r2
R2_BUCKET=<bucket name>                                # required when r2
R2_ACCESS_KEY_ID=<key id>                              # required when r2
R2_SECRET_ACCESS_KEY=<secret>                          # required when r2
R2_REGION=auto                                         # optional, default "auto"

# Alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXX/YYY
TELEGRAM_BOT_TOKEN=1234567890:AAF...
TELEGRAM_CHAT_ID=987654321

# Frontend (.env in frontend/)
VITE_RENDER_URL=https://your-app.onrender.com
```

### Vault storage backends

Pluggable storage for PDFs + extracted text (`storage/vault_backend.py`):

- **LocalVaultBackend** (default) — writes to `backend/resume_vault/pdf/`
  and `text/`. Same layout as before the backend refactor.
- **R2VaultBackend** — Cloudflare R2 (S3-compatible). Keys mirror the
  local layout: `pdf/<filename>` and `text/<version_key>.txt`. Custom
  metadata field `submitted-at` preserves the application date so the
  dashboard's `modified_at` survives the round-trip through object
  storage.

On `VAULT_BACKEND=r2`, server startup runs a lazy rehydrate:
`rehydrate_metadata_from_vault()` walks the bucket and rebuilds
`resume_versions` rows when the SQLite DB is empty. This is the recovery
path for Render's free-tier ephemeral disk — PDFs survive cold starts
in R2, and the DB self-heals from them on boot.

---

## Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py --fast          # Tier 1 only (~30s)
python main.py                 # All 109 companies (~3 min)
python server.py               # API server on :10000

# Frontend
cd frontend
npm install && npm run dev     # Vite dev server on :5173

# Resume Vault CLI
cd backend
python vault_cli.py stats
python vault_cli.py best-match "Senior Data Engineer with Spark, Kafka, Azure..."
python vault_cli.py compare gs_data meta_ml
```

---

## Roadmap

### Phase 1: Vault UI Integration (immediate)
1. Build vault tab in App.jsx — browse, stats, compare, upload
2. Wire `POST /api/vault/best-match` into job cards
3. Add job-fit score chips — "Resume Match: 87%"
4. Resume recommendation flow — see job → best resume → download

### Phase 2: AutoApply AI — Core Pipeline
1. Work history profile store — PostgreSQL schema
2. FastAPI backend — question classification, answer generation, form field mapping
3. Multi-LLM routing — Claude for behavioral, GPT for short, direct lookup for factual
4. Redis cache — common question-answer patterns

### Phase 3: AutoApply AI — Chrome Extension
1. Wire floatingPanel.ts into vite.config.ts + manifest.json
2. Form field detection — DOM parsing per ATS
3. Pop-up UI — auto-fill status, confidence scores, application history
4. Auto-fill engine + application tracker sync

### Phase 4: Polish
- GitHub-based resume versioning with diff tracking
- Batch auto-apply queue
- Vector embeddings (sentence-transformers) to upgrade TF-IDF
- Answer quality feedback loop

---

## Resume Quality Standards (aligned with tailor-resume skill)

All resumes scored or rendered through JobScout must conform to the STAR + 2-line standard:

- **Every bullet ≤20 words** and contains an Action verb + measurable Result (%, $, time, count)
- **STAR enforced in code** via `~/.claude/skills/tailor-resume/scripts/star_validator.py`
  - `score_star(text)` → STARScore with `passes: bool` and `violations: list`
  - `bullet_quality_score(bullet_dict)` → float 0.0–1.0 composite quality signal
- **ATS scoring formula** — use `jd_gap_analyzer.estimate_ats_score()` for gap scoring:
  `40% keyword overlap + 30% category coverage + 20% bullet quality + 10% seniority signal`
- **Resume vault scoring** (`storage/resume_vault.py`) already uses `60% skill_match + 40% tfidf`.
  Long-term: incorporate `bullet_quality_score` into the vault relevance ranking.

---

## Next Steps (priority order)

Done (kept for history):
- ~~Build vault UI tab in App.jsx~~ → shipped, full tab with stats / upload / compare / browse
- ~~Wire best-match into job cards~~ → shipped, "📄 Find Best Resume" button with ranked drawer
- ~~Add job-fit chips on cards~~ → shipped, lazy-fetched per-card chip with WCAG-compliant
  color+icon coding (concurrency-capped at 5, 60-card visible slice)
- ~~Add pytest suite~~ → shipped, 17 test files / 210 passing tests
- ~~#35 vault upload path traversal~~ → closed; whitelist regex + realpath + 80-char caps
- ~~#36 PDF magic-byte + 10MB size cap~~ → closed; storage + route layer
- ~~#39 Default-resume chip + PDF download~~ → closed; both Approach A and Gap 2 shipped
- ~~#41 Unbounded job_description DoS~~ → closed; 50KB cap on best-match + job-fit
- ~~#44 DELETE endpoint inconsistency~~ → closed; legacy endpoint now routes through delete_vault_version

Open (priority order):
1. Design work history PostgreSQL schema (AutoApply prerequisite)
2. Wire up `floatingPanel.ts` in the AutoApply Chrome extension
3. Validate end-to-end AutoApply loop on a real ATS page
4. Browser smoke-test all 9 tabs after the App.jsx split (PRs #69-85) —
   the Vite build is clean but visual correctness needs interactive
   verification. Spot-check Jobs/Vault/Tracker/Pipeline first since they
   have the highest interactivity.
