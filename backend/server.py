#!/usr/bin/env python3
"""
JobScout Server — Flask + Background Scraper Thread.

Endpoints:
  GET  /ping               → keepalive (prevents Render free-tier sleep)
  GET  /api/data           → full JSON export for dashboard
  GET  /api/health         → uptime, last scrape, cycle count, errors
  GET  /api/stats          → quick DB stats
  POST /api/scrape         → trigger immediate full scrape (manual or GitHub Actions)
  GET  /api/profile        → get user profile (skills, preferences, dream config)
  POST /api/profile        → update profile preferences
  POST /api/resume         → upload resume text → extract skills
  POST /api/verify-pin     → verify dashboard PIN
  POST /api/set-pin        → set/change dashboard PIN

Night quiet hours:
  Scraping is paused 12:00am–5:30am CST (06:00–11:30 UTC)
  to avoid wasting Render compute when no new jobs are posted.
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

# ─── Config ────────────────────────────────────────────────────────
DB_PATH      = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))
FAST_INTERVAL = int(os.environ.get("FAST_INTERVAL", "300"))    # seconds between cycles
SCRAPE_DELAY  = float(os.environ.get("SCRAPE_DELAY", "0.3"))
PORT          = int(os.environ.get("PORT", "10000"))
API_SECRET    = os.environ.get("API_SECRET", "")               # optional auth for POST /api/scrape

app = Flask(__name__)

# ─── Scraper Registry ──────────────────────────────────────────────
SCRAPERS: dict = {}

def _load_scrapers():
    global SCRAPERS
    if SCRAPERS:
        return
    from scrapers import greenhouse, lever, ashby, smartrecruiters, bamboohr
    SCRAPERS = {
        "greenhouse": greenhouse,
        "lever":      lever,
        "ashby":      ashby,
        "smartrecruiters": smartrecruiters,
        "bamboohr":   bamboohr,
    }
    # Workday (optional — only loaded if workday.py exists)
    try:
        from scrapers import workday
        SCRAPERS["workday"] = workday
        log.info("Workday scraper loaded")
    except ImportError:
        log.warning("Workday scraper not found — skipping Workday companies")


# ─── Shared State ──────────────────────────────────────────────────
class State:
    def __init__(self):
        self._lock = threading.Lock()
        self.started_at   = datetime.now(timezone.utc).isoformat()
        self.last_scrape_at = None
        self.last_duration  = 0
        self.total_cycles   = 0
        self.total_new      = 0
        self.last_error     = None
        self.is_scraping    = False
        self._cached_json   = None
        self._cached_at     = None

    def update_cache(self, data: dict):
        with self._lock:
            self._cached_json = json.dumps(data, default=str, separators=(",", ":"))
            self._cached_at   = datetime.now(timezone.utc).isoformat()

    def get_cache(self) -> str | None:
        with self._lock:
            return self._cached_json

    def record_cycle(self, duration: float, stats: dict, error: str = None):
        with self._lock:
            self.last_scrape_at = datetime.now(timezone.utc).isoformat()
            self.last_duration  = round(duration, 1)
            self.total_cycles  += 1
            self.total_new     += stats.get("new", 0)
            self.last_error     = error
            self.is_scraping    = False

    def health(self) -> dict:
        with self._lock:
            return {
                "status":            "scraping" if self.is_scraping else "idle",
                "started_at":        self.started_at,
                "uptime_hours":      round(
                    (datetime.now(timezone.utc) - datetime.fromisoformat(self.started_at)).total_seconds() / 3600, 1
                ),
                "last_scrape_at":    self.last_scrape_at,
                "last_duration_sec": self.last_duration,
                "total_cycles":      self.total_cycles,
                "total_new_jobs":    self.total_new,
                "last_error":        self.last_error,
                "cache_fresh_at":    self._cached_at,
                "companies_tracked": TOTAL_COMPANIES,
                "fast_interval_sec": FAST_INTERVAL,
            }


state = State()

# ─── Cycle counter (persists on disk) ─────────────────────────────
COUNTER_PATH = Path(DB_PATH).parent / ".cycle_counter"

def _next_cycle() -> int:
    try:
        n = int(COUNTER_PATH.read_text().strip()) + 1
    except Exception:
        n = 1
    COUNTER_PATH.write_text(str(n))
    return n


# ─── Night quiet hours ────────────────────────────────────────────
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


# ─── Scrape Engine ────────────────────────────────────────────────
def _detect_sponsorship(job: dict) -> bool:
    text = ((job.get("description") or "") + " " + (job.get("company") or "")).lower()
    pos = any(kw in text for kw in ["visa sponsor", "h1b", "h-1b", "sponsorship available"])
    neg = any(kw in text for kw in ["no sponsorship", "not sponsor", "unable to sponsor"])
    return pos and not neg


def run_scrape(mode: str = "fast") -> dict:
    """
    Execute one scrape cycle.
      mode="fast" → Tier 1 only (~30s)
      mode="full" → All tiers eligible this cycle (~3 min)
    """
    _load_scrapers()
    engine = RelevanceEngine()
    init_db(DB_PATH)
    conn = get_conn(DB_PATH)
    run_id = start_run(conn)
    cycle = _next_cycle()

    companies = (
        [c for c in COMPANIES if c.get("tier", 3) == 1]
        if mode == "fast"
        else get_batch(cycle)
    )

    stats = {
        "companies": 0, "found": 0, "new": 0,
        "updated": 0,  "errors": 0, "skipped": 0, "relevant": 0,
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
                raw_job["matched_skills"]  = matched
                raw_job["sponsorship"]     = _detect_sponsorship(raw_job)

                result = upsert_job(conn, raw_job)
                if result == "new":
                    stats["new"] += 1
                    # Fire dream-job alert for new matches
                    _maybe_alert(raw_job)
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


def _maybe_alert(job: dict):
    """Fire dream-job alert (silently swallow errors so scraping continues)."""
    try:
        from alerts.notifier import notify_dream_job
        notify_dream_job(job)
    except Exception as e:
        log.debug("Alert check failed: %s", e)


def build_cache():
    """Rebuild JSON cache from DB after each scrape."""
    try:
        from export_data import export
        data = export(DB_PATH)
        state.update_cache(data)
        log.info("Cache rebuilt — %d jobs", data.get("stats", {}).get("total_jobs", 0))
    except Exception as e:
        log.error("Cache rebuild failed: %s", e)


# ─── Background scraper loop ──────────────────────────────────────
def scraper_loop():
    log.info("Background scraper started — interval=%ds", FAST_INTERVAL)
    local_cycle = 0

    while True:
        # ── Night quiet hours: skip and sleep ──
        if is_quiet_hours():
            log.info("😴 Quiet hours (12am–5:30am CST) — skipping cycle")
            time.sleep(FAST_INTERVAL)
            continue

        try:
            local_cycle += 1
            state.is_scraping = True
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


# ─── Flask routes ─────────────────────────────────────────────────

@app.route("/ping")
def ping():
    """Keepalive — GitHub Actions / UptimeRobot hits this every 14 min."""
    return "ok", 200


@app.route("/api/data")
def api_data():
    """Full JSON export for dashboard."""
    cached = state.get_cache()
    if not cached:
        build_cache()
        cached = state.get_cache()
    if cached:
        return Response(cached, mimetype="application/json", headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=60",
        })
    return jsonify({"error": "No data yet — first scrape in progress"}), 503


@app.route("/api/health")
def api_health():
    return jsonify(state.health()), 200, {"Access-Control-Allow-Origin": "*"}


@app.route("/api/stats")
def api_stats():
    try:
        return jsonify(get_stats(DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scrape", methods=["POST", "OPTIONS"])
def api_trigger_scrape():
    """Trigger an immediate full scrape (manual button or GitHub Actions)."""
    if request.method == "OPTIONS":
        return "", 204

    if API_SECRET:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != API_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    if state.is_scraping:
        return jsonify({"status": "already_scraping", "message": "Scrape already running"}), 409

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
    return jsonify({"status": "scrape_triggered", "message": "Full scrape started — refresh in ~2 min"}), 202


# ─── Profile & Resume endpoints ────────────────────────────────────

@app.route("/api/profile", methods=["GET"])
def api_get_profile():
    try:
        from storage.profile_manager import init_profile_tables, get_profile
        init_profile_tables(DB_PATH)
        return jsonify(get_profile(DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profile", methods=["POST", "OPTIONS"])
def api_update_profile():
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, update_profile
        init_profile_tables(DB_PATH)
        update_profile(request.get_json() or {}, DB_PATH)
        return jsonify({"status": "updated"}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resume", methods=["POST", "OPTIONS"])
def api_upload_resume():
    """Upload resume text → extract skills → store in DB."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, upload_resume
        init_profile_tables(DB_PATH)
        data = request.get_json() or {}
        resume_text = data.get("resume_text", "").strip()
        if not resume_text:
            return jsonify({"error": "resume_text field required"}), 400
        skills = upload_resume(resume_text, DB_PATH)
        return jsonify({
            "status": "ok",
            "skills_extracted": len(skills),
            "skills": skills,
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-pin", methods=["POST", "OPTIONS"])
def api_verify_pin():
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, verify_pin
        init_profile_tables(DB_PATH)
        pin = (request.get_json() or {}).get("pin", "")
        return jsonify({"verified": verify_pin(pin, DB_PATH)}), 200, {
            "Access-Control-Allow-Origin": "*"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/set-pin", methods=["POST", "OPTIONS"])
def api_set_pin():
    if request.method == "OPTIONS":
        return "", 204
    if API_SECRET:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != API_SECRET:
            return jsonify({"error": "unauthorized"}), 401
    try:
        from storage.profile_manager import init_profile_tables, set_pin
        init_profile_tables(DB_PATH)
        pin = (request.get_json() or {}).get("pin", "")
        if len(pin) < 4:
            return jsonify({"error": "PIN must be at least 4 characters"}), 400
        set_pin(pin, DB_PATH)
        return jsonify({"status": "pin_set"}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return jsonify({
        "service":   "JobScout API",
        "version":   "3.0",
        "endpoints": ["/api/data", "/api/health", "/api/stats", "/api/scrape",
                      "/api/profile", "/api/resume", "/api/verify-pin", "/ping"],
        **state.health(),
    }), 200, {"Access-Control-Allow-Origin": "*"}


# ─── CORS preflight ───────────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ─── Startup ──────────────────────────────────────────────────────
init_db(DB_PATH)

_scraper_thread = threading.Thread(target=scraper_loop, daemon=True, name="scraper")
_scraper_thread.start()
log.info("Background scraper thread started (interval=%ds)", FAST_INTERVAL)


def main():
    log.info("Starting dev server on port %d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
