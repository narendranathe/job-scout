"""Shared auth helpers for cookie sessions, CSRF, and Bearer fallback.

PRD #89 Slice 1. Three auth modes the dashboard + bulk uploader use:

1. **Bearer token** (existing) — ``Authorization: Bearer <API_SECRET>``.
   How ``tools/bulk_upload_to_render.py`` and curl scripts authenticate.
   CSRF doesn't apply (request crafted by trusted code, not a browser).

2. **Session cookie** (new) — ``jobscout_session=<signed-payload>``.
   Set by ``POST /api/login`` after a valid PIN, expires after 30 days.
   For browser sessions: state-changing requests must also carry
   ``X-CSRF-Token: <token>`` matching the token embedded in the session.

3. **Open (dev)** — when ``API_SECRET`` is unset, every request passes.

The signed cookie uses ``itsdangerous.URLSafeTimedSerializer`` — Flask's
own session signing primitive, transitive dep, no new package. Signature
key precedence: ``SESSION_SECRET_KEY`` env → ``API_SECRET`` env →
process-local random fallback (cookies invalidate on each restart in
dev, which is fine).

API surface — every route blueprint should call ``require_auth(request)``
instead of hand-rolling its own ``_check_auth``. Returns:

* ``None`` if the request is authorised (continue)
* a ``(json, status)`` tuple if not (return directly)
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import time
from typing import Optional, Tuple

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger(__name__)

# Cookie + header names. Centralised so tests, docs, and the frontend
# don't drift from the server.
SESSION_COOKIE_NAME = "jobscout_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FIELD_NAME = "csrf"  # key inside the signed cookie payload
SCOPE_FIELD_NAME = "scope"  # "full" (PIN-authenticated) or "setup" (pre-PIN wizard)

# Scope values for the signed payload. ``full`` is the historical
# 30-day, full-privilege session minted after a verified PIN. ``setup``
# is the narrow pre-PIN wizard cookie introduced to fix the no-PIN
# privilege-escalation vulnerability (a fresh Render instance with no
# PIN used to mint a 30-day full-power session for *anyone* who hit
# /api/login first). Now /api/login on a pinless server returns a
# ``setup`` cookie that only unlocks the small allowlist of routes the
# onboarding wizard needs. The first call to /api/set-pin invalidates
# all outstanding setup cookies by stamping a server-side epoch.
SCOPE_FULL = "full"
SCOPE_SETUP = "setup"

# Routes the ``setup`` scope is allowed to touch. Read carefully — every
# entry here is reachable WITHOUT a PIN on a fresh install. The wizard's
# Step 5 (resume upload) goes through /api/vault/upload, but the wizard
# also calls it pre-PIN, so it must be on the allowlist. The roster
# endpoints don't need to be here because they're public anyway.
#
# Anything not on this list returns 403 with "setup_scope_insufficient"
# even if the setup cookie is otherwise valid.
SETUP_SCOPE_ALLOWED_PATHS = frozenset({
    "/api/profile",                  # POST: save wizard answers
    "/api/resume",                   # POST: paste resume text
    "/api/set-pin",                  # POST: ends the setup phase
    "/api/vault/upload",             # POST: Slice 3 PDF upload step
    "/api/vault/parse-filename",     # POST: Slice 3 filename echo
    "/api/vault/list",               # GET: confirm upload succeeded
    "/api/vault/stats",              # GET: post-upload summary widget
})

# 30 days — matches Set-Cookie Max-Age. Re-validated server-side on every
# request via ``SignatureExpired`` so a stolen cookie auto-expires.
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

# 30 minutes. Setup cookies are short-lived on purpose: an attacker who
# races the legitimate user to a freshly-deployed instance gets at most
# a 30-minute window to attempt the (already narrow) setup-scope path
# set. Real wizard runs are sub-5-minute per PRD #89 G1, so 30 minutes
# is generous headroom for someone who walks away mid-flow and comes
# back. Setting the PIN re-issues a full 30-day session anyway.
SETUP_COOKIE_MAX_AGE_SECONDS = 30 * 60

_BEARER_RE = re.compile(r"^Bearer\s+(\S+)\s*$", re.IGNORECASE)

# Per-process fallback signing key so a dev server without
# SESSION_SECRET_KEY or API_SECRET still works (cookies invalidate on
# restart, which is the expected dev-mode behaviour).
_FALLBACK_KEY = secrets.token_hex(32)

# Server-side setup-epoch cache. Holds the unix timestamp at which the
# last ``invalidate_setup_cookies`` call was made. Setup cookies whose
# iat is older are rejected. Held in a tiny on-disk file (next to the
# SQLite DB) so it survives process restarts but doesn't require a new
# schema migration. Set to 0 / missing means "no epoch yet" — fresh
# install behaviour.
_SETUP_EPOCH_CACHE: dict = {"ts": 0, "loaded": False}

# State-changing methods that require CSRF for cookie auth. GET/HEAD/
# OPTIONS are exempt because they're considered safe per RFC 7231 §4.2.1
# and CORS already prevents cross-origin cookie sends without preflight.
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _signing_key() -> str:
    """Resolve the cookie signing key — env first, then fallback.

    Read live so pytest fixtures that ``monkeypatch.setenv`` take effect
    without re-importing. The microsecond cost is negligible compared
    to the SQLite + IO work that follows every authenticated request.
    """
    return (
        os.environ.get("SESSION_SECRET_KEY", "").strip()
        or os.environ.get("API_SECRET", "").strip()
        or _FALLBACK_KEY
    )


def _api_secret() -> str:
    """Live read of API_SECRET (matches core.config.check_api_secret pattern)."""
    return os.environ.get("API_SECRET", "").strip()


def _serializer() -> URLSafeTimedSerializer:
    """Fresh serializer per call so key rotation via env var takes effect."""
    return URLSafeTimedSerializer(_signing_key(), salt="jobscout-session-v1")


def _setup_epoch_path() -> str:
    """Resolve the path to the on-disk setup-epoch marker.

    Located next to the SQLite DB so it inherits the same persistent-
    volume mount on Render. A separate file rather than a new column to
    avoid pulling profile_manager into the auth layer (would create an
    import cycle with vault_routes' before_request hook).
    """
    db_path = os.environ.get("DB_PATH", "")
    if db_path:
        return db_path + ".setup_epoch"
    # Fall back to a process-local temp file. Survives within a single
    # gunicorn worker but not across restarts — acceptable for dev.
    return os.path.join(os.path.dirname(__file__), "..", ".setup_epoch")


def _read_setup_epoch() -> int:
    """Read the persisted setup-epoch (unix ts). 0 if unset."""
    if _SETUP_EPOCH_CACHE.get("loaded"):
        return int(_SETUP_EPOCH_CACHE.get("ts") or 0)
    try:
        with open(_setup_epoch_path(), "r", encoding="utf-8") as f:
            ts = int((f.read() or "0").strip() or "0")
    except FileNotFoundError:
        ts = 0
    except Exception as e:  # pragma: no cover — defensive
        log.warning("setup-epoch read failed (%s): treating as 0", e)
        ts = 0
    _SETUP_EPOCH_CACHE["ts"] = ts
    _SETUP_EPOCH_CACHE["loaded"] = True
    return ts


def invalidate_setup_cookies() -> int:
    """Mark every outstanding setup-scope cookie as superseded.

    Called from ``/api/set-pin`` the moment a PIN gets set. Setup
    cookies whose ``iat`` is earlier than the new epoch will fail
    ``read_session`` on the very next request, forcing the holder to
    log in fresh (with the just-set PIN this time). Returns the new
    epoch for log/test visibility.

    Atomic write: write to ``.tmp`` then ``os.replace`` so a crashed
    write doesn't leave a half-formed epoch file that defeats the
    invalidation.
    """
    new_epoch = int(time.time())
    path = _setup_epoch_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(new_epoch))
        os.replace(tmp, path)
    except Exception as e:
        # Don't raise — the PIN was set successfully and the setup
        # cookie expires in 30 min anyway. Log loudly and continue.
        log.warning("failed to persist setup-epoch: %s", e)
    _SETUP_EPOCH_CACHE["ts"] = new_epoch
    _SETUP_EPOCH_CACHE["loaded"] = True
    return new_epoch


def reset_setup_epoch_cache() -> None:
    """Drop the in-memory setup-epoch cache. Tests call this in fixtures.

    Without this hook, the per-process cache would survive between
    pytest cases that swap DB paths via monkeypatch, so a stale epoch
    from a prior test could reject a fresh-DB setup cookie.
    """
    _SETUP_EPOCH_CACHE["ts"] = 0
    _SETUP_EPOCH_CACHE["loaded"] = False


def issue_session(scope: str = SCOPE_FULL) -> Tuple[str, str]:
    """Mint a fresh signed session token + CSRF token.

    Returns ``(cookie_value, csrf_token)``. The CSRF token is embedded
    in the cookie payload so the server can compare it against the
    client-provided header without storing per-session state.

    ``scope`` is either ``SCOPE_FULL`` (PIN-authenticated, 30-day, every
    route) or ``SCOPE_SETUP`` (pre-PIN wizard, 30-minute, narrow
    allowlist — see ``SETUP_SCOPE_ALLOWED_PATHS``).
    """
    if scope not in (SCOPE_FULL, SCOPE_SETUP):
        raise ValueError(f"unknown session scope: {scope!r}")
    csrf = secrets.token_urlsafe(24)
    payload = {
        CSRF_FIELD_NAME: csrf,
        SCOPE_FIELD_NAME: scope,
        "iat": int(time.time()),
    }
    cookie = _serializer().dumps(payload)
    return cookie, csrf


def read_session(cookie_value: str) -> Optional[dict]:
    """Verify + decode a session cookie.

    Returns the payload dict (with ``csrf``, ``scope``, and ``iat``) when
    the signature is valid and the cookie is within its scope-specific
    max-age (30 days for ``full``, 30 minutes for ``setup``). Returns
    ``None`` for tampered, expired, or missing cookies — callers treat
    ``None`` as "not authenticated" without distinguishing why.

    Decoding is done in two phases: first with the maximum max-age, then
    we re-check the iat against the scope-specific max-age. This avoids
    leaking timing about which scope a cookie carries.
    """
    if not cookie_value:
        return None
    try:
        payload = _serializer().loads(
            cookie_value, max_age=SESSION_MAX_AGE_SECONDS
        )
    except SignatureExpired:
        log.info("session cookie expired")
        return None
    except BadSignature:
        log.warning("session cookie failed signature check")
        return None
    except Exception as e:  # pragma: no cover — defensive
        log.warning("session cookie decode failed: %s", e)
        return None

    # Scope-specific max-age. Setup cookies are short-lived (30 min) by
    # policy — a cookie whose iat is older than that is treated as
    # expired even if the outer signature is still within 30 days.
    # Default scope for legacy cookies (pre-this-patch) is ``full`` so
    # in-flight sessions don't get invalidated by the rollout.
    scope = payload.get(SCOPE_FIELD_NAME, SCOPE_FULL)
    if scope == SCOPE_SETUP:
        iat = int(payload.get("iat") or 0)
        if iat <= 0 or (int(time.time()) - iat) > SETUP_COOKIE_MAX_AGE_SECONDS:
            log.info("setup cookie expired (>%ds)", SETUP_COOKIE_MAX_AGE_SECONDS)
            return None
        # Cross-check against the server-side setup-epoch — see
        # ``invalidate_setup_cookies``. If the user (or attacker) called
        # /api/set-pin after this cookie was issued, the epoch advances
        # and the cookie is rejected, forcing a re-login. The compare
        # is ``<=`` rather than ``<`` so that a cookie issued in the
        # *same second* as the invalidation is also killed — without
        # this, a test (or an attacker on a fast LAN) could squeeze a
        # cookie through the second-resolution clock.
        epoch = _read_setup_epoch()
        if epoch and iat <= epoch:
            log.info("setup cookie superseded by /api/set-pin")
            return None
    return payload


def _bearer_matches(request) -> bool:
    """Constant-time comparison of the Bearer token against API_SECRET."""
    secret = _api_secret()
    if not secret:
        return True  # dev mode passthrough handled by caller too
    m = _BEARER_RE.match(request.headers.get("Authorization", ""))
    if not m:
        return False
    token = m.group(1)
    return secrets.compare_digest(
        token.encode("utf-8"), secret.encode("utf-8")
    )


def _cookie_matches(request) -> Optional[dict]:
    """Return the decoded session payload when the cookie is valid."""
    return read_session(request.cookies.get(SESSION_COOKIE_NAME, ""))


def _csrf_ok(request, session: dict) -> bool:
    """Constant-time CSRF compare between session payload and header."""
    expected = session.get(CSRF_FIELD_NAME, "")
    provided = request.headers.get(CSRF_HEADER_NAME, "")
    if not expected or not provided:
        return False
    return secrets.compare_digest(
        expected.encode("utf-8"), provided.encode("utf-8")
    )


def require_auth(request) -> Optional[Tuple[dict, int]]:
    """Gate any request behind the unified auth check.

    Returns ``None`` when the request is allowed. Otherwise returns a
    ``(body_dict, status_int)`` tuple the caller can ``jsonify`` and
    return directly, so each route stays a one-liner:

        deny = require_auth(request)
        if deny is not None:
            body, status = deny
            return jsonify(body), status

    Auth rules:

    * Dev mode (``API_SECRET`` unset) → always pass.
    * Bearer token matches → pass (no CSRF check; non-browser caller).
    * Valid session cookie + (safe method OR matching CSRF header) → pass.
    * Otherwise → 401 (no auth at all) or 403 (cookie ok, CSRF missing).
    """
    # Dev mode bypass — preserves the existing local-dev workflow where
    # nobody sets API_SECRET and every endpoint is open.
    if not _api_secret():
        return None

    if _bearer_matches(request):
        return None

    session = _cookie_matches(request)
    if session is None:
        return ({"error": "unauthorized"}, 401)

    # Scope gate. A ``setup`` session may only touch the narrow wizard
    # allowlist. Anything else — vault writes against existing data,
    # admin endpoints, etc. — is denied even though the cookie itself
    # signed cleanly. This is the load-bearing fix for the no-PIN
    # privilege-escalation vulnerability: an attacker who races a
    # legitimate user to /api/login on a freshly-deployed pinless
    # instance now gets a cookie that can do almost nothing.
    scope = session.get(SCOPE_FIELD_NAME, SCOPE_FULL)
    if scope == SCOPE_SETUP and request.path not in SETUP_SCOPE_ALLOWED_PATHS:
        log.warning(
            "setup-scope cookie rejected on out-of-scope path: %s %s",
            request.method, request.path,
        )
        return ({"error": "setup_scope_insufficient"}, 403)

    # Safe methods don't require CSRF; readers can mount no-side-effect
    # GETs from the dashboard with just the cookie.
    if request.method not in _STATE_CHANGING_METHODS:
        return None

    if not _csrf_ok(request, session):
        return ({"error": "csrf_token_invalid"}, 403)

    return None


def current_session(request) -> Optional[dict]:
    """Return the decoded session payload for the request, or None.

    Distinct from ``require_auth`` — this is a non-failing probe for
    routes that want to behave differently for cookie-vs-Bearer callers
    (e.g. emitting CSRF tokens only when the caller is browser-based).
    """
    return _cookie_matches(request)


def set_session_cookie_headers(cookie_value: str) -> dict:
    """Build the headers needed to set the session cookie.

    Flask routes pre-PR #94 returned ``Response`` objects with
    ``set_cookie``; the existing route style here returns
    ``(jsonify(...), status, headers_dict)``. Returning the headers as
    a dict so the route can splat ``{**base, **set_session_cookie_headers(c)}``
    instead of constructing a Response. ``Set-Cookie`` is a multi-value
    header, but we only set one — a dict suffices.
    """
    parts = [
        f"{SESSION_COOKIE_NAME}={cookie_value}",
        "Path=/",
        f"Max-Age={SESSION_MAX_AGE_SECONDS}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
        parts.append("Secure")
    return {"Set-Cookie": "; ".join(parts)}


def clear_session_cookie_headers() -> dict:
    """Build the Set-Cookie header to clear the session (logout)."""
    parts = [
        f"{SESSION_COOKIE_NAME}=",
        "Path=/",
        "Max-Age=0",
        "HttpOnly",
        "SameSite=Lax",
    ]
    return {"Set-Cookie": "; ".join(parts)}
