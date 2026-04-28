#!/usr/bin/env python3
"""
JobScout CLI — For GitHub Actions and local testing.

This is the GitHub Actions component of Option D:
  • Hourly cron runs full 109-company sweep
  • Exports api-data.json (static fallback for dashboard)
  • Pings Render server to sync fresh data

Usage:
    python main.py                        # Full scrape (all tiers)
    python main.py --fast                 # Tier 1 only (~30s)
    python main.py --stats                # Print DB stats
    python main.py --export-only          # Re-export JSON
    python main.py --notify-render URL    # Ping Render after scrape
"""

import sys
import os
import time
import json
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.companies import COMPANIES, get_batch, TOTAL_COMPANIES
from config.profile import PROFILE
from core.relevance import RelevanceEngine
from storage.db import (
    init_db, get_conn, upsert_job, mark_stale_jobs,
    start_run, finish_run, get_stats,
)
from scrapers.utils import scrape_with_retry, parse_salary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jobscout")

# ─── Scraper Registry ────────────────────────────────
SCRAPERS = {}

def _load_scrapers():
    global SCRAPERS
    if SCRAPERS:
        return
    from scrapers import greenhouse, lever, ashby, smartrecruiters, bamboohr
    SCRAPERS = {
        "greenhouse": greenhouse,
        "lever": lever,
        "ashby": ashby,
        "smartrecruiters": smartrecruiters,
        "bamboohr": bamboohr,
    }
    try:
        from scrapers import workday
        SCRAPERS["workday"] = workday
        log.info("Workday scraper loaded")
    except ImportError:
        log.warning("Workday scraper not found — skipping Workday companies")


# ─── Cycle Counter ───────────────────────────────────
JSON_OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "api-data.json"
)


def load_cycle_counter() -> int:
    """Read cycle counter from api-data.json metadata, increment, return new value."""
    try:
        with open(JSON_OUTPUT_PATH) as f:
            data = json.load(f)
        return data.get("metadata", {}).get("cycle_counter", 0) + 1
    except Exception:
        return 1


# ─── Scrape Engine ───────────────────────────────────
def _detect_sponsorship(job: dict) -> bool:
    text = ((job.get("description") or "") + " " + (job.get("company") or "")).lower()
    pos = any(kw in text for kw in ["visa sponsor", "h1b", "h-1b", "sponsorship available"])
    neg = any(kw in text for kw in ["no sponsorship", "not sponsor", "unable to sponsor"])
    return pos and not neg


def run_scrape(db_path: str, mode: str = "full", delay: float = 0.3) -> dict:
    _load_scrapers()
    engine = RelevanceEngine()
    init_db(db_path)
    conn = get_conn(db_path)
    run_id = start_run(conn)
    cycle = load_cycle_counter()

    if mode == "fast":
        companies = [c for c in COMPANIES if c.get("tier", 3) in (0, 1)]
    else:
        companies = get_batch(cycle)

    stats = {
        "companies": 0, "found": 0, "new": 0,
        "updated": 0, "errors": 0, "skipped": 0, "relevant": 0,
    }

    log.info("═══ %s cycle %d — %d companies of %d total ═══",
             mode.upper(), cycle, len(companies), TOTAL_COMPANIES)

    for company in companies:
        scraper = SCRAPERS.get(company.get("ats", ""))
        if not scraper:
            if company.get("ats") != "playwright":
                stats["errors"] += 1  # Only count as error if not playwright
            continue

        stats["companies"] += 1
        co_relevant = 0

        jobs_from_co = scrape_with_retry(
            lambda: list(scraper.scrape(company)),
            company["name"],
        )
        for raw_job in jobs_from_co:
            stats["found"] += 1
            if not engine.is_relevant_title(raw_job.get("title", "")):
                stats["skipped"] += 1
                continue

            # Assign tier BEFORE scoring so the Platinum boost fires correctly
            tier_label = "platinum" if company.get("tier") == 0 else f"tier{company.get('tier', 1)}"
            raw_job["tier"] = tier_label

            score, matched = engine.score(raw_job)
            raw_job["relevance_score"] = score
            raw_job["matched_skills"] = matched
            raw_job["sponsorship"] = _detect_sponsorship(raw_job)

            # Parse salary from description if not already set
            if not raw_job.get("salary_min") and not raw_job.get("salary_max"):
                desc = raw_job.get("description", "")
                sal_min, sal_max = parse_salary(desc)
                if sal_min:
                    raw_job["salary_min"] = sal_min
                    raw_job["salary_max"] = sal_max

            min_score = PROFILE.get("min_score_threshold", 0.30)
            if score < min_score:
                stats["skipped"] += 1
                continue

            result = upsert_job(conn, raw_job)
            if result == "new":
                stats["new"] += 1
            elif result == "updated":
                stats["updated"] += 1
            stats["relevant"] += 1
            co_relevant += 1

        conn.commit()
        tier_label = f"T{company.get('tier', '?')}"
        log.info("✓ [%s] %s — %d relevant", tier_label, company["name"], co_relevant)
        time.sleep(delay)

    mark_stale_jobs(conn, hours=96)
    conn.commit()

    # Playwright scrapers (quant/HFT firms with custom portals)
    try:
        from scrapers.playwright_scraper import scrape_all_playwright
        pw_jobs = scrape_all_playwright()
        for raw_job in pw_jobs:
            # Playwright targets store their tier as "tier1" / "platinum" in the job dict
            # Ensure platinum boost fires by normalising the tier field
            if raw_job.get("tier") not in ("platinum", "tier1", "tier2", "tier3"):
                raw_job["tier"] = "tier1"
            score, matched = engine.score(raw_job)
            raw_job["relevance_score"] = score
            raw_job["matched_skills"] = matched
            raw_job["sponsorship"] = _detect_sponsorship(raw_job)
            if score < PROFILE.get("min_score_threshold", 0.30):
                continue
            result = upsert_job(conn, raw_job)
            if result == "new":
                stats["new"] += 1
                stats["found"] += 1
            elif result == "updated":
                stats["updated"] += 1
        conn.commit()
        log.info("Playwright: %d jobs processed", len(pw_jobs))
    except Exception as e:
        log.warning("Playwright scrape skipped (playwright may not be installed): %s", e)

    finish_run(conn, run_id, stats)
    conn.close()

    log.info("═══ Done — found=%d relevant=%d new=%d updated=%d errors=%d ═══",
             stats["found"], stats["relevant"], stats["new"], stats["updated"], stats["errors"])
    stats["cycle"] = cycle
    from alerts.notifier import alert_high_error_rate
    alert_high_error_rate(stats)
    return stats


def export_json(db_path: str, cycle: int = 0) -> dict:
    """Export DB → JSON for frontend static fallback."""
    output = JSON_OUTPUT_PATH
    os.makedirs(os.path.dirname(output), exist_ok=True)
    from export_data import export
    data = export(db_path, output, cycle_counter=cycle)
    log.info("Exported %d jobs → %s", data.get("stats", {}).get("total_jobs", 0), output)
    return data


def notify_render(render_url: str):
    """Ping Render server to trigger cache refresh after Actions scrape."""
    import requests
    try:
        resp = requests.post(f"{render_url}/api/scrape", timeout=10)
        log.info("Render notified: %s", resp.status_code)
    except Exception as e:
        log.warning("Render notification failed (non-critical): %s", e)


def main():
    parser = argparse.ArgumentParser(description="JobScout CLI — GitHub Actions + Local")
    parser.add_argument("--fast", action="store_true", help="Tier 1 only")
    parser.add_argument("--stats", action="store_true", help="Print stats")
    parser.add_argument("--export-only", action="store_true", help="Re-export JSON")
    parser.add_argument("--db", default="", help="Database path")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between companies")
    parser.add_argument("--notify-render", default="", help="Render URL to ping after scrape")
    args = parser.parse_args()

    db = args.db or os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))

    if args.stats:
        init_db(db)
        print(json.dumps(get_stats(db), indent=2, default=str))
        return

    if args.export_only:
        export_json(db)
        return

    mode = "fast" if args.fast else "full"
    stats = run_scrape(db, mode, args.delay)
    export_json(db, cycle=stats.get("cycle", 1))

    if args.notify_render:
        notify_render(args.notify_render)


if __name__ == "__main__":
    main()
