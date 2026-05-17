"""Tests for issue #44: /api/resume/versions/<key> DELETE consistency.

Before #44, the legacy ``/api/resume/versions/<key>`` DELETE only removed
the DB row, orphaning the PDF + text files on disk — entries resurrected
on the next vault refresh because ``list_vault()`` scans disk. The sibling
``/api/vault/version/<key>`` DELETE was already fixed in #37 to clean up
all three.

These tests prove both endpoints now share identical behavior on
identical input (cleans up everything; idempotent for retries; rejects
malformed keys), routed through the same ``delete_vault_version`` helper.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client with isolated DB + isolated vault directory.

    Mirrors test_vault_delete.py's fixture so both endpoints can be exercised
    against the same seeded state.
    """
    db_path = str(tmp_path / "test.db")
    vault_dir = tmp_path / "vault"
    (vault_dir / "pdf").mkdir(parents=True)
    (vault_dir / "text").mkdir(parents=True)

    from storage.db import init_db
    init_db(db_path)

    import storage.resume_vault as rv_mod
    monkeypatch.setattr(rv_mod, "VAULT_DIR", str(vault_dir))

    import routes.vault_routes as vr_mod
    monkeypatch.setattr(vr_mod, "DB_PATH", db_path)
    monkeypatch.setattr(vr_mod, "API_SECRET", "", raising=False)

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True

    with server.app.test_client() as c:
        c._test_db_path = db_path
        c._test_vault_dir = str(vault_dir)
        yield c

    importlib.reload(server)


def _seed_version(client, version_key="goldman_sachs_data"):
    """Seed a complete vault entry: DB row + PDF on disk + text cache."""
    from storage.db import get_conn, upsert_resume_version
    from storage.resume_vault import parse_resume_filename

    conn = get_conn(client._test_db_path)
    upsert_resume_version(
        conn,
        version_key=version_key,
        display_name="Goldman Sachs",
        resume_text="Python SQL Spark data engineer.",
        skills=["python", "sql", "spark"],
        target_companies=["Goldman Sachs"],
    )
    conn.commit()
    conn.close()

    pdf_filename = f"Narendranath_{version_key}.pdf"
    parsed = parse_resume_filename(pdf_filename)["version_key"]
    assert parsed == version_key, (
        f"Test fixture mismatch: {pdf_filename!r} parses to {parsed!r}, "
        f"expected {version_key!r}"
    )

    pdf_path = os.path.join(client._test_vault_dir, "pdf", pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\nfake pdf bytes\n%%EOF\n")

    text_path = os.path.join(client._test_vault_dir, "text", f"{version_key}.txt")
    with open(text_path, "w") as f:
        f.write("Python SQL Spark data engineer.")

    return {"pdf_path": pdf_path, "text_path": text_path}


def _row_exists(client, version_key):
    from storage.db import get_conn, get_resume_version
    conn = get_conn(client._test_db_path)
    rv = get_resume_version(conn, version_key)
    conn.close()
    return rv is not None


# ─────────────────────────────────────────────────────────────────────
#  Core fix: PDF + text + DB row all removed (was: only DB row)
# ─────────────────────────────────────────────────────────────────────

def test_legacy_delete_removes_pdf_text_and_db_row(client):
    """The whole point of #44: legacy endpoint must clean up disk too."""
    paths = _seed_version(client, version_key="goldman_sachs_data")
    assert os.path.exists(paths["pdf_path"])
    assert os.path.exists(paths["text_path"])
    assert _row_exists(client, "goldman_sachs_data")

    resp = client.delete("/api/resume/versions/goldman_sachs_data")
    assert resp.status_code == 200

    # All three artifacts gone — this was the bug.
    assert not os.path.exists(paths["pdf_path"]), \
        "PDF file leaked on disk — issue #44 not fixed"
    assert not os.path.exists(paths["text_path"]), \
        "text cache leaked on disk — issue #44 not fixed"
    assert not _row_exists(client, "goldman_sachs_data")


def test_legacy_delete_response_shape_matches_vault_delete(client):
    """Same fields, same casing — both endpoints should return identical shapes
    for the same input, since they route through the same helper."""
    _seed_version(client, version_key="meta_ml")
    legacy = client.delete("/api/resume/versions/meta_ml")
    assert legacy.status_code == 200
    body = legacy.get_json()
    # These keys are exactly what /api/vault/version/<key> returns post-#37.
    assert body["status"] == "deleted"
    assert body["version_key"] == "meta_ml"
    assert body["db_row_deleted"] is True
    assert body["pdf_deleted"] is True
    assert body["text_deleted"] is True
    assert body["pdf_filename"] == "Narendranath_meta_ml.pdf"
    # No absolute paths leaked.
    assert "pdf_path" not in body
    assert "text_path" not in body


# ─────────────────────────────────────────────────────────────────────
#  Idempotency: retried DELETE on already-gone version
# ─────────────────────────────────────────────────────────────────────

def test_legacy_delete_idempotent_when_already_gone(client):
    """Retried DELETE on a missing version → 200 with already_gone:true.

    Same contract as the vault endpoint — DELETE's post-condition is
    'resource does not exist', so a never-existed key satisfies it.
    """
    resp = client.delete("/api/resume/versions/never_existed")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["already_gone"] is True
    assert body["db_row_deleted"] is False
    assert body["pdf_deleted"] is False


# ─────────────────────────────────────────────────────────────────────
#  Malformed keys rejected at the route, not the storage layer
# ─────────────────────────────────────────────────────────────────────

# Two layers of rejection: Flask's <string:> URL converter refuses keys
# containing "/", returning 404 at the routing layer before our handler runs.
# Keys without "/" reach the handler and get rejected with 400. Both stop
# the attack — we just test the route they take is the one we expect.

@pytest.mark.parametrize("bad_key", [
    "..",            # bare ".." — reaches handler
    "foo\\bar",      # backslash — reaches handler
    "foo\x00bar",    # null byte — reaches handler
])
def test_legacy_delete_rejects_malformed_keys_at_handler(client, bad_key):
    """Path-traversal keys without "/" hit our handler and get 400."""
    from urllib.parse import quote
    resp = client.delete(f"/api/resume/versions/{quote(bad_key, safe='')}")
    assert resp.status_code == 400, f"{bad_key!r} should be rejected with 400"
    body = resp.get_json()
    assert "version_key" in body["error"].lower() or "invalid" in body["error"].lower()


@pytest.mark.parametrize("bad_key", [
    "../etc/passwd",  # contains "/"
    "foo/../bar",     # contains "/"
])
def test_legacy_delete_slash_keys_blocked_by_flask_router(client, bad_key):
    """Keys with "/" are stopped by Flask's <string:> converter before
    reaching our code (404 routing miss). Different status code, same
    practical outcome — the attack never lands."""
    from urllib.parse import quote
    resp = client.delete(f"/api/resume/versions/{quote(bad_key, safe='')}")
    # The URL splits at the encoded /, so Flask routes it to a non-existent
    # path → 404. We just confirm the request doesn't succeed.
    assert resp.status_code in (404, 405, 400), \
        f"{bad_key!r} unexpectedly returned {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────
#  Regression: the function deleted from profile_manager stays deleted
# ─────────────────────────────────────────────────────────────────────

def test_legacy_profile_manager_delete_helper_removed():
    """profile_manager.delete_resume_version was the bug — make sure no one
    accidentally re-adds it without routing through delete_vault_version."""
    import storage.profile_manager as pm
    assert not hasattr(pm, "delete_resume_version"), (
        "profile_manager.delete_resume_version was removed in #44. "
        "If a new caller needs to delete a vault version, use "
        "storage.resume_vault.delete_vault_version which cleans up "
        "the PDF + text + DB row together."
    )
