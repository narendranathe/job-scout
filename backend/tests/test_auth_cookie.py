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

    # Drop the in-memory setup-epoch cache so a stale value from a
    # previous test (which used a different DB_PATH) doesn't reject
    # setup cookies issued under this fixture's fresh DB.
    from routes._auth import reset_setup_epoch_cache
    reset_setup_epoch_cache()

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
    """Fresh install: no PIN means login still mints a session — but a
    scope-limited one. The wizard needs the cookie to walk through Steps
    1-5; we just refuse to give it full-app powers until /api/set-pin
    has run.
    """
    resp = client.post("/api/login", json={"pin": ""})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["scope"] == "setup", (
        "fresh-install login must return a setup-scope cookie, not a "
        "full-power one (CVE-style privilege-escalation regression)"
    )
    assert "jobscout_session=" in resp.headers.get("Set-Cookie", "")


# ─── Regression: no-PIN privilege escalation ──────────────────────────────

def test_no_pin_login_cookie_cannot_touch_vault_writes(client):
    """REGRESSION: pre-fix, /api/login with no PIN minted a full 30-day
    session that could call every gated endpoint. Now the setup-scope
    cookie should be rejected with ``setup_scope_insufficient`` on
    routes outside the narrow wizard allowlist.

    Allowlist routes (/api/profile POST, /api/set-pin, /api/vault/upload,
    /api/vault/parse-filename, /api/vault/list, /api/vault/stats) are
    covered by their own positive-path tests below. We pick
    ``/api/vault/import`` and ``/api/vault/best-match`` as the
    out-of-scope probes — both are real attack surface (bulk import
    overwrites the vault; best-match exfiltrates whatever resumes the
    server has) and both flow through the unified ``require_auth`` hook.
    """
    # Get the no-PIN setup cookie.
    resp = client.post("/api/login", json={"pin": ""})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["scope"] == "setup"
    csrf = body["csrf_token"]

    # /api/vault/import — bulk import is not on the setup allowlist.
    resp = client.post(
        "/api/vault/import",
        json={"directory": "/etc"},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert resp.status_code == 403, (
        f"setup-scope cookie reached /api/vault/import (got "
        f"{resp.status_code}); the privilege-escalation vuln is back"
    )
    assert resp.get_json().get("error") == "setup_scope_insufficient"

    # /api/vault/best-match — exfiltration probe; also not allowlisted.
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "x" * 100},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert resp.status_code == 403
    assert resp.get_json().get("error") == "setup_scope_insufficient"


def test_setup_cookie_invalidated_after_set_pin(client):
    """Once a PIN is set, every outstanding setup cookie must stop
    working. The legitimate user (or an attacker, in the race scenario)
    has to call /api/login again with the new PIN to get back in.
    """
    # 1. Mint a setup cookie pre-PIN.
    resp = client.post("/api/login", json={"pin": ""})
    assert resp.status_code == 200
    csrf = resp.get_json()["csrf_token"]

    # 2. Use the cookie to set a PIN (this is the legitimate flow).
    resp = client.post(
        "/api/set-pin",
        json={"pin": "9999"},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    # 3. Same cookie should now be rejected on the very next request,
    # even on an allowlisted path — the epoch advanced past iat.
    resp = client.get("/api/vault/list")
    assert resp.status_code == 401, (
        "setup cookie survived /api/set-pin; epoch invalidation is broken"
    )

    # 4. Logging in with the new PIN issues a full-scope cookie.
    resp = client.post("/api/login", json={"pin": "9999"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["scope"] == "full"


def test_setup_cookie_allows_pin_set_and_profile_update(client):
    """Positive path: the wizard's actual happy-path calls must succeed
    on the setup cookie. /api/profile POST and /api/set-pin are the two
    that are strictly required to get out of setup mode.
    """
    resp = client.post("/api/login", json={"pin": ""})
    csrf = resp.get_json()["csrf_token"]

    # /api/profile POST — wizard Steps 2/3/4 persist roles, companies, etc.
    resp = client.post(
        "/api/profile",
        json={"dream_companies": ["Anthropic", "OpenAI"]},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, (
        f"setup-scope cookie should allow /api/profile POST (got "
        f"{resp.status_code} {resp.get_data(as_text=True)[:200]})"
    )

    # /api/set-pin — wizard Step 6 ends setup phase.
    resp = client.post(
        "/api/set-pin",
        json={"pin": "1234"},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, (
        f"setup-scope cookie should allow /api/set-pin (got "
        f"{resp.status_code} {resp.get_data(as_text=True)[:200]})"
    )


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
