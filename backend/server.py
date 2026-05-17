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


@app.route("/api/resume/versions", methods=["GET"])
def api_list_resume_versions():
    """List all saved resume versions."""
    try:
        from storage.profile_manager import init_profile_tables, list_resume_versions
        init_profile_tables(DB_PATH)
        return jsonify(list_resume_versions(DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resume/versions", methods=["POST", "OPTIONS"])
def api_save_resume_version():
    """Save/update a resume version and extract skills from resume_text."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, save_resume_version
        init_profile_tables(DB_PATH)
        data = request.get_json() or {}
        if not data.get("version_key"):
            return jsonify({"error": "version_key required"}), 400
        skills = save_resume_version(data, DB_PATH)
        return jsonify({
            "status": "ok",
            "version_key": data["version_key"],
            "skills_extracted": len(skills),
            "skills": skills,
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resume/versions/upload", methods=["POST", "OPTIONS"])
def api_upload_resume_version_pdf():
    """Upload a PDF resume → extract text → save as a named version."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, save_resume_version
        init_profile_tables(DB_PATH)

        version_key = request.form.get("version_key", "").strip()
        if not version_key:
            return jsonify({"error": "version_key required"}), 400
        if "file" not in request.files:
            return jsonify({"error": "PDF file required (field name: file)"}), 400

        file = request.files["file"]
        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only PDF files are supported"}), 400

        # Standardized on pypdf (CLAUDE.md tech-debt #3): one PDF library
        # across the whole project. Same extractor as the vault uses on disk.
        try:
            from storage.resume_vault import extract_text_from_pdf_bytes
            pdf_bytes = file.read()
            text = extract_text_from_pdf_bytes(
                pdf_bytes,
                source=f"upload:{file.filename or version_key}",
            ).strip()
        except Exception as e:
            return jsonify({"error": f"PDF extraction failed: {e}"}), 500

        if not text:
            return jsonify({"error": "Could not extract text — try pasting resume text instead"}), 422

        data = {
            "version_key": version_key,
            "display_name": request.form.get("display_name", version_key),
            "resume_text": text,
            "notes": request.form.get("notes", ""),
            "target_companies": [],
        }
        skills = save_resume_version(data, DB_PATH)
        return jsonify({
            "status": "ok",
            "version_key": version_key,
            "skills_extracted": len(skills),
            "skills": skills,
            "text_length": len(text),
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resume/versions/compare", methods=["GET"])
def api_compare_resume_versions():
    """Compare two resume versions — returns skill overlap + diffs.
    Query: ?a=<version_key>&b=<version_key>
    """
    a_key = request.args.get("a", "").strip()
    b_key = request.args.get("b", "").strip()
    if not a_key or not b_key:
        return jsonify({"error": "Query params ?a=<key>&b=<key> required"}), 400
    try:
        from storage.profile_manager import get_resume_version
        a = get_resume_version(a_key, DB_PATH)
        b = get_resume_version(b_key, DB_PATH)
        if not a:
            return jsonify({"error": f"Version '{a_key}' not found"}), 404
        if not b:
            return jsonify({"error": f"Version '{b_key}' not found"}), 404

        a_skills = set(a.get("extracted_skills", []))
        b_skills = set(b.get("extracted_skills", []))
        shared   = sorted(a_skills & b_skills)
        only_a   = sorted(a_skills - b_skills)
        only_b   = sorted(b_skills - a_skills)
        total    = len(a_skills | b_skills)
        similarity_pct = round(len(shared) / total * 100) if total else 0

        return jsonify({
            "a": {"version_key": a_key, "display_name": a.get("display_name", a_key), "skill_count": len(a_skills)},
            "b": {"version_key": b_key, "display_name": b.get("display_name", b_key), "skill_count": len(b_skills)},
            "similarity_pct": similarity_pct,
            "shared": shared,
            "only_a": only_a,
            "only_b": only_b,
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resume/versions/<version_key>", methods=["GET"])
def api_get_resume_version(version_key):
    """Get a specific resume version including full resume text."""
    try:
        from storage.profile_manager import get_resume_version
        v = get_resume_version(version_key, DB_PATH)
        if not v:
            return jsonify({"error": "not found"}), 404
        return jsonify(v), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resume/versions/<version_key>", methods=["DELETE", "OPTIONS"])
def api_delete_resume_version(version_key):
    """Delete a resume version by key.

    Issue #44: routes through the same ``delete_vault_version`` helper as
    ``/api/vault/version/<key>``. Previously this called the legacy
    ``profile_manager.delete_resume_version`` which only removed the DB row,
    orphaning the PDF + text files on disk — entries resurrected on the
    next vault refresh because ``list_vault()`` reads disk.

    Behavior matches the vault endpoint: malformed keys → 400, missing →
    200 with ``already_gone: true`` (idempotent for retried DELETEs),
    filesystem errors → 500 (DB row preserved so caller can retry).
    """
    if request.method == "OPTIONS":
        return "", 204

    # Reject obviously malformed keys BEFORE touching disk. Identical guard
    # to the vault DELETE branch (routes/vault_routes.py).
    if (
        not version_key
        or "\x00" in version_key
        or "/" in version_key
        or "\\" in version_key
        or ".." in version_key
    ):
        return jsonify({"error": f"Invalid version_key: {version_key!r}"}), 400, \
            {"Access-Control-Allow-Origin": "*"}

    from storage.db import get_conn, get_resume_version
    from storage.resume_vault import delete_vault_version, list_vault

    # Idempotency: if neither a DB row nor a PDF on disk maps to this key,
    # treat as success (already gone). Mirrors the vault endpoint contract.
    conn = get_conn(DB_PATH)
    rv = get_resume_version(conn, version_key)
    conn.close()
    on_disk = any(f.get("version_key") == version_key for f in list_vault())
    if not rv and not on_disk:
        return jsonify({
            "status": "deleted",
            "version_key": version_key,
            "db_row_deleted": False,
            "pdf_deleted": False,
            "text_deleted": False,
            "already_gone": True,
        }), 200, {"Access-Control-Allow-Origin": "*"}

    try:
        result = delete_vault_version(version_key, db_path=DB_PATH)
    except ValueError as e:
        # Don't leak filesystem paths from storage-layer messages.
        log.warning("Legacy delete '%s' rejected: %s", version_key, e)
        return jsonify({"error": "Invalid version_key"}), 400, \
            {"Access-Control-Allow-Origin": "*"}
    except OSError as e:
        log.error("Legacy delete '%s' filesystem error: %s", version_key, e)
        return jsonify({"error": "Filesystem error while deleting version"}), 500, \
            {"Access-Control-Allow-Origin": "*"}

    # Drop absolute paths from response; keep only basename for UX.
    pdf_path = result.pop("pdf_path", None)
    result.pop("text_path", None)
    result["pdf_filename"] = os.path.basename(pdf_path) if pdf_path else None
    return jsonify({"status": "deleted", **result}), 200, \
        {"Access-Control-Allow-Origin": "*"}


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
