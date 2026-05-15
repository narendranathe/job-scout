"""
Canonical scrape orchestrator.

Single source of truth for one scrape cycle, shared by:
  • backend/main.py        — CLI / GitHub Actions cron (status_broker=None)
  • backend/server.py      — Flask background thread (status_broker=broker)

Replaces the two near-identical run_scrape() functions that previously lived
in main.py and server.py. Drift between them was the root cause of issue #19.

The full scoring + persistence pipeline runs here unconditionally:
keyword title pre-filter, salary backfill, tier labeling, sponsorship
detection, relevance scoring, upsert, stale-marking, cycle-absence
inference, and Playwright targets. Live progress is reported through the
optional status broker (start/tick/finish); CLI callers pass None and
get the same scrape work with zero broker overhead.

Connection lifecycle: the caller owns `conn` (open + close). SQLite
connections are not thread-safe, so server.py creates the connection
*inside* the background thread that calls this function.
"""

import os
import time
import json
import logging
from pathlib import Path

from config.companies import COMPANIES, get_batch, TOTAL_COMPANIES
from config.profile import PROFILE
from core.relevance import RelevanceEngine
from storage.db import (
    upsert_job, mark_stale_jobs,
    increment_cycles_missing,
    start_run, finish_run,
)
from scrapers.utils import scrape_with_retry, parse_salary

log = logging.getLogger(__name__)


# ─── Scraper Registry ─────────────────────────────────────────────
SCRAPERS: dict = {}


def _load_scrapers() -> None:
    global SCRAPERS
    if SCRAPERS:
        return
    from scrapers import greenhouse, lever, ashby, smartrecruiters, bamboohr
    SCRAPERS = {
        "greenhouse":      greenhouse,
        "lever":           lever,
        "ashby":           ashby,
        "smartrecruiters": smartrecruiters,
        "bamboohr":        bamboohr,
    }
    try:
        from scrapers import workday
        SCRAPERS["workday"] = workday
        log.info("Workday scraper loaded")
    except ImportError:
        log.warning("Workday scraper not found — skipping Workday companies")


# ─── Cycle counter ────────────────────────────────────────────────
_JSON_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend" / "public" / "api-data.json"
)


def _load_cycle_counter() -> int:
    """Read cycle counter from api-data.json metadata, increment, return new value."""
    try:
        with open(_JSON_OUTPUT_PATH) as f:
            data = json.load(f)
        return data.get("metadata", {}).get("cycle_counter", 0) + 1
    except Exception:
        return 1


# ─── Helpers ──────────────────────────────────────────────────────
def _detect_sponsorship(job: dict) -> bool:
    text = ((job.get("description") or "") + " " + (job.get("company") or "")).lower()
    pos = any(kw in text for kw in ["visa sponsor", "h1b", "h-1b", "sponsorship available"])
    neg = any(kw in text for kw in ["no sponsorship", "not sponsor", "unable to sponsor"])
    return pos and not neg


def _load_resume_text(conn) -> str | None:
    """Best-effort fetch of the most recent resume version's text for the
    TF-IDF booster. Returns None on any error so scoring continues with
    keyword-only logic when no resume has been uploaded."""
    try:
        from storage.db import list_resume_versions
        versions = list_resume_versions(conn)
        if not versions:
            return None
        return versions[0].get("resume_text") or None
    except Exception as e:
        log.debug("Resume load skipped: %s", e)
        return None


def _maybe_alert(job: dict) -> None:
    """Fire dream-job alert; swallow errors so scraping continues."""
    try:
        from alerts.notifier import notify_dream_job
        notify_dream_job(job)
    except Exception as e:
        log.debug("Alert check failed: %s", e)


# ─── Orchestrator ─────────────────────────────────────────────────
def run_scrape(conn, *, mode: str = "fast", status_broker=None) -> dict:
    """Execute one scrape cycle against an already-open DB connection.

    Args:
        conn: SQLite connection. Caller owns open/close. SQLite connections
            are not thread-safe, so threaded callers (e.g. server.py's
            /api/scrape) must create the connection inside the worker thread.
        mode: "fast" → Tier 0/1 only (~30s); "full" → all tiers eligible
            this cycle per get_batch() (~3 min).
        status_broker: Optional progress broker (core.scrape_status.broker).
            When provided, start/tick/finish are called to drive
            GET /api/scrape/status. CLI invocations pass None.

    Returns:
        Stats dict: {companies, found, new, updated, errors, skipped,
                     relevant, cycle}.
    """
    _load_scrapers()
    delay = float(os.environ.get("SCRAPE_DELAY", "0.3"))

    engine = RelevanceEngine(resume_text=_load_resume_text(conn))
    run_id = start_run(conn)
    cycle = _load_cycle_counter()

    if mode == "fast":
        companies = [c for c in COMPANIES if c.get("tier", 3) in (0, 1)]
    else:
        companies = get_batch(cycle)

    stats = {
        "companies": 0, "found": 0, "new": 0,
        "updated": 0, "errors": 0, "skipped": 0, "relevant": 0,
    }
    # External_ids the scraper actually pulled this cycle, regardless of
    # whether they passed the score filter. Drives cycle-absence inference
    # (see increment_cycles_missing). Filtering would defeat the purpose:
    # a still-listed job that dipped below threshold shouldn't be marked
    # missing.
    seen_external_ids: set[str] = set()
    # Companies whose scrapers actually ran. Tier 2/3 only run every Nth
    # cycle (see config.companies.get_batch), so jobs from other companies
    # must be excluded from the absence penalty.
    scraped_companies: set[str] = set()

    # The /api/scrape handler may have pre-armed the broker via try_start()
    # so its 202 response can return an already-running snapshot. In that
    # case we must NOT re-start (it would reset started_at). Direct callers
    # (CLI, future cron) hit the True branch.
    if status_broker is not None and not status_broker.is_running():
        status_broker.start(mode, len(companies))

    log.info("═══ %s cycle %d — %d companies of %d total ═══",
             mode.upper(), cycle, len(companies), TOTAL_COMPANIES)

    try:
        for company in companies:
            scraper = SCRAPERS.get(company.get("ats", ""))
            if not scraper:
                # Playwright targets are not in SCRAPERS — they run via
                # scrape_all_playwright() below. Don't count them as errors.
                if company.get("ats") != "playwright":
                    stats["errors"] += 1
                    if status_broker is not None:
                        status_broker.tick(company.get("name", "?"), error_delta=1)
                continue

            stats["companies"] += 1
            scraped_companies.add(company["name"])
            co_relevant = 0
            company_found = 0
            company_new = 0

            try:
                jobs_from_co = scrape_with_retry(
                    lambda: list(scraper.scrape(company)),
                    company["name"],
                )
                for raw_job in jobs_from_co:
                    stats["found"] += 1
                    company_found += 1
                    ext_id = raw_job.get("external_id")
                    if ext_id:
                        seen_external_ids.add(ext_id)
                    if not engine.is_relevant_title(raw_job.get("title", "")):
                        stats["skipped"] += 1
                        continue

                    # Assign tier BEFORE scoring so the Platinum boost fires
                    tier_label = (
                        "platinum" if company.get("tier") == 0
                        else f"tier{company.get('tier', 1)}"
                    )
                    raw_job["tier"] = tier_label

                    # Parse salary BEFORE scoring so the salary tier boost
                    # (issue #10) can read salary_max/salary_min off the dict.
                    if not raw_job.get("salary_min") and not raw_job.get("salary_max"):
                        desc = raw_job.get("description", "")
                        sal_min, sal_max = parse_salary(desc)
                        if sal_min:
                            raw_job["salary_min"] = sal_min
                            raw_job["salary_max"] = sal_max

                    score, matched = engine.score(raw_job)
                    raw_job["relevance_score"] = score
                    raw_job["matched_skills"]  = matched
                    raw_job["sponsorship"]     = _detect_sponsorship(raw_job)

                    min_score = PROFILE.get("min_score_threshold", 0.30)
                    if score < min_score:
                        stats["skipped"] += 1
                        continue

                    result = upsert_job(conn, raw_job)
                    if result == "new":
                        stats["new"] += 1
                        company_new += 1
                        # Dream-job alerts were historically a server-only
                        # behavior (broker-driven Flask path). Keep them gated
                        # on status_broker so the CLI / Actions cron retains
                        # the strict pre-#21 behavior of no per-job alerts.
                        if status_broker is not None:
                            _maybe_alert(raw_job)
                    elif result == "updated":
                        stats["updated"] += 1
                    stats["relevant"] += 1
                    co_relevant += 1

                conn.commit()
                log.info("✓ [T%s] %s — %d relevant",
                         company.get("tier", "?"), company["name"], co_relevant)
                if status_broker is not None:
                    status_broker.tick(company["name"],
                                       found_delta=company_found,
                                       new_delta=company_new)
                time.sleep(delay)
            except Exception as e:
                log.error("✗ %s — %s", company["name"], e)
                stats["errors"] += 1
                if status_broker is not None:
                    status_broker.tick(company.get("name", "?"),
                                       found_delta=company_found,
                                       new_delta=company_new,
                                       error_delta=1)

        mark_stale_jobs(conn, hours=96)
        conn.commit()

        # Playwright scrapers (quant/HFT firms with custom portals)
        playwright_ran = False
        try:
            from scrapers.playwright_scraper import scrape_all_playwright, PLAYWRIGHT_TARGETS
            pw_jobs = scrape_all_playwright()
            playwright_ran = True
            # Playwright targets aren't gated by tier rotation — they all run
            # when playwright is available, so include their company names in
            # the absence-eligibility set even if pw_jobs is empty.
            for t in PLAYWRIGHT_TARGETS:
                scraped_companies.add(t.get("name", ""))
            for raw_job in pw_jobs:
                ext_id = raw_job.get("external_id")
                if ext_id:
                    seen_external_ids.add(ext_id)
                # Mirror the title filter from the classical ATS path.
                if not engine.is_relevant_title(raw_job.get("title", "")):
                    stats["skipped"] += 1
                    continue
                # Normalise tier so the Platinum boost fires correctly.
                if raw_job.get("tier") not in ("platinum", "tier1", "tier2", "tier3"):
                    raw_job["tier"] = "tier1"
                score, matched = engine.score(raw_job)
                raw_job["relevance_score"] = score
                raw_job["matched_skills"]  = matched
                raw_job["sponsorship"]     = _detect_sponsorship(raw_job)
                if score < PROFILE.get("min_score_threshold", 0.30):
                    continue
                result = upsert_job(conn, raw_job)
                if result == "new":
                    stats["new"] += 1
                    stats["found"] += 1
                    # See note above — gate alerts on the broker so CLI
                    # callers preserve pre-#21 behavior.
                    if status_broker is not None:
                        _maybe_alert(raw_job)
                elif result == "updated":
                    stats["updated"] += 1
            conn.commit()
            log.info("Playwright: %d jobs processed", len(pw_jobs))
        except Exception as e:
            log.warning("Playwright scrape skipped (playwright may not be installed): %s", e)

        # Cycle-absence inference runs AFTER all scrapers so
        # seen_external_ids is complete. If playwright didn't run, exclude
        # its targets so we don't penalise jobs the scraper couldn't have
        # observed this cycle.
        if not playwright_ran:
            try:
                from scrapers.playwright_scraper import PLAYWRIGHT_TARGETS
                for t in PLAYWRIGHT_TARGETS:
                    scraped_companies.discard(t.get("name", ""))
            except ImportError:
                pass
        increment_cycles_missing(conn, seen_external_ids, scraped_companies)
        conn.commit()

        finish_run(conn, run_id, stats)

        log.info("═══ Done — found=%d relevant=%d new=%d updated=%d errors=%d ═══",
                 stats["found"], stats["relevant"], stats["new"],
                 stats["updated"], stats["errors"])
        stats["cycle"] = cycle

        try:
            from alerts.notifier import alert_high_error_rate
            alert_high_error_rate(stats)
        except Exception as e:
            log.debug("Error-rate alert skipped: %s", e)

        return stats
    finally:
        if status_broker is not None:
            status_broker.finish(stats)
