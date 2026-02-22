# JobScout — Personal Job Discovery Dashboard

Zero-cost, real-time job scraper + intelligent React dashboard built for data engineers and ML professionals. Monitors 120+ companies across 6 ATS platforms, sends dream-job alerts via Slack/WhatsApp, and personalizes results from your resume.

## Features

| Feature | Details |
|---------|---------|
| **120+ companies** | Greenhouse, Lever, Ashby, SmartRecruiters, BambooHR, Workday |
| **Finance companies** | Goldman Sachs, Capital One, Walmart, Disney, Target, Amex, Deloitte |
| **Real-time scraping** | Render: Tier 1 every 5 min · GitHub Actions: all 120+ every 2 hrs |
| **Smart scheduling** | Skips 12am–5:30am CST — no new roles overnight |
| **Dream job alerts** | Slack webhook + WhatsApp (Twilio) — fires instantly on new matches |
| **Ranked search** | Exact title → title contains → company → skills → description |
| **Resume personalization** | Upload resume → extract skills → personalize relevance scores |
| **Profile & PIN** | Store preferences, dream companies, access PIN via Render API |
| **Mobile responsive** | Works on phone, tablet, desktop |
| **Manual triggers** | Dashboard button to kick off Render scrape, GitHub Actions link |
| **Dark / Light theme** | Persists in memory |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  RENDER (FREE)                       │
│  Flask + Background Thread                           │
│  ├── Every 5 min:  Tier 1 (24 companies)             │
│  ├── Every 60 min: All tiers (full sweep)            │
│  ├── Night skip:   12am–5:30am CST paused            │
│  ├── Dream alerts: Slack + WhatsApp on new job       │
│  └── SQLite DB:    jobs + profile + resume           │
│                                                      │
│  API Endpoints:                                      │
│    GET  /api/data      → JSON for dashboard          │
│    GET  /api/health    → server status               │
│    POST /api/scrape    → manual trigger              │
│    GET  /api/profile   → user profile                │
│    POST /api/resume    → upload resume               │
│    POST /api/verify-pin → check PIN                  │
└──────────────────────┬──────────────────────────────┘
                       │ primary source (~5 min fresh)
┌──────────────────────▼──────────────────────────────┐
│             REACT DASHBOARD (GitHub Pages)           │
│  ├── Jobs: ranked search, multi-filter, pagination   │
│  ├── Analytics: ATS pie, salary bar, 30-day trend    │
│  ├── Companies: logo grid + sample roles             │
│  ├── Trends: posting timeline + top companies        │
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

## Setup (15 min)

### 1. Clone & configure

```bash
git clone https://github.com/narendranathe/job-scout.git
cd job-scout
```

Edit your profile:
```bash
# backend/config/profile.py — set your skills, locations, experience level
```

### 2. Test locally

```bash
cd backend
pip install -r requirements.txt

python main.py --fast    # Tier 1 only (~30 sec)
python main.py           # All companies (~3 min)
python main.py --stats   # Check results
```

### 3. Deploy Render

1. Go to [render.com](https://render.com) → New → Blueprint → connect this repo
2. Render reads `render.yaml` → deploys automatically
3. Note your URL: `https://jobscout-api.onrender.com`

### 4. Connect dashboard to Render

```bash
cd frontend
cp .env.example .env
# Edit .env: VITE_RENDER_URL=https://jobscout-api.onrender.com
```

### 5. Push to GitHub + enable Pages

```bash
git add -A && git commit -m "config: render url"
git push
```

In GitHub: **Settings → Pages → Source: GitHub Actions**

Add these secrets (**Settings → Secrets → Actions**):
- `RENDER_URL` — your Render URL
- `API_SECRET` — optional auth token

### 6. Verify

After ~5 min, check the Monitor tab — all 5 checks should be green.

---

## Dream Job Alerts

Get notified via **Slack** and/or **WhatsApp** the moment your dream role appears at a dream company.

### Setup Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create App → Incoming Webhooks
2. Activate webhooks → Add to workspace → copy the webhook URL
3. Add to Render environment variables:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

### Setup WhatsApp (Twilio)

1. Sign up at [twilio.com](https://www.twilio.com) → free trial ($15 credit)
2. Enable WhatsApp Sandbox: console.twilio.com → Messaging → Try it out → Send a WhatsApp message
3. Follow the sandbox join instructions (send a WhatsApp message to the Twilio number)
4. Add to Render environment variables:

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_TO=whatsapp:+1XXXXXXXXXX
```

### Configure what triggers alerts

```
DREAM_COMPANIES=Anthropic,OpenAI,Stripe,Databricks,Snowflake
DREAM_ROLE_KEYWORDS=data engineer,ml engineer,data scientist
```

The alert fires when **both** conditions match: company in DREAM_COMPANIES **AND** role keyword in job title.

---

## Resume Personalization

Upload your resume text to Render — the backend extracts 50+ skills automatically and weights your job relevance scores accordingly.

```bash
# Via curl:
curl -X POST https://your-render-url.onrender.com/api/resume \
  -H "Content-Type: application/json" \
  -d '{"resume_text": "Python, Spark, Airflow, AWS, dbt, Snowflake..."}'

# Response:
# {"status": "ok", "skills_extracted": 12, "skills": ["python", "spark", "airflow", ...]}
```

The extracted skills merge with `backend/config/profile.py` core skills for scoring.

### Update profile preferences

```bash
curl -X POST https://your-render-url.onrender.com/api/profile \
  -H "Content-Type: application/json" \
  -d '{
    "dream_companies": ["Anthropic", "OpenAI", "Stripe"],
    "dream_role_keywords": ["data engineer", "ml engineer"],
    "preferred_locations": ["remote", "dallas", "austin"],
    "custom_skills": ["dbt", "kafka", "terraform"]
  }'
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

## Manual Triggers

### Dashboard (Monitor tab)
- **Trigger Render Scrape** — kicks off a full scrape on Render immediately
- **Open GitHub Actions** — link to run the workflow manually (full or fast mode)

### GitHub Actions (manual dispatch)
Go to: `Actions → Full Sweep & Deploy → Run workflow`
- Choose `full` (all 120+ companies, ~3 min) or `fast` (Tier 1 only, ~30 sec)

### API
```bash
# Trigger full scrape via API
curl -X POST https://your-render-url.onrender.com/api/scrape \
  -H "Authorization: Bearer YOUR_API_SECRET"
```

---

## File Structure

```
job-scout/
├── backend/
│   ├── config/
│   │   ├── companies.py         # 120+ companies — 6 ATS platforms + Workday
│   │   └── profile.py           # Your skills, locations, experience level
│   ├── scrapers/
│   │   ├── greenhouse.py        # 87 companies
│   │   ├── lever.py             # 4 companies
│   │   ├── ashby.py             # 11 companies
│   │   ├── smartrecruiters.py   # 4 companies
│   │   ├── bamboohr.py          # 3 companies
│   │   └── workday.py           # 7 finance companies (Goldman, Walmart, etc.)
│   ├── core/
│   │   └── relevance.py         # Keyword scoring engine (0–100%)
│   ├── storage/
│   │   ├── db.py                # SQLite jobs + scrape_runs tables
│   │   └── profile_manager.py   # User profile + resume storage + skill extraction
│   ├── alerts/
│   │   └── notifier.py          # Slack + WhatsApp dream-job alerts
│   ├── server.py                # Flask API + background scraper + night skip
│   ├── main.py                  # CLI (GitHub Actions + local testing)
│   ├── export_data.py           # DB → api-data.json
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
- Sleeps if no traffic for 15 min (GitHub Actions keepalive pings /ping)

**Total cost: $0/month.**

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
```python
# Render (env var on Render dashboard):
FAST_INTERVAL=180   # 3 min instead of 5 min
```
