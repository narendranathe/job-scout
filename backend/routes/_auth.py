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

# 30 days — matches Set-Cookie Max-Age. Re-validated server-side on every
# request via ``SignatureExpired`` so a stolen cookie auto-expires.
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

_BEARER_RE = re.compile(r"^Bearer\s+(\S+)\s*$", re.IGNORECASE)

# Per-process fallback signing key so a dev server without
# SESSION_SECRET_KEY or API_SECRET still works (cookies invalidate on
# restart, which is the expected dev-mode behaviour).
_FALLBACK_KEY = secrets.token_hex(32)

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


def issue_session() -> Tuple[str, str]:
    """Mint a fresh signed session token + CSRF token.

    Returns ``(cookie_value, csrf_token)``. The CSRF token is embedded
    in the cookie payload so the server can compare it against the
    client-provided header without storing per-session state.
    """
    csrf = secrets.token_urlsafe(24)
    payload = {
        CSRF_FIELD_NAME: csrf,
        "iat": int(time.time()),
    }
    cookie = _serializer().dumps(payload)
    return cookie, csrf


def read_session(cookie_value: str) -> Optional[dict]:
    """Verify + decode a session cookie.

    Returns the payload dict (with ``csrf`` and ``iat``) when the
    signature is valid and the cookie is within ``SESSION_MAX_AGE_SECONDS``.
    Returns ``None`` for tampered, expired, or missing cookies — callers
    treat ``None`` as "not authenticated" without distinguishing why.
    """
    if not cookie_value:
        return None
    try:
        return _serializer().loads(
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
