# JobScout — Personal Job Discovery Dashboard

Zero-cost, real-time job scraper + intelligent React dashboard built for data engineers and ML professionals. Monitors 130+ companies across 6 ATS platforms, sends dream-job alerts via Discord and Telegram (free forever), and builds a semantic memory of every resume version and company you've ever applied to.

## Features

| Feature | Details |
|---------|---------|
| **130+ companies** | Greenhouse, Lever, Ashby, SmartRecruiters, BambooHR, Workday |
| **Finance & Big Tech** | Goldman Sachs, JP Morgan, Walmart, Disney, Target, Amex, Deloitte |
| **Real-time scraping** | Render: Tier 1 every 5 min · GitHub Actions: all 130+ every 2 hrs |
| **Smart scheduling** | Skips 12am–5:30am CST — no new roles overnight |
| **Dream job alerts** | Discord webhook + Telegram Bot — free forever, fires instantly |
| **Ranked search** | Exact title → title contains → company (alias-aware) → skills → description |
| **Search autocomplete** | Ranked company suggestions dropdown — prefix first, then substring, tier badges |
| **Company priority panel** | Drag-to-reorder priority list with Score Boost (×1.5→×1.05 multipliers) or Hard Sort (pin to top) |
| **Resume versions** | Store _DE, _GS, _SWE, _AI, custom — extract skills from each |
| **Application memory** | Track status, resume used, notes; see full history per company |
| **"Applied here" badge** | Expand any job card to see your history at that company |
| **Multi-user Supabase auth** | GitHub + Google OAuth + email magic link; each user gets their own profile, priorities, and preferences |
| **Profile & PIN** | Legacy PIN auth still works alongside Supabase for dev/scraper use |
| **Mobile responsive** | Works on phone, tablet, desktop |
| **Manual triggers panel** | Live progress bar + concurrency-safe scrape + 5 admin ops (Doctor, Purge, Re-extract, Vault Re-index, Clear Cache) |
| **Live scrape progress** | Real-time polling: current company, completed/total, jobs found, ETA |
| **Doctor health-check** | One-click readiness probe: DB, scrapers, recent runs, env vars, vault, disk |
| **Dark / Light theme** | Persists in memory |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  RENDER (FREE)                       │
│  Flask + Background Thread                           │
│  ├── Every 5 min:  Tier 1 (24 companies)             │
│  ├── Every 60 min: All tiers (full sweep)            │
│  ├── Night skip:   12am–5:30am CST paused            │
│  ├── Dream alerts: Discord + Telegram on new job     │
│  └── SQLite DB:    jobs + profile + resume versions  │
│                                                      │
│  API Endpoints:                                      │
│    GET  /api/data                → JSON for dashboard│
│    GET  /api/health              → server status     │
│    POST /api/scrape              → manual trigger    │
│    GET  /api/profile             → user profile      │
│    POST /api/resume              → upload resume     │
│    POST /api/resume/versions     → save version      │
│    GET  /api/resume/versions     → list versions     │
│    GET  /api/applications        → tracker data      │
│    GET  /api/applications/company/<name> → history   │
│    POST /api/verify-pin          → check PIN         │
└──────────────────────┬──────────────────────────────┘
                       │ primary source (~5 min fresh)
┌──────────────────────▼──────────────────────────────┐
│             REACT DASHBOARD (GitHub Pages)           │
│  ├── Jobs: ranked search, multi-filter, pagination   │
│  ├── Analytics: ATS pie, salary bar, 30-day trend    │
│  ├── Companies: logo grid + sample roles             │
│  ├── Trends: posting timeline + top companies        │
│  ├── Tracker: resume versions, application history   │
│  └── Monitor: health, manual triggers, run history   │
└──────────────────────▲──────────────────────────────┘
                       │ fallback (~2 hr fresh)
┌──────────────────────┴──────────────────────────────┐
│              GITHUB ACTIONS (FREE)                   │
│  ├── 9×/day scrape  (skip 12am–5:30am CST)          │
│  ├── Manual dispatch (full or fast mode)             │
│  ├── Export api-data.json → commit → deploy Pages   │
│  └── Budget: ~1,080 min/month (free tier = 2,000)   │
└──────────────────────────────────────────────────────┘
```

## Fork Setup Guide

Six steps to make this your own:

**1. Clone & configure skills**
```bash
git clone https://github.com/narendranathe/job-scout.git
cd job-scout
# Edit backend/config/profile.py — your skills, locations, experience level
```

**2. Test locally**
```bash
cd backend
pip install -r requirements.txt
python main.py --fast    # Tier 1 only (~30 sec)
python main.py           # All companies (~3 min)
python main.py --stats   # Check results
```

**3. Deploy to Render**
1. Go to [render.com](https://render.com) → New → Blueprint → connect this repo
2. Render reads `render.yaml` → deploys automatically
3. Note your URL from the Render dashboard. Render usually appends a
   random suffix when the service name is taken, so it'll look like
   `https://jobscout-api-lasz.onrender.com` rather than
   `https://jobscout-api.onrender.com`. Always copy it from the
   service page — don't guess.

**4. Connect dashboard**
- Easiest (v3.1+): open the deployed dashboard, click ⚙️ in the header,
  paste your URL into the **Server Settings** panel, and click Save.
  Stored in browser localStorage — no rebuild needed.
- Or via env (for CI builds):
  ```bash
  cd frontend
  cp .env.example .env
  # Edit .env: VITE_RENDER_URL=https://jobscout-api-lasz.onrender.com
  ```

**5. Push to GitHub + enable Pages**
```bash
git add -A && git commit -m "config: personal profile"
git push
```
In GitHub: **Settings → Pages → Source: GitHub Actions**

Add secrets (**Settings → Secrets → Actions**):
- `RENDER_URL` — your Render URL
- `API_SECRET` — optional auth token
- `VITE_SUPABASE_URL` — Supabase project URL (required for auth)
- `VITE_SUPABASE_ANON_KEY` — Supabase anon key (required for auth)

**6. Set up alerts (Discord + Telegram — free forever)**

See [Dream Job Alerts](#dream-job-alerts) below.

---

## Dream Job Alerts

Get notified the moment a dream role appears. Both platforms are **free with no expiry**.

### Discord (Recommended — easiest)

1. Open any Discord server → **Edit Channel → Integrations → Webhooks → New Webhook**
2. Copy the webhook URL
3. Add to Render environment variables:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXX/YYY
```

### Telegram Bot

1. Message [@BotFather](https://t.me/botfather) → `/newbot` → follow prompts → copy token
2. Start your bot in Telegram, then get your chat ID:
```bash
curl https://api.telegram.org/bot<TOKEN>/getUpdates
```
3. Add to Render environment variables:

```
TELEGRAM_BOT_TOKEN=1234567890:AAF...
TELEGRAM_CHAT_ID=987654321
```

### Alert trigger conditions

Both conditions must match for an alert to fire:

```
DREAM_COMPANIES=Anthropic,OpenAI,Stripe,Databricks,Goldman Sachs
DREAM_ROLE_KEYWORDS=data engineer,ml engineer,ai engineer
DREAM_ALERT_SCORE=0.70
```

The alert fires when: **company in DREAM_COMPANIES AND role keyword in title AND relevance_score ≥ 0.70**

### Legacy options (not free long-term)

- **Slack** — 30-day free trial, then requires paid plan
- **WhatsApp (Twilio)** — $15 trial credit, then ~$0.005/message

---

## Resume Personalization

### Upload your main resume

Upload resume text to extract skills and personalize relevance scores:

```bash
curl -X POST https://your-render-url.onrender.com/api/resume \
  -H "Content-Type: application/json" \
  -d '{"resume_text": "Python, Spark, Airflow, AWS, dbt, Snowflake, Kafka..."}'

# Response:
# {"status": "ok", "skills_extracted": 14, "skills": ["python", "spark", ...]}
```

### Resume Version Manager

The Tracker tab has a built-in Resume Version Manager. Each version stores:
- **version_key** — short ID like `_DE`, `_GS`, `standard`
- **display_name** — readable label like "Data Engineering" or "Goldman Sachs"
- **resume_text** — full plain text (for skill extraction)
- **target_companies** — which companies received this version
- **extracted_skills** — auto-detected from text

Via API:
```bash
# Save a version
curl -X POST https://your-render-url.onrender.com/api/resume/versions \
  -H "Content-Type: application/json" \
  -d '{"version_key":"_DE","display_name":"Data Engineering","resume_text":"Python Spark Airflow..."}'

# List all versions
curl https://your-render-url.onrender.com/api/resume/versions

# Get one version (includes full text)
curl https://your-render-url.onrender.com/api/resume/versions/_DE
```

---

## Application Memory

JobScout remembers every company you've applied to:

- **"Already applied here" badge** — Expand any job card from a company you've applied to and see your full history: role title, date applied, resume version used, current status
- **Tracker tab** — Full list with status buttons (saved / applied / interview / offer / rejected), notes, and resume version picker
- **Company history API** — Query your history for any company:

```bash
curl https://your-render-url.onrender.com/api/applications/company/Goldman%20Sachs
# Returns: {company, applied: true, applications: [{title, status, resume_version, applied_at}]}
```

---

## ATS Coverage

| ATS | Companies | API |
|-----|-----------|-----|
| Greenhouse | 87 | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` |
| Lever | 4 | `api.lever.co/v0/postings/{slug}` |
| Ashby | 11 | `api.ashbyhq.com/posting-api/job-board/{slug}` |
| SmartRecruiters | 4 | `api.smartrecruiters.com/v1/companies/{slug}/postings` |
| BambooHR | 3 | `{slug}.bamboohr.com/careers/list` |
| Workday | 7 | `{slug}.wd1.myworkdayjobs.com/wday/cxs/{slug}/{board}/jobs` |

### Finding ATS slugs

| ATS | How to find slug |
|-----|-----------------|
| Greenhouse | `boards.greenhouse.io/**slug**/jobs` |
| Lever | `jobs.lever.co/**slug**` |
| Ashby | `jobs.ashbyhq.com/**slug**` |
| SmartRecruiters | `careers.smartrecruiters.com/**slug**` |
| BambooHR | `**slug**.bamboohr.com/careers` |
| Workday | `**slug**.wd1.myworkdayjobs.com` — slug = subdomain, board = path segment |

---

## Manual Triggers Panel (Monitor tab)

The dashboard ships a six-card maintenance panel for live operations. Every card respects the same `API_SECRET` Bearer auth as `/api/scrape`.

| Card | What it does | Endpoint |
|------|--------------|----------|
| 🚀 **Trigger Render Scrape** | Fires a fast scrape (Tier 1, ~30s). Returns `202` and starts streaming live progress (current company, X/Y companies, jobs found). Returns `409` if a scrape is already running; UI shows the running scrape's progress bar instead of the button. | `POST /api/scrape` + `GET /api/scrape/status` |
| ⚡ **Trigger GitHub Actions** | External link to the workflow manual dispatch (full or fast). | — |
| 🩺 **Doctor** | Health-check probe: DB connectivity, all 6 scrapers importable, recent successful scrape run, env vars, vault dirs writable, disk space. Each check returns pass/warn/fail. | `GET /api/admin/doctor` |
| 🗑️ **Purge Stale Jobs** | Deletes inactive jobs older than N hours (default 96). Returns count. Refuses (`409`) during an active scrape. Confirm dialog before fire. | `POST /api/admin/purge-stale` |
| 🧠 **Re-extract Skills** | Reruns skill extraction across all stored resume versions. Returns count updated. | `POST /api/admin/reextract-skills` |
| 📚 **Vault Re-index** | Rebuilds the in-memory TF-IDF index from `resume_vault/text/`. Returns count + duration. | `POST /api/admin/vault-reindex` |
| ♻️ **Clear DB Cache** | Runs `VACUUM` on the SQLite DB. Returns bytes reclaimed. Refuses (`409`) during an active scrape. Confirm dialog before fire. | `POST /api/admin/clear-cache` |

### Live Progress Architecture

```
                 broker.start(mode, total)
                 broker.tick(company, found, new)
                 broker.finish(stats)
                       │
            ┌──────────┴──────────┐
            │                     │
   /api/scrape (manual)     5-min background thread
            │                     │
            └─────────┬───────────┘
                      ▼
               core/scrape_status.py (singleton broker)
                      ▲
                      │ GET /api/scrape/status (1.5s polling)
                      │
                Frontend progress bar
```

A single thread-safe broker (`core/scrape_status.py`) tracks scrape state. Both the manual trigger and the 5-min cron report through it. The broker has a 10-min watchdog — if a scrape thread dies without calling `finish()`, the next status read reports `is_running: false`.

### Backend CLI

```bash
# Manual scrape — same orchestrator, no progress feedback
python main.py            # full sweep (all 130+ companies)
python main.py --fast     # Tier 1 only (~30 sec)

# Adjust per-request delay (formerly the --delay flag; now an env var)
SCRAPE_DELAY=0.5 python main.py --fast
```

### Direct API

```bash
# Trigger scrape (returns 202 with snapshot, or 409 if running)
curl -X POST https://your-render-url.onrender.com/api/scrape \
  -H "Authorization: Bearer YOUR_API_SECRET"

# Poll status (returns broker snapshot)
curl https://your-render-url.onrender.com/api/scrape/status

# Run doctor (read-only health-check)
curl https://your-render-url.onrender.com/api/admin/doctor | python -m json.tool
```

---

## File Structure

```
job-scout/
├── backend/
│   ├── config/
│   │   ├── companies.py         # 130+ companies — 6 ATS platforms + Workday
│   │   └── profile.py           # Your skills, locations, experience level
│   ├── scrapers/
│   │   ├── greenhouse.py        # 87 companies
│   │   ├── lever.py             # 4 companies
│   │   ├── ashby.py             # 11 companies
│   │   ├── smartrecruiters.py   # 4 companies
│   │   ├── bamboohr.py          # 3 companies
│   │   ├── workday.py           # 7 finance companies
│   │   └── utils.py             # shared HTTP helpers
│   ├── core/
│   │   ├── relevance.py          # Keyword scoring engine (0–100%)
│   │   ├── scrape_orchestrator.py # Canonical run_scrape() — shared by CLI + server
│   │   └── scrape_status.py      # Thread-safe broker for live progress
│   ├── routes/
│   │   ├── vault_routes.py       # 8 resume-vault endpoints
│   │   └── admin_routes.py       # Doctor + 5 destructive/maintenance ops
│   ├── storage/
│   │   ├── db.py                 # SQLite: jobs + applications + resume_versions
│   │   ├── db_admin.py           # Purge + VACUUM helpers used by admin_routes
│   │   ├── profile_manager.py    # Profile + resume storage + skill extraction
│   │   └── resume_vault.py       # PDF vault + TF-IDF engine
│   ├── alerts/
│   │   └── notifier.py           # Discord + Telegram dream-job alerts
│   ├── server.py                 # Flask API + background scraper + night skip
│   ├── main.py                   # CLI (GitHub Actions + local testing)
│   ├── export_data.py            # DB → api-data.json
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   └── App.jsx              # Full React dashboard (mobile responsive)
│   ├── public/
│   │   └── api-data.json        # Static fallback (Actions updates 9×/day)
│   └── package.json
├── .github/workflows/
│   └── scrape-and-deploy.yml    # 9×/day scrape (skip 12am–5:30am CST) + Pages deploy
├── Dockerfile                   # Render deployment
├── render.yaml                  # One-click Render blueprint
└── README.md
```

---

## Customization

### Add a company
```python
# backend/config/companies.py
{"name": "Acme Corp", "ats": "greenhouse", "slug": "acmecorp", "tier": 2},

# For Workday:
{"name": "Big Bank", "ats": "workday", "slug": "bigbank", "wd_instance": "wd5", "wd_board": "ExternalCareers", "tier": 3},
```

### Update your profile
```python
# backend/config/profile.py
PROFILE = {
    "core_skills": ["python", "sql", "spark", "kafka", "airflow", "dbt", "snowflake"],
    "preferred_locations": ["remote", "dallas", "tx", "austin"],
    "experience_keywords": ["senior", "staff", "lead"],
    "needs_sponsorship": True,
}
```

### Change scrape frequency
```
# Render environment variable:
FAST_INTERVAL=180   # 3 min instead of 5 min
```

---

## Schedule & Budget

### GitHub Actions runs per day
Cron: `20 0,2,4,12,14,16,18,20,22 * * *` (skips 6, 8, 10 UTC = 12am–4am CST)

| Workflow | Runs/day | Min/run | Monthly |
|----------|----------|---------|---------|
| Full sweep + deploy | 9 | ~4 min | ~1,080 min |

GitHub free tier: **2,000 min/month** — well within budget.

### Render (free tier)
- Tier 1 scrape every 5 min during active hours
- Full sweep every 60 min
- GitHub Actions keepalive pings `/ping` every 14 min to prevent sleep

**Total cost: $0/month.**

---

## Authentication Setup (Supabase)

JobScout uses Supabase for multi-user auth. Add these to your Render service environment and GitHub Actions secrets:

| Variable | Where | Value |
|----------|-------|-------|
| `SUPABASE_JWT_SECRET` | Render env | Supabase Settings → API → JWT Settings → JWT Secret |
| `GITHUB_TOKEN` | Render env | GitHub PAT with `repo` scope — enables auto-filing issues for unknown companies |
| `VITE_SUPABASE_URL` | GitHub Actions secret | Supabase Settings → API → Project URL |
| `VITE_SUPABASE_ANON_KEY` | GitHub Actions secret | Supabase Settings → API → `anon / public` key |

In Supabase → Authentication → Providers: enable GitHub and/or Google (each needs an OAuth App from that platform with the Supabase callback URL).

In Supabase → Authentication → URL Configuration → Site URL: set to your GitHub Pages URL (e.g. `https://yourusername.github.io/job-scout/`).

---

## Roadmap

Features intentionally deferred (not in scope for free-tier personal use):

- **Score weight dial wiring** — ScoreWeightDials UI is live and persisted; multiply each relevance component by the normalized weight to make sliders affect ranking
- **CompanyPriorityPanel add-company modal** — connect the "+" button to an overlay using CompanyAutocomplete; unify the two "add to priority" paths
- **LinkedIn OAuth** — LoginPage has the button; Supabase provider setup needed
- **Vector embeddings** — sentence-transformers for true semantic job matching (needs ML model runtime)
- **AI resume tailoring** — Claude API to rewrite bullets targeting a specific JD
- **PDF auto-import** — read local PDF resume files server-side (security boundary)
- **Interview prep** — company-specific question bank linked to tracked applications
