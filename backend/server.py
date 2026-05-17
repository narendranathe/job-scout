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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jobscout")

# ─── Config ────────────────────────────────────────────────────────
DB_PATH      = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))
FAST_INTERVAL = int(os.environ.get("FAST_INTERVAL", "300"))    # seconds between cycles
# Note: per-company delay is SCRAPE_DELAY in the env; the orchestrator
# reads it directly. Kept out of this module to avoid two copies.
PORT          = int(os.environ.get("PORT", "10000"))
API_SECRET    = os.environ.get("API_SECRET", "")               # optional auth for POST /api/scrape

app = Flask(__name__)


# ─── Blueprints ────────────────────────────────────────────────────
from routes.vault_routes import vault_bp
app.register_blueprint(vault_bp)
from routes.admin_routes import admin_bp
app.register_blueprint(admin_bp)


# ─── Shared State ──────────────────────────────────────────────────
class State:
    def __init__(self):
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
        self._cached_json = json.dumps(data, default=str, separators=(",", ":"))
        self._cached_at   = datetime.now(timezone.utc).isoformat()

    def get_cache(self) -> str | None:
        return self._cached_json

    def record_cycle(self, duration: float, stats: dict, error: str = None):
        self.last_scrape_at = datetime.now(timezone.utc).isoformat()
        self.last_duration  = round(duration, 1)
        self.total_cycles  += 1
        self.total_new     += stats.get("new", 0)
        self.last_error     = error
        self.is_scraping    = False

    def health(self) -> dict:
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


def build_cache():
    """Rebuild JSON cache from DB after each scrape."""
    try:
        from export_data import export
        data = export(DB_PATH)
        state.update_cache(data)
        log.info("Cache rebuilt — %d jobs", data.get("stats", {}).get("total_jobs", 0))
    except Exception as e:
        log.error("Cache rebuild failed: %s", e)


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


def _count_fast_companies() -> int:
    """Number of companies in 'fast' mode — Tier 0/1. Computed here so we can
    pre-arm the broker with the real total inside the request handler, before
    the worker thread starts. Keeps the snapshot returned by POST /api/scrape
    immediately useful for the dashboard."""
    return sum(1 for c in COMPANIES if c.get("tier", 3) in (0, 1))


def _run_scrape_async(mode: str = "fast") -> None:
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


def _check_api_secret() -> bool:
    """Returns True if the request is authorized (or no secret is configured)."""
    if not API_SECRET:
        return True
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return token == API_SECRET


@app.route("/api/scrape", methods=["POST", "OPTIONS"])
def api_trigger_scrape():
    """Trigger an immediate scrape in a background daemon thread.

    Returns 202 with a status snapshot so the dashboard can poll
    /api/scrape/status for live progress. A 409 is returned if a scrape is
    already in flight (per the broker's 10-min watchdog).
    """
    if request.method == "OPTIONS":
        return "", 204

    if not _check_api_secret():
        return jsonify({"error": "unauthorized"}), 401

    # Atomic check-and-arm: closes the race where two concurrent POSTs both
    # pass is_running() and spawn two scrape threads. The broker is armed
    # synchronously before we return 202, so the embedded snapshot already
    # shows is_running=True — no false "scrape complete" on the first poll.
    if not broker.try_start("fast", _count_fast_companies()):
        return jsonify({
            "started":  False,
            "reason":   "scrape_in_progress",
            "snapshot": broker.snapshot(),
        }), 409

    threading.Thread(
        target=_run_scrape_async,
        args=("fast",),
        daemon=True,
        name="scrape-worker",
    ).start()

    return jsonify({
        "started":  True,
        "snapshot": broker.snapshot(),
    }), 202


@app.route("/api/scrape/status", methods=["GET"])
def api_scrape_status():
    """Live progress snapshot for the in-flight scrape (or last finished run).

    Auth-gated symmetrically with POST /api/scrape: if API_SECRET is set, a
    matching Bearer token is required. This prevents the snapshot leaking
    cadence/company-name info to anonymous pollers in deployments that have
    locked down the trigger.
    """
    if not _check_api_secret():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(broker.snapshot()), 200, {"Access-Control-Allow-Origin": "*"}


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


# ─── Application tracker endpoints ───────────────────────────────

@app.route("/api/applications", methods=["GET"])
def api_get_applications():
    """Get all saved/applied jobs with optional status filter."""
    try:
        status_filter = request.args.get("status")  # ?status=applied
        conn = get_conn(DB_PATH)
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY updated_at DESC",
                (status_filter,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications WHERE status != 'removed' ORDER BY updated_at DESC"
            ).fetchall()
        conn.close()
        return jsonify({"applications": [dict(r) for r in rows]}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/applications", methods=["POST", "OPTIONS"])
def api_save_application():
    """Save or update a job application."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        data  = request.get_json() or {}
        ext_id = data.get("external_id", "")
        if not ext_id:
            return jsonify({"error": "external_id required"}), 400

        now = datetime.now(timezone.utc).isoformat()
        conn = get_conn(DB_PATH)

        existing = conn.execute(
            "SELECT id, status FROM applications WHERE external_id = ?", (ext_id,)
        ).fetchone()

        new_status = data.get("status", "saved")
        applied_at = now if new_status == "applied" and (not existing or existing["status"] != "applied") else (
            existing["applied_at"] if existing else None
        ) if existing else None

        # Look up content_hash from the job row so applied-job dedup survives
        # external_id churn (Greenhouse/Lever req republish).
        content_hash = None
        if new_status == "applied":
            job_row = conn.execute(
                "SELECT content_hash FROM jobs WHERE external_id = ?", (ext_id,)
            ).fetchone()
            if job_row and job_row["content_hash"]:
                content_hash = job_row["content_hash"]

        if existing:
            conn.execute("""
                UPDATE applications SET
                    status = ?, notes = COALESCE(?, notes),
                    resume_version = COALESCE(?, resume_version),
                    applied_at = COALESCE(?, applied_at),
                    content_hash = COALESCE(?, content_hash),
                    updated_at = ?
                WHERE external_id = ?
            """, (
                new_status,
                data.get("notes"),
                data.get("resume_version"),
                now if new_status == "applied" else None,
                content_hash,
                now, ext_id,
            ))
            action = "updated"
        else:
            conn.execute("""
                INSERT INTO applications
                    (external_id, title, company, url, status, relevance_score,
                     salary_min, salary_max, location, notes, resume_version,
                     saved_at, applied_at, updated_at, content_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ext_id,
                data.get("title", ""),
                data.get("company", ""),
                data.get("url", ""),
                new_status,
                data.get("relevance_score", 0.0),
                data.get("salary_min", 0),
                data.get("salary_max", 0),
                data.get("location", ""),
                data.get("notes", ""),
                data.get("resume_version", ""),
                now,
                now if new_status == "applied" else None,
                now,
                content_hash,
            ))
            action = "saved"

        conn.commit()
        conn.close()
        return jsonify({"status": action, "external_id": ext_id}), 200, {
            "Access-Control-Allow-Origin": "*"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/applications/<ext_id>", methods=["DELETE", "OPTIONS"])
def api_delete_application(ext_id):
    """Soft-delete a job from the tracker (sets status to 'removed')."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_conn(DB_PATH)
        conn.execute(
            "UPDATE applications SET status = 'removed', updated_at = ? WHERE external_id = ?",
            (now, ext_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "removed": ext_id}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/applications/<string:ext_id>", methods=["PATCH"])
def patch_application(ext_id):
    """Partially update an application (status, notes, resume_version)."""
    data = request.get_json() or {}
    allowed = {"status", "notes", "resume_version"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields"}), 400
    # Handle applied_at automatically when status becomes 'applied'
    if updates.get("status") == "applied":
        updates["applied_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    SAFE_COLS = {"status", "notes", "resume_version", "applied_at", "updated_at", "content_hash"}
    try:
        conn = get_conn(DB_PATH)
        # When transitioning to 'applied', pin the job's content_hash onto the
        # application row so export-side dedup still catches it after the
        # underlying req gets republished with a new external_id. A manual
        # application with no matching job row simply leaves content_hash NULL.
        if updates.get("status") == "applied":
            job_row = conn.execute(
                "SELECT content_hash FROM jobs WHERE external_id = ?", (ext_id,)
            ).fetchone()
            if job_row and job_row["content_hash"]:
                updates["content_hash"] = job_row["content_hash"]
        set_parts = [f"{k} = ?" for k in updates if k in SAFE_COLS]
        values = [v for k, v in updates.items() if k in SAFE_COLS] + [ext_id]
        conn.execute(
            f"UPDATE applications SET {', '.join(set_parts)} WHERE external_id = ?",
            values
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE external_id = ?", (ext_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/applications/company/<company_name>", methods=["GET"])
def api_company_history(company_name):
    """Get all applications for a company (case-insensitive)."""
    try:
        from storage.profile_manager import get_company_application_history
        return jsonify(get_company_application_history(company_name, DB_PATH)), 200, {
            "Access-Control-Allow-Origin": "*"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/applications/export", methods=["GET"])
def api_export_applications():
    """Export all applications as JSON (for backup)."""
    try:
        conn = get_conn(DB_PATH)
        rows = conn.execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()
        conn.close()
        data = [dict(r) for r in rows]
        return Response(
            json.dumps(data, default=str, indent=2),
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Content-Disposition": "attachment; filename=applications.json",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

        try:
            import pdfplumber, io
            pdf_bytes = file.read()
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = [p.extract_text() or "" for p in pdf.pages]
            text = "\n".join(pages_text).strip()
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
    """Delete a resume version by key."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import delete_resume_version
        delete_resume_version(version_key, DB_PATH)
        return jsonify({"status": "deleted"}), 200, {"Access-Control-Allow-Origin": "*"}
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
def _bg_scrape_loop() -> None:
    log.info("Background scraper enabled — interval=%ds", FAST_INTERVAL)
    # First tick gets a short delay so the Flask boot path isn't competing
    # with the scraper for SQLite init/imports on cold starts.
    time.sleep(15)
    while True:
        try:
            if is_quiet_hours():
                log.debug("BG scrape: quiet hours, skipping")
            elif not broker.try_start("fast", _count_fast_companies()):
                # Atomic check-and-arm: must mirror POST /api/scrape's gate
                # exactly. A plain `if broker.is_running()` check would leave
                # a race window where a manual POST wins the broker while
                # we're about to call run_scrape() — both threads would then
                # tick the same broker and double-scrape the same companies.
                log.debug("BG scrape: broker busy, skipping cycle")
            else:
                log.info("BG scrape: starting fast cycle")
                threading.Thread(
                    target=_run_scrape_async,
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


def _should_run_bg_scraper() -> bool:
    """Background loop is opt-out via DISABLE_BG_SCRAPE=1, and auto-disabled
    under pytest so test_client() reloads don't spawn rogue threads that
    write to the test DB."""
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return False
    if os.environ.get("DISABLE_BG_SCRAPE", "").lower() in ("1", "true", "yes"):
        return False
    return os.environ.get("ENABLE_BG_SCRAPE", "1") == "1"


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
