#  JobScout

**Self-recovering job pipeline — 100+ companies, zero API keys, direct ATS integrations.**

Scrapes job listings directly from company career pages using their public ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday) and custom scrapers for Google, Amazon, Apple, Microsoft, Meta, and Bloomberg. Scores every listing against your profile with weighted multi-signal relevance matching, then sends you email alerts for high-relevance matches — all with circuit breakers, concurrent execution, and a live monitoring API.

**No Apify. No third-party scrapers. No API keys needed for scraping.**

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Orchestrator                               │
│   Concurrent scraping (semaphore) · Circuit breakers · Retry      │
│                                                                    │
│   ┌──────────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  │
│   │  Greenhouse  │  │   Lever   │  │   Ashby   │  │SmartRecr. │  │
│   │   42 cos.    │  │  15 cos.  │  │  5 cos.   │  │  2 cos.   │  │
│   │  Public API  │  │ Public API│  │Public API │  │Public API │  │
│   └──────┬───────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  │
│          │                │              │              │        │
│   ┌──────┴───────┐  ┌─────┴──────┐  ┌────┴────┐                  │
│   │   Workday    │  │  Big Tech  │  │ Custom  │                  │
│   │  13 cos.     │  │  G/A/Ap/MS │  │ Others  │                  │
│   │  JSON SPA    │  │  Meta/BB   │  │         │                  │
│   └──────┬───────┘  └─────┬──────┘  └────┬────┘                  │
│          └────────────────┴──────────────┘                        │
│                           │                                        │
│                  ┌────────▼─────────┐                              │
│                  │ Relevance Engine  │  Weighted scoring 0–100%    │
│                  └────────┬─────────┘                              │
│                  ┌────────▼─────────┐                              │
│                  │  SQLite (WAL)    │  Dedup · History · Metrics   │
│                  └────────┬─────────┘                              │
│           ┌───────────────┼───────────────┐                        │
│     ┌─────▼──────┐  ┌────▼────┐  ┌───────▼───────┐               │
│     │   Email    │  │Circuit  │  │    Health     │               │
│     │  Digest    │  │Breaker  │  │   Monitor     │               │
│     └────────────┘  └─────────┘  └───────────────┘               │
└──────────────────────────────────────────────────────────────────┘
```

## Companies Tracked (100+)

| ATS Platform | # Companies | API Type | Examples |
|---|---|---|---|
| **Greenhouse** | 42 | Free public JSON API | Uber, Stripe, Datadog, Snowflake, Databricks, Coinbase, Anthropic, OpenAI |
| **Lever** | 15 | Free public JSON API | Netflix, Spotify, Two Sigma, Citadel, Jane Street |
| **Ashby** | 5 | Free public JSON API | Hightouch, Prefect, Linear |
| **SmartRecruiters** | 2 | Free public JSON API | Visa, KPMG |
| **Workday** | 13 | Internal SPA JSON API | Disney, Capital One, American Airlines, AT&T, Goldman Sachs, JPMorgan |
| **Custom** | 18 | Company-specific APIs | Google, Amazon, Apple, Microsoft, Meta, Bloomberg, NVIDIA |

Run `python main.py --companies` to see the full list.

## Self-Recovery Features

| Pattern | Implementation |
|---|---|
| **Circuit Breaker** | Per-company: 5 consecutive failures → disabled 15 min → half-open test |
| **Exponential Backoff** | `2^attempt` seconds between retries (3 attempts max) |
| **Domain Rate Limiting** | 2s minimum between requests to the same domain |
| **Concurrent Scraping** | Semaphore-bounded (default 5) — fast but respectful |
| **Graceful Degradation** | If Uber fails, 99 other companies still scrape fine |
| **Quiet Hours** | No scraping 11PM–6AM UTC |
| **Health Monitoring** | `/health` endpoint, cycle metrics, per-company status |

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USER/job-scout.git
cd job-scout

# Install (only 2 dependencies: httpx, aiohttp)
pip install -r requirements.txt

# Configure email (optional)
cp .env.example .env
# Edit .env with Gmail app password

# Test single cycle
python main.py --once

# View stats
python main.py --stats

# Run continuously (scrapes every 30 min)
python main.py
```

## Deploy

### Fly.io (recommended — $5/mo, Dallas region)
```bash
fly launch              # Creates app from fly.toml
fly secrets set SMTP_USER=you@gmail.com SMTP_PASSWORD=xxx RECIPIENT_EMAIL=you@gmail.com
fly deploy
```

### Docker (any VPS)
```bash
cp .env.example .env    # Edit with your settings
docker compose up -d
```

### Railway
```bash
railway init
railway up
```

### Render
Push to GitHub → connect repo in Render dashboard → auto-deploys from `render.yaml`.

## Monitoring API

Running on port `8089`:

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "healthy"}` |
| `GET /api/dashboard` | Full stats, runs, top jobs, circuit states |
| `GET /api/jobs?limit=25` | Top scored jobs |
| `GET /api/runs` | Recent scrape runs with status |
| `GET /api/metrics?name=cycle_duration&hours=24` | Time-series metrics |

## Customizing

### Your Profile (`config/profile.py`)
Edit target titles, skills with proficiency weights, preferred locations, target companies, exclude keywords, salary floor.

### Company Registry (`config/company_registry.py`)
Add/remove companies. Each entry needs: name, ATS platform, board slug, career URL, priority (1-3).

To add a new Greenhouse company:
```python
Company("NewCo", ATSPlatform.GREENHOUSE, "newco-slug", "https://newco.com/careers", 2),
```

### Priority Levels
- **Priority 1**: Dream companies — scraped every cycle
- **Priority 2**: Strong interest — scraped by default
- **Priority 3**: Nice to have — set `PRIORITY_FILTER=3` to include

## Project Structure

```
job-scout/
├── main.py                         # Entry point + CLI
├── config/
│   ├── settings.py                 # Environment-based config
│   ├── profile.py                  # Your candidate profile
│   └── company_registry.py         # 100+ companies → ATS mapping
├── scrapers/
│   ├── base.py                     # HTTP client, retry, rate limiting
│   ├── factory.py                  # Routes companies → scrapers
│   └── ats/
│       ├── greenhouse.py           # Greenhouse public API
│       ├── lever.py                # Lever public API
│       ├── ashby.py                # Ashby public API
│       ├── smartrecruiters.py      # SmartRecruiters public API
│       ├── workday.py              # Workday internal JSON API
│       └── custom.py               # Google, Amazon, Apple, MS, Meta, Bloomberg
├── core/
│   ├── relevance_engine.py         # Multi-signal scoring
│   └── orchestrator.py             # Main loop + self-recovery
├── storage/
│   └── database.py                 # SQLite WAL persistence
├── notifiers/
│   └── email_notifier.py           # HTML digest emails
├── monitors/
│   └── health_monitor.py           # HTTP health/metrics server
├── .github/workflows/ci.yml        # CI + deploy pipeline
├── Dockerfile                       # Multi-stage production build
├── docker-compose.yml               # Local/server deployment
├── fly.toml                         # Fly.io config (Dallas region)
├── render.yaml                      # Render config
└── setup.sh                         # One-command setup + GitHub push
```
