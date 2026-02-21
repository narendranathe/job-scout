#!/usr/bin/env python3
"""
JobScout Server — Flask + Background Scraper Thread.

This is the Render-deployed component of Option D:
  • Background thread: scrapes Tier 1 (24 companies) every 5 min
  • HTTP server: serves fresh JSON at GET /api/data
  • GitHub Actions hits POST /api/scrape to trigger full sweeps

Endpoints:
  GET  /ping        → 200 OK (keepalive, prevents Render free-tier sleep)
  GET  /api/data    → Full JSON export (same schema as static api-data.json)
  GET  /api/health  → Uptime, last scrape time, cycle count, errors
  GET  /api/stats   → Quick DB stats
  POST /api/scrape  → Trigger immediate full scrape (called by GitHub Actions)

Deploy:
  Render reads render.yaml → starts this server on port 10000
  GitHub Actions pings /ping every 14 min to prevent sleep
"""

import os
import sys
import json
import time
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, Response, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.companies import COMPANIES, get_batch, TOTAL_COMPANIES
from core.relevance import RelevanceEngine
from storage.db import (
    init_db, get_conn, upsert_job, mark_stale_jobs,
    start_run, finish_run, get_stats,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jobscout")

# ─── Config ───────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))
FAST_INTERVAL = int(os.environ.get("FAST_INTERVAL", "300"))     # 5 min
SCRAPE_DELAY = float(os.environ.get("SCRAPE_DELAY", "0.3"))
PORT = int(os.environ.get("PORT", "10000"))
API_SECRET = os.environ.get("API_SECRET", "")  # Optional auth for POST /api/scrape

app = Flask(__name__)

# ─── Scraper Registry (lazy loaded) ──────────────────
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


# ─── Shared State ────────────────────────────────────
class State:
    """Thread-safe state shared between scraper thread and Flask handlers."""
    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.last_scrape_at = None
        self.last_duration = 0
        self.total_cycles = 0
        self.total_new = 0
        self.last_error = None
        self.is_scraping = False
        self._cached_json = None
        self._cached_at = None

    def update_cache(self, data: dict):
        with self._lock:
            self._cached_json = json.dumps(data, default=str, separators=(",", ":"))
            self._cached_at = datetime.now(timezone.utc).isoformat()

    def get_cache(self) -> str | None:
        with self._lock:
            return self._cached_json

    def record_cycle(self, duration: float, stats: dict, error: str = None):
        with self._lock:
            self.last_scrape_at = datetime.now(timezone.utc).isoformat()
            self.last_duration = round(duration, 1)
            self.total_cycles += 1
            self.total_new += stats.get("new", 0)
            self.last_error = error
            self.is_scraping = False

    def health(self) -> dict:
        with self._lock:
            return {
                "status": "scraping" if self.is_scraping else "idle",
                "started_at": self.started_at,
                "uptime_hours": round(
                    (datetime.now(timezone.utc) - datetime.fromisoformat(self.started_at)).total_seconds() / 3600, 1
                ),
                "last_scrape_at": self.last_scrape_at,
                "last_duration_sec": self.last_duration,
                "total_cycles": self.total_cycles,
                "total_new_jobs": self.total_new,
                "last_error": self.last_error,
                "cache_fresh_at": self._cached_at,
                "companies_tracked": TOTAL_COMPANIES,
                "fast_interval_sec": FAST_INTERVAL,
            }


state = State()

# ─── Cycle Counter (persists across runs via disk) ───
COUNTER_PATH = Path(DB_PATH).parent / ".cycle_counter"

def _next_cycle() -> int:
    try:
        n = int(COUNTER_PATH.read_text().strip()) + 1
    except Exception:
        n = 1
    COUNTER_PATH.write_text(str(n))
    return n


# ─── Scrape Engine ───────────────────────────────────
def _detect_sponsorship(job: dict) -> bool:
    text = ((job.get("description") or "") + " " + (job.get("company") or "")).lower()
    pos = any(kw in text for kw in ["visa sponsor", "h1b", "h-1b", "sponsorship available"])
    neg = any(kw in text for kw in ["no sponsorship", "not sponsor", "unable to sponsor"])
    return pos and not neg


def run_scrape(mode: str = "fast") -> dict:
    """
    Execute one scrape cycle.
      mode="fast" → Tier 1 only (24 companies, ~30s)
      mode="full" → All tiers eligible this cycle (~3 min)
    """
    _load_scrapers()
    engine = RelevanceEngine()
    init_db(DB_PATH)
    conn = get_conn(DB_PATH)
    run_id = start_run(conn)
    cycle = _next_cycle()

    if mode == "fast":
        companies = [c for c in COMPANIES if c.get("tier", 3) == 1]
    else:
        companies = get_batch(cycle)

    stats = {
        "companies": 0, "found": 0, "new": 0,
        "updated": 0, "errors": 0, "skipped": 0, "relevant": 0,
    }

    for company in companies:
        scraper = SCRAPERS.get(company.get("ats", ""))
        if not scraper:
            stats["errors"] += 1
            continue

        try:
            stats["companies"] += 1
            for raw_job in scraper.scrape(company):
                stats["found"] += 1

                if not engine.is_relevant_title(raw_job.get("title", "")):
                    stats["skipped"] += 1
                    continue

                score, matched = engine.score(raw_job)
                raw_job["relevance_score"] = score
                raw_job["matched_skills"] = matched
                raw_job["sponsorship"] = _detect_sponsorship(raw_job)

                result = upsert_job(conn, raw_job)
                if result == "new":
                    stats["new"] += 1
                elif result == "updated":
                    stats["updated"] += 1
                stats["relevant"] += 1

            conn.commit()
            time.sleep(SCRAPE_DELAY)
        except Exception as e:
            log.error("✗ %s — %s", company["name"], e)
            stats["errors"] += 1

    mark_stale_jobs(conn, hours=96)
    conn.commit()
    finish_run(conn, run_id, stats)
    conn.close()

    log.info(
        "═══ %s cycle %d — companies=%d found=%d relevant=%d new=%d errors=%d ═══",
        mode.upper(), cycle, stats["companies"], stats["found"],
        stats["relevant"], stats["new"], stats["errors"],
    )
    return stats


def build_cache():
    """Build the JSON cache from DB (called after each scrape)."""
    try:
        from export_data import export
        data = export(DB_PATH)
        state.update_cache(data)
        log.info("Cache rebuilt — %d jobs", data.get("stats", {}).get("total_jobs", 0))
    except Exception as e:
        log.error("Cache rebuild failed: %s", e)


# ─── Background Scraper Thread ───────────────────────
def scraper_loop():
    """
    Runs forever in background thread:
      • Tier 1 every 5 min (24 top-target companies)
      • Full sweep every 12th cycle (~1 hour) as backup
    """
    log.info("Background scraper started — Tier 1 every %ds", FAST_INTERVAL)
    local_cycle = 0

    while True:
        try:
            local_cycle += 1
            state.is_scraping = True

            # Every 12th local cycle (~1 hour), do full sweep
            mode = "full" if local_cycle % 12 == 0 else "fast"

            t0 = time.time()
            stats = run_scrape(mode)
            duration = time.time() - t0

            state.record_cycle(duration, stats)
            build_cache()

        except Exception as e:
            log.error("Scraper loop error: %s", e)
            state.record_cycle(0, {}, str(e))

        log.info("💤 Next scrape in %ds...", FAST_INTERVAL)
        time.sleep(FAST_INTERVAL)


# ─── Flask Routes ────────────────────────────────────

@app.route("/ping")
def ping():
    """Keepalive endpoint — GitHub Actions hits this every 14 min."""
    return "ok", 200


@app.route("/api/data")
def api_data():
    """
    Full JSON export — same schema as static api-data.json.
    Dashboard fetches this endpoint for real-time data.
    """
    cached = state.get_cache()
    if cached:
        return Response(cached, mimetype="application/json", headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=60",
        })
    # No cache yet — build it on demand
    build_cache()
    cached = state.get_cache()
    if cached:
        return Response(cached, mimetype="application/json", headers={
            "Access-Control-Allow-Origin": "*",
        })
    return jsonify({"error": "No data yet, first scrape in progress"}), 503


@app.route("/api/health")
def api_health():
    """Server health + scraper status."""
    return jsonify(state.health()), 200, {"Access-Control-Allow-Origin": "*"}


@app.route("/api/stats")
def api_stats():
    """Quick DB stats."""
    try:
        s = get_stats(DB_PATH)
        return jsonify(s), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scrape", methods=["POST"])
def api_trigger_scrape():
    """
    Trigger an immediate full scrape.
    Called by GitHub Actions after its own scrape to sync data,
    or manually for testing.
    """
    # Optional auth
    if API_SECRET:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != API_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    if state.is_scraping:
        return jsonify({"status": "already_scraping"}), 409

    def _trigger():
        state.is_scraping = True
        t0 = time.time()
        try:
            stats = run_scrape("full")
            state.record_cycle(time.time() - t0, stats)
            build_cache()
        except Exception as e:
            state.record_cycle(0, {}, str(e))

    threading.Thread(target=_trigger, daemon=True).start()
    return jsonify({"status": "scrape_triggered"}), 202


@app.route("/")
def index():
    """Root — redirect to health."""
    return jsonify({
        "service": "JobScout API",
        "version": "2.0",
        "endpoints": ["/api/data", "/api/health", "/api/stats", "/ping"],
        **state.health(),
    }), 200, {"Access-Control-Allow-Origin": "*"}


# ─── CORS preflight ──────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ─── Main ────────────────────────────────────────────
# Initialize DB and start background scraper when module loads.
# This ensures gunicorn workers start scraping automatically.
init_db(DB_PATH)

_scraper_thread = threading.Thread(target=scraper_loop, daemon=True, name="scraper")
_scraper_thread.start()
log.info("Background scraper thread started (interval=%ds)", FAST_INTERVAL)


def main():
    """Direct run (not gunicorn) — for local development."""
    log.info("Starting dev server on port %d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
