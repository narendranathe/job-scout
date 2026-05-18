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
file-backed shared fallback (multi-worker safe in dev; production hard-
fails if neither env var is set).

Multi-worker safety: under gunicorn's pre-fork model each forked worker
imports modules fresh, so a ``secrets.token_hex()`` generated at import
time would yield a DIFFERENT key per worker. A user logs in on worker 1
and the next request hits worker 2 → signature check fails → random
401s under load. The fallback key is therefore persisted to a shared
file (``SESSION_KEY_FILE`` env, default ``/tmp/jobscout-session-key``)
written atomically by the first worker and read by the rest, so every
worker signs and verifies with the same key.

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
import tempfile
import threading
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

# Env vars that flag this process as running in production. Any one being
# truthy means "production" — when neither SESSION_SECRET_KEY nor
# API_SECRET is set in that mode, we hard-fail rather than silently
# minting a fallback key (which under multi-worker gunicorn would give
# every worker its own key and cause random session invalidation).
_PRODUCTION_ENV_FLAGS = (
    ("JOBSCOUT_ENV", ("production", "prod")),
    ("FLASK_ENV", ("production", "prod")),
    ("RENDER", ("true", "1", "yes")),     # Render sets RENDER=true
    ("DYNO", None),                        # Heroku sets DYNO=web.1 etc.
)

# Default location for the shared fallback key. ``~/.jobscout/session-key``
# beats the previous ``/tmp/jobscout-session-key`` on two counts:
#   1. ``/tmp`` is world-writable — a local unprivileged user could
#      pre-create the path as a symlink to a file they own; the chmod
#      0600 then applies to *their* file and the rename follows the
#      symlink (the parent dir is what matters).
#   2. ``/tmp`` is typically tmpfs and gets cleaned at boot. Stored
#      under the home dir, the key survives reboots so local-dev
#      sessions don't invalidate every morning.
# Operators can override via SESSION_KEY_FILE to pin a different path
# (e.g. ``/var/lib/jobscout/session.key`` for system-wide installs).
_DEFAULT_KEY_DIR = os.path.expanduser("~/.jobscout")
_DEFAULT_KEY_FILE = os.path.join(_DEFAULT_KEY_DIR, "session-key")

# Process-local memoisation so we don't re-read the key file on every
# request. Guarded by a lock so concurrent first-touch from multiple
# threads doesn't race the file write.
_FALLBACK_KEY_CACHE: Optional[str] = None
_FALLBACK_KEY_LOCK = threading.Lock()


def _is_production() -> bool:
    """Truthy when any production-marker env var is set."""
    for name, truthy_vals in _PRODUCTION_ENV_FLAGS:
        val = os.environ.get(name, "").strip().lower()
        if not val:
            continue
        if truthy_vals is None:
            return True  # presence alone is enough (DYNO)
        if val in truthy_vals:
            return True
    return False


def _key_file_path() -> str:
    """Resolve the shared fallback key file path (env-overridable)."""
    return os.environ.get("SESSION_KEY_FILE", "").strip() or _DEFAULT_KEY_FILE


def _load_or_create_fallback_key() -> str:
    """Read the shared fallback key from disk, generating + persisting it
    on first call. Multi-worker safe: each worker that races to create
    the file uses an atomic rename so the last writer wins without
    leaving a partial file visible to readers, and any worker that finds
    the file already populated reads the existing key.

    Cached in module state after the first successful read so the file
    is touched at most once per worker process.
    """
    global _FALLBACK_KEY_CACHE
    if _FALLBACK_KEY_CACHE is not None:
        return _FALLBACK_KEY_CACHE

    with _FALLBACK_KEY_LOCK:
        # Re-check after acquiring the lock in case another thread won.
        if _FALLBACK_KEY_CACHE is not None:
            return _FALLBACK_KEY_CACHE

        path = _key_file_path()

        # Fast path: file already exists from a previous worker / start.
        try:
            with open(path, "r", encoding="ascii") as fh:
                existing = fh.read().strip()
            if existing and len(existing) >= 32:
                _FALLBACK_KEY_CACHE = existing
                return existing
        except FileNotFoundError:
            pass
        except OSError as e:  # pragma: no cover — defensive
            log.warning("could not read session key file %s: %s", path, e)

        # Slow path: generate a new key and persist it atomically. We
        # write to a temp file in the same directory then rename — POSIX
        # rename is atomic so concurrent workers either see the old file
        # (none) or the new file (complete), never a half-written one.
        new_key = secrets.token_hex(32)
        try:
            dir_ = os.path.dirname(path) or "."
            # mode=0o700 on the dir prevents the symlink-pre-creation
            # attack: even if the path inside is world-writable on the
            # filesystem, the parent dir restricts who can stat/list/
            # cd into it. Existing dirs keep their permissions.
            os.makedirs(dir_, mode=0o700, exist_ok=True)
            try:
                os.chmod(dir_, 0o700)
            except OSError:
                pass  # best-effort on non-POSIX
            fd, tmp_path = tempfile.mkstemp(
                prefix=".jobscout-session-key.", dir=dir_
            )
            try:
                with os.fdopen(fd, "w", encoding="ascii") as fh:
                    fh.write(new_key)
                # Restrict to owner — the key is sensitive.
                try:
                    os.chmod(tmp_path, 0o600)
                except OSError:
                    pass  # best-effort on non-POSIX
                os.replace(tmp_path, path)
            except Exception:
                # Clean up tmp file if rename failed.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            # Re-read after rename in case another worker beat us — we
            # want every worker to converge on the same value.
            try:
                with open(path, "r", encoding="ascii") as fh:
                    final_key = fh.read().strip()
                if final_key and len(final_key) >= 32:
                    _FALLBACK_KEY_CACHE = final_key
                    log.warning(
                        "auth: using file-backed fallback signing key at %s — "
                        "set SESSION_SECRET_KEY in production",
                        path,
                    )
                    return final_key
            except OSError:
                pass
        except OSError as e:
            # No silent process-local fallback here — that would re-
            # introduce the multi-worker bug this whole function exists
            # to fix. If we can't persist the key, the operator MUST
            # know via a hard failure rather than via random 401s in
            # production logs days later. Raise with a remediation
            # pointer so the cause is obvious from the traceback.
            raise RuntimeError(
                f"auth: could not persist session key to {path}: {e}. "
                "Set SESSION_KEY_FILE to a writable path or export "
                "SESSION_SECRET_KEY directly to skip the file-backed "
                "fallback entirely."
            ) from e

        # Defensive: if we reach here without returning a key, raise
        # rather than caching None. Shouldn't be possible given the
        # branching above, but make the failure mode explicit.
        raise RuntimeError(
            f"auth: session key file at {path} ended up empty after "
            "atomic write — refusing to mint per-worker keys"
        )


def _fallback_key() -> str:
    """Return the fallback signing key, hard-failing in production.

    In production (any of JOBSCOUT_ENV / FLASK_ENV / RENDER / DYNO set),
    a missing SESSION_SECRET_KEY *and* missing API_SECRET is a config
    error — silently generating a key would cause random logouts as
    workers cycle. Raise loudly so the operator sees it at startup.
    """
    if _is_production():
        raise RuntimeError(
            "auth: refusing to mint a fallback signing key in production. "
            "Set SESSION_SECRET_KEY (preferred) or API_SECRET in the "
            "environment so all gunicorn workers share the same key."
        )
    return _load_or_create_fallback_key()

# State-changing methods that require CSRF for cookie auth. GET/HEAD/
# OPTIONS are exempt because they're considered safe per RFC 7231 §4.2.1
# and CORS already prevents cross-origin cookie sends without preflight.
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _signing_key() -> str:
    """Resolve the cookie signing key — env first, then fallback.

    Read live so pytest fixtures that ``monkeypatch.setenv`` take effect
    without re-importing. The microsecond cost is negligible compared
    to the SQLite + IO work that follows every authenticated request.

    Precedence:
      1. ``SESSION_SECRET_KEY`` (explicit, recommended for production)
      2. ``API_SECRET`` (re-used so single-secret deployments still work)
      3. Shared file-backed fallback (dev only — see ``_fallback_key``)
    """
    explicit = (
        os.environ.get("SESSION_SECRET_KEY", "").strip()
        or os.environ.get("API_SECRET", "").strip()
    )
    if explicit:
        return explicit
    return _fallback_key()


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


def _bearer_request_is_safe(request) -> bool:
    """Guard the "Bearer skips CSRF" path against XSS-via-localStorage.

    Threat: an XSS payload in the dashboard can read
    ``localStorage["vault_token"]`` and then issue ``Authorization:
    Bearer ...`` requests. Because Bearer auth bypasses CSRF (the
    standard design — machine clients have no cookies to protect), an
    attacker who exfiltrated only the token can mount fully-authorised
    cross-site writes. The cookie CSRF check is useless here.

    Defence: when a Bearer request also carries a browser-set ``Origin``
    or ``Sec-Fetch-Site`` header, require the ``Origin`` to be in
    ``ALLOWED_ORIGINS``. Browsers set ``Origin`` on all cross-origin
    POST / PUT / PATCH / DELETE (and on same-origin POST too in
    practice); curl / Python ``requests`` / the ``bulk_upload_to_render``
    CLI do not, so the legitimate machine-to-machine path is unaffected.

    Rules:
      * No ``Origin`` AND no ``Sec-Fetch-Site`` → CLI / proxy caller →
        pass.
      * ``Origin`` present and matches one of ``ALLOWED_ORIGINS`` →
        legitimate browser caller (dashboard itself) → pass.
      * ``Origin`` present and ``ALLOWED_ORIGINS`` unset → dev / single-
        origin deploy → pass with a one-time WARN log so operators set
        the allowlist before production.
      * ``Origin`` present but NOT in the allowlist → likely XSS or
        cross-site abuse → reject.

    Safe methods (GET / HEAD / OPTIONS) are exempt; they can't be
    weaponised for state changes anyway.
    """
    if request.method not in _STATE_CHANGING_METHODS:
        return True

    origin = request.headers.get("Origin", "").strip()
    sec_fetch_site = request.headers.get("Sec-Fetch-Site", "").strip()

    # Pure machine caller — neither header present.
    if not origin and not sec_fetch_site:
        return True

    # Browser caller. If the deploy hasn't configured an allowlist,
    # we degrade to "warn but allow" so dev workflows don't break;
    # production operators get a loud log line to fix it.
    allowed = _allowed_origins()
    if not allowed:
        if not _bearer_request_is_safe._warned_no_allowlist:  # type: ignore[attr-defined]
            log.warning(
                "Bearer request from browser context (Origin=%r) but "
                "ALLOWED_ORIGINS is unset — set it in production to block "
                "XSS-via-localStorage Bearer forgery",
                origin or "<missing>",
            )
            _bearer_request_is_safe._warned_no_allowlist = True  # type: ignore[attr-defined]
        return True

    if origin and origin in allowed:
        return True

    log.warning(
        "Bearer request rejected: Origin=%r not in ALLOWED_ORIGINS (browser "
        "context detected via Origin or Sec-Fetch-Site header)",
        origin or "<missing>",
    )
    return False


# Initialise the one-time-warn flag as a function attribute. Cheaper
# than a module global with a lock — re-entrance is fine, we just
# don't want to spam the log on every request.
_bearer_request_is_safe._warned_no_allowlist = False  # type: ignore[attr-defined]


def _allowed_origins() -> list[str]:
    """Resolve ALLOWED_ORIGINS live so operator-changed values take effect
    without restart (matches the rest of this module's live-env pattern).
    """
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]


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
    * Bearer token matches:
        * If the request is a state-changing method AND has a browser-set
          ``Origin`` / ``Sec-Fetch-Site`` header, the Origin must be in
          ``ALLOWED_ORIGINS`` (defence against XSS-via-localStorage
          Bearer forgery — see ``_bearer_request_is_safe``).
        * Otherwise → pass (machine-to-machine caller, e.g. the bulk
          uploader).
    * Valid session cookie + (safe method OR matching CSRF header) → pass.
    * Otherwise → 401 (no auth at all) or 403 (cookie ok, CSRF missing,
      or Bearer from blocked origin).
    """
    # Dev mode bypass — preserves the existing local-dev workflow where
    # nobody sets API_SECRET and every endpoint is open.
    if not _api_secret():
        return None

    if _bearer_matches(request):
        if not _bearer_request_is_safe(request):
            return ({"error": "origin_not_allowed"}, 403)
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
