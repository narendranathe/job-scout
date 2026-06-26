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

import flask
from flask import Blueprint, jsonify, request

# Import the module so test fixtures that monkeypatch core.config.DB_PATH
# (and the existing pattern that mutates server.DB_PATH at fixture setup)
# reach us via attribute lookup, not the import-time-bound name.
from core import config as _config
from core.config import check_api_secret
from routes._auth import (
    issue_session,
    set_session_cookie_headers,
    clear_session_cookie_headers,
)
from middleware.supabase_auth import require_auth

log = logging.getLogger("jobscout")

profile_bp = Blueprint("profile", __name__)


def _profile_auth():
    """Hybrid auth helper for profile write routes.

    Tries Supabase JWT / API_SECRET Bearer via ``check_auth()`` first
    (sets ``flask.g.user_id`` on success). Falls back to the legacy
    ``routes._auth.require_auth`` which handles dev-mode passthrough
    (API_SECRET unset) and session-cookie + CSRF.

    Returns ``(deny_response, user_id)`` where deny_response is None on
    success (caller continues) or a Flask response tuple on failure
    (caller should return it directly).
    """
    from middleware.supabase_auth import check_auth as _check_auth_jwt
    result = _check_auth_jwt()
    if result is None:
        # JWT / scraper path succeeded; user_id set on flask.g.
        # Profile data is single-user: map the API_SECRET scraper identity
        # back to "legacy" so reads (which default to "legacy") and writes
        # share the same row. Real Supabase JWTs get their own user_id.
        uid = flask.g.user_id
        if uid == "scraper":
            uid = "legacy"
        return None, uid
    # Fall back to legacy (dev-mode / cookie / API_SECRET Bearer).
    from routes._auth import require_auth as _legacy_require_auth
    deny = _legacy_require_auth(request)
    if deny is None:
        return None, "legacy"
    body, status = deny
    return (jsonify(body), status, {"Access-Control-Allow-Origin": "*"}), "legacy"


@profile_bp.route("/api/profile", methods=["GET"])
def api_get_profile():
    """Get user profile (preferences + default_resume_version + onboarding flags).

    Auth: uses _profile_auth() so Supabase JWT / Bearer / session-cookie
    callers get their own user-scoped row. Unauthenticated callers fall
    through to the "legacy" row (dev-mode passthrough when API_SECRET
    is unset) matching the existing single-user behaviour.
    """
    deny, user_id = _profile_auth()
    if deny is not None:
        return deny
    try:
        from storage.profile_manager import init_profile_tables, get_profile
        init_profile_tables(_config.DB_PATH)
        return jsonify(get_profile(user_id=user_id, db_path=_config.DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/profile", methods=["POST", "OPTIONS"])
def api_update_profile():
    """Update preferences. Bearer- OR session-cookie-authed.

    Validates the 5 onboarding-wizard fields (tracked_companies,
    min_total_comp, show_unsalaried, onboarded_at, skip_pin_acknowledged)
    alongside the existing fields. ``default_resume_version`` still
    cross-validates against the resume_versions table.

    Side effect: when ``tracked_companies`` adds names that aren't in
    ``config/companies.py``, fire a rate-limited Discord ping to the
    maintainer (PRD #89 Slice 4 / Q1). Failure to ping is swallowed —
    it's a notification, not a correctness invariant.
    """
    if request.method == "OPTIONS":
        return "", 204
    # Hybrid auth: Supabase JWT (new path) then legacy Bearer/cookie (compat).
    # check_auth() sets flask.g.user_id on success; legacy path does not.
    deny, user_id = _profile_auth()
    if deny is not None:
        return deny
    try:
        from storage.profile_manager import (
            init_profile_tables,
            update_profile,
            get_profile,
            ProfileValidationError,
        )
        init_profile_tables(_config.DB_PATH)
        payload = request.get_json() or {}

        # Snapshot the prior tracked_companies BEFORE update_profile so
        # we can diff and only ping on NEW additions.
        prior_tracked = []
        if "tracked_companies" in payload:
            try:
                prior_tracked = list(
                    get_profile(user_id, db_path=_config.DB_PATH).get("tracked_companies", [])
                )
            except Exception:
                prior_tracked = []

        try:
            update_profile(user_id, updates=payload, db_path=_config.DB_PATH)
        except ProfileValidationError as ve:
            # Validation failures (e.g. unknown default_resume_version key,
            # negative min_total_comp) are client errors → 400 lets the
            # dashboard show a useful message instead of an opaque 500.
            return jsonify({"error": str(ve)}), 400, {"Access-Control-Allow-Origin": "*"}

        # Fire-and-forget Discord ping for newly-tracked unscraped names.
        # Runs in the request thread; the notifier itself has an 8s
        # network timeout and swallows failures.
        if "tracked_companies" in payload:
            _maybe_ping_unscraped(payload.get("tracked_companies") or [], prior_tracked)

        return jsonify({"status": "updated"}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _maybe_ping_unscraped(new_tracked, prior_tracked):
    """Fire the rate-limited Discord ping for new unscraped company names.

    Only the diff (new ∖ prior) is reported; the notifier's own
    rate-limiter handles batching across multiple POSTs in a window.
    Swallows every exception — notifications are best-effort.
    """
    try:
        from config.companies import COMPANIES
        scraped = {(c.get("name") or "").lower() for c in COMPANIES}
        prior_set = {(n or "").lower() for n in (prior_tracked or [])}
        novel = [
            n for n in (new_tracked or [])
            if (n or "").strip()
            and n.lower() not in scraped
            and n.lower() not in prior_set
        ]
        if not novel:
            return
        from alerts.notifier import notify_unscraped_tracking
        notify_unscraped_tracking(novel)
    except Exception as e:  # pragma: no cover — defensive
        log.warning("unscraped-tracking ping failed: %s", e)


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
        skills = upload_resume(resume_text=resume_text, db_path=_config.DB_PATH)
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
        return jsonify({"verified": verify_pin(pin=pin, db_path=_config.DB_PATH)}), 200, {
            "Access-Control-Allow-Origin": "*"
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/set-pin", methods=["POST", "OPTIONS"])
def api_set_pin():
    """Set or change the dashboard PIN. Bearer- or cookie-authed."""
    if request.method == "OPTIONS":
        return "", 204
    deny, _user_id = _profile_auth()
    if deny is not None:
        return deny
    try:
        from storage.profile_manager import init_profile_tables, set_pin
        init_profile_tables(_config.DB_PATH)
        pin = (request.get_json() or {}).get("pin", "")
        if len(pin) < 4:
            return jsonify({"error": "PIN must be at least 4 characters"}), 400
        # PIN is a server-wide credential in the single-user model; always
        # stored under the "legacy" row so /api/login and /api/verify-pin
        # (which have no auth and use the legacy default) can look it up.
        set_pin(pin=pin, db_path=_config.DB_PATH)
        return jsonify({"status": "pin_set"}), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/api/login", methods=["POST", "OPTIONS"])
def api_login():
    """Trade a valid PIN for a signed session cookie + CSRF token.

    Refuses to mint a session when no PIN is set on this server (HTTP
    403, ``error: pin_not_set``). Without that guard a fresh-install
    Render instance would hand out a 30-day write-scoped cookie to the
    first caller who reaches ``POST /api/login`` with any body — see
    the security note below.

    Why this is safe for the onboarding wizard: the wizard's PinSetup
    component (PRD #89 Slice 3, step 6) first calls ``POST /api/set-pin``
    using whatever auth the early steps relied on (Bearer token when
    ``API_SECRET`` is set, dev-mode passthrough when it isn't) and only
    then calls ``POST /api/login`` with the freshly created PIN. By the
    time login fires there is always a PIN to verify, so this branch
    never hits the wizard happy path.

    UI hint: a 403 ``pin_not_set`` response is the dashboard's signal
    to route the user into ``/setup`` instead of the login screen.

    Response body on success:

        {"status": "ok", "csrf_token": "..."}

    The CSRF token MUST be sent with every state-changing request as
    ``X-CSRF-Token: <token>``. It rotates on every login.
    """
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import (
            init_profile_tables,
            verify_pin,
            has_pin,
        )
        init_profile_tables(_config.DB_PATH)
        # Refuse login entirely when no PIN is configured. verify_pin
        # returns True for any input in this state (open-access dev
        # semantics), which would otherwise let an unauthenticated
        # attacker mint a 30-day session cookie + CSRF on a fresh
        # install before the owner has run the wizard.
        if not has_pin(db_path=_config.DB_PATH):
            # 412 Precondition Failed is semantically more accurate than
            # 403 here: it's not that the caller lacks permission, it's
            # that the prerequisite resource (the PIN) doesn't exist yet.
            # The dashboard's frontend reads this status to redirect to
            # /setup, so the precise code matters for the contract.
            return jsonify({"error": "pin_not_set"}), 412, {
                "Access-Control-Allow-Origin": "*"
            }
        pin = (request.get_json(silent=True) or {}).get("pin", "")
        if not verify_pin(pin=pin, db_path=_config.DB_PATH):
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
    """Clear the session cookie. Idempotent on success.

    CSRF gate: logout DOES require a valid CSRF token (or a Bearer
    token from an approved origin) — without it, a hostile site could
    auto-submit ``<form action="/api/logout">`` and silently log out
    every JobScout user that visits. Annoying-but-not-catastrophic is
    still a UX denial-of-service we can cheaply prevent. The earlier
    no-CSRF stance was wrong (per Phase-2 critic, systemic miss B).

    Three valid auth shapes:
      * Unauthenticated (no cookie, no Bearer) → 200 no-op so a stale
        client trying to "clean up" doesn't 401-loop. No cookie is
        cleared because there was nothing to clear.
      * Cookie + matching ``X-CSRF-Token`` → 200, cookie cleared.
      * Bearer + (no browser-Origin, OR Origin in allowlist) → 200,
        cookie cleared (covers ``bulk_upload_to_render.py`` flows
        that may stash a stale cookie).
    """
    if request.method == "OPTIONS":
        return "", 204

    has_cookie = bool(request.cookies.get("jobscout_session", ""))
    has_bearer = bool(request.headers.get("Authorization", "").strip())

    # No auth at all → idempotent. Still emit the Set-Cookie clear
    # header in case the browser has a session cookie that wasn't sent
    # this request (different cookie-jar, SameSite weirdness) so the
    # public contract — "after /api/logout, no jobscout_session
    # cookie remains" — holds even on the no-auth path.
    if not has_cookie and not has_bearer:
        return jsonify({"status": "logged_out"}), 200, {
            "Access-Control-Allow-Origin": "*",
            **clear_session_cookie_headers(),
        }

    # Some form of auth present → apply the full gate so the CSRF /
    # Origin checks run. Failure here returns 403 so the client knows
    # the request was rejected (cookie / Bearer still valid server-
    # side). Use the legacy require_auth here so session-cookie + CSRF
    # flows work (cookie auth is not handled by supabase_auth).
    from routes._auth import require_auth as _legacy_require_auth
    deny = _legacy_require_auth(request)
    if deny is not None:
        body, status = deny
        return jsonify(body), status, {"Access-Control-Allow-Origin": "*"}

    headers = {
        "Access-Control-Allow-Origin": "*",
        **clear_session_cookie_headers(),
    }
    return jsonify({"status": "logged_out"}), 200, headers


# Kept as a no-op import-time reference so static analysers don't flag
# ``check_api_secret`` as unused — older route bodies still imported it
# from this module via re-export. Will go in the next cleanup pass.
_ = check_api_secret
