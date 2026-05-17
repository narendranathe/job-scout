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
    set_pin("1234", os.environ["DB_PATH"])
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


def test_login_when_no_pin_set_succeeds(client):
    """Fresh install: no PIN means login is a no-op that still mints a session."""
    resp = client.post("/api/login", json={"pin": ""})
    assert resp.status_code == 200
    assert "jobscout_session=" in resp.headers.get("Set-Cookie", "")


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
