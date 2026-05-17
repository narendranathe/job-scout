"""Tests for vault delete endpoint (issue #37) (DELETE /api/vault/version/<key>).

Covers the issue-#37 fix: delete now removes the PDF + text file from the
filesystem in addition to the DB row, so list_vault() (which scans the disk)
no longer resurrects the entry on next refresh.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client with isolated DB + isolated vault directory."""
    db_path = str(tmp_path / "test.db")
    vault_dir = tmp_path / "vault"
    (vault_dir / "pdf").mkdir(parents=True)
    (vault_dir / "text").mkdir(parents=True)

    from storage.db import init_db
    init_db(db_path)

    # Patch vault dir + route DB path
    import storage.resume_vault as rv_mod
    monkeypatch.setattr(rv_mod, "VAULT_DIR", str(vault_dir))

    import routes.vault_routes as vr_mod
    monkeypatch.setattr(vr_mod, "DB_PATH", db_path)
    # Disable any auth gate if a sibling branch added one (issue-#34).
    monkeypatch.setattr(vr_mod, "API_SECRET", "", raising=False)

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True

    with server.app.test_client() as c:
        c._test_db_path = db_path
        c._test_vault_dir = str(vault_dir)
        yield c

    importlib.reload(server)


def _seed_version(client, version_key="goldman_sachs_data",
                   display_name="Goldman Sachs",
                   create_pdf=True, create_text=True, pdf_filename=None):
    """Create a vault entry: DB row + optionally PDF + text files.

    Picks a PDF filename that round-trips through parse_resume_filename to
    the supplied version_key — that's how list_vault() links files to keys.
    """
    from storage.db import get_conn, upsert_resume_version
    from storage.resume_vault import parse_resume_filename

    conn = get_conn(client._test_db_path)
    upsert_resume_version(
        conn,
        version_key=version_key,
        display_name=display_name,
        resume_text="Python SQL Spark data engineer experience.",
        skills=["python", "sql", "spark"],
        target_companies=["Goldman Sachs"],
    )
    conn.commit()
    conn.close()

    pdf_path = None
    if create_pdf:
        if pdf_filename is None:
            pdf_filename = f"Narendranath_{version_key}.pdf"
            assert parse_resume_filename(pdf_filename)["version_key"] == version_key, (
                f"Test fixture mismatch: {pdf_filename!r} parses to "
                f"{parse_resume_filename(pdf_filename)['version_key']!r}, "
                f"expected {version_key!r}"
            )
        pdf_path = os.path.join(client._test_vault_dir, "pdf", pdf_filename)
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\nfake pdf bytes\n%%EOF\n")

    text_path = None
    if create_text:
        text_path = os.path.join(client._test_vault_dir, "text", f"{version_key}.txt")
        with open(text_path, "w") as f:
            f.write("Python SQL Spark data engineer experience.")

    return {"pdf_path": pdf_path, "text_path": text_path}


# ─────────────────────────────────────────────────────────────────────
#  Happy path: full delete
# ─────────────────────────────────────────────────────────────────────

def test_delete_removes_pdf_text_and_db_row(client):
    paths = _seed_version(client, version_key="goldman_sachs_data")
    assert os.path.exists(paths["pdf_path"])
    assert os.path.exists(paths["text_path"])

    resp = client.delete("/api/vault/version/goldman_sachs_data")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "deleted"
    assert body["version_key"] == "goldman_sachs_data"
    assert body["pdf_deleted"] is True
    assert body["text_deleted"] is True
    assert body["db_row_deleted"] is True

    assert not os.path.exists(paths["pdf_path"])
    assert not os.path.exists(paths["text_path"])

    from storage.db import get_conn, get_resume_version
    conn = get_conn(client._test_db_path)
    assert get_resume_version(conn, "goldman_sachs_data") is None
    conn.close()


def test_delete_then_list_does_not_return_entry(client):
    """The bug being fixed: after DELETE, GET /list must not include it."""
    _seed_version(client, version_key="goldman_sachs_data")

    resp = client.get("/api/vault/list")
    assert resp.status_code == 200
    pre_keys = [f["version_key"] for f in resp.get_json()["files"]]
    assert "goldman_sachs_data" in pre_keys

    resp = client.delete("/api/vault/version/goldman_sachs_data")
    assert resp.status_code == 200

    resp = client.get("/api/vault/list")
    assert resp.status_code == 200
    post_keys = [f["version_key"] for f in resp.get_json()["files"]]
    assert "goldman_sachs_data" not in post_keys


# ─────────────────────────────────────────────────────────────────────
#  Partial-state vault — should NOT 500
# ─────────────────────────────────────────────────────────────────────

def test_delete_db_row_only_when_pdf_missing(client):
    """DB row exists but no PDF on disk → 200, DB row gone."""
    _seed_version(client, version_key="meta_ml", create_pdf=False, create_text=True)

    resp = client.delete("/api/vault/version/meta_ml")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "deleted"
    assert body["db_row_deleted"] is True
    assert body["pdf_deleted"] is False
    assert body["text_deleted"] is True

    from storage.db import get_conn, get_resume_version
    conn = get_conn(client._test_db_path)
    assert get_resume_version(conn, "meta_ml") is None
    conn.close()


def test_delete_pdf_only_when_db_row_missing(client):
    """PDF on disk but no DB row → 200, file gone."""
    version_key = "goldman_sachs_data"
    fname = f"Narendranath_{version_key}.pdf"
    pdf_path = os.path.join(client._test_vault_dir, "pdf", fname)
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\nfake\n%%EOF\n")

    resp = client.delete(f"/api/vault/version/{version_key}")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pdf_deleted"] is True
    assert body["db_row_deleted"] is False
    assert not os.path.exists(pdf_path)


# ─────────────────────────────────────────────────────────────────────
#  Response shape (Round 2 Fix #1): no absolute paths leaked
# ─────────────────────────────────────────────────────────────────────

def test_delete_response_does_not_leak_absolute_paths(client):
    """Response must not include `pdf_path`/`text_path` (server filesystem
    structure leak). Only the basename of the deleted PDF is allowed."""
    paths = _seed_version(client, version_key="goldman_sachs_data")
    resp = client.delete("/api/vault/version/goldman_sachs_data")

    assert resp.status_code == 200
    body = resp.get_json()
    assert "pdf_path" not in body
    assert "text_path" not in body
    # Basename ok — it's the filename the user uploaded.
    assert body.get("pdf_filename") == os.path.basename(paths["pdf_path"])
    # Sanity: no absolute path snuck into any field.
    for k, v in body.items():
        if isinstance(v, str):
            assert not v.startswith("/"), f"field {k!r} leaks absolute path: {v!r}"


# ─────────────────────────────────────────────────────────────────────
#  Idempotency (Round 2 Fix #5): retried DELETE returns 200 already_gone
# ─────────────────────────────────────────────────────────────────────

def test_delete_nonexistent_key_returns_200_already_gone(client):
    """No DB row AND no file on disk → 200 with already_gone:true.

    DELETE's post-condition (resource doesn't exist) is satisfied, so a
    404 would be hostile to queues/clients that retry on transient errors."""
    resp = client.delete("/api/vault/version/totally_made_up_key")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "deleted"
    assert body["already_gone"] is True
    assert body["db_row_deleted"] is False
    assert body["pdf_deleted"] is False
    assert body["text_deleted"] is False


def test_delete_idempotent_double_call(client):
    """Two DELETE calls in a row both succeed; second one says already_gone."""
    _seed_version(client, version_key="goldman_sachs_data")

    first = client.delete("/api/vault/version/goldman_sachs_data")
    assert first.status_code == 200
    assert first.get_json().get("already_gone") is not True
    assert first.get_json()["db_row_deleted"] is True

    second = client.delete("/api/vault/version/goldman_sachs_data")
    assert second.status_code == 200
    body = second.get_json()
    assert body["status"] == "deleted"
    assert body["already_gone"] is True


# ─────────────────────────────────────────────────────────────────────
#  Path-traversal defense
# ─────────────────────────────────────────────────────────────────────

def test_delete_path_traversal_url_encoded_slash(client):
    """`..%2Fetc%2Fpasswd` → decoded to `../etc/passwd`. Flask's default
    <string:> converter rejects slashes → 404 at routing. File system stays
    untouched (sentinel outside the vault survives)."""
    sentinel = os.path.join(client._test_vault_dir, "..", "sentinel.txt")
    with open(sentinel, "w") as f:
        f.write("do not delete me")

    resp = client.delete("/api/vault/version/..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)
    assert os.path.exists(sentinel)


def test_delete_path_traversal_dotdot_in_key(client):
    """A key with `..` but no slashes passes Flask routing, so the handler
    must reject it explicitly with 400. The filesystem stays untouched."""
    sentinel = os.path.join(client._test_vault_dir, "..", "sentinel.txt")
    with open(sentinel, "w") as f:
        f.write("do not delete me")

    resp = client.delete("/api/vault/version/..foo")
    assert resp.status_code == 400
    assert os.path.exists(sentinel)


def test_delete_safe_unlink_refuses_outside_vault(monkeypatch, tmp_path):
    """Belt-and-suspenders: even if a path somehow resolves outside the
    vault, _safe_unlink_in_vault refuses with ValueError. Verified by
    mocking realpath to force an escape result."""
    import storage.resume_vault as rv_mod
    vault_dir = str(tmp_path / "vault")
    os.makedirs(vault_dir, exist_ok=True)
    monkeypatch.setattr(rv_mod, "VAULT_DIR", vault_dir)

    real_realpath = os.path.realpath
    outside = "/tmp/escape_target.txt"

    def fake_realpath(p):
        # The VAULT_DIR call should resolve honestly; everything else escapes.
        if p == vault_dir:
            return real_realpath(p)
        return outside

    monkeypatch.setattr(rv_mod.os.path, "realpath", fake_realpath)

    with pytest.raises(ValueError, match="outside vault"):
        rv_mod._safe_unlink_in_vault("/anything")


# ─────────────────────────────────────────────────────────────────────
#  Round 2 Fix #4: adversarial key shapes
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw_key,expected_status,label",
    [
        # Absolute path. Flask <string:> rejects the slashes → routing 404
        # before our handler sees it. Either way, no traversal occurs.
        ("/etc/passwd", (400, 404), "absolute_path"),
        # Backslash-only (Windows-style traversal).
        ("..\\\\etc", (400,), "backslash_only"),
        # Bare `..` — two dots, no slashes. Passes Flask routing → handler
        # must explicitly 400 it.
        ("..", (400,), "bare_dotdot"),
    ],
)
def test_delete_rejects_adversarial_keys(client, raw_key, expected_status, label):
    """Adversarial keys must be rejected without touching the filesystem.

    Sentinel file lives outside the vault. If any of these keys triggered
    a delete, the sentinel could vanish. It must survive every case."""
    sentinel = os.path.join(client._test_vault_dir, "..", f"sentinel_{label}.txt")
    with open(sentinel, "w") as f:
        f.write("do not delete me")

    resp = client.delete(f"/api/vault/version/{raw_key}")
    assert resp.status_code in expected_status, (
        f"{label}: got {resp.status_code}, expected one of {expected_status}"
    )
    assert os.path.exists(sentinel)


def test_delete_null_byte_in_key_returns_400(client):
    """A null byte in the key must NOT propagate to os.path.realpath()
    (which raises ValueError → 500). Route layer rejects it as 400."""
    sentinel = os.path.join(client._test_vault_dir, "..", "sentinel_null.txt")
    with open(sentinel, "w") as f:
        f.write("do not delete me")

    # Flask's test client URL-decodes; use raw %00 in the URL.
    resp = client.delete("/api/vault/version/foo%00.pdf")
    assert resp.status_code == 400, (
        f"Expected 400 for null-byte key; got {resp.status_code} "
        f"(body={resp.get_data(as_text=True)})"
    )
    assert os.path.exists(sentinel)


def test_delete_symlink_target_outside_vault_is_refused(client, tmp_path):
    """Create a real symlink inside vault/pdf/ pointing OUTSIDE the vault.
    A delete attempt must refuse — symlink and target both stay intact."""
    # Real file far away that an attacker would want destroyed.
    outside_target = tmp_path / "outside_target.txt"
    outside_target.write_text("precious user data")

    vault_dir = client._test_vault_dir
    pdf_dir = os.path.join(vault_dir, "pdf")
    # Use a filename that parses to a clean version_key.
    symlink_name = "Narendranath_symlink_attack.pdf"
    symlink_path = os.path.join(pdf_dir, symlink_name)

    try:
        os.symlink(str(outside_target), symlink_path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform")

    from storage.resume_vault import parse_resume_filename
    version_key = parse_resume_filename(symlink_name)["version_key"]

    # The route should refuse: _safe_unlink_in_vault resolves the symlink's
    # realpath, sees it's outside the vault, raises ValueError → 400.
    resp = client.delete(f"/api/vault/version/{version_key}")
    assert resp.status_code == 400, (
        f"Expected 400 for symlink-to-outside; got {resp.status_code} "
        f"(body={resp.get_data(as_text=True)})"
    )

    # Target file untouched. The symlink itself we don't care about
    # (it's inside the vault and harmless on its own), but the precious
    # data it pointed to MUST survive.
    assert outside_target.exists()
    assert outside_target.read_text() == "precious user data"


# ─────────────────────────────────────────────────────────────────────
#  Round 3: error responses must NOT leak absolute paths
# ─────────────────────────────────────────────────────────────────────

def test_delete_valueerror_response_does_not_leak_paths(client, monkeypatch):
    """If the storage layer raises ValueError with absolute paths in the
    message (e.g. symlink-escape rejection), the 400 response body must
    NOT echo those paths back to the client.

    Round 2 introduced a leak at vault_routes.py line 252 where
    `str(e)` was returned verbatim. Round 3 closes it.
    """
    # Seed enough state to get past the idempotency short-circuit.
    _seed_version(client, version_key="goldman_sachs_data")

    # The route imports delete_vault_version locally, so we patch the
    # source module's attribute.
    import storage.resume_vault as rv_mod

    def fake_delete(*args, **kwargs):
        raise ValueError(
            "Refusing to delete path outside vault: "
            "'/opt/secret/whatever' not under '/opt/vault'"
        )

    monkeypatch.setattr(rv_mod, "delete_vault_version", fake_delete)

    resp = client.delete("/api/vault/version/goldman_sachs_data")
    assert resp.status_code == 400

    body = resp.get_data(as_text=True)
    assert "/opt/secret" not in body, f"absolute path leaked: {body!r}"
    assert "/opt/vault" not in body, f"absolute path leaked: {body!r}"
    assert "/opt/whatever" not in body, f"absolute path leaked: {body!r}"

    data = resp.get_json()
    assert data == {"error": "Invalid version_key"}, (
        f"Expected generic error, got {data!r}"
    )


def test_delete_oserror_response_does_not_leak_paths(client, monkeypatch):
    """If the storage layer raises OSError/PermissionError (whose repr
    embeds the absolute path), the 500 response body must NOT echo that
    path back to the client.

    Round 2's Fix #3 (OSError re-raise) introduced the leak via
    `f"Filesystem error while deleting: {e}"` at line 258.
    """
    _seed_version(client, version_key="goldman_sachs_data")

    # The route imports delete_vault_version locally, so we patch the
    # source module's attribute.
    import storage.resume_vault as rv_mod

    def fake_delete(*args, **kwargs):
        # PermissionError(errno, strerror, filename) — repr() includes the
        # filename: "[Errno 13] Permission denied: '/opt/secret/path.pdf'"
        raise PermissionError(13, "Permission denied", "/opt/secret/path.pdf")

    monkeypatch.setattr(rv_mod, "delete_vault_version", fake_delete)

    resp = client.delete("/api/vault/version/goldman_sachs_data")
    assert resp.status_code == 500

    body = resp.get_data(as_text=True)
    assert "/opt/secret" not in body, f"absolute path leaked: {body!r}"
    assert "path.pdf" not in body, f"filename leaked: {body!r}"

    data = resp.get_json()
    assert data == {"error": "Filesystem error while deleting version"}, (
        f"Expected generic error, got {data!r}"
    )
