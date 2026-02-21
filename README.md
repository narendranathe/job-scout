# ⚡ JobScout — Option D: 5-Minute Latency, $0/Month

Dual-engine job discovery system: **Render** scrapes your top 24 targets every 5 min, **GitHub Actions** does the full 109-company sweep hourly. Dashboard auto-switches between live and static data sources.

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                    RENDER (FREE)                        │
│                                                         │
│  Flask Server + Background Thread                       │
│  ┌───────────────────────────────────────┐              │
│  │ Every 5 min:  Tier 1 (24 companies)   │──→ SQLite   │
│  │ Every 60 min: All tiers (109 cos)     │    on disk   │
│  └───────────────────────────────────────┘              │
│                                                         │
│  GET /api/data  → JSON (dashboard fetches this)         │
│  GET /api/health → server status + metrics              │
│  GET /ping       → keepalive (prevents sleep)           │
└────────────────────┬───────────────────────────────────┘
                     │  ← primary source (~5 min fresh)
                     │
┌────────────────────▼───────────────────────────────────┐
│              REACT DASHBOARD (GitHub Pages)              │
│                                                         │
│  useJobData() hook:                                     │
│    1. Try Render /api/data    → show "🟢 Live"          │
│    2. Fallback api-data.json  → show "🟡 Static"        │
│    3. Auto-refresh every 2 min                          │
│                                                         │
│  Tabs: Jobs | Analytics | Companies | Trends | Monitor  │
└────────────────────▲───────────────────────────────────┘
                     │  ← fallback source (~60 min fresh)
                     │
┌────────────────────┴───────────────────────────────────┐
│              GITHUB ACTIONS (FREE)                      │
│                                                         │
│  Hourly:  Full 109-company scrape                       │
│           Export api-data.json → commit → deploy Pages   │
│                                                         │
│  Every 14 min (business hours):                         │
│           Ping Render /ping → prevent free-tier sleep    │
└────────────────────────────────────────────────────────┘
```

## End-to-End Setup (15 minutes)

### Step 1: Create GitHub Repo

```bash
mkdir jobscout && cd jobscout
git init

# Unzip the package
unzip jobscout-option-d.zip

git add -A
git commit -m "init: jobscout option d"
```

### Step 2: Edit Config

```bash
# 1. Set your repo name for GitHub Pages
# Edit frontend/vite.config.js → base: '/YOUR-REPO-NAME/'

# 2. (Optional) Customize your skills/preferences
# Edit backend/config/profile.py

# 3. (Optional) Add/remove companies
# Edit backend/config/companies.py
```

### Step 3: Test Locally

```bash
cd backend
pip install -r requirements.txt

# Quick test — Tier 1 only (24 companies, ~30 sec)
python main.py --fast

# Full test — all 109 companies (~3 min)
python main.py

# Check results
python main.py --stats

# Test the server locally
python server.py
# Visit http://localhost:10000/api/health
# Visit http://localhost:10000/api/data
```

### Step 4: Deploy Render (5 min)

1. Go to [render.com](https://render.com) → Sign up with GitHub
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub repo
4. Render reads `render.yaml` → deploys automatically
5. Wait ~2 min for first deploy
6. Note your URL: `https://jobscout-api.onrender.com`

After deploy, verify:
```bash
curl https://jobscout-api.onrender.com/ping       # Should return "ok"
curl https://jobscout-api.onrender.com/api/health  # Should show status
```

### Step 5: Connect Dashboard to Render

```bash
# In your repo root:
cd frontend

# Create .env file
cp .env.example .env

# Edit .env — set your Render URL:
# VITE_RENDER_URL=https://jobscout-api.onrender.com
```

### Step 6: Push to GitHub + Enable Pages

```bash
cd ..  # back to repo root
git add -A
git commit -m "config: render url + page base"
git remote add origin https://github.com/YOUR_USER/jobscout.git
git push -u origin main
```

Then in GitHub:
1. **Settings** → **Pages** → **Source: GitHub Actions**
2. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:
   - Name: `RENDER_URL`
   - Value: `https://jobscout-api.onrender.com`

### Step 7: Verify Everything Works

After ~5 minutes:
- Dashboard: `https://YOUR_USER.github.io/jobscout/`
- Monitor tab should show all green checks:
  - ✅ VITE_RENDER_URL configured
  - ✅ Render API responding
  - ✅ Health endpoint reachable
  - ✅ First scrape completed
  - ✅ Jobs flowing to dashboard

## What Runs When

| Component | Frequency | What | Platform | Cost |
|-----------|-----------|------|----------|:----:|
| Fast scrape | Every 5 min | 24 Tier-1 companies | Render | $0 |
| Full sweep | Every 60 min | 109 companies (all tiers) | GitHub Actions | $0 |
| Keepalive | Every 14 min (biz hours) | Pings Render /ping | GitHub Actions | $0 |
| Dashboard deploy | After each full sweep | Build + deploy Pages | GitHub Actions | $0 |
| **Total** | | | | **$0** |

## GitHub Actions Minutes Budget

| Workflow | Runs/Day | Min/Run | Monthly |
|----------|----------|---------|---------|
| Full sweep | 24 | ~4 min | ~2,880 min |
| Keepalive (biz hours) | ~60 | ~0.1 min | ~180 min |
| **Total** | | | **~3,060 min** |

⚠️ This exceeds the 2,000 min/month free tier. Pick one solution:

**Option A (recommended):** Use [UptimeRobot](https://uptimerobot.com) for keepalive instead of GitHub Actions:
- Free plan: 50 monitors, 5-min intervals
- Add monitor: `GET https://jobscout-api.onrender.com/ping`
- Delete `.github/workflows/keepalive.yml`
- This saves ~180 min/month

**Option B:** Run full sweeps every 2 hours instead of hourly:
- Change cron to `'20 */2 * * *'` in `scrape-and-deploy.yml`
- Saves ~1,440 min/month → fits in free tier

**Option C (recommended combo):** UptimeRobot + every 2 hours:
- Total: ~1,440 min/month — comfortably within free tier
- Render still scrapes Tier 1 every 5 min regardless

## File Structure

```
jobscout/
├── backend/
│   ├── config/
│   │   ├── companies.py         # 109 companies, 3 tiers, 5 ATS platforms
│   │   └── profile.py           # Your skills & preferences
│   ├── scrapers/
│   │   ├── greenhouse.py        # 87 companies
│   │   ├── lever.py             # 4 companies
│   │   ├── ashby.py             # 11 companies
│   │   ├── smartrecruiters.py   # 4 companies
│   │   └── bamboohr.py          # 3 companies (Prefect, Dagster...)
│   ├── core/
│   │   └── relevance.py         # Multi-signal scoring engine
│   ├── storage/
│   │   └── db.py                # SQLite + dedup + stale detection
│   ├── server.py                # Flask + background scraper (Render)
│   ├── main.py                  # CLI orchestrator (Actions + local)
│   ├── export_data.py           # DB → JSON bridge
│   └── requirements.txt         # requests, flask, gunicorn
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Dashboard (dual-source + monitor tab)
│   │   └── main.jsx             # React entry
│   ├── public/
│   │   └── api-data.json        # Static fallback (Actions updates hourly)
│   ├── .env.example             # Template: set VITE_RENDER_URL
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .github/workflows/
│   ├── scrape-and-deploy.yml    # Hourly full sweep + Pages deploy
│   └── keepalive.yml            # Render keepalive (or use UptimeRobot)
├── Dockerfile                    # Render deployment
├── render.yaml                   # One-click Render blueprint
└── README.md
```

## Customizing

### Add a company
```python
# backend/config/companies.py — add to the list:
{"name": "Company", "ats": "greenhouse", "slug": "their-slug", "tier": 2},
```

### Change scrape frequency
```python
# Render (backend/server.py or env var):
FAST_INTERVAL = 300   # 5 min (default) — change to 180 for 3 min

# GitHub Actions (.github/workflows/scrape-and-deploy.yml):
cron: '20 */2 * * *'  # Every 2 hours (saves Actions minutes)
```

### Find ATS slugs
| ATS | How to find the slug |
|-----|---------------------|
| Greenhouse | boards.greenhouse.io/**slug**/jobs |
| Lever | jobs.lever.co/**slug** |
| Ashby | jobs.ashbyhq.com/**slug** |
| SmartRecruiters | careers.smartrecruiters.com/**slug** |
| BambooHR | **slug**.bamboohr.com/careers |
