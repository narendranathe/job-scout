"""Tests for /api/login, /api/logout, and the cookie + Bearer dual-mode
auth gate on /api/vault/upload.

PRD #89 Slice 1 acceptance criteria:

* POST /api/login with correct PIN → 200 + Set-Cookie; wrong PIN → 401
* Cookie-authed POST /api/vault/upload WITH CSRF → succeeds
* Cookie-authed POST /api/vault/upload WITHOUT CSRF → 403
* Bearer-authed POST /api/vault/upload → works unchanged (regression)
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


SECRET = "test-secret-abc123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "auth.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(vault_dir, exist_ok=True)

    from storage.db import init_db
    from storage.profile_manager import init_profile_tables
    init_db(db_path)
    init_profile_tables(db_path)

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("API_SECRET", SECRET)
    monkeypatch.setenv("VAULT_DIR", vault_dir)

    # Force a clean re-import so the new env vars take effect inside
    # routes that read them at import time (vault_routes.API_SECRET in
    # particular).
    for mod in list(sys.modules):
        if mod == "server" or mod.startswith("routes.") or mod == "core.config":
            del sys.modules[mod]

    import server
    from core import config as _config
    _config.DB_PATH = db_path
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True

    with server.app.test_client() as c:
        yield c


@pytest.fixture
def client_with_pin(client):
    """Set a PIN on the server so login flows have something to validate."""
    from storage.profile_manager import set_pin
    # Tests use DB_PATH from env; set_pin honours that.
    set_pin(pin="1234", db_path=os.environ["DB_PATH"])
    return client


# ─── /api/login ────────────────────────────────────────────────────────────

def test_login_with_correct_pin_sets_cookie(client_with_pin):
    resp = client_with_pin.post("/api/login", json={"pin": "1234"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert "csrf_token" in body
    # Set-Cookie header should mention our session cookie.
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "jobscout_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie


def test_login_with_wrong_pin_returns_401(client_with_pin):
    resp = client_with_pin.post("/api/login", json={"pin": "9999"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_pin"
    # No cookie issued on failure.
    assert "Set-Cookie" not in resp.headers or "jobscout_session=" not in resp.headers.get("Set-Cookie", "")


def test_login_with_empty_pin_returns_401(client_with_pin):
    resp = client_with_pin.post("/api/login", json={"pin": ""})
    assert resp.status_code == 401


def test_login_when_no_pin_set_is_refused(client):
    """Fresh install: /api/login must refuse to mint a session before a
    PIN exists. Previously this returned 200 + cookie, letting any
    attacker who reached a fresh Render instance first get a 30-day
    write-scoped cookie and full vault write access. See PRD #89 +
    fix/login-no-pin-vuln. The wizard's PinSetup component handles
    the bootstrap by calling /api/set-pin first, then /api/login.
    """
    resp = client.post("/api/login", json={"pin": ""})
    assert resp.status_code == 412
    body = resp.get_json()
    assert body["error"] == "pin_not_set"
    # Critically, NO cookie is issued — the response must not let the
    # caller drive subsequent CSRF-gated writes.
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "jobscout_session=" not in set_cookie


def test_login_when_no_pin_set_rejects_any_pin_value(client):
    """Even sending a fake PIN must not mint a session before /api/set-pin
    has run. Catches the regression where an attacker submits any string
    in the hope of bypassing the empty-string short-circuit.
    """
    for guess in ("0000", "1234", "anything", "x" * 64):
        resp = client.post("/api/login", json={"pin": guess})
        assert resp.status_code == 412, f"PIN guess {guess!r} accepted (expected 412)"
        assert "jobscout_session=" not in resp.headers.get("Set-Cookie", "")


def test_no_pin_login_then_vault_write_still_unauthorized(client):
    """End-to-end: even if the /api/login response is misused (e.g. a
    client treats 403 as success), no session cookie was set, so the
    follow-up vault write must still 401. Pins the integration: the
    /api/login fix and the /api/vault/upload gate work together.
    """
    # Attacker hits /api/login before the owner has run the wizard.
    client.post("/api/login", json={"pin": ""})
    # Try a vault write afterwards — should be flatly unauthorized
    # because no cookie was minted.
    from io import BytesIO
    resp = client.post(
        "/api/vault/upload",
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 401


def test_logout_clears_cookie(client_with_pin):
    resp = client_with_pin.post("/api/logout")
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "jobscout_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


# ─── Cookie + CSRF round-trip on vault upload ──────────────────────────────

def _login_and_extract(client, pin):
    """Helper: log in, return (cookie_header, csrf_token)."""
    resp = client.post("/api/login", json={"pin": pin})
    assert resp.status_code == 200
    csrf = resp.get_json()["csrf_token"]
    # The test client maintains its own cookie jar automatically, but the
    # Set-Cookie value is what we'd send manually if needed.
    set_cookie = resp.headers.get("Set-Cookie", "")
    m = re.match(r"jobscout_session=([^;]+)", set_cookie)
    assert m
    return m.group(1), csrf


# Minimal valid PDF (%PDF- magic + trailer).
_MIN_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    b"xref\n0 3\n0000000000 65535 f \n"
    b"0000000009 00000 n \n0000000056 00000 n \n"
    b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n111\n%%EOF\n"
)


def test_cookie_auth_with_csrf_allows_vault_upload(client_with_pin):
    """Cookie session + CSRF header → vault upload succeeds."""
    _cookie, csrf = _login_and_extract(client_with_pin, "1234")

    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
        },
        headers={"X-CSRF-Token": csrf},
        content_type="multipart/form-data",
        buffered=True,
        # Werkzeug test client requires the file as a tuple
        builder={"file": (BytesIO(_MIN_PDF), "test.pdf")},
    ) if False else client_with_pin.post(
        "/api/vault/upload",
        headers={"X-CSRF-Token": csrf},
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    # 200 on success — or 400 if the vault writer rejected the PDF for
    # unrelated reasons. Critically, NOT 401 / 403.
    assert resp.status_code != 401, "auth was rejected — cookie+CSRF should work"
    assert resp.status_code != 403, "csrf was rejected — header matched, should work"


def test_cookie_auth_without_csrf_returns_403(client_with_pin):
    """Cookie session WITHOUT CSRF header on a write → 403."""
    _login_and_extract(client_with_pin, "1234")

    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_token_invalid"


def test_cookie_auth_with_wrong_csrf_returns_403(client_with_pin):
    """Stale or attacker-supplied CSRF → 403."""
    _login_and_extract(client_with_pin, "1234")

    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        headers={"X-CSRF-Token": "wrong-token-xxx"},
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_bearer_auth_still_works_for_vault_upload(client_with_pin):
    """Regression: bulk_upload_to_render.py uses Bearer auth, no cookie."""
    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        headers={"Authorization": f"Bearer {SECRET}"},
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    # Critically, NOT 401 / 403 — Bearer auth means no CSRF check applies.
    assert resp.status_code not in {401, 403}, (
        f"Bearer auth should bypass CSRF; got {resp.status_code} "
        f"{resp.get_data(as_text=True)[:200]}"
    )


def test_no_auth_at_all_returns_401(client_with_pin):
    """Neither cookie nor Bearer → 401 (unauthorized)."""
    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        data={
            "company": "TestCorp",
            "role": "Data Engineer",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 401


def test_safe_method_with_cookie_no_csrf_required(client_with_pin):
    """GET requests with just a cookie work without CSRF."""
    _login_and_extract(client_with_pin, "1234")
    resp = client_with_pin.get("/api/vault/list")
    # 200 or 5xx-from-empty-vault, but not 401 / 403.
    assert resp.status_code not in {401, 403}


# ─── Cookie cryptography ───────────────────────────────────────────────────

def test_tampered_cookie_rejected(client_with_pin, monkeypatch):
    """Flipping any bit in the signed cookie value → 401 on next request."""
    cookie_val, _csrf = _login_and_extract(client_with_pin, "1234")
    # Mutate the cookie. The test client maintains its own jar — use direct
    # header injection on a fresh client to simulate a tampered cookie.
    import server
    with server.app.test_client() as fresh:
        fresh.set_cookie("jobscout_session", cookie_val + "X")
        resp = fresh.get("/api/vault/list")
        assert resp.status_code == 401


def test_cookie_signed_with_session_secret_key(monkeypatch):
    """SESSION_SECRET_KEY overrides API_SECRET for cookie signing."""
    from routes._auth import issue_session, read_session

    monkeypatch.setenv("API_SECRET", "secret-a")
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-key-1")
    cookie_a, _ = issue_session()

    monkeypatch.setenv("SESSION_SECRET_KEY", "session-key-2")
    # A cookie signed under key 1 must not decode under key 2.
    assert read_session(cookie_a) is None

    monkeypatch.setenv("SESSION_SECRET_KEY", "session-key-1")
    payload = read_session(cookie_a)
    assert payload is not None
    assert "csrf" in payload


# ─── Multi-worker fallback key (regression for random-401s bug) ────────────

def _reset_fallback_cache():
    """Helper: clear the module-level fallback key cache so subsequent
    calls hit the file (or generate fresh). Mirrors what a freshly-forked
    gunicorn worker sees on its first auth request."""
    import routes._auth as auth
    auth._FALLBACK_KEY_CACHE = None


def test_fallback_key_is_shared_across_workers(tmp_path, monkeypatch):
    """Two simulated worker processes (cleared module cache) must derive
    the SAME fallback key from the shared file — a cookie signed by one
    must verify on the other. Pre-fix this failed because each worker
    generated its own random ``secrets.token_hex(32)`` at import time.
    """
    from routes._auth import issue_session, read_session

    # Force dev mode + a writable, isolated key file.
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("JOBSCOUT_ENV", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DYNO", raising=False)
    key_file = tmp_path / "session.key"
    monkeypatch.setenv("SESSION_KEY_FILE", str(key_file))

    # Worker A starts cold, mints a session.
    _reset_fallback_cache()
    cookie, _csrf = issue_session()
    assert key_file.exists(), "first worker should have persisted the key"
    key_a = key_file.read_text().strip()
    assert len(key_a) >= 32

    # Worker B starts cold and tries to verify worker A's cookie.
    _reset_fallback_cache()
    payload = read_session(cookie)
    assert payload is not None, (
        "second worker rejected the first worker's cookie — fallback key "
        "is not being shared across forked workers"
    )
    assert "csrf" in payload

    # And the file content didn't change (B read, didn't overwrite).
    assert key_file.read_text().strip() == key_a


def test_production_mode_hard_fails_without_secret(monkeypatch, tmp_path):
    """In production, neither SESSION_SECRET_KEY nor API_SECRET set must
    raise immediately rather than silently mint a per-worker key."""
    from routes._auth import issue_session
    import routes._auth as auth

    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.setenv("SESSION_KEY_FILE", str(tmp_path / "k"))
    monkeypatch.setenv("JOBSCOUT_ENV", "production")
    _reset_fallback_cache()

    with pytest.raises(RuntimeError, match="fallback signing key in production"):
        issue_session()

    # Cleanup: drop the prod flag so later tests aren't affected.
    monkeypatch.delenv("JOBSCOUT_ENV", raising=False)
    _reset_fallback_cache()


def test_production_with_session_secret_key_works(monkeypatch, tmp_path):
    """Production mode is fine as long as SESSION_SECRET_KEY is set —
    the hard-fail is only the fallback path, not every prod request."""
    from routes._auth import issue_session, read_session

    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.setenv("SESSION_SECRET_KEY", "prod-key-xyz")
    monkeypatch.setenv("JOBSCOUT_ENV", "production")
    monkeypatch.setenv("SESSION_KEY_FILE", str(tmp_path / "k"))
    _reset_fallback_cache()

    cookie, _csrf = issue_session()
    assert read_session(cookie) is not None


def test_production_with_api_secret_only_works(monkeypatch, tmp_path):
    """API_SECRET alone (legacy single-secret deployments) is also fine
    in production — it satisfies the explicit-key requirement."""
    from routes._auth import issue_session, read_session

    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.setenv("API_SECRET", "legacy-prod-secret")
    monkeypatch.setenv("JOBSCOUT_ENV", "production")
    monkeypatch.setenv("SESSION_KEY_FILE", str(tmp_path / "k"))
    _reset_fallback_cache()

    cookie, _csrf = issue_session()
    assert read_session(cookie) is not None


def test_render_env_flag_triggers_production(monkeypatch, tmp_path):
    """RENDER=true (set by Render automatically) must trip the prod check."""
    from routes._auth import issue_session

    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("JOBSCOUT_ENV", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("SESSION_KEY_FILE", str(tmp_path / "k"))
    _reset_fallback_cache()

    with pytest.raises(RuntimeError):
        issue_session()

    monkeypatch.delenv("RENDER", raising=False)
    _reset_fallback_cache()


def test_fallback_key_file_permissions_restricted(tmp_path, monkeypatch):
    """The persisted fallback key file must not be world-readable —
    cookies signed with a leaked key can be forged."""
    import stat
    from routes._auth import issue_session

    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("JOBSCOUT_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    key_file = tmp_path / "perm-test.key"
    monkeypatch.setenv("SESSION_KEY_FILE", str(key_file))
    _reset_fallback_cache()

    issue_session()
    mode = stat.S_IMODE(os.stat(key_file).st_mode)
    # Owner read/write only — no group or other access.
    assert mode & stat.S_IRWXG == 0, f"group bits set: {oct(mode)}"
    assert mode & stat.S_IRWXO == 0, f"world bits set: {oct(mode)}"


def test_pre_existing_key_file_is_reused(tmp_path, monkeypatch):
    """If the key file already exists (e.g. left from a previous run or
    written by the parent gunicorn process), workers must read it
    verbatim instead of overwriting."""
    from routes._auth import issue_session, read_session, _load_or_create_fallback_key

    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("JOBSCOUT_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DYNO", raising=False)
    key_file = tmp_path / "preseeded.key"
    preseeded = "a" * 64  # 64 hex chars
    key_file.write_text(preseeded)
    monkeypatch.setenv("SESSION_KEY_FILE", str(key_file))
    _reset_fallback_cache()

    loaded = _load_or_create_fallback_key()
    assert loaded == preseeded

    # And cookies sign/verify with this preseeded key.
    cookie, _ = issue_session()
    assert read_session(cookie) is not None
    # File content unchanged.
    assert key_file.read_text() == preseeded


# ─── Critic-flagged hardening ──────────────────────────────────────────────


def test_fallback_key_raises_on_unwritable_filesystem(tmp_path, monkeypatch):
    """If the key file can't be persisted, we MUST raise, not silently
    fall back to a process-local key. Silent fallback re-introduces the
    multi-worker bug this function was written to fix.

    Forces the failure by monkeypatching ``os.makedirs`` to raise —
    direct filesystem-perm tests don't work as root (Docker/CI). The
    interesting behaviour is the exception-handling branch, not how
    we got there.
    """
    from routes import _auth as auth

    monkeypatch.setenv("SESSION_KEY_FILE", str(tmp_path / "wont-be-created" / "key"))
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    _reset_fallback_cache()

    real_makedirs = os.makedirs

    def boom_on_jobscout_dir(path, *a, **kw):
        if "wont-be-created" in str(path):
            raise OSError(13, "Permission denied")
        return real_makedirs(path, *a, **kw)

    monkeypatch.setattr(os, "makedirs", boom_on_jobscout_dir)

    import pytest as _pytest
    with _pytest.raises(RuntimeError, match=r"could not persist session key"):
        auth._load_or_create_fallback_key()

    # Cache must NOT have been populated with a process-local key —
    # this is the regression guard against the previous silent fallback.
    assert auth._FALLBACK_KEY_CACHE is None


def test_default_key_dir_is_under_home_not_tmp():
    """Predictable /tmp paths invite symlink-pre-creation attacks.

    The default key file must live under ~/.jobscout/, not anywhere a
    local unprivileged user could plant a symlink before first start.
    """
    from routes import _auth as auth
    assert auth._DEFAULT_KEY_FILE.startswith(os.path.expanduser("~/.jobscout"))
    assert "tmp" not in auth._DEFAULT_KEY_FILE.lower()


def test_default_key_dir_created_with_restrictive_perms(tmp_path, monkeypatch):
    """First-use of the default dir creates it 0o700, not 0o755."""
    from routes import _auth as auth

    custom = tmp_path / "subdir" / "session-key"
    monkeypatch.setenv("SESSION_KEY_FILE", str(custom))
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    _reset_fallback_cache()

    auth._load_or_create_fallback_key()
    # The parent dir we just created should be 0o700.
    parent = custom.parent
    mode = parent.stat().st_mode & 0o777
    assert mode == 0o700, f"key dir perms = {oct(mode)} (expected 0o700)"


def test_wizard_bootstrap_path_works_under_pin_gated_deploy(client):
    """Positive test: the wizard's documented bootstrap sequence on a
    pin-gated deploy must succeed end-to-end. Critic flagged that the
    pre-PIN-refusal change had no positive coverage — only refusal
    coverage — so an over-tight gate could break the wizard silently.

    Bootstrap: Bearer (API_SECRET) -> POST /api/set-pin -> POST /api/login
    -> session cookie + CSRF token returned.
    """
    # Step 1: Bearer-auth POST /api/set-pin (the wizard's PinSetup
    # calls this with the user's chosen PIN).
    set_resp = client.post(
        "/api/set-pin",
        json={"pin": "9876"},
        headers={"Authorization": f"Bearer {SECRET}"},
    )
    assert set_resp.status_code == 200, set_resp.get_data(as_text=True)

    # Step 2: POST /api/login with the just-set PIN. Now should mint
    # a real session cookie (no longer pre-PIN-refusal territory).
    login_resp = client.post("/api/login", json={"pin": "9876"})
    assert login_resp.status_code == 200, login_resp.get_data(as_text=True)
    body = login_resp.get_json()
    assert "csrf_token" in body
    assert "jobscout_session=" in login_resp.headers.get("Set-Cookie", "")


# ─── /api/logout CSRF gate (systemic miss B) ──────────────────────────────


def test_logout_with_cookie_and_csrf_clears(client_with_pin):
    """Authenticated session + matching CSRF → logout succeeds and the
    server emits a Max-Age=0 Set-Cookie."""
    _cookie, csrf = _login_and_extract(client_with_pin, "1234")
    resp = client_with_pin.post(
        "/api/logout", headers={"X-CSRF-Token": csrf}
    )
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "jobscout_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


def test_logout_with_cookie_no_csrf_returns_403(client_with_pin):
    """The reason this PR exists: a cross-site `<form action=/api/logout>`
    will send the cookie but not the CSRF header. Pre-fix this returned
    200 and the user was silently logged out. Now it MUST 403.
    """
    _login_and_extract(client_with_pin, "1234")
    resp = client_with_pin.post("/api/logout")  # no CSRF header
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_token_invalid"


def test_logout_with_cookie_wrong_csrf_returns_403(client_with_pin):
    """Attacker-supplied / stale CSRF → 403."""
    _login_and_extract(client_with_pin, "1234")
    resp = client_with_pin.post(
        "/api/logout", headers={"X-CSRF-Token": "wrong-token-xxx"}
    )
    assert resp.status_code == 403


def test_logout_with_bearer_no_browser_origin_clears(client_with_pin):
    """Bearer-from-CLI (no Origin / Sec-Fetch-Site) → logout works
    without CSRF. Covers bulk_upload_to_render.py edge cases."""
    resp = client_with_pin.post(
        "/api/logout", headers={"Authorization": f"Bearer {SECRET}"}
    )
    assert resp.status_code == 200
    assert "Max-Age=0" in resp.headers.get("Set-Cookie", "")


def test_logout_no_auth_at_all_is_idempotent(client_with_pin):
    """Stale client trying to "clean up" with neither cookie nor Bearer
    must not 401-loop. Returns 200 + Set-Cookie clear so the contract
    "no jobscout_session after logout" holds defensively."""
    # Fresh test client — no cookie jar, no previous login.
    import server
    with server.app.test_client() as fresh:
        resp = fresh.post("/api/logout")
        assert resp.status_code == 200
        assert "Max-Age=0" in resp.headers.get("Set-Cookie", "")


# ─── Bearer-from-browser Origin guard (systemic miss B) ───────────────────


def test_bearer_without_origin_passes(client_with_pin, monkeypatch):
    """Pure CLI caller (Python requests / curl) → no Origin / Sec-Fetch-
    Site header → must pass. This is the bulk_upload_to_render.py path."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://dashboard.example.com")
    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        headers={"Authorization": f"Bearer {SECRET}"},
        data={
            "company": "TestCo", "role": "DE",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    # NOT 401 / 403 — the legitimate machine-to-machine path.
    assert resp.status_code not in {401, 403}


def test_bearer_from_allowed_origin_passes(client_with_pin, monkeypatch):
    """Dashboard's own Bearer request (Origin in allowlist) → pass.
    Pre-fix this was unconditional; post-fix we explicitly verify the
    matching-origin branch."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://dashboard.example.com")
    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        headers={
            "Authorization": f"Bearer {SECRET}",
            "Origin": "https://dashboard.example.com",
        },
        data={
            "company": "TestCo", "role": "DE",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code not in {401, 403}


def test_bearer_from_blocked_origin_returns_403(client_with_pin, monkeypatch):
    """The core fix: an XSS that read localStorage["vault_token"] and
    forges a Bearer request from a hostile site will carry the hostile
    Origin. Reject."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://dashboard.example.com")
    from io import BytesIO
    resp = client_with_pin.post(
        "/api/vault/upload",
        headers={
            "Authorization": f"Bearer {SECRET}",
            "Origin": "https://attacker.example.com",
        },
        data={
            "company": "TestCo", "role": "DE",
            "file": (BytesIO(_MIN_PDF), "test.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "origin_not_allowed"


def test_bearer_from_browser_no_allowlist_warns_but_allows(
    client_with_pin, monkeypatch, caplog
):
    """When ALLOWED_ORIGINS is unset (single-origin dev / pre-prod
    deploy), the guard degrades to warn-but-allow so existing setups
    don't break. Operators get a one-time log line to fix it."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    # Reset the one-time-warn flag so this test gets a fresh log line.
    from routes import _auth
    _auth._bearer_request_is_safe._warned_no_allowlist = False

    from io import BytesIO
    with caplog.at_level("WARNING"):
        resp = client_with_pin.post(
            "/api/vault/upload",
            headers={
                "Authorization": f"Bearer {SECRET}",
                "Origin": "https://anywhere.example.com",
            },
            data={
                "company": "TestCo", "role": "DE",
                "file": (BytesIO(_MIN_PDF), "test.pdf"),
            },
            content_type="multipart/form-data",
        )
    # Request goes through.
    assert resp.status_code not in {401, 403}
    # Warning emitted.
    assert any(
        "ALLOWED_ORIGINS is unset" in r.getMessage() for r in caplog.records
    ), "expected one-time warn log; got: " + repr([r.getMessage() for r in caplog.records])


def test_bearer_safe_method_with_blocked_origin_still_allowed(
    client_with_pin, monkeypatch
):
    """Safe methods (GET / HEAD / OPTIONS) can't be weaponised for state
    changes; the Origin guard explicitly exempts them so a malicious
    Origin reading public data still works (and isn't a security issue —
    the data is public)."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://dashboard.example.com")
    resp = client_with_pin.get(
        "/api/vault/list",
        headers={
            "Authorization": f"Bearer {SECRET}",
            "Origin": "https://attacker.example.com",
        },
    )
    assert resp.status_code not in {401, 403}
