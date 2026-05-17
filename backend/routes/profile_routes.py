"""Profile, resume-text, and PIN endpoints — server.py split (6/8).

Four routes that share the user-profile storage layer:

    GET  /api/profile      — read preferences (open; pin_hash is stripped)
    POST /api/profile      — update preferences (auth-gated)
    POST /api/resume       — paste resume text, extract skills, persist
    POST /api/verify-pin   — check dashboard PIN
    POST /api/set-pin      — change dashboard PIN (auth-gated)

All write paths gate on check_api_secret(request) when API_SECRET is set.
OPTIONS preflights pass through unconditionally so browser CORS works.
"""
import logging

from flask import Blueprint, jsonify, request

# Import the module so test fixtures that monkeypatch core.config.DB_PATH
# (and the existing pattern that mutates server.DB_PATH at fixture setup)
# reach us via attribute lookup, not the import-time-bound name.
from core import config as _config
from core.config import check_api_secret

log = logging.getLogger("jobscout")

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/api/profile", methods=["GET"])
def api_get_profile():
    """Get user profile (preferences + default_resume_version).

    Auth: deliberately left open. The payload is the user's own
    preferences (custom skills, dream-company list, default resume key) —
    not credentials. The pin_hash is stripped in ``get_profile`` so
    readers can't even mount an offline brute-force. If a deployment
    decides this should be gated, flip the same Bearer check used on POST.
    """
    try:
        from storage.profile_manager import init_profile_tables, get_profile
        init_profile_tables(_config.DB_PATH)
        return jsonify(get_profile(_config.DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/profile", methods=["POST", "OPTIONS"])
def api_update_profile():
    """Update preferences (custom_skills, dream_*, default_resume_version).

    Auth: Bearer-gated when API_SECRET is configured. Without this, an
    anonymous attacker could flip ``default_resume_version`` and silently
    change which resume the dashboard auto-scores every job against
    (Issue #39 part A R2 #1). OPTIONS preflights pass through so browser
    CORS preflight isn't blocked by the missing Authorization header.
    """
    if request.method == "OPTIONS":
        return "", 204
    if not check_api_secret(request):
        return jsonify({"error": "unauthorized"}), 401, {"Access-Control-Allow-Origin": "*"}
    try:
        from storage.profile_manager import (
            init_profile_tables,
            update_profile,
            ProfileValidationError,
        )
        init_profile_tables(_config.DB_PATH)
        try:
            update_profile(request.get_json() or {}, _config.DB_PATH)
        except ProfileValidationError as ve:
            # Validation failures (e.g. unknown default_resume_version key)
            # are client errors → 400 lets the dashboard show a useful
            # message instead of an opaque 500.
            return jsonify({"error": str(ve)}), 400, {"Access-Control-Allow-Origin": "*"}
        return jsonify({"status": "updated"}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/resume", methods=["POST", "OPTIONS"])
def api_upload_resume():
    """Upload resume text → extract skills → store in DB."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, upload_resume
        init_profile_tables(_config.DB_PATH)
        data = request.get_json() or {}
        resume_text = data.get("resume_text", "").strip()
        if not resume_text:
            return jsonify({"error": "resume_text field required"}), 400
        skills = upload_resume(resume_text, _config.DB_PATH)
        return jsonify({
            "status": "ok",
            "skills_extracted": len(skills),
            "skills": skills,
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/verify-pin", methods=["POST", "OPTIONS"])
def api_verify_pin():
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, verify_pin
        init_profile_tables(_config.DB_PATH)
        pin = (request.get_json() or {}).get("pin", "")
        return jsonify({"verified": verify_pin(pin, _config.DB_PATH)}), 200, {
            "Access-Control-Allow-Origin": "*"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/set-pin", methods=["POST", "OPTIONS"])
def api_set_pin():
    if request.method == "OPTIONS":
        return "", 204
    if not check_api_secret(request):
        return jsonify({"error": "unauthorized"}), 401
    try:
        from storage.profile_manager import init_profile_tables, set_pin
        init_profile_tables(_config.DB_PATH)
        pin = (request.get_json() or {}).get("pin", "")
        if len(pin) < 4:
            return jsonify({"error": "PIN must be at least 4 characters"}), 400
        set_pin(pin, _config.DB_PATH)
        return jsonify({"status": "pin_set"}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500
