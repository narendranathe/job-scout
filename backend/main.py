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
import json
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.db import init_db, get_conn, get_stats
from core.scrape_orchestrator import run_scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jobscout")


# ─── Cycle Counter (for JSON export only) ─────────────
JSON_OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "api-data.json"
)


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
    # Backwards-compat alias: orchestrator reads SCRAPE_DELAY from env. Only
    # override when --delay is explicitly passed so a user-set env var still
    # wins for invocations that don't supply the flag.
    parser.add_argument("--delay", type=float, default=None,
                        help="Delay between companies (overrides SCRAPE_DELAY env)")
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

    if args.delay is not None:
        os.environ["SCRAPE_DELAY"] = str(args.delay)

    mode = "fast" if args.fast else "full"
    init_db(db)
    conn = get_conn(db)
    try:
        stats = run_scrape(conn, mode=mode)
    finally:
        conn.close()
    export_json(db, cycle=stats.get("cycle", 1))

    if args.notify_render:
        notify_render(args.notify_render)


if __name__ == "__main__":
    main()
