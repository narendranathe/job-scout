# Job Scout Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three vertical slices: (1) scraping reliability + tier DB column, (2) Platinum $220K+ tier with salary parsing and UI badges, (3) applications kanban pipeline + Playwright scrapers for quant/HFT firms.

**Architecture:** Existing Flask + SQLite + React stack unchanged. Each slice is an additive change — no rewrites. Reliability fixes go into `utils.py`, `main.py`, `export_data.py`, `server.py`. Platinum tier touches `companies.py`, `relevance.py`, `export_data.py`, and `App.jsx`. Pipeline view adds two Flask endpoints and a React kanban tab. Playwright scrapers run as a separate module after all API-based scrapers.

**Tech Stack:** Python 3.12, Flask 3, SQLite WAL, React 18 + Vite, `requests`, `playwright` (new dep for Slice 3), `pytest`.

**Spec:** `docs/superpowers/specs/2026-04-27-job-scout-enhancements-design.md`

---

## Important Context

- **Working directory for all Python tasks:** `job-scout/backend/`
- **Run tests from:** `job-scout/backend/` with `python -m pytest tests/ -v`
- **companies.py key fact:** Walmart and Disney are ALREADY in the config. HRT, Two Sigma, AQR have no public ATS APIs — they need Playwright (Slice 3).
- **get_batch() logic:** tier 1 = every cycle, tier 2 = every 2nd, tier 3 = every 4th. Platinum uses tier value `0` — must update `get_batch()` to include it.
- **Cycle counter:** currently lives in `.cycle_counter` file, saved/restored as GitHub Actions artifact. Fix: embed in `api-data.json` metadata.

---

## SLICE 1 — Reliability

---

### Task 1: Add `tier` column to `jobs` table

**Files:**
- Modify: `backend/storage/db.py`
- Create: `backend/tests/test_db_tier.py`

- [ ] **Step 1.1: Write failing test**

Create `backend/tests/test_db_tier.py`:

```python
import sqlite3
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from storage.db import init_db, upsert_job, get_conn


def make_job(ext_id="test-1"):
    return {
        "external_id": ext_id,
        "title": "Senior Data Engineer",
        "company": "Test Co",
        "location": "Remote",
        "department": "",
        "description": "Python, Spark, Kafka",
        "url": "https://example.com/job/1",
        "ats": "greenhouse",
        "is_remote": True,
        "posted_at": "2026-04-27",
        "salary_min": 200000,
        "salary_max": 280000,
        "relevance_score": 0.85,
        "matched_skills": ["python", "spark"],
        "sponsorship": False,
        "tier": "platinum",
    }


def test_tier_column_exists_after_init():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()
        assert "tier" in cols, f"tier column missing from jobs; got: {cols}"


def test_upsert_job_stores_tier():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        init_db(db_path)
        conn = get_conn(db_path)
        result = upsert_job(conn, make_job("test-1"))
        conn.commit()
        row = conn.execute("SELECT tier FROM jobs WHERE external_id = 'test-1'").fetchone()
        conn.close()
        assert result == "new"
        assert row[0] == "platinum"
```

- [ ] **Step 1.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_db_tier.py -v
```
Expected: FAIL — `tier column missing from jobs`

- [ ] **Step 1.3: Add `tier` column to `init_db` and `upsert_job` in `storage/db.py`**

In `init_db`, after the `CREATE TABLE IF NOT EXISTS jobs (...)` block (line 48, after `is_active INTEGER DEFAULT 1`), add the `tier` column and a one-time migration. Replace the `CREATE TABLE IF NOT EXISTS jobs` block with:

```python
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT DEFAULT '',
            department TEXT DEFAULT '',
            description TEXT DEFAULT '',
            url TEXT DEFAULT '',
            ats TEXT DEFAULT '',
            is_remote INTEGER DEFAULT 0,
            posted_at TEXT DEFAULT '',
            salary_min INTEGER DEFAULT 0,
            salary_max INTEGER DEFAULT 0,
            relevance_score REAL DEFAULT 0.0,
            matched_skills TEXT DEFAULT '',
            sponsorship INTEGER DEFAULT 0,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            tier TEXT DEFAULT 'tier1'
        );
    """)
    # One-time migration: add tier if existing DB lacks it
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN tier TEXT DEFAULT 'tier1'")
        conn.commit()
    except Exception:
        pass  # Column already exists — safe to ignore
```

In `upsert_job`, update the INSERT statement to include `tier`. Find the `conn.execute(""" INSERT INTO jobs (` block and add `tier` to both the column list and VALUES:

```python
    if existing is None:
        conn.execute("""
            INSERT INTO jobs (
                external_id, title, company, location, department,
                description, url, ats, is_remote, posted_at,
                salary_min, salary_max, relevance_score, matched_skills,
                sponsorship, first_seen_at, last_seen_at, is_active, tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            job["external_id"], job["title"], job["company"],
            job.get("location", ""), job.get("department", ""),
            job.get("description", ""), job.get("url", ""),
            job.get("ats", ""), int(job.get("is_remote", False)),
            job.get("posted_at", ""),
            job.get("salary_min", 0), job.get("salary_max", 0),
            job.get("relevance_score", 0.0),
            json.dumps(job.get("matched_skills", [])),
            int(job.get("sponsorship", False)),
            now, now,
            job.get("tier", "tier1"),
        ))
        return "new"
```

Also update the UPDATE branch — add `tier = ?` to the SET clause. Find the `conn.execute(""" UPDATE jobs SET` block and add `tier = ?,` and pass `job.get("tier", "tier1")` in the values tuple.

- [ ] **Step 1.4: Run test to confirm it passes**

```bash
cd backend
python -m pytest tests/test_db_tier.py -v
```
Expected: PASS — both tests green

- [ ] **Step 1.5: Commit**

```bash
git add backend/storage/db.py backend/tests/test_db_tier.py
git commit -m "feat: add tier column to jobs table with one-time migration"
```

---

### Task 2: Fix cycle counter — embed in `api-data.json`

**Files:**
- Modify: `backend/export_data.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_cycle_counter.py`

- [ ] **Step 2.1: Write failing test**

Create `backend/tests/test_cycle_counter.py`:

```python
import json
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_export_includes_cycle_counter():
    """export() must write metadata.cycle_counter into the JSON output."""
    from export_data import export
    import sqlite3
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        out_path = os.path.join(d, "api-data.json")
        from storage.db import init_db
        init_db(db_path)
        export(db_path, out_path, cycle_counter=7)
        with open(out_path) as f:
            data = json.load(f)
        assert "metadata" in data, "metadata key missing from export"
        assert data["metadata"]["cycle_counter"] == 7


def test_load_cycle_from_json():
    """load_cycle_counter() must read metadata.cycle_counter from api-data.json."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        json_path = os.path.join(d, "api-data.json")
        with open(json_path, "w") as f:
            json.dump({"metadata": {"cycle_counter": 42}}, f)
        # Patch DEFAULT_OUTPUT temporarily
        import main as m
        original = m.JSON_OUTPUT_PATH
        m.JSON_OUTPUT_PATH = json_path
        result = m.load_cycle_counter()
        m.JSON_OUTPUT_PATH = original
        assert result == 43, f"Expected 43 (42+1), got {result}"
```

- [ ] **Step 2.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_cycle_counter.py -v
```
Expected: FAIL — `export() got unexpected keyword argument 'cycle_counter'`

- [ ] **Step 2.3: Update `export_data.py` to accept and embed `cycle_counter`**

Change the `export()` function signature and the `data = {...}` dict:

```python
def export(db_path: str = DB_PATH, output_path: str = None, cycle_counter: int = 0) -> dict:
```

In the `data = { ... }` dict, add the `"metadata"` key right after `"exported_at"`:

```python
    data = {
        "jobs": jobs,
        "stats": { ... },  # unchanged
        "distributions": { ... },  # unchanged
        "top_companies": [...],  # unchanged
        "trend": [...],  # unchanged
        "runs": runs,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "cycle_counter": cycle_counter,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "jobs_total": total,
        },
    }
```

- [ ] **Step 2.4: Update `main.py` to read counter from JSON and pass it to `export()`**

At the top of `main.py`, add:

```python
JSON_OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "api-data.json"
)
```

Replace the `_next_cycle()` function entirely:

```python
def load_cycle_counter() -> int:
    """Read cycle counter from api-data.json metadata, increment, return new value."""
    try:
        with open(JSON_OUTPUT_PATH) as f:
            data = json.load(f)
        return data.get("metadata", {}).get("cycle_counter", 0) + 1
    except Exception:
        return 1
```

In `run_scrape()`, replace `cycle = _next_cycle()` with:

```python
    cycle = load_cycle_counter()
```

In `export_json()`, pass the cycle counter:

```python
def export_json(db_path: str, cycle: int = 0) -> dict:
    output = JSON_OUTPUT_PATH
    os.makedirs(os.path.dirname(output), exist_ok=True)
    from export_data import export
    data = export(db_path, output, cycle_counter=cycle)
    log.info("Exported %d jobs → %s", data.get("stats", {}).get("total_jobs", 0), output)
    return data
```

In `main()`, capture cycle from `run_scrape()` and pass to `export_json()`:

```python
    mode = "fast" if args.fast else "full"
    stats = run_scrape(db, mode, args.delay)
    export_json(db, cycle=stats.get("cycle", 1))
```

In `run_scrape()`, add `cycle` to the returned stats dict:

```python
    stats["cycle"] = cycle
    ...
    return stats
```

- [ ] **Step 2.5: Run tests to confirm they pass**

```bash
cd backend
python -m pytest tests/test_cycle_counter.py -v
```
Expected: PASS

- [ ] **Step 2.6: Commit**

```bash
git add backend/export_data.py backend/main.py backend/tests/test_cycle_counter.py
git commit -m "feat: embed cycle_counter in api-data.json metadata — fixes artifact fragility"
```

---

### Task 3: Add `scrape_with_retry` to `utils.py`

**Files:**
- Modify: `backend/scrapers/utils.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_utils.py`

- [ ] **Step 3.1: Write failing test**

Create `backend/tests/test_utils.py`:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_scrape_with_retry_returns_on_success():
    from scrapers.utils import scrape_with_retry
    calls = []
    def good_fn():
        calls.append(1)
        return [{"title": "Data Engineer"}]
    result = scrape_with_retry(good_fn, "TestCo")
    assert result == [{"title": "Data Engineer"}]
    assert len(calls) == 1


def test_scrape_with_retry_retries_on_failure():
    from scrapers.utils import scrape_with_retry
    calls = []
    def flaky_fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("timeout")
        return [{"title": "Data Engineer"}]
    result = scrape_with_retry(flaky_fn, "TestCo", max_attempts=3, base_delay=0)
    assert result == [{"title": "Data Engineer"}]
    assert len(calls) == 3


def test_scrape_with_retry_returns_empty_after_all_failures():
    from scrapers.utils import scrape_with_retry
    def bad_fn():
        raise ConnectionError("always fails")
    result = scrape_with_retry(bad_fn, "TestCo", max_attempts=3, base_delay=0)
    assert result == []


def test_parse_salary_k_notation():
    from scrapers.utils import parse_salary
    assert parse_salary("Compensation: $180K - $250K per year") == (180000, 250000)


def test_parse_salary_full_notation():
    from scrapers.utils import parse_salary
    assert parse_salary("Base salary $200,000 - $280,000") == (200000, 280000)


def test_parse_salary_returns_zeros_when_not_found():
    from scrapers.utils import parse_salary
    assert parse_salary("Competitive salary, no range listed") == (0, 0)
```

- [ ] **Step 3.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_utils.py -v
```
Expected: FAIL — `cannot import name 'scrape_with_retry'`

- [ ] **Step 3.3: Add `scrape_with_retry` and `parse_salary` to `scrapers/utils.py`**

Append to the existing `backend/scrapers/utils.py` (keep existing `is_remote` and `strip_html`):

```python
import time
import logging

log = logging.getLogger(__name__)

SALARY_PATTERNS = [
    r'\$(\d{2,3})[Kk][\s\-]+\$?(\d{2,3})[Kk]',           # $180K - $250K
    r'\$(\d{3},\d{3})[\s\-]+\$?(\d{3},\d{3})',             # $180,000 - $250,000
    r'(\d{2,3})[Kk][\s\-]+(\d{2,3})[Kk]\s*(?:USD|per year)',  # 180K-250K USD
]


def parse_salary(text: str) -> tuple[int, int]:
    """Extract (salary_min, salary_max) from description text. Returns (0, 0) if not found."""
    for pattern in SALARY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            lo, hi = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            if lo < 1000:
                lo *= 1000
            if hi < 1000:
                hi *= 1000
            return lo, hi
    return 0, 0


def scrape_with_retry(fn, company_name: str, max_attempts: int = 3, base_delay: float = 2.0) -> list:
    """
    Call fn() up to max_attempts times with exponential backoff.
    Returns [] and logs error if all attempts fail — never raises.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                log.error("✗ %s — all %d attempts failed: %s", company_name, max_attempts, e)
                return []
            delay = base_delay * (2 ** attempt)  # 2s, 4s
            log.warning("✗ %s — attempt %d failed (%s), retrying in %.0fs",
                        company_name, attempt + 1, e, delay)
            time.sleep(delay)
    return []
```

Note: `re` is already imported at the top of `utils.py`. Add `import time` and `import logging` at the top.

- [ ] **Step 3.4: Run tests to confirm they pass**

```bash
cd backend
python -m pytest tests/test_utils.py -v
```
Expected: PASS — all 6 tests green

- [ ] **Step 3.5: Wire `scrape_with_retry` into `main.py` scrape loop**

In `run_scrape()`, the inner scrape call currently does:

```python
        try:
            stats["companies"] += 1
            co_relevant = 0

            for raw_job in scraper.scrape(company):
```

Replace with:

```python
        stats["companies"] += 1
        co_relevant = 0

        jobs_from_co = scrape_with_retry(
            lambda: list(scraper.scrape(company)),
            company["name"],
        )
        for raw_job in jobs_from_co:
```

Remove the outer `try/except Exception as e:` that wraps the per-company block (the retry wrapper handles failures now). Keep only the inner stats/scoring logic. Also remove the `stats["errors"] += 1` in that outer except.

Add import at top of `main.py`:

```python
from scrapers.utils import scrape_with_retry
```

Also wire `parse_salary` into `run_scrape` — after `engine.score(raw_job)` is called, add:

```python
                from scrapers.utils import parse_salary
                if not raw_job.get("salary_min") and not raw_job.get("salary_max"):
                    desc = raw_job.get("description", "")
                    sal_min, sal_max = parse_salary(desc)
                    if sal_min:
                        raw_job["salary_min"] = sal_min
                        raw_job["salary_max"] = sal_max
```

- [ ] **Step 3.6: Commit**

```bash
git add backend/scrapers/utils.py backend/main.py backend/tests/test_utils.py
git commit -m "feat: add scrape_with_retry (3x backoff) and parse_salary to utils"
```

---

### Task 4: Remove background scraping thread from `server.py`

**Files:**
- Modify: `backend/server.py`

- [ ] **Step 4.1: Find and remove the background thread**

In `server.py`, search for `threading.Thread` and the `background_scraper` function. Remove:
1. The `background_scraper()` function definition entirely
2. The `threading.Thread(target=background_scraper, daemon=True).start()` line (or similar)
3. The `import threading` if it's only used for this

Keep the `/api/scrape` endpoint — it already runs a synchronous scrape when called. Set a 300s timeout on the Flask response for that endpoint if not already set.

In the `/api/scrape` route, make sure it calls `run_scrape()` directly (not via thread) and returns the stats:

```python
@app.route("/api/scrape", methods=["POST"])
def trigger_scrape():
    from main import run_scrape
    db = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))
    stats = run_scrape(db, mode="fast", delay=0.3)
    return jsonify({"ok": True, "stats": stats})
```

- [ ] **Step 4.2: Verify server starts without background thread**

```bash
cd backend
timeout 5 python server.py 2>&1 | head -20
```
Expected: server starts, no `threading` or `background_scraper` in output, no errors

- [ ] **Step 4.3: Commit**

```bash
git add backend/server.py
git commit -m "fix: remove background scraping thread from Render server — GitHub Actions is the scheduler"
```

---

### Task 5: Add error-rate Discord alert after scrape runs

**Files:**
- Modify: `backend/alerts/notifier.py`
- Modify: `backend/main.py`

- [ ] **Step 5.1: Add `alert_high_error_rate()` to `notifier.py`**

At the end of `backend/alerts/notifier.py`, add:

```python
def alert_high_error_rate(stats: dict):
    """
    Fire Discord alert if >10% of scraped companies errored.
    stats dict must contain 'companies' (int) and 'errors' (int).
    """
    companies = stats.get("companies", 0)
    errors = stats.get("errors", 0)
    if companies == 0 or errors / companies <= 0.10:
        return

    error_pct = round(errors / companies * 100)
    msg = (
        f"⚠️ **JobScout scrape error rate: {error_pct}%**\n"
        f"Companies attempted: {companies} | Errors: {errors}\n"
        f"Cycle: {stats.get('cycle', '?')} | New jobs found: {stats.get('new', 0)}"
    )
    _send_discord(msg)


def _send_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
    except Exception as e:
        log.warning("Discord alert failed: %s", e)
```

- [ ] **Step 5.2: Wire into `main.py`**

At the end of `run_scrape()`, before `return stats`, add:

```python
    from alerts.notifier import alert_high_error_rate
    alert_high_error_rate(stats)
    return stats
```

- [ ] **Step 5.3: Verify manually (no test needed — external HTTP call)**

```bash
cd backend
python -c "
from alerts.notifier import alert_high_error_rate
# Simulate >10% error rate
alert_high_error_rate({'companies': 10, 'errors': 2, 'cycle': 99, 'new': 5})
print('alert_high_error_rate() ran without error')
"
```
Expected: prints confirmation (Discord only fires if `DISCORD_WEBHOOK_URL` env var is set)

- [ ] **Step 5.4: Commit**

```bash
git add backend/alerts/notifier.py backend/main.py
git commit -m "feat: Discord alert when scrape error rate exceeds 10%"
```

---

## SLICE 2 — Platinum Tier + $220K+ Surfacing

---

### Task 6: Add Platinum tier to `companies.py` + update `get_batch()`

**Files:**
- Modify: `backend/config/companies.py`
- Create: `backend/tests/test_companies.py`

- [ ] **Step 6.1: Write failing test**

Create `backend/tests/test_companies.py`:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_platinum_companies_in_every_batch():
    from config.companies import get_batch, COMPANIES
    platinum = [c for c in COMPANIES if c.get("tier") == 0]
    assert len(platinum) >= 5, f"Expected at least 5 Platinum companies, got {len(platinum)}"
    for cycle in [1, 2, 3, 4, 5, 100]:
        batch = get_batch(cycle)
        batch_names = [c["name"] for c in batch]
        for co in platinum:
            assert co["name"] in batch_names, (
                f"Platinum company {co['name']} missing from cycle {cycle} batch"
            )


def test_tier1_companies_in_every_batch():
    from config.companies import get_batch, COMPANIES
    tier1 = [c for c in COMPANIES if c.get("tier") == 1]
    batch_1 = get_batch(1)
    for co in tier1:
        assert co in batch_1


def test_tier2_only_on_even_cycles():
    from config.companies import get_batch, COMPANIES
    tier2 = [c for c in COMPANIES if c.get("tier") == 2]
    batch_odd = get_batch(1)
    batch_even = get_batch(2)
    odd_names = [c["name"] for c in batch_odd]
    even_names = [c["name"] for c in batch_even]
    for co in tier2[:3]:  # spot check first 3
        assert co["name"] not in odd_names
        assert co["name"] in even_names
```

- [ ] **Step 6.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_companies.py::test_platinum_companies_in_every_batch -v
```
Expected: FAIL — no companies have tier 0

- [ ] **Step 6.3: Add Platinum companies (tier=0) to `companies.py`**

At the TOP of the `COMPANIES` list, before the Tier 1 section, add:

```python
    # ═══════════════════════════════════════
    #  PLATINUM — $220K+ known comp bands (every cycle, highest priority)
    #  Based on Levels.fyi senior data/ML engineer total comp as of 2026.
    #  Review quarterly.
    # ═══════════════════════════════════════

    # ── Quant/HFT (Playwright scrapers — see scrapers/playwright_scraper.py) ──
    # These companies have no public ATS API. Scraped via Playwright in Slice 3.
    # Listed here for config completeness; main.py skips ats=playwright in API loop.
    {"name": "Jane Street",          "ats": "playwright", "slug": "janestreet",    "tier": 0},
    {"name": "Two Sigma",            "ats": "playwright", "slug": "twosigma",      "tier": 0},
    {"name": "Hudson River Trading", "ats": "playwright", "slug": "hrt",           "tier": 0},
    {"name": "AQR Capital",          "ats": "playwright", "slug": "aqr",           "tier": 0},
    {"name": "D.E. Shaw",            "ats": "playwright", "slug": "deshaw",        "tier": 0},
    {"name": "Jump Trading",         "ats": "playwright", "slug": "jumptrading",   "tier": 0},

    # ── Big Tech Platinum (already in Tier 1 via Workday/Greenhouse) ──
    # These are already scraped — the platinum designation is a scoring/UI signal only.
    # Duplicate entries here would cause double-scraping. Instead, mark existing
    # entries with tier=0 below:
    # (Google, Meta, Apple, Microsoft, Amazon, NVIDIA, Anthropic, OpenAI, Stripe,
    #  Goldman Sachs, Citadel, Bloomberg are already Tier 1 — update their tier to 0)
```

Then update these existing company entries to `"tier": 0` (they're already in COMPANIES):

```python
    {"name": "Anthropic",          "ats": "greenhouse", "slug": "anthropic",             "tier": 0},
    {"name": "OpenAI",             "ats": "greenhouse", "slug": "openai",                "tier": 0},
    {"name": "Stripe",             "ats": "greenhouse", "slug": "stripe",                "tier": 0},
    {"name": "Databricks",         "ats": "greenhouse", "slug": "databricks",            "tier": 0},
    {"name": "Goldman Sachs",   "ats": "workday", "slug": "goldmansachs",  "wd_instance": "wd1", "wd_board": "GS",              "tier": 0},
    {"name": "Citadel",         "ats": "workday", "slug": "citadel",       "wd_instance": "wd5", "wd_board": "Careers",         "tier": 0},
    {"name": "Bloomberg",       "ats": "workday", "slug": "bloomberg",     "wd_instance": "wd5", "wd_board": "BloombergLP",     "tier": 0},
    {"name": "Apple",           "ats": "workday", "slug": "apple",         "wd_instance": "wd5", "wd_board": "US",              "tier": 0},
    {"name": "NVIDIA",          "ats": "workday", "slug": "nvidia",        "wd_instance": "wd5", "wd_board": "NVIDIAExternalCareerSite","tier": 0},
    {"name": "Microsoft",       "ats": "workday", "slug": "microsoft",     "wd_instance": "wd5", "wd_board": "MicrosoftExternalCareerSite","tier": 0},
    {"name": "Amazon",          "ats": "workday", "slug": "amazon",        "wd_instance": "wd5", "wd_board": "External",        "tier": 0},
    {"name": "Meta",            "ats": "workday", "slug": "meta",          "wd_instance": "wd5", "wd_board": "FBExternalCareerSite","tier": 0},
    {"name": "Google",          "ats": "workday", "slug": "google",        "wd_instance": "wd5", "wd_board": "jobs",            "tier": 0},
```

- [ ] **Step 6.4: Update `get_batch()` to include tier 0 every cycle**

In `get_batch()`, add the tier 0 condition:

```python
def get_batch(cycle_number: int, batch_size: int = 0) -> list[dict]:
    eligible = []
    for co in COMPANIES:
        tier = co.get("tier", 3)
        if tier in (0, 1):          # Platinum + Tier 1 — every cycle
            eligible.append(co)
        elif tier == 2 and cycle_number % 2 == 0:
            eligible.append(co)
        elif tier == 3 and cycle_number % 4 == 0:
            eligible.append(co)
    ...
```

Also update `run_scrape()` in `main.py` — skip companies with `ats == "playwright"` in the API scrape loop (they'll be handled in Task 14):

```python
        scraper = SCRAPERS.get(company.get("ats", ""))
        if not scraper:
            if company.get("ats") != "playwright":
                stats["errors"] += 1  # Only count as error if not playwright
            continue
```

- [ ] **Step 6.5: Run tests**

```bash
cd backend
python -m pytest tests/test_companies.py -v
```
Expected: PASS — all 3 tests green

- [ ] **Step 6.6: Commit**

```bash
git add backend/config/companies.py backend/tests/test_companies.py
git commit -m "feat: add Platinum tier (tier=0) for $220K+ companies, update get_batch"
```

---

### Task 7: Add Platinum score boost to `relevance.py`

**Files:**
- Modify: `backend/core/relevance.py`
- Create: `backend/tests/test_relevance.py`

- [ ] **Step 7.1: Write failing test**

Create `backend/tests/test_relevance.py`:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_platinum_boost_applied():
    from core.relevance import RelevanceEngine
    engine = RelevanceEngine()
    job_base = {
        "title": "Senior Data Engineer",
        "description": "Python, Spark, Kafka, ETL, data pipeline",
        "location": "Remote",
        "is_remote": True,
        "tier": "tier1",
    }
    job_platinum = {**job_base, "tier": "platinum"}
    score_base, _ = engine.score(job_base)
    score_platinum, _ = engine.score(job_platinum)
    assert score_platinum > score_base, (
        f"Platinum job should score higher than tier1 job: {score_platinum} <= {score_base}"
    )
    assert score_platinum <= 1.0, "Score must not exceed 1.0"


def test_platinum_boost_is_eight_percent():
    from core.relevance import RelevanceEngine, PLATINUM_BOOST
    engine = RelevanceEngine()
    job = {
        "title": "Data Engineer",
        "description": "Python Spark",
        "location": "Dallas TX",
        "is_remote": False,
        "tier": "platinum",
    }
    score, _ = engine.score(job)
    job_no_boost = {**job, "tier": "tier1"}
    score_no_boost, _ = engine.score(job_no_boost)
    expected_diff = PLATINUM_BOOST
    actual_diff = round(score - score_no_boost, 4)
    # Allow for clamping at 1.0
    assert actual_diff == expected_diff or score == 1.0
```

- [ ] **Step 7.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_relevance.py -v
```
Expected: FAIL — `cannot import name 'PLATINUM_BOOST'`

- [ ] **Step 7.3: Add `PLATINUM_BOOST` and boost logic to `relevance.py`**

Add the constant near the top of `relevance.py`:

```python
PLATINUM_BOOST = 0.08
```

In `RelevanceEngine.score()`, after the `score = max(0.0, min(1.0, score))` clamp line, add:

```python
        # ── Platinum company boost (8%) ──
        if job.get("tier") == "platinum":
            score = min(1.0, score + PLATINUM_BOOST)
```

- [ ] **Step 7.4: Run tests**

```bash
cd backend
python -m pytest tests/test_relevance.py -v
```
Expected: PASS

- [ ] **Step 7.5: Wire tier into `run_scrape()` in `main.py`**

In the per-company loop in `run_scrape()`, after `score, matched = engine.score(raw_job)`, add:

```python
                tier_label = "platinum" if company.get("tier") == 0 else f"tier{company.get('tier', 1)}"
                raw_job["tier"] = tier_label
```

- [ ] **Step 7.6: Commit**

```bash
git add backend/core/relevance.py backend/main.py backend/tests/test_relevance.py
git commit -m "feat: add 8% Platinum score boost in relevance engine"
```

---

### Task 8: Include `tier` and `salary` in `export_data.py` JSON output

**Files:**
- Modify: `backend/export_data.py`
- Create: `backend/tests/test_export.py`

- [ ] **Step 8.1: Write failing test**

Create `backend/tests/test_export.py`:

```python
import json
import sqlite3
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _seed_db(db_path):
    from storage.db import init_db, upsert_job, get_conn
    init_db(db_path)
    conn = get_conn(db_path)
    upsert_job(conn, {
        "external_id": "gh-test-1",
        "title": "Senior Data Engineer",
        "company": "Jane Street",
        "location": "Remote",
        "department": "",
        "description": "Python Spark",
        "url": "https://janestreet.com/apply",
        "ats": "playwright",
        "is_remote": True,
        "posted_at": "2026-04-27",
        "salary_min": 220000,
        "salary_max": 350000,
        "relevance_score": 0.91,
        "matched_skills": ["python", "spark"],
        "sponsorship": False,
        "tier": "platinum",
    })
    conn.commit()
    conn.close()


def test_export_includes_tier_in_jobs():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        out_path = os.path.join(d, "api-data.json")
        _seed_db(db_path)
        from export_data import export
        export(db_path, out_path, cycle_counter=1)
        with open(out_path) as f:
            data = json.load(f)
        assert len(data["jobs"]) == 1
        job = data["jobs"][0]
        assert job.get("tier") == "platinum", f"Expected tier='platinum', got: {job.get('tier')}"
        assert job.get("salary_max") == 350000
```

- [ ] **Step 8.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_export.py -v
```
Expected: FAIL — `tier` missing from exported job dict (SELECT * should include it after Task 1)

- [ ] **Step 8.3: Verify `export_data.py` already selects `*` from jobs**

The query is `SELECT * FROM jobs WHERE is_active = 1`. Since we added `tier` to the table in Task 1, this should now include `tier` automatically. Run the test:

```bash
cd backend
python -m pytest tests/test_export.py -v
```
If it passes already — great, commit without changes. If it still fails, check that `init_db` added the `tier` column correctly.

- [ ] **Step 8.4: Commit (or no-op if test already passed)**

```bash
git add backend/tests/test_export.py
git commit -m "test: verify export includes tier and salary in job payload"
```

---

### Task 9: Add Platinum badge + filter + $220K chip to React dashboard

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 9.1: Add `isPlatinum` helper and Platinum badge to job cards**

In `App.jsx`, find where job cards are rendered (search for `relevance_score` display or job card `className`). Add a helper near the top of the component or in a utils section:

```javascript
const isPlatinum = (job) => job.tier === 'platinum';
const isHighComp = (job) => job.salary_max >= 220000 || isPlatinum(job);
```

In the job card JSX, add a Platinum badge next to the company name (right after where company name is displayed):

```jsx
{isPlatinum(job) && (
  <span style={{
    background: 'linear-gradient(135deg, #b8860b, #ffd700)',
    color: '#1a1a1a',
    fontSize: '10px',
    fontWeight: '700',
    padding: '2px 6px',
    borderRadius: '4px',
    marginLeft: '6px',
    letterSpacing: '0.5px',
  }}>
    PLATINUM
  </span>
)}
```

Also add a salary display on the card when `salary_min > 0`:

```jsx
{job.salary_min > 0 && (
  <span style={{ color: '#22c55e', fontSize: '12px', fontWeight: '600' }}>
    ${Math.round(job.salary_min / 1000)}K–${Math.round(job.salary_max / 1000)}K
  </span>
)}
```

- [ ] **Step 9.2: Add Platinum filter tab and $220K+ chip**

Find the filter tabs section (search for `"All"` or the tab bar rendering). Add a "Platinum" tab:

```javascript
const FILTER_TABS = ['All', 'Platinum', '$220K+', 'Dream', 'Remote', 'H1B'];
```

In the filtering logic (where jobs are filtered based on active tab), add cases:

```javascript
case 'Platinum':
  filtered = filtered.filter(j => j.tier === 'platinum');
  break;
case '$220K+':
  filtered = filtered.filter(j => j.salary_max >= 220000 || j.tier === 'platinum');
  break;
```

In the sorted results, Platinum jobs should sort to the top within any active filter. After filtering, add:

```javascript
filtered.sort((a, b) => {
  if (isPlatinum(a) && !isPlatinum(b)) return -1;
  if (!isPlatinum(a) && isPlatinum(b)) return 1;
  return (b.relevance_score || 0) - (a.relevance_score || 0);
});
```

- [ ] **Step 9.3: Run frontend dev server and verify**

```bash
cd frontend
npm run dev
```

Open browser at `http://localhost:5173`. Verify:
- "Platinum" and "$220K+" filter tabs appear
- Job cards for Platinum companies show gold "PLATINUM" badge
- Salary range appears on cards where `salary_min > 0`
- Platinum tab shows only Platinum jobs
- $220K+ tab shows Platinum + high-salary jobs

- [ ] **Step 9.4: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: Platinum badge, filter tab, and $220K+ chip in React dashboard"
```

---

## SLICE 3 — Pipeline View + Playwright Scrapers

---

### Task 10: Add PATCH + DELETE `/api/applications` endpoints to `server.py`

**Files:**
- Modify: `backend/server.py`
- Create: `backend/tests/test_applications_api.py`

- [ ] **Step 10.1: Write failing test**

Create `backend/tests/test_applications_api.py`:

```python
import json
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["DB_PATH"] = ":memory:"  # won't work with Flask test client — use temp file

import pytest


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    os.environ["DB_PATH"] = db_path
    from storage.db import init_db
    init_db(db_path)
    import server
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


def _seed_application(client):
    payload = {
        "external_id": "gh-test-1",
        "title": "Senior Data Engineer",
        "company": "Anthropic",
        "url": "https://anthropic.com/careers/1",
        "status": "saved",
        "relevance_score": 0.9,
        "salary_min": 250000,
        "salary_max": 350000,
        "location": "Remote",
    }
    return client.post("/api/applications", json=payload)


def test_patch_application_status(client):
    _seed_application(client)
    resp = client.patch("/api/applications/gh-test-1", json={
        "status": "applied",
        "notes": "Applied via website",
        "resume_version": "anthropic_de",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "applied"
    assert data["notes"] == "Applied via website"


def test_delete_application(client):
    _seed_application(client)
    resp = client.delete("/api/applications/gh-test-1")
    assert resp.status_code == 200
    # Verify it no longer appears in GET
    list_resp = client.get("/api/applications")
    apps = list_resp.get_json().get("applications", [])
    ext_ids = [a["external_id"] for a in apps]
    assert "gh-test-1" not in ext_ids
```

- [ ] **Step 10.2: Run test to confirm it fails**

```bash
cd backend
python -m pytest tests/test_applications_api.py -v
```
Expected: FAIL — 404 or 405 for PATCH/DELETE

- [ ] **Step 10.3: Add PATCH and DELETE routes to `server.py`**

Find where existing `/api/applications` routes are defined. Add after them:

```python
@app.route("/api/applications/<string:ext_id>", methods=["PATCH"])
def update_application(ext_id):
    """Update application status, notes, or resume_version."""
    data = request.get_json() or {}
    allowed = {"status", "notes", "resume_version", "applied_at"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    conn = get_conn(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [ext_id]
    conn.execute(
        f"UPDATE applications SET {set_clause} WHERE external_id = ?", values
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM applications WHERE external_id = ?", (ext_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": "Application not found"}), 404
    return jsonify(dict(row))


@app.route("/api/applications/<string:ext_id>", methods=["DELETE"])
def delete_application(ext_id):
    """Soft-delete: set status to 'removed'."""
    conn = get_conn(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE applications SET status = 'removed', updated_at = ? WHERE external_id = ?",
        (now, ext_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "removed": ext_id})
```

Also ensure `GET /api/applications` excludes `status='removed'` entries:

```python
@app.route("/api/applications", methods=["GET"])
def list_applications():
    status_filter = request.args.get("status", "")
    conn = get_conn(DB_PATH)
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM applications WHERE status = ? ORDER BY saved_at DESC",
            (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM applications WHERE status != 'removed' ORDER BY saved_at DESC"
        ).fetchall()
    conn.close()
    return jsonify({"applications": [dict(r) for r in rows]})
```

Add `from datetime import datetime, timezone` at the top of server.py if not already present.

- [ ] **Step 10.4: Run tests**

```bash
cd backend
python -m pytest tests/test_applications_api.py -v
```
Expected: PASS

- [ ] **Step 10.5: Commit**

```bash
git add backend/server.py backend/tests/test_applications_api.py
git commit -m "feat: add PATCH/DELETE /api/applications endpoints for pipeline tracking"
```

---

### Task 11: Add applications kanban pipeline view to `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 11.1: Add pipeline data fetching**

In `App.jsx`, in the API data fetch logic (where `/api/data` or similar is fetched), add a parallel fetch for applications:

```javascript
// In the useEffect that fetches job data, also fetch applications
const fetchApplications = async () => {
  try {
    const base = window.RENDER_URL || import.meta.env.VITE_RENDER_URL || '';
    const resp = await fetch(`${base}/api/applications`);
    if (resp.ok) {
      const data = await resp.json();
      setApplications(data.applications || []);
    }
  } catch (e) {
    console.warn('Could not fetch applications:', e);
  }
};
```

Add `const [applications, setApplications] = useState([])` to state declarations.

- [ ] **Step 11.2: Add the Pipeline tab to the tab bar**

Find where the 6 tabs are rendered (search for `"Monitor"` or `"Tracker"`). Add or replace the Tracker tab with "Pipeline":

```javascript
const TABS = ['Jobs', 'Analytics', 'Companies', 'Trends', 'Pipeline', 'Monitor'];
```

- [ ] **Step 11.3: Add kanban pipeline JSX**

Add a new section rendered when `activeTab === 'Pipeline'`. The pipeline columns are:

```javascript
const PIPELINE_STAGES = [
  { key: 'saved',        label: 'Saved',        color: '#6b7280' },
  { key: 'applied',      label: 'Applied',      color: '#3b82f6' },
  { key: 'interview',    label: 'Phone Screen', color: '#f59e0b' },
  { key: 'technical',    label: 'Technical',    color: '#8b5cf6' },
  { key: 'offer',        label: 'Offer',        color: '#22c55e' },
  { key: 'rejected',     label: 'Rejected',     color: '#ef4444' },
];
```

Render as horizontal columns:

```jsx
{activeTab === 'Pipeline' && (
  <div>
    {/* Stats bar */}
    <div style={{ display: 'flex', gap: '16px', marginBottom: '20px', flexWrap: 'wrap' }}>
      <span>Applied this week: {applications.filter(a =>
        a.status === 'applied' &&
        new Date(a.applied_at) > new Date(Date.now() - 7*24*60*60*1000)
      ).length}</span>
      <span>In technical: {applications.filter(a => a.status === 'technical').length}</span>
      <span>Offers: {applications.filter(a => a.status === 'offer').length}</span>
    </div>

    {/* Kanban columns */}
    <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', alignItems: 'flex-start' }}>
      {PIPELINE_STAGES.map(stage => {
        const stageApps = applications.filter(a => a.status === stage.key);
        return (
          <div key={stage.key} style={{
            minWidth: '200px', flex: '0 0 200px',
            background: 'var(--card-bg, #1e1e2e)',
            borderRadius: '8px', padding: '12px',
          }}>
            <div style={{
              fontWeight: '700', fontSize: '13px',
              color: stage.color, marginBottom: '10px',
              display: 'flex', justifyContent: 'space-between',
            }}>
              {stage.label}
              <span style={{ color: '#888' }}>{stageApps.length}</span>
            </div>
            {stageApps.map(app => (
              <div key={app.external_id} style={{
                background: 'var(--bg, #13131d)',
                borderRadius: '6px', padding: '10px', marginBottom: '8px',
                borderLeft: `3px solid ${stage.color}`,
              }}>
                <div style={{ fontWeight: '600', fontSize: '13px' }}>{app.company}</div>
                <div style={{ fontSize: '11px', color: '#888', marginBottom: '6px' }}>{app.title}</div>
                {app.salary_max > 0 && (
                  <div style={{ fontSize: '11px', color: '#22c55e' }}>
                    ${Math.round(app.salary_min/1000)}K–${Math.round(app.salary_max/1000)}K
                  </div>
                )}
                <select
                  value={app.status}
                  onChange={async (e) => {
                    const newStatus = e.target.value;
                    const base = window.RENDER_URL || import.meta.env.VITE_RENDER_URL || '';
                    await fetch(`${base}/api/applications/${app.external_id}`, {
                      method: 'PATCH',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ status: newStatus }),
                    });
                    setApplications(prev => prev.map(a =>
                      a.external_id === app.external_id ? { ...a, status: newStatus } : a
                    ));
                  }}
                  style={{ fontSize: '11px', marginTop: '6px', width: '100%' }}
                >
                  {PIPELINE_STAGES.map(s => (
                    <option key={s.key} value={s.key}>{s.label}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  </div>
)}
```

- [ ] **Step 11.4: Add "Mark Applied" button to job cards in main Jobs tab**

In the job card JSX, add a button after the "Apply" link:

```jsx
<button
  onClick={async () => {
    const base = window.RENDER_URL || import.meta.env.VITE_RENDER_URL || '';
    const payload = {
      external_id: job.external_id,
      title: job.title,
      company: job.company,
      url: job.url,
      status: 'applied',
      relevance_score: job.relevance_score,
      salary_min: job.salary_min || 0,
      salary_max: job.salary_max || 0,
      location: job.location || '',
    };
    const resp = await fetch(`${base}/api/applications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      const newApp = await resp.json();
      setApplications(prev => [...prev.filter(a =>
        a.external_id !== job.external_id
      ), newApp]);
      alert(`Marked as applied: ${job.company} — ${job.title}`);
    }
  }}
  style={{
    background: '#3b82f6', color: '#fff', border: 'none',
    borderRadius: '4px', padding: '4px 10px', fontSize: '12px',
    cursor: 'pointer', marginLeft: '8px',
  }}
>
  Mark Applied
</button>
```

- [ ] **Step 11.5: Test in browser**

```bash
cd frontend
npm run dev
```

Verify:
- "Pipeline" tab appears in tab bar
- Pipeline tab shows 6 kanban columns
- Stats bar shows counts
- "Mark Applied" button on job cards moves job to Applied column in Pipeline tab
- Status dropdown on pipeline cards updates the status immediately

- [ ] **Step 11.6: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: applications kanban pipeline view with Mark Applied button"
```

---

### Task 12: Create Playwright scrapers for quant/HFT firms

**Files:**
- Create: `backend/scrapers/playwright_scraper.py`
- Create: `backend/tests/test_playwright.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 12.1: Add playwright to requirements**

Add to `backend/requirements.txt`:

```
playwright>=1.40.0
```

Install it:

```bash
cd backend
pip install playwright
playwright install chromium
```

- [ ] **Step 12.2: Create `backend/scrapers/playwright_scraper.py`**

```python
"""
Playwright scrapers for quant/HFT firms that run their own career portals.
These companies have no public ATS API.

Run once per scrape cycle alongside Tier 1 companies.
Each scraper has a 60-second timeout.
"""

import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)

PLAYWRIGHT_TARGETS = [
    {
        "name": "Jane Street",
        "ats": "playwright",
        "tier": 0,
        "url": "https://www.janestreet.com/join-jane-street/open-roles/",
        "wait_for": "networkidle",
        "job_container": "div.open-role",
        "title_selector": "h3, .role-title, [class*='title']",
        "link_selector": "a",
        "location_text": "New York, NY / Remote",
    },
    {
        "name": "Two Sigma",
        "ats": "playwright",
        "tier": 0,
        "url": "https://careers.twosigma.com/careers/SearchJobs/",
        "wait_for": "networkidle",
        "job_container": "li.mat-list-item, .job-listing, [class*='jobItem']",
        "title_selector": "h3, .job-title, [class*='title']",
        "link_selector": "a",
        "location_text": "New York, NY",
    },
    {
        "name": "Hudson River Trading",
        "ats": "playwright",
        "tier": 0,
        "url": "https://www.hudsonrivertrading.com/careers/",
        "wait_for": "networkidle",
        "job_container": ".job-item, .career-listing, [class*='job']",
        "title_selector": "h3, .job-title, [class*='title']",
        "link_selector": "a",
        "location_text": "New York, NY",
    },
    {
        "name": "D.E. Shaw",
        "ats": "playwright",
        "tier": 0,
        "url": "https://www.deshaw.com/careers/open-positions",
        "wait_for": "networkidle",
        "job_container": ".position-item, .job-card, [class*='position']",
        "title_selector": "h2, h3, .position-title",
        "link_selector": "a",
        "location_text": "New York, NY",
    },
    {
        "name": "AQR Capital",
        "ats": "playwright",
        "tier": 0,
        "url": "https://careers.aqr.com/jobs",
        "wait_for": "networkidle",
        "job_container": ".job-listing, [class*='job'], li[class*='position']",
        "title_selector": "h3, .job-title, a",
        "link_selector": "a",
        "location_text": "Greenwich, CT / Remote",
    },
    {
        "name": "Jump Trading",
        "ats": "playwright",
        "tier": 0,
        "url": "https://www.jumptrading.com/careers/",
        "wait_for": "networkidle",
        "job_container": ".job-card, [class*='career'], [class*='role']",
        "title_selector": "h3, h4, .job-title",
        "link_selector": "a",
        "location_text": "Chicago, IL / Remote",
    },
]

# Only scrape these title patterns (same keywords used in relevance engine)
RELEVANT_PATTERNS = re.compile(
    r'(data engineer|ml engineer|machine learning|data scientist|analytics engineer'
    r'|ai engineer|data platform|mlops|platform engineer|infrastructure engineer'
    r'|quant|quantitative|researcher)',
    re.IGNORECASE,
)


def _make_external_id(company_name: str, title: str, url: str) -> str:
    slug = re.sub(r'[^a-z0-9]', '-', company_name.lower())
    title_slug = re.sub(r'[^a-z0-9]', '-', title.lower())[:40]
    url_hash = str(abs(hash(url)) % 100000)
    return f"pw-{slug}-{title_slug}-{url_hash}"


def scrape_playwright_company(target: dict) -> list[dict]:
    """
    Scrape one career portal using Playwright. Returns normalized job dicts.
    Returns [] on any error — never raises.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("playwright not installed — skipping %s", target["name"])
        return []

    jobs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(60000)

            log.info("Playwright → %s (%s)", target["name"], target["url"])
            page.goto(target["url"], wait_until=target.get("wait_for", "networkidle"))

            containers = page.query_selector_all(target["job_container"])
            log.info("  Found %d containers on %s", len(containers), target["name"])

            for el in containers:
                # Try to extract title
                title_el = el.query_selector(target["title_selector"])
                title = (title_el.inner_text() if title_el else el.inner_text()).strip()
                title = " ".join(title.split())[:200]  # normalize whitespace

                if not title or not RELEVANT_PATTERNS.search(title):
                    continue

                # Try to extract link
                link_el = el.query_selector(target["link_selector"])
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(target["url"], href)

                ext_id = _make_external_id(target["name"], title, href or target["url"])
                now = datetime.now(timezone.utc).isoformat()

                jobs.append({
                    "external_id": ext_id,
                    "title": title,
                    "company": target["name"],
                    "location": target.get("location_text", ""),
                    "department": "",
                    "description": f"{title} at {target['name']}. Apply at: {href}",
                    "url": href or target["url"],
                    "ats": "playwright",
                    "is_remote": "remote" in target.get("location_text", "").lower(),
                    "posted_at": now[:10],
                    "salary_min": 0,
                    "salary_max": 0,
                    "tier": "platinum",
                })

            browser.close()

    except Exception as e:
        log.error("Playwright failed for %s: %s", target["name"], e)

    log.info("  %s → %d relevant jobs", target["name"], len(jobs))
    return jobs


def scrape_all_playwright(targets: list[dict] = None) -> list[dict]:
    """Scrape all Playwright targets. Returns combined list of job dicts."""
    if targets is None:
        targets = PLAYWRIGHT_TARGETS
    all_jobs = []
    for target in targets:
        all_jobs.extend(scrape_playwright_company(target))
    return all_jobs
```

- [ ] **Step 12.3: Write a smoke test for Playwright scraper structure**

Create `backend/tests/test_playwright.py`:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_playwright_targets_have_required_keys():
    from scrapers.playwright_scraper import PLAYWRIGHT_TARGETS
    required = {"name", "ats", "tier", "url", "job_container", "title_selector", "link_selector"}
    for target in PLAYWRIGHT_TARGETS:
        missing = required - set(target.keys())
        assert not missing, f"{target['name']} missing keys: {missing}"


def test_make_external_id_is_stable():
    from scrapers.playwright_scraper import _make_external_id
    id1 = _make_external_id("Jane Street", "Senior Data Engineer", "https://janestreet.com/apply/123")
    id2 = _make_external_id("Jane Street", "Senior Data Engineer", "https://janestreet.com/apply/123")
    assert id1 == id2
    assert id1.startswith("pw-jane-street-")


def test_relevant_patterns_match_expected_titles():
    from scrapers.playwright_scraper import RELEVANT_PATTERNS
    assert RELEVANT_PATTERNS.search("Senior Data Engineer")
    assert RELEVANT_PATTERNS.search("ML Engineer, Research")
    assert RELEVANT_PATTERNS.search("Quantitative Researcher")
    assert not RELEVANT_PATTERNS.search("Software Engineer, Trading UI")
    assert not RELEVANT_PATTERNS.search("Recruiter, Technology")
```

- [ ] **Step 12.4: Run structural tests**

```bash
cd backend
python -m pytest tests/test_playwright.py -v
```
Expected: PASS (no network calls, pure structure tests)

- [ ] **Step 12.5: Commit**

```bash
git add backend/scrapers/playwright_scraper.py backend/tests/test_playwright.py backend/requirements.txt
git commit -m "feat: Playwright scrapers for Jane Street, Two Sigma, HRT, D.E. Shaw, AQR, Jump Trading"
```

---

### Task 13: Wire Playwright into `main.py` scrape loop

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 13.1: Add Playwright call after the main scrape loop**

In `run_scrape()`, after the `for company in companies:` loop finishes (after `mark_stale_jobs` and before `finish_run`), add:

```python
    # ── Playwright scrapers (quant/HFT firms with no ATS API) ──
    try:
        from scrapers.playwright_scraper import scrape_all_playwright, PLAYWRIGHT_TARGETS
        pw_jobs = scrape_all_playwright(PLAYWRIGHT_TARGETS)
        for raw_job in pw_jobs:
            score, matched = engine.score(raw_job)
            raw_job["relevance_score"] = score
            raw_job["matched_skills"] = matched
            raw_job["sponsorship"] = _detect_sponsorship(raw_job)

            min_score = PROFILE.get("min_score_threshold", 0.30)
            if score < min_score:
                continue

            result = upsert_job(conn, raw_job)
            if result == "new":
                stats["new"] += 1
                stats["found"] += 1
            elif result == "updated":
                stats["updated"] += 1

        conn.commit()
        log.info("Playwright scrapers: %d jobs processed", len(pw_jobs))
    except Exception as e:
        log.warning("Playwright scrape failed (non-critical): %s", e)
```

- [ ] **Step 13.2: Verify main.py runs without error (no-network dry run)**

```bash
cd backend
python -c "
import main
print('main.py imports OK')
print('load_cycle_counter:', main.load_cycle_counter())
"
```
Expected: prints without error (cycle counter may be 1 if no api-data.json exists yet)

- [ ] **Step 13.3: Commit**

```bash
git add backend/main.py
git commit -m "feat: wire Playwright scrapers into main scrape loop"
```

---

### Task 14: Create GitHub issue for auto-tracking future spec

**Files:**
- No code files — GitHub issue only

- [ ] **Step 14.1: Create the issue**

```bash
gh issue create \
  --title "[Feature] Automatic application tracking via email parsing + extension events" \
  --body "$(cat <<'EOF'
## Vision

Close the loop between job discovery and application tracking without any manual input.

## Phase 2 Scope

### Email Parsing
- Monitor Gmail inbox for ATS confirmation emails
- Sender patterns: `no-reply@greenhouse.io`, `apply@lever.co`, `noreply@myworkdayjobs.com`
- Subject patterns: "Application received", "Thank you for applying", "We received your application"
- Auto-create `applications` record on match with `status='applied'`
- Status updates from follow-up emails: interview invite → `status='interview'`, rejection → `status='rejected'`

### Extension Event Integration  
- When autoapply-ai Chrome extension submits an application, fire `POST /api/applications` to job-scout
- Payload: `{ external_id, title, company, url, status: 'applied', resume_version }`
- job-scout already exposes this endpoint — just needs the extension to call it

### Implementation Notes
- Gmail API: OAuth 2.0, `gmail.readonly` scope
- Polling interval: every 30 minutes via GitHub Actions cron
- Deduplication: check `applications.external_id` before insert
- autoapply-ai endpoint to add: `POST /api/external/job-scout-sync` (calls job-scout with credentials)

## Not In Scope
- Parsing offer details from email
- Automatic reply drafting

## Dependencies
- Job Scout PATCH /api/applications endpoint (done in Slice 3)
- autoapply-ai Chrome extension APPLICATION_SUBMITTED event (partially built)
EOF
)"
```

- [ ] **Step 14.2: Note the issue URL in the CLAUDE.md**

Open `job-scout/CLAUDE.md` and add under the Roadmap section:

```markdown
### Phase 2: Auto-Tracking (GitHub Issue #[N])
Auto-tracking via email parsing + extension events. See GitHub issue for scope.
```

- [ ] **Step 14.3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note auto-tracking feature issue in roadmap"
```

---

## Final Integration Check

- [ ] **Run all tests**

```bash
cd backend
python -m pytest tests/ -v
```
Expected: All tests pass

- [ ] **Run a fast local scrape to verify end-to-end**

```bash
cd backend
python main.py --fast --export-only
```
Check `frontend/public/api-data.json` contains `metadata.cycle_counter` and that at least one job has `tier` set.

- [ ] **Check frontend builds**

```bash
cd frontend
npm run build
```
Expected: No TypeScript/build errors

- [ ] **Final commit + tag**

```bash
git add -A
git commit -m "chore: job-scout v4.0 — Platinum tier, reliability, pipeline view, Playwright scrapers"
git tag v4.0.0
```
