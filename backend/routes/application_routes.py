"""Application tracker endpoints — server.py split (7/8).

Six routes that drive the dashboard's Tracker/Pipeline tabs:

    GET    /api/applications                   — list with optional status filter
    POST   /api/applications                   — save/update (upsert by external_id)
    DELETE /api/applications/<ext_id>          — soft-delete (status='removed')
    PATCH  /api/applications/<ext_id>          — partial update (status/notes/resume)
    GET    /api/applications/company/<name>    — full company history
    GET    /api/applications/export            — JSON dump for backup

No auth gate — the dashboard owns the data and uses the same DB. If a
deployment later wants this gated, flip check_api_secret() on the writes.
"""
import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from core import config as _config
from storage.db import get_conn

log = logging.getLogger("jobscout")

application_bp = Blueprint("application", __name__)


@application_bp.route("/api/applications", methods=["GET"])
def api_get_applications():
    """Get all saved/applied jobs with optional status filter."""
    try:
        status_filter = request.args.get("status")  # ?status=applied
        conn = get_conn(_config.DB_PATH)
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


@application_bp.route("/api/applications", methods=["POST", "OPTIONS"])
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
        conn = get_conn(_config.DB_PATH)

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


@application_bp.route("/api/applications/<ext_id>", methods=["DELETE", "OPTIONS"])
def api_delete_application(ext_id):
    """Soft-delete a job from the tracker (sets status to 'removed')."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_conn(_config.DB_PATH)
        conn.execute(
            "UPDATE applications SET status = 'removed', updated_at = ? WHERE external_id = ?",
            (now, ext_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "removed": ext_id}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@application_bp.route("/api/applications/<string:ext_id>", methods=["PATCH"])
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
        conn = get_conn(_config.DB_PATH)
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


@application_bp.route("/api/applications/company/<company_name>", methods=["GET"])
def api_company_history(company_name):
    """Get all applications for a company (case-insensitive)."""
    try:
        from storage.profile_manager import get_company_application_history
        return jsonify(get_company_application_history(company_name, _config.DB_PATH)), 200, {
            "Access-Control-Allow-Origin": "*"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@application_bp.route("/api/applications/export", methods=["GET"])
def api_export_applications():
    """Export all applications as JSON (for backup)."""
    try:
        conn = get_conn(_config.DB_PATH)
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
