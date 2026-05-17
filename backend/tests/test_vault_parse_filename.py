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
