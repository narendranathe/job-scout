# Job Scout Enhancement Design
**Date:** 2026-04-27
**Status:** Approved - Moving to Implementation
**Approach:** A — Three Vertical Slices

---

## Problem Statement

Job Scout is functional but has three compounding weaknesses:

1. **Unreliable scraping** — the GitHub Actions artifact used to persist the cycle counter fails intermittently, resetting tier batching and causing Tier 2/3 companies to be scraped every run (burning free-tier minutes) or not at all (missing jobs).

2. **Missing high-comp targets** — several $220K+ companies (HRT, Two Sigma, Jump Trading, Jane Street, D.E. Shaw) are absent from `companies.py` entirely. Some are on existing ATS platforms and are pure config additions; others require new scrapers.

3. **No application pipeline visibility** — the `applications` table schema is sound but the React dashboard has no pipeline view, no "Mark Applied" button, and no kanban tracking. Applied roles are tracked manually in SQLite.

---

## Chosen Approach: Three Vertical Slices

Each slice is independently deployable and testable. No slice depends on the next being complete.

---

## Slice 1: Reliability + Company Expansion

### 1A. Cycle Counter Fix

**Problem:** `cycle_counter` is stored as a GitHub Actions artifact. Artifact download fails intermittently → counter resets → tier batching breaks → either over-scraping (minutes burned) or under-scraping (missed companies).

**Fix:** Embed `cycle_counter` as a metadata field in `frontend/public/api-data.json`, which is already committed to the repo on every run. At startup, the scraper reads the counter from this file. No artifact upload/download, no extra git push, zero additional minutes.

```python
# backend/export_data.py — add to export payload
"metadata": {
    "cycle_counter": current_cycle,
    "last_run_at": datetime.utcnow().isoformat(),
    "jobs_total": total_jobs,
}
```

```python
# backend/main.py — read at startup
def load_cycle_counter():
    try:
        with open("../frontend/public/api-data.json") as f:
            data = json.load(f)
        return data.get("metadata", {}).get("cycle_counter", 0)
    except Exception:
        return 0
```

### 1B. Per-Scraper Retry with Exponential Backoff

**Problem:** A single network timeout silently drops that company for the entire run with no record in `scrape_runs`.

**Fix:** Add `scrape_with_retry()` wrapper in `backend/scrapers/utils.py`.

```python
def scrape_with_retry(fn, company_name, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                log_scrape_error(company_name, str(e))
                return []
            time.sleep(2 ** (attempt + 1))  # 2s, 4s, 8s
```

All scraper `fetch_jobs()` calls are wrapped. Failed companies are logged to `scrape_runs.errors` and the run continues.

### 1C. Render Flask = API Only

**Problem:** Render free tier VMs go dormant after 15 minutes of inactivity. The background scraping thread dies silently, and when it wakes it duplicates or corrupts runs.

**Fix:** Remove `threading.Thread(target=background_scraper)` from `server.py`. GitHub Actions is the authoritative scheduler. The `/api/scrape` manual trigger endpoint stays (synchronous, 5-minute timeout) for on-demand use.

### 1D. Discord Alert on High Error Rate

If a completed `scrape_run` has errors affecting >10% of targeted companies, fire the existing Discord webhook with a summary. Hooks into `notifier.py` which already has webhook infrastructure.

### 1E. Company Config Expansion (Config Only — No New Scrapers)

These companies are already on supported ATS platforms; they just aren't in `companies.py`:

**Add to Greenhouse (Tier 1/Platinum):**
| Company | Greenhouse Slug | New Tier |
|---------|----------------|----------|
| Hudson River Trading (HRT) | `hudsonrivertrading` | Platinum |
| Two Sigma | `twosigma` | Platinum |
| Jump Trading | `jumptrading` | Platinum |
| Point72 | `point72` | Platinum |
| AQR Capital | `aqr` | Platinum |

Note: D.E. Shaw runs its own career portal — it goes in Slice 3 (Playwright), not here.

**Add to Workday (Tier 1/2):**
| Company | Workday Slug | Instance | New Tier |
|---------|-------------|---------|----------|
| Disney | `disney` | `wd5` | Tier 1 |
| Walmart | `walmart` | `wd5` | Tier 1 |
| Intel | `intel` | `wd3` | Tier 2 |

---

## Slice 2: Platinum Tier + $220K+ Surfacing

### 2A. Platinum Tier in Company Config

New tier above Tier 1 in `companies.py`. Scraped every cycle (same as Tier 1). Distinguished by known comp bands from Levels.fyi data (hardcoded, reviewed quarterly).

**Platinum companies (15-20, $220K+ base for senior data/ML roles):**
- Quant/HFT: HRT, Two Sigma, Jump Trading, Point72, AQR, Citadel, Millennium, Virtu
- Big Tech (senior levels): Google, Meta, Apple, Microsoft, Amazon, NVIDIA
- AI-first: Anthropic, OpenAI, Databricks (Staff+)
- Finance: Goldman Sachs (VP+), Bloomberg (Principal+)

```python
# backend/config/companies.py
PLATINUM = [
    {"name": "Hudson River Trading", "ats": "greenhouse", "slug": "hudsonrivertrading"},
    {"name": "Two Sigma", "ats": "greenhouse", "slug": "twosigma"},
    # ...
]

TIERS = {
    "platinum": PLATINUM,  # every cycle
    "tier1": TIER1,        # every cycle
    "tier2": TIER2,        # every 2nd cycle
    "tier3": TIER3,        # every 4th cycle
}
```

### 2B. Salary Parser

Parse salary ranges from job description text where disclosed. Store in existing `salary_min` / `salary_max` columns.

```python
# backend/scrapers/utils.py
SALARY_PATTERNS = [
    r'\$(\d{2,3})[Kk][\s\-–—]+\$?(\d{2,3})[Kk]',           # $180K - $250K
    r'\$(\d{3},\d{3})[\s\-–—]+\$?(\d{3},\d{3})',             # $180,000 - $250,000
    r'(\d{2,3})[Kk][\s\-–—]+(\d{2,3})[Kk]\s*(?:USD|per year)',
]

def parse_salary(text: str) -> tuple[int, int]:
    for pattern in SALARY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo < 1000: lo *= 1000   # normalize K notation
            if hi < 1000: hi *= 1000
            return lo, hi
    return 0, 0
```

### 2C. Platinum Score Boost in Relevance Engine

```python
# backend/core/relevance.py
PLATINUM_BOOST = 0.08

def score(job, profile):
    base_score = _compute_base_score(job, profile)
    if job.get("tier") == "platinum":
        base_score = min(1.0, base_score + PLATINUM_BOOST)
    return base_score
```

### 2D. React UI: Platinum Badge + Filter

- Gold "PLATINUM" badge on job cards for Platinum companies
- Dedicated "Platinum" filter tab alongside "All", "Dream", "Remote"
- Platinum jobs sort to the top within any active filter
- Salary band displayed on card where `salary_min > 0`
- `$220K+` filter chip in the filter bar (shows jobs where `salary_min >= 220000` OR company is Platinum)

---

## Slice 3: Pipeline View + Playwright Scrapers + Future Spec

### 3A. Applications Pipeline View (React)

Kanban board with columns: **Saved → Applied → Phone Screen → Technical → Offer → Rejected**

Each card shows: company (with tier badge), role title, relevance score, salary band if known, applied date, resume version used, notes.

**"Mark Applied" flow:**
1. User clicks "Apply" button on a job card in the main feed
2. Modal: resume version selector + optional notes field
3. On confirm: `POST /api/applications` → job moves to "Applied" column in pipeline view
4. Status transitions: dropdown on card → `PATCH /api/applications/:id` (drag-and-drop is a stretch goal, not in scope)

**Stats bar** above pipeline: "12 applied this week · 3 in technical · 1 offer"

### 3B. Flask API Completions

The `applications` table and basic `POST /api/applications` endpoint exist. What's missing:

```python
# backend/server.py — add/complete:
PATCH  /api/applications/<id>     # update status, notes, resume_version
GET    /api/applications          # list all with ?status= filter
DELETE /api/applications/<id>     # remove (soft delete: set status="removed")
```

### 3C. Playwright Scrapers for Non-ATS Firms

For quant/HFT firms that run their own career portals and can't be reached via the 6 existing ATS APIs:

| Company | Career URL | Notes |
|---------|-----------|-------|
| Jane Street | `janestreet.com/join-jane-street/open-roles/` | React SPA, needs browser |
| D.E. Shaw | `deshaw.com/careers/open-positions/` | React SPA, needs browser |
| Virtu Financial | `virtu.com/careers/` | Needs browser |

```python
# backend/scrapers/playwright_scraper.py
from playwright.sync_api import sync_playwright

PLAYWRIGHT_TARGETS = [
    {
        "name": "Jane Street",
        "url": "https://www.janestreet.com/join-jane-street/open-roles/",
        "job_selector": "[data-testid='job-listing']",
        "title_selector": ".job-title",
        "link_selector": "a",
    },
    # ...
]

def fetch_playwright_jobs(target: dict) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(target["url"], wait_until="networkidle")
        # parse and return normalized job dicts
```

Playwright runs execute every cycle (same cadence as Tier 1/Platinum) in a separate execution block after all API-based scrapers complete, with a 60s timeout per company. GitHub Actions budget note: Playwright adds ~3 min per run (3 companies × 60s). Current budget is ~1,080 min/month against a 2,000-minute limit, so headroom exists.

### 3D. Auto-Tracking Future Spec (GitHub Issue)

Create a GitHub issue titled: **"[Feature] Automatic application tracking via email parsing + extension events"**

Vision:
- Parse Gmail inbox for application confirmation emails (sender patterns: `no-reply@greenhouse.io`, `apply@lever.co`, ATS confirmation patterns)
- When autoapply-ai extension submits an application, fire a webhook to job-scout `/api/applications` to auto-create the record
- Status updates from email follow-up parsing (interview invite, rejection, offer)

Scope: Phase 2, not this sprint.

---

## Data Model Changes

One schema migration required. The `jobs` table does not have a `tier` column. Add it:

```sql
ALTER TABLE jobs ADD COLUMN tier TEXT DEFAULT 'tier1';
```

This runs once at startup in `db.py` via `IF NOT EXISTS` pattern (already used there for other columns). All other required columns (`salary_min`, `salary_max`, `status`) already exist.

Additional non-schema additions:
- `api-data.json` gains a `metadata` object (backward-compatible, frontend ignores unknown fields)
- `companies.py` gains a `PLATINUM` list (read by the same batching logic)

---

## Testing Approach

- **Slice 1:** Run a manual scrape locally after changes; verify `cycle_counter` appears in `api-data.json`; kill a scraper mid-run and verify the run completes with errors logged
- **Slice 2:** Verify Platinum badge renders correctly in React; verify salary parser correctly normalizes `$180K-$250K` and `$180,000-$250,000` formats
- **Slice 3:** Verify "Mark Applied" creates a record and card appears in pipeline; verify Playwright scrapers return at least 1 job from Jane Street in headless mode

---

## Out of Scope (This Sprint)

- Email parsing for auto-tracking (future spec filed as GitHub issue)
- ML-based scoring (pure heuristic scoring stays)
- Resume auto-tailoring integration (autoapply-ai handles this)
- iCIMS scraper (Disney and Walmart covered by Workday config additions)
