"""Background scrape loop + cache rebuild — extracted from server.py.

This module owns everything the daemon scraper thread needs:
- Quiet-hours detection (12am–5:30am CST)
- Cache rebuild after each cycle
- Fast-mode batch sizing
- Async scrape runner (used both by the loop and by /api/scrape)
- The loop itself + its enable-gate

Why a separate module: the daemon thread mutates the shared State
singleton, and POST /api/scrape calls into _run_scrape_async too. Routes
moving into their own Blueprint files in the upcoming split need to
import this without circular-importing server.py.

Side effects:
- Reads core.config (DB_PATH, FAST_INTERVAL)
- Mutates core.state.state
- Calls core.scrape_orchestrator.run_scrape
- Drives core.scrape_status.broker
"""
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone

from config.companies import COMPANIES
from core.config import DB_PATH, FAST_INTERVAL
from core.scrape_status import broker
from core.scrape_orchestrator import run_scrape
from core.state import state
from storage.db import get_conn

log = logging.getLogger("jobscout")


def is_quiet_hours() -> bool:
    """
    Returns True during 12:00am–5:30am CST (06:00–11:30 UTC).
    No new roles are typically posted overnight, so we skip scraping.
    """
    now = datetime.now(timezone.utc)
    utc_mins = now.hour * 60 + now.minute
    # 12:00am CST = 06:00 UTC = 360 min
    # 05:30am CST = 11:30 UTC = 690 min
    return 360 <= utc_mins < 690


def build_cache():
    """Rebuild JSON cache from DB after each scrape.

    Called by:
    - _run_scrape_async after each cycle completes
    - api_data route on cache miss (cold start before first scrape)
    """
    try:
        from export_data import export
        data = export(DB_PATH)
        state.update_cache(data)
        log.info("Cache rebuilt — %d jobs", data.get("stats", {}).get("total_jobs", 0))
    except Exception as e:
        log.error("Cache rebuild failed: %s", e)


def count_fast_companies() -> int:
    """Number of companies in 'fast' mode — Tier 0/1. Computed here so we can
    pre-arm the broker with the real total inside the request handler, before
    the worker thread starts. Keeps the snapshot returned by POST /api/scrape
    immediately useful for the dashboard."""
    return sum(1 for c in COMPANIES if c.get("tier", 3) in (0, 1))


def run_scrape_async(mode: str = "fast") -> None:
    """Background runner: executes a scrape, records cycle stats, rebuilds cache.

    SQLite connections are not thread-safe, so we open `conn` here inside the
    worker thread rather than reusing one from the request thread. The
    orchestrator's own try/finally guarantees broker.finish(); the inner
    try/finally closes the conn even if the orchestrator raises. The outer
    try/except mirrors that for state.is_scraping so it's always cleared.
    """
    state.is_scraping = True
    t0 = time.time()
    try:
        conn = get_conn(DB_PATH)
        try:
            stats = run_scrape(conn, mode=mode, status_broker=broker)
        finally:
            conn.close()
        state.record_cycle(time.time() - t0, stats)
        build_cache()
    except Exception as e:
        log.exception("Async scrape failed")
        state.record_cycle(0, {}, str(e))
    finally:
        # record_cycle() already clears is_scraping; keep this for the
        # exception-before-record_cycle window.
        state.is_scraping = False


def bg_scrape_loop() -> None:
    """The daemon thread that scrapes every FAST_INTERVAL seconds during
    business hours. Designed to be unkillable — exceptions are logged and
    the loop continues so a transient ATS failure doesn't take down the
    whole scheduler."""
    log.info("Background scraper enabled — interval=%ds", FAST_INTERVAL)
    # First tick gets a short delay so the Flask boot path isn't competing
    # with the scraper for SQLite init/imports on cold starts.
    time.sleep(15)
    while True:
        try:
            if is_quiet_hours():
                log.debug("BG scrape: quiet hours, skipping")
            elif not broker.try_start("fast", count_fast_companies()):
                # Atomic check-and-arm: must mirror POST /api/scrape's gate
                # exactly. A plain `if broker.is_running()` check would leave
                # a race window where a manual POST wins the broker while
                # we're about to call run_scrape() — both threads would then
                # tick the same broker and double-scrape the same companies.
                log.debug("BG scrape: broker busy, skipping cycle")
            else:
                log.info("BG scrape: starting fast cycle")
                threading.Thread(
                    target=run_scrape_async,
                    args=("fast",),
                    daemon=True,
                    name="bg-scrape-worker",
                ).start()
        except Exception:
            # Never let the loop die — log and continue. The 10-min watchdog
            # in StatusBroker.is_running() rescues us if a scrape crashed
            # before its finally-finish() ran.
            log.exception("BG scrape loop tick failed")
        time.sleep(FAST_INTERVAL)


def should_run_bg_scraper() -> bool:
    """Background loop is opt-out via DISABLE_BG_SCRAPE=1, and auto-disabled
    under pytest so test_client() reloads don't spawn rogue threads that
    write to the test DB."""
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return False
    if os.environ.get("DISABLE_BG_SCRAPE", "").lower() in ("1", "true", "yes"):
        return False
    return os.environ.get("ENABLE_BG_SCRAPE", "1") == "1"
