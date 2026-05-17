"""Tests for /api/vault/parse-filename — the wizard's drag-drop preview.

PRD #89 Slice 3. Three things must hold:

1. No auth required (the wizard runs this before login).
2. Returns the same shape as ``parse_resume_filename()``.
3. Empty + oversize inputs return 400 (cheap validation).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SECRET = "test-secret-xyz"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(vault_dir, exist_ok=True)

    from storage.db import init_db
    from storage.profile_manager import init_profile_tables
    init_db(db_path)
    init_profile_tables(db_path)

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("API_SECRET", SECRET)
    monkeypatch.setenv("VAULT_DIR", vault_dir)

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


def test_parse_filename_no_auth_required(client):
    """No Authorization header → still 200. Key acceptance criterion."""
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 200, (
        f"unauthenticated request rejected: {resp.status_code} "
        f"{resp.get_data(as_text=True)[:200]}"
    )


def test_parse_filename_returns_company_and_role(client):
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    data = resp.get_json()
    assert data["company"] == "Goldman Sachs"
    assert data["role"] == "Data Engineer"


def test_parse_filename_returns_expected_keys(client):
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_Meta_MLE.pdf"},
    )
    data = resp.get_json()
    for k in ("original_filename", "company", "role", "version_key",
              "display_name", "extension"):
        assert k in data, f"missing key {k}: {data}"


def test_parse_filename_rejects_empty(client):
    resp = client.post("/api/vault/parse-filename", json={"filename": ""})
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"].lower()


def test_parse_filename_rejects_missing_field(client):
    resp = client.post("/api/vault/parse-filename", json={})
    assert resp.status_code == 400


def test_parse_filename_rejects_whitespace_only(client):
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "    "},
    )
    assert resp.status_code == 400


def test_parse_filename_rejects_oversize_input(client):
    huge = "A" * 300 + ".pdf"
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": huge},
    )
    assert resp.status_code == 400
    assert "too long" in resp.get_json()["error"].lower()


def test_parse_filename_handles_257_chars_rejected(client):
    """Boundary: 257 chars rejected, 256 accepted."""
    just_over = "A" * 253 + ".pdf"  # 257 chars total
    assert len(just_over) == 257
    resp = client.post("/api/vault/parse-filename", json={"filename": just_over})
    assert resp.status_code == 400


def test_parse_filename_with_bearer_token_also_works(client):
    """Bearer auth shouldn't be rejected either — the gate is just open."""
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_Meta_MLE.pdf"},
        headers={"Authorization": f"Bearer {SECRET}"},
    )
    assert resp.status_code == 200


def test_parse_filename_options_passes(client):
    """OPTIONS preflight returns 200."""
    resp = client.open("/api/vault/parse-filename", method="OPTIONS")
    assert resp.status_code in (200, 204)


# --------------------------------------------------------------------------
# Hardening regression tests (Attempt A).
# Bug A: parse_resume_filename() now wrapped in try/except → 400, not 500.
# Bug B(i): JSON body >4 KB → 413 before any decoding.
# Bug B(ii): >30 req/60s per IP → 429.
# --------------------------------------------------------------------------


def test_parse_filename_parser_exception_returns_400_not_500(client, monkeypatch):
    """Bug A: if parse_resume_filename() raises (regex blowup, IndexError,
    etc.) we MUST return a generic 400 — never a 500 with a traceback that
    leaks internal paths.

    We monkeypatch the parser to raise; the endpoint should catch the
    exception, log it server-side, and return 400 with a generic message
    that does NOT include the exception text.
    """
    from storage import resume_vault as rv_mod
    from routes import vault_routes  # ensure rate-limit helpers are loaded

    # Reset rate limiter so this test isn't polluted by prior calls.
    vault_routes._reset_parse_filename_rate_limiter()

    def boom(_):
        raise IndexError("string index out of range /opt/render/project/secret/path")

    monkeypatch.setattr(rv_mod, "parse_resume_filename", boom)

    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 400, (
        f"expected 400, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)[:200]}"
    )
    body = resp.get_json()
    assert "error" in body
    # Generic error — must NOT leak the underlying exception text or paths.
    assert "could not parse" in body["error"].lower()
    assert "/opt/render" not in body["error"]
    assert "IndexError" not in body["error"]
    assert "string index" not in body["error"]


def test_parse_filename_rejects_oversize_body_413(client):
    """Bug B(i): JSON body larger than PARSE_FILENAME_MAX_BODY_BYTES (4 KB)
    must be rejected with 413 — before any parsing. The handler's own
    256-char filename cap can't help; we have to bounce the request at
    the size gate, otherwise an attacker can send megabytes of junk
    around a tiny filename field.
    """
    from routes import vault_routes
    vault_routes._reset_parse_filename_rate_limiter()

    # Build a payload bigger than 4 KB. The filename itself is short; a
    # padding field carries the bulk. The endpoint cares about *total
    # body size*, not just the filename length.
    payload = {"filename": "x.pdf", "padding": "A" * 10_000}
    resp = client.post("/api/vault/parse-filename", json=payload)
    assert resp.status_code == 413, (
        f"expected 413, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)[:200]}"
    )
    body = resp.get_json()
    assert "too large" in body["error"].lower()


def test_parse_filename_rate_limit_returns_429(client):
    """Bug B(ii): per-IP token bucket. First N requests succeed; request
    N+1 from the same IP within the window returns 429.

    Werkzeug's test client always uses ``127.0.0.1`` as remote_addr so
    every call lands in the same bucket — exactly what we want to
    exercise.
    """
    from routes import vault_routes

    # Start with a fresh limiter so the first PARSE_FILENAME_RATE_PER_MIN
    # requests all succeed.
    vault_routes._reset_parse_filename_rate_limiter()

    limit = vault_routes.PARSE_FILENAME_RATE_PER_MIN
    accepted = 0
    for _ in range(limit):
        resp = client.post(
            "/api/vault/parse-filename",
            json={"filename": "Narendranath_GS_DE.pdf"},
        )
        # All of the first `limit` requests should be accepted (200).
        assert resp.status_code == 200, (
            f"unexpected non-200 within budget: {resp.status_code}"
        )
        accepted += 1
    assert accepted == limit

    # One more request → over the budget → 429.
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 429, (
        f"expected 429 after exhausting budget, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)[:200]}"
    )
    body = resp.get_json()
    assert "rate limit" in body["error"].lower()

    # Cleanup so later tests in the file aren't affected.
    vault_routes._reset_parse_filename_rate_limiter()


def test_parse_filename_rate_limit_window_resets(monkeypatch):
    """After the sliding window expires (60s by default) the bucket is
    refilled — we simulate this by monkeypatching ``time.monotonic`` in
    the rate-limiter module, exhausting the budget, then jumping forward.
    """
    from routes import vault_routes

    fake_now = [10_000.0]

    def fake_monotonic():
        return fake_now[0]

    monkeypatch.setattr(vault_routes.time, "monotonic", fake_monotonic)
    vault_routes._reset_parse_filename_rate_limiter()

    # Fill the bucket exactly to the cap.
    for _ in range(vault_routes.PARSE_FILENAME_RATE_PER_MIN):
        ok = vault_routes._parse_filename_rate_check("1.2.3.4")
        assert ok is True
    # Next call inside the window should fail.
    assert vault_routes._parse_filename_rate_check("1.2.3.4") is False

    # Jump the clock forward past the window.
    fake_now[0] += vault_routes.PARSE_FILENAME_WINDOW_SEC + 1.0
    # Bucket should be empty again → allowed.
    assert vault_routes._parse_filename_rate_check("1.2.3.4") is True

    vault_routes._reset_parse_filename_rate_limiter()


def test_parse_filename_rate_limit_per_ip_isolation(monkeypatch):
    """One IP exhausting its budget must NOT lock out other IPs — that's
    the whole point of per-IP keying. Unit-test the limiter directly so
    we don't have to spoof remote_addr on the Werkzeug test client.
    """
    from routes import vault_routes

    fake_now = [42.0]
    monkeypatch.setattr(vault_routes.time, "monotonic", lambda: fake_now[0])
    vault_routes._reset_parse_filename_rate_limiter()

    # IP "A" exhausts its budget.
    for _ in range(vault_routes.PARSE_FILENAME_RATE_PER_MIN):
        assert vault_routes._parse_filename_rate_check("10.0.0.1") is True
    assert vault_routes._parse_filename_rate_check("10.0.0.1") is False

    # IP "B" must still be allowed — totally independent bucket.
    assert vault_routes._parse_filename_rate_check("10.0.0.2") is True

    vault_routes._reset_parse_filename_rate_limiter()
