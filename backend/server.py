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
import logging
import threading
from datetime import datetime, timezone


from flask import Flask, jsonify, Response, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.companies import COMPANIES, TOTAL_COMPANIES
from core.scrape_status import broker
from core.scrape_orchestrator import run_scrape
from storage.db import init_db, get_conn, get_stats

# CLAUDE.md tech-debt #2 — server.py split. Shared constants and state
# now live in core/* so new route blueprints can import them without
# having to import server itself (which would cause circular imports).
# Re-exported here for now so existing routes keep working unchanged;
# each subsequent extraction PR will swap the in-file references over.
from core.config import (
    DB_PATH,
    FAST_INTERVAL,
    PORT,
    API_SECRET,
    _BEARER_RE,
    check_api_secret,
)
from core.state import State, state
# Background scraper + cache rebuild extracted to core/scrape_loop.py (PR 3/8).
# Kept as re-exports here so existing route bodies still work; will be
# inlined-via-import in the per-route-blueprint extractions.
from core.scrape_loop import (
    is_quiet_hours,
    build_cache,
    count_fast_companies as _count_fast_companies,
    run_scrape_async as _run_scrape_async,
    bg_scrape_loop as _bg_scrape_loop,
    should_run_bg_scraper as _should_run_bg_scraper,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jobscout")

app = Flask(__name__)


# ─── Blueprints ────────────────────────────────────────────────────
from routes.vault_routes import vault_bp
app.register_blueprint(vault_bp)
from routes.admin_routes import admin_bp
app.register_blueprint(admin_bp)
# Read-only data endpoints extracted to routes/data_routes.py (PR 4/8 of the
# server.py split). Five routes: /, /ping, /api/data, /api/health, /api/stats.
from routes.data_routes import data_bp
app.register_blueprint(data_bp)
# Scrape control endpoints extracted to routes/scrape_routes.py (PR 5/8).
# POST /api/scrape, GET /api/scrape/status.
from routes.scrape_routes import scrape_bp
app.register_blueprint(scrape_bp)
# Profile + PIN + resume-text endpoints extracted to routes/profile_routes.py
# (PR 6/8). Five routes: /api/profile (GET/POST), /api/resume, /api/verify-pin,
# /api/set-pin. All write paths Bearer-gated when API_SECRET is set.
from routes.profile_routes import profile_bp
app.register_blueprint(profile_bp)
# Application tracker endpoints extracted to routes/application_routes.py (7/8).
# Six routes: GET/POST /api/applications, DELETE/PATCH /api/applications/<id>,
# /company/<name> history, /export.
from routes.application_routes import application_bp
app.register_blueprint(application_bp)
# Resume-version endpoints extracted to routes/resume_version_routes.py (8/8 — final).
# Five routes: GET/POST /api/resume/versions, /upload, /compare, /<key> GET+DELETE.
from routes.resume_version_routes import resume_version_bp
app.register_blueprint(resume_version_bp)
# Public roster endpoints (PRD #89 Slice 1) — power the onboarding wizard
# pickers. /api/role-taxonomy, /api/companies-roster, /api/locations-roster.
from routes.roster_routes import roster_bp
app.register_blueprint(roster_bp)
# Company request endpoint — POST /api/companies/request
# Files GitHub Issues via GITHUB_TOKEN for unknown companies.
from routes.company_request_routes import company_request_bp
app.register_blueprint(company_request_bp)


# State + state singleton are imported above from core.state (PR 2/8).
# Kept the import block compact so future readers see all shared deps in
# one place at the top of the file rather than scattered through.

# is_quiet_hours + build_cache imported above from core.scrape_loop (PR 3/8).
# /ping, /api/data, /api/health, /api/stats, / extracted to routes/data_routes.py (PR 4/8).

# ─── Flask routes (write/auth endpoints; data endpoints in Blueprint) ─

# _count_fast_companies + _run_scrape_async imported above from core.scrape_loop.

def _check_api_secret() -> bool:
    """Backward-compat shim over core.config.check_api_secret.

    Existing callers pass no args (they rely on Flask's thread-local
    ``request``). The new helper takes ``request`` explicitly so it can
    be tested without a Flask context. Equivalent runtime behavior.
    """
    return check_api_secret(request)


# /api/scrape, /api/scrape/status extracted to routes/scrape_routes.py (PR 5/8).

# ─── Profile & Resume endpoints ────────────────────────────────────

# /api/profile, /api/resume, /api/verify-pin extracted to routes/profile_routes.py (PR 6/8).

# /api/applications/* (6 routes) extracted to routes/application_routes.py (PR 7/8).


# /api/resume/versions/* (5 routes) extracted to routes/resume_version_routes.py (PR 8/8 - final).


# /api/set-pin extracted to routes/profile_routes.py (PR 6/8).
# / (self-describing root) extracted to routes/data_routes.py (PR 4/8).

# ─── CORS preflight ───────────────────────────────────────────────
@app.after_request
def add_cors(response):
    # Skip vault + admin routes — their blueprints own their own CORS
    # (issue #34: vault endpoints honor ALLOWED_ORIGINS env allowlist
    # instead of returning a blanket "*"). Flask runs blueprint
    # after_request hooks before app-level hooks, so without this guard
    # the blueprint's restricted Allow-Origin gets clobbered by "*" here.
    path = request.path or ""
    if path.startswith("/api/vault/") or path.startswith("/api/admin/"):
        return response
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ─── Background scrape loop ───────────────────────────────────────
# Wraps run_scrape() in a daemon thread so the dashboard sees the broker
# tick in real time even when the cycle wasn't user-triggered. Skips when
# the broker is already running (a manual POST /api/scrape can race the
# cron tick — manual wins; this thread quietly waits for the next slot).
# _bg_scrape_loop + _should_run_bg_scraper imported above from core.scrape_loop.

# ─── Startup ──────────────────────────────────────────────────────
init_db(DB_PATH)
from storage.migrate_add_user_id import migrate as _migrate_user_id
_migrate_user_id(DB_PATH)

if _should_run_bg_scraper():
    threading.Thread(
        target=_bg_scrape_loop,
        daemon=True,
        name="bg-scrape-loop",
    ).start()
else:
    log.info("Background scraper disabled (DISABLE_BG_SCRAPE set or running under pytest)")


def main():
    log.info("Starting dev server on port %d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
