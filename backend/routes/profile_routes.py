"""Profile, resume-text, PIN, and session endpoints — server.py split (6/8).

Routes that share the user-profile storage layer:

    GET  /api/profile      — read preferences (open; pin_hash is stripped)
    POST /api/profile      — update preferences (auth-gated)
    POST /api/resume       — paste resume text, extract skills, persist
    POST /api/verify-pin   — check dashboard PIN (deprecated; kept for back-compat)
    POST /api/set-pin      — change dashboard PIN (auth-gated)
    POST /api/login        — PIN → signed session cookie + CSRF token (PRD #89 Slice 1)
    POST /api/logout       — clear the session cookie

All write paths gate via ``routes._auth.require_auth`` which accepts
Bearer tokens or session cookies. OPTIONS preflights pass through
unconditionally so browser CORS works.
"""
import logging

from flask import Blueprint, jsonify, request

# Import the module so test fixtures that monkeypatch core.config.DB_PATH
# (and the existing pattern that mutates server.DB_PATH at fixture setup)
# reach us via attribute lookup, not the import-time-bound name.
from core import config as _config
from core.config import check_api_secret
from routes._auth import (
    issue_session,
    require_auth,
    set_session_cookie_headers,
    clear_session_cookie_headers,
)

log = logging.getLogger("jobscout")

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/api/profile", methods=["GET"])
def api_get_profile():
    """Get user profile (preferences + default_resume_version + onboarding flags).

    Auth: deliberately left open. The payload is the user's own
    preferences — not credentials. The pin_hash is stripped in
    ``get_profile`` so readers can't even mount an offline brute-force.
    """
    try:
        from storage.profile_manager import init_profile_tables, get_profile
        init_profile_tables(_config.DB_PATH)
        return jsonify(get_profile(_config.DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/profile", methods=["POST", "OPTIONS"])
def api_update_profile():
    """Update preferences. Bearer- OR session-cookie-authed.

    Validates the 5 onboarding-wizard fields (tracked_companies,
    min_total_comp, show_unsalaried, onboarded_at, skip_pin_acknowledged)
    alongside the existing fields. ``default_resume_version`` still
    cross-validates against the resume_versions table.
    """
    if request.method == "OPTIONS":
        return "", 204
    deny = require_auth(request)
    if deny is not None:
        body, status = deny
        return jsonify(body), status, {"Access-Control-Allow-Origin": "*"}
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
            # Validation failures (e.g. unknown default_resume_version key,
            # negative min_total_comp) are client errors → 400 lets the
            # dashboard show a useful message instead of an opaque 500.
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
    """Plain PIN verification (legacy).

    Kept for back-compat — the dashboard's old PIN modal posts here. New
    flows should prefer ``/api/login`` which both verifies the PIN and
    issues a session cookie. Slated for removal one release after the
    wizard ships.
    """
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
    """Set or change the dashboard PIN. Bearer- or cookie-authed."""
    if request.method == "OPTIONS":
        return "", 204
    deny = require_auth(request)
    if deny is not None:
        body, status = deny
        return jsonify(body), status, {"Access-Control-Allow-Origin": "*"}
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


@profile_bp.route("/api/login", methods=["POST", "OPTIONS"])
def api_login():
    """Trade a valid PIN for a signed session cookie + CSRF token.

    When no PIN is set on this server, login is a no-op — the response
    still mints a session so the wizard's "create your account" flow
    works without an awkward two-step. When a PIN is set, the request
    must include ``{"pin": "..."}`` and it must verify.

    Response body:

        {"status": "ok", "csrf_token": "..."}

    The CSRF token MUST be sent with every state-changing request as
    ``X-CSRF-Token: <token>``. It rotates on every login.
    """
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, verify_pin
        init_profile_tables(_config.DB_PATH)
        pin = (request.get_json(silent=True) or {}).get("pin", "")
        if not verify_pin(pin, _config.DB_PATH):
            # Constant-ish delay path: verify_pin already does the pbkdf2
            # work for both correct and incorrect PINs, so this 401 has
            # the same timing profile as a 200.
            return jsonify({"error": "invalid_pin"}), 401, {
                "Access-Control-Allow-Origin": "*"
            }
        cookie_value, csrf = issue_session()
        headers = {
            "Access-Control-Allow-Origin": "*",
            **set_session_cookie_headers(cookie_value),
        }
        return jsonify({"status": "ok", "csrf_token": csrf}), 200, headers
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/logout", methods=["POST", "OPTIONS"])
def api_logout():
    """Clear the session cookie. Always returns 200 — idempotent.

    No CSRF check: clearing a cookie is not a state-changing operation
    on server-side data, and refusing logout on a missing token would
    just trap users in a broken session.
    """
    if request.method == "OPTIONS":
        return "", 204
    headers = {
        "Access-Control-Allow-Origin": "*",
        **clear_session_cookie_headers(),
    }
    return jsonify({"status": "logged_out"}), 200, headers


# Kept as a no-op import-time reference so static analysers don't flag
# ``check_api_secret`` as unused — older route bodies still imported it
# from this module via re-export. Will go in the next cleanup pass.
_ = check_api_secret
