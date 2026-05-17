"""Shared backend configuration — environment-driven constants.

Extracted from server.py (CLAUDE.md tech-debt #2 — server.py monolith
split). Module-leaf by design: anything else can import from here, but
this module imports only from the stdlib. Keeps the dependency graph
acyclic so new route blueprints don't have to ``import server``.

Environment variables consumed:
  DB_PATH        — SQLite database path (default: backend/jobscout.db)
  FAST_INTERVAL  — seconds between background scrape cycles (default: 300)
  PORT           — HTTP port (default: 10000, matches Render)
  API_SECRET     — Bearer-token gate for write endpoints (optional;
                   when unset, auth is bypassed = dev mode)
"""
import os
import re
import secrets

# Path to backend/ so the default DB sits alongside the package.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.environ.get("DB_PATH", os.path.join(_BACKEND_DIR, "jobscout.db"))
FAST_INTERVAL = int(os.environ.get("FAST_INTERVAL", "300"))
PORT = int(os.environ.get("PORT", "10000"))

# .strip() so trailing whitespace from .env files / shell exports doesn't
# silently invalidate every auth attempt with a mysterious 401.
API_SECRET = os.environ.get("API_SECRET", "").strip()

# RFC 7235: auth scheme is case-insensitive ("Bearer" / "bearer" / "BEARER"
# all valid). Pre-compiled so the per-request hot path is one regex match.
_BEARER_RE = re.compile(r"^Bearer\s+(\S+)\s*$", re.IGNORECASE)


def check_api_secret(request) -> bool:
    """Returns True if the request is authorized (or no secret is configured).

    Hardened against:
    - Bearer scheme case (RFC 7235): "bearer", "Bearer", "BEARER" all match.
    - Timing side-channels: ``secrets.compare_digest`` runs in constant time
      so an attacker can't probe the secret byte-by-byte over many requests.

    Reads ``os.environ`` live on each call rather than the module-level
    ``API_SECRET`` constant. This matters because pytest fixtures (and
    operators rotating secrets without process restart) expect
    ``monkeypatch.setenv("API_SECRET", "...")`` to take effect immediately.
    Microsecond cost is negligible compared to the DB / IO work that
    follows. The module-level constant is kept for startup-time uses
    (e.g. logging "API_SECRET is unset" warnings) where the at-import
    value is the right semantic.

    Takes the Flask ``request`` object as a parameter rather than importing
    it at module level so this module stays Flask-free (testable without a
    Flask context, no implicit thread-local dependency).
    """
    live_secret = os.environ.get("API_SECRET", "").strip()
    if not live_secret:
        return True  # dev mode passthrough
    m = _BEARER_RE.match(request.headers.get("Authorization", ""))
    if not m:
        return False
    token = m.group(1)
    return secrets.compare_digest(token.encode("utf-8"), live_secret.encode("utf-8"))
