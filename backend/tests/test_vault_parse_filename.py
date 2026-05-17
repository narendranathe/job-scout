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


# ---------------------------------------------------------------------------
# Hardening tests — Bug A (exception trap) + Bug B (concurrency cap)
# Attempt B: semaphore-based concurrency limit + structured error trap.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_semaphore_between_tests():
    """Make sure no test leaves a saturated semaphore behind.

    Each test that touches ``_parse_filename_semaphore`` should start
    from a fresh (fully available) bucket; without this autouse fixture
    a test that drains the cap could poison every subsequent test.
    """
    yield
    try:
        from routes import vault_routes
        vault_routes._reset_parse_filename_semaphore()
    except Exception:
        # If the module isn't loaded yet (e.g. very first run), no-op.
        pass


def test_parse_filename_exception_returns_400_not_500(client, monkeypatch):
    """Bug A — parser raising TypeError/ValueError → 400, not 500.

    Stub the parser to raise so we test the *route's* exception trap
    independent of which specific inputs trip the real parser today.
    """
    from routes import vault_routes

    def boom(_fn):
        raise TypeError("expected str, bytes or os.PathLike, not NoneType")

    monkeypatch.setattr(
        "storage.resume_vault.parse_resume_filename", boom
    )
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 400, (
        f"expected 400 from trapped exception, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)[:200]}"
    )
    body = resp.get_json()
    assert body.get("error") == "could not parse filename"


def test_parse_filename_exception_does_not_leak_internals(client, monkeypatch):
    """Bug A (part 2) — never echo the raw exception message.

    The parser's exception text can include file paths and traceback
    fragments; the route's job is to give the wizard a clean 400.
    """
    def boom(_fn):
        raise ValueError("/opt/render/project/secret.txt no such file")

    monkeypatch.setattr(
        "storage.resume_vault.parse_resume_filename", boom
    )
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "foo.pdf"},
    )
    assert resp.status_code == 400
    body_text = resp.get_data(as_text=True)
    assert "secret.txt" not in body_text
    assert "/opt/render" not in body_text


def test_parse_filename_exception_does_not_leak_partial_parse(client, monkeypatch):
    """Bug A (part 3) — never return partial parsed-so-far fields.

    A half-guessed company name would mislead the wizard preview
    ("looks like a Goldman Sachs resume!" for what's actually junk).
    """
    def boom(_fn):
        raise IndexError("list index out of range")

    monkeypatch.setattr(
        "storage.resume_vault.parse_resume_filename", boom
    )
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    body = resp.get_json()
    # The structured 400 may echo the original filename back (helpful
    # for client-side error display), but MUST NOT include any parsed
    # fields that would look authoritative.
    for forbidden in ("company", "role", "version_key", "display_name"):
        assert forbidden not in body, (
            f"leaked parsed-so-far field {forbidden}: {body}"
        )


def test_parse_filename_semaphore_releases_after_success(client):
    """Bug B side-effect — N successful calls in a row don't exhaust the cap.

    Without ``finally: release()`` the cap would shrink by one per
    request and lock the endpoint within N calls.
    """
    from routes import vault_routes
    # Force cap=2 so a leaked lease would obviously break by call 3.
    vault_routes._reset_parse_filename_semaphore(max_concurrent=2)
    for i in range(10):
        resp = client.post(
            "/api/vault/parse-filename",
            json={"filename": f"Narendranath_GS_DE_{i}.pdf"},
        )
        assert resp.status_code == 200, (
            f"semaphore appears to be leaking — call {i} got "
            f"{resp.status_code}"
        )


def test_parse_filename_semaphore_releases_after_exception(client, monkeypatch):
    """Bug B side-effect — exception path must also release the lease.

    Otherwise an attacker who knows how to trip the parser (Bug A)
    could exhaust the cap in N calls.
    """
    from routes import vault_routes
    vault_routes._reset_parse_filename_semaphore(max_concurrent=1)

    def boom(_fn):
        raise TypeError("synthetic")
    monkeypatch.setattr(
        "storage.resume_vault.parse_resume_filename", boom
    )

    for i in range(5):
        resp = client.post(
            "/api/vault/parse-filename",
            json={"filename": f"x_{i}.pdf"},
        )
        # Exception path returns 400, but the semaphore must release.
        assert resp.status_code == 400, (
            f"call {i} unexpected status {resp.status_code}"
        )


def test_parse_filename_concurrency_cap_rejects_with_503(client):
    """Bug B — when the cap is saturated, return 503 + Retry-After.

    We drain the semaphore manually (no need to spawn real threads —
    the route uses ``acquire(blocking=False)`` so a single held lease
    is enough to trigger the 503 branch deterministically).
    """
    from routes import vault_routes
    vault_routes._reset_parse_filename_semaphore(max_concurrent=1)

    # Drain the single slot — the next request will hit the 503 branch.
    acquired = vault_routes._parse_filename_semaphore.acquire(blocking=False)
    assert acquired, "test setup: expected to grab the only slot"
    try:
        resp = client.post(
            "/api/vault/parse-filename",
            json={"filename": "Narendranath_GS_DE.pdf"},
        )
        assert resp.status_code == 503, (
            f"expected 503 when cap saturated, got {resp.status_code}"
        )
        body = resp.get_json()
        assert "busy" in body.get("error", "").lower()
        assert "Retry-After" in resp.headers
        # Retry-After must be a non-negative integer per RFC 7231.
        retry_after = int(resp.headers["Retry-After"])
        assert retry_after >= 0
    finally:
        # Always release the manual lease so other tests aren't affected.
        vault_routes._parse_filename_semaphore.release()


def test_parse_filename_cap_recovers_after_release(client):
    """Bug B — after the drained slot is released, requests succeed again."""
    from routes import vault_routes
    vault_routes._reset_parse_filename_semaphore(max_concurrent=1)

    # 1) Saturate.
    vault_routes._parse_filename_semaphore.acquire(blocking=False)
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 503

    # 2) Release.
    vault_routes._parse_filename_semaphore.release()

    # 3) Should be 200 again.
    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 200


def test_parse_filename_bad_body_does_not_consume_slot(client):
    """Bug B detail — body-validation 400s happen *before* semaphore acquire.

    Otherwise a flood of empty-body requests could indirectly saturate
    the cap (we acquire → validate → reject) and lock out legitimate
    callers. The route validates first, then acquires.
    """
    from routes import vault_routes
    vault_routes._reset_parse_filename_semaphore(max_concurrent=1)

    # Bombard with malformed bodies. Each must be 400 and must NOT
    # consume the semaphore slot — so a real request still succeeds.
    for _ in range(20):
        resp = client.post("/api/vault/parse-filename", json={"filename": ""})
        assert resp.status_code == 400

    resp = client.post(
        "/api/vault/parse-filename",
        json={"filename": "Narendranath_GS_DE.pdf"},
    )
    assert resp.status_code == 200, (
        "validation rejects appear to be consuming the concurrency slot"
    )


def test_parse_filename_503_includes_retry_after_seconds_in_body(client):
    """Bug B — body carries machine-readable retry_after for fetch clients."""
    from routes import vault_routes
    vault_routes._reset_parse_filename_semaphore(max_concurrent=1)
    vault_routes._parse_filename_semaphore.acquire(blocking=False)
    try:
        resp = client.post(
            "/api/vault/parse-filename",
            json={"filename": "x.pdf"},
        )
        assert resp.status_code == 503
        body = resp.get_json()
        assert isinstance(body.get("retry_after"), int)
        assert body["retry_after"] >= 0
    finally:
        vault_routes._parse_filename_semaphore.release()
