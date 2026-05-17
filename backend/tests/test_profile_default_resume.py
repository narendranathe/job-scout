"""Tests for default_resume_version on user_profile (Issue #39 part A).

Covers:
- column migration in init_profile_tables (idempotent)
- GET /api/profile returns default_resume_version (None when never set)
- POST /api/profile rejects unknown version keys with 400
- POST /api/profile accepts a valid version key and round-trips it
- POST /api/profile clears the default when given null/empty string
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    from storage.db import init_db
    init_db(db_path)
    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    # profile_manager caches DB_PATH from os.environ at import-time, so we
    # also patch its module-level so update_profile() hits the temp DB.
    from storage import profile_manager as pm
    pm.DB_PATH = db_path
    with server.app.test_client() as c:
        yield c
    importlib.reload(server)


def _seed_version(db_path, version_key="data-eng-v1", display_name="Data Eng v1"):
    """Insert a resume_versions row so default_resume_version can point at it."""
    from storage.db import get_conn, upsert_resume_version
    conn = get_conn(db_path)
    upsert_resume_version(conn, version_key, display_name, "python sql spark")
    conn.commit()
    conn.close()


def test_init_profile_adds_default_resume_version_column(tmp_path):
    """Migration runs on a pre-existing DB without the column."""
    import sqlite3
    db_path = str(tmp_path / "legacy.db")
    # Create the OLD schema (no default_resume_version column).
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE user_profile (
            id INTEGER PRIMARY KEY,
            pin_hash TEXT DEFAULT '',
            resume_text TEXT DEFAULT '',
            extracted_skills TEXT DEFAULT '[]',
            custom_skills TEXT DEFAULT '[]',
            preferred_locations TEXT DEFAULT '[]',
            dream_companies TEXT DEFAULT '[]',
            dream_role_keywords TEXT DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.execute("INSERT INTO user_profile (id) VALUES (1)")
    conn.commit()
    conn.close()

    from storage.profile_manager import init_profile_tables
    init_profile_tables(db_path)
    # Idempotent: calling twice must not raise.
    init_profile_tables(db_path)

    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(user_profile)").fetchall()]
    conn.close()
    assert "default_resume_version" in cols


def test_get_profile_includes_default_resume_version_null(client):
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "default_resume_version" in data
    assert data["default_resume_version"] is None


def test_post_profile_rejects_unknown_default(client):
    resp = client.post("/api/profile", json={"default_resume_version": "does-not-exist"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert "not found" in body.get("error", "").lower()


def test_post_profile_sets_valid_default(client):
    import server
    _seed_version(server.DB_PATH, "data-eng-v1")

    resp = client.post("/api/profile", json={"default_resume_version": "data-eng-v1"})
    assert resp.status_code == 200

    g = client.get("/api/profile")
    assert g.status_code == 200
    assert g.get_json().get("default_resume_version") == "data-eng-v1"


def test_post_profile_clears_default_with_null(client):
    import server
    _seed_version(server.DB_PATH, "data-eng-v1")
    client.post("/api/profile", json={"default_resume_version": "data-eng-v1"})

    # Empty string → cleared
    resp = client.post("/api/profile", json={"default_resume_version": ""})
    assert resp.status_code == 200
    g = client.get("/api/profile")
    assert g.get_json().get("default_resume_version") is None

    # Re-set then clear with null
    client.post("/api/profile", json={"default_resume_version": "data-eng-v1"})
    resp = client.post("/api/profile", json={"default_resume_version": None})
    assert resp.status_code == 200
    g = client.get("/api/profile")
    assert g.get_json().get("default_resume_version") is None


def test_post_profile_rejects_non_string_default(client):
    resp = client.post("/api/profile", json={"default_resume_version": 12345})
    assert resp.status_code == 400


def test_post_profile_other_fields_still_work(client):
    """Regression: existing whitelist fields still update normally."""
    resp = client.post("/api/profile", json={
        "custom_skills": ["rust", "wasm"],
        "preferred_locations": ["remote"],
    })
    assert resp.status_code == 200
    g = client.get("/api/profile").get_json()
    assert g.get("custom_skills") == ["rust", "wasm"]
    assert g.get("preferred_locations") == ["remote"]
