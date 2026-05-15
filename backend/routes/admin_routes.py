"""
Admin API — Flask Blueprint for operator/health endpoints.

Plug into server.py with:
    from routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp)

Endpoints:
    GET  /api/admin/doctor             — Server health probe (DB, scrapers, env, vault, disk)
    POST /api/admin/reextract-skills   — Re-run skill extraction over all resume_versions rows
    POST /api/admin/vault-reindex      — Rebuild TF-IDF index from resume_vault/text/ on disk
"""

import importlib
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db"))
API_SECRET = os.environ.get("API_SECRET", "")

VAULT_ROOT = os.environ.get(
    "RESUME_VAULT_PATH",
    os.path.join(os.path.dirname(__file__), "..", "resume_vault"),
)
SCRAPER_MODULES = ["greenhouse", "lever", "ashby", "smartrecruiters", "bamboohr", "workday"]


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _check_db_connectivity() -> dict:
    # Use storage.db.get_conn so we exercise the same WAL-mode connection
    # the rest of the app actually uses, not a raw sqlite3.connect.
    try:
        from storage.db import get_conn
        conn = get_conn(DB_PATH)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return _check("db_connectivity", "pass", "SELECT 1 OK")
    except Exception as e:
        return _check("db_connectivity", "fail", f"DB unreachable: {e.__class__.__name__}")


def _check_scrapers_importable() -> dict:
    missing = []
    for mod in SCRAPER_MODULES:
        try:
            importlib.import_module(f"scrapers.{mod}")
        except Exception as e:
            missing.append(f"{mod} ({e.__class__.__name__})")
    if missing:
        return _check("scrapers_importable", "fail",
                      f"missing: {', '.join(missing)}; ok: {len(SCRAPER_MODULES) - len(missing)}/{len(SCRAPER_MODULES)}")
    return _check("scrapers_importable", "pass",
                  f"all {len(SCRAPER_MODULES)} scrapers importable")


def _check_recent_scrape_run() -> dict:
    # finish_run() in storage/db.py writes status='complete'; tolerate
    # legacy 'success' rows as well.
    try:
        from storage.db import get_conn
        conn = get_conn(DB_PATH)
        try:
            row = conn.execute(
                "SELECT MAX(finished_at) FROM scrape_runs WHERE status IN ('success','complete')"
            ).fetchone()
        finally:
            conn.close()
        last = row[0] if row else None
        if not last:
            # Fresh deploy with no scrape history is a soft signal, not a failure.
            return _check("recent_scrape_run", "warn", "no completed scrape runs yet")
        try:
            finished = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
        except Exception:
            return _check("recent_scrape_run", "warn", f"unparseable timestamp: {last}")
        age_h = (datetime.now(timezone.utc) - finished).total_seconds() / 3600
        if age_h < 24:
            return _check("recent_scrape_run", "pass", f"last success {age_h:.1f}h ago")
        if age_h < 72:
            return _check("recent_scrape_run", "warn", f"last success {age_h:.1f}h ago (>24h)")
        return _check("recent_scrape_run", "fail", f"last success {age_h:.1f}h ago (>72h)")
    except Exception as e:
        return _check("recent_scrape_run", "fail", f"query failed: {e.__class__.__name__}")


def _check_env_vars_present() -> dict:
    # DB_PATH has a code-level default → always considered set.
    optional = ["DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN"]
    missing_count = sum(1 for v in optional if not os.environ.get(v))
    if missing_count:
        return _check("env_vars_present", "warn",
                      f"DB_PATH ok; {missing_count}/{len(optional)} optional alert vars unset")
    return _check("env_vars_present", "pass",
                  "DB_PATH ok; all optional alert vars set")


def _check_vault_dirs_writable() -> dict:
    # Vault subdirs are gitignored and created lazily on first upload, so
    # "missing" is a soft signal (warn). Existing-but-unwritable is hard fail.
    pdf_dir = os.path.join(VAULT_ROOT, "pdf")
    text_dir = os.path.join(VAULT_ROOT, "text")
    fails, warns = [], []
    for label, path in [("pdf", pdf_dir), ("text", text_dir)]:
        if not os.path.isdir(path):
            warns.append(f"{label}/ not yet provisioned")
        elif not os.access(path, os.W_OK):
            fails.append(f"{label}/ not writable")
    if fails:
        return _check("vault_dirs_writable", "fail", "; ".join(fails + warns))
    if warns:
        return _check("vault_dirs_writable", "warn", "; ".join(warns))
    return _check("vault_dirs_writable", "pass", "pdf/ and text/ writable")


def _check_disk_space() -> dict:
    try:
        usage = shutil.disk_usage("/")
        free_mb = usage.free / (1024 * 1024)
    except Exception:
        return _check("disk_space", "warn", "unavailable on this platform")
    if free_mb < 100:
        return _check("disk_space", "fail", f"{free_mb:.0f}MB free (<100MB)")
    if free_mb < 500:
        return _check("disk_space", "warn", f"{free_mb:.0f}MB free (<500MB)")
    return _check("disk_space", "pass", f"{free_mb:.0f}MB free")


def _aggregate(checks: list) -> str:
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


# Registry — tests can monkeypatch this list to inject fakes.
DOCTOR_CHECKS = [
    _check_db_connectivity,
    _check_scrapers_importable,
    _check_recent_scrape_run,
    _check_env_vars_present,
    _check_vault_dirs_writable,
    _check_disk_space,
]


@admin_bp.route("/doctor", methods=["GET", "OPTIONS"])
def doctor():
    """Run all health probes; return per-check results + aggregated overall status."""
    if request.method == "OPTIONS":
        return "", 200

    if API_SECRET:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != API_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    checks = []
    for fn in DOCTOR_CHECKS:
        try:
            checks.append(fn())
        except Exception as e:
            log.exception("doctor check %s crashed", getattr(fn, "__name__", fn))
            checks.append(_check(getattr(fn, "__name__", "unknown"), "fail",
                                 f"check crashed: {e}"))

    return jsonify({
        "checks": checks,
        "overall": _aggregate(checks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }), 200


def _require_bearer():
    """Return None if auth passes, else a (response, status) tuple to bail with."""
    if not API_SECRET:
        return None
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != API_SECRET:
        return jsonify({"error": "unauthorized"}), 401
    return None


@admin_bp.route("/reextract-skills", methods=["POST", "OPTIONS"])
def reextract_skills():
    """
    Re-run profile_manager.extract_skills_from_resume() over every row in
    resume_versions. Non-destructive: only the extracted_skills column is
    rewritten — resume_text, target_roles, etc. are untouched.

    Returns {"updated": N, "total": M, "errors": E}.
    """
    if request.method == "OPTIONS":
        return "", 200

    auth_err = _require_bearer()
    if auth_err is not None:
        return auth_err

    try:
        from storage.db import get_conn
        from storage.profile_manager import extract_skills_from_resume
    except Exception as e:
        log.exception("reextract-skills: import failure")
        return jsonify({"error": f"import failed: {e.__class__.__name__}"}), 500

    updated, errors = 0, 0
    now = datetime.now(timezone.utc).isoformat()

    conn = get_conn(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT id, resume_text FROM resume_versions"
        ).fetchall()
        total = len(rows)
        for row in rows:
            row_id = row["id"]
            text = row["resume_text"] or ""
            try:
                skills = extract_skills_from_resume(text)
                conn.execute(
                    "UPDATE resume_versions SET extracted_skills = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(skills), now, row_id),
                )
                updated += 1
            except Exception as e:
                log.warning("reextract-skills: row id=%s failed (%s)", row_id, e.__class__.__name__)
                errors += 1
        conn.commit()
    finally:
        conn.close()

    log.info("reextract-skills: updated=%d total=%d errors=%d", updated, total, errors)
    return jsonify({"updated": updated, "total": total, "errors": errors}), 200


@admin_bp.route("/vault-reindex", methods=["POST", "OPTIONS"])
def vault_reindex():
    """
    Rebuild the resume vault TF-IDF index from disk. Re-reads every .txt file
    in resume_vault/text/ and recomputes term-document vectors. Read-only with
    respect to historical data — does not delete or rewrite any file.

    Returns {"indexed": N, "files_scanned": M, "duration_ms": int}.
    """
    if request.method == "OPTIONS":
        return "", 200

    auth_err = _require_bearer()
    if auth_err is not None:
        return auth_err

    try:
        from storage.resume_vault import rebuild_index
    except Exception as e:
        log.exception("vault-reindex: import failure")
        return jsonify({"error": f"import failed: {e.__class__.__name__}"}), 500

    started = time.monotonic()
    try:
        result = rebuild_index()
    except Exception as e:
        log.exception("vault-reindex: rebuild failed")
        return jsonify({"error": f"reindex failed: {e.__class__.__name__}"}), 500
    duration_ms = int((time.monotonic() - started) * 1000)

    payload = {
        "indexed": int(result.get("indexed", 0)),
        "files_scanned": int(result.get("files_scanned", 0)),
        "duration_ms": duration_ms,
    }
    log.info("vault-reindex: %s", payload)
    return jsonify(payload), 200


@admin_bp.after_request
def admin_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response
