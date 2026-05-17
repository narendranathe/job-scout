"""Tests for ``GET /api/vault/version/<version_key>/pdf`` — one-click PDF
download from the best-match panel (issue #39 part B).

Covers:
- Happy path: valid version_key → 200 + application/pdf + Content-Disposition.
- Nonexistent key → 404.
- Malformed/traversal-shaped keys → 400, never served.
- Null byte / backslash / parent-dir keys → 400.
- Realpath escape via a symlink in the vault → caught + 400.
- Auth: API_SECRET set, no Bearer → 401; with Bearer → 200.

The fixtures mirror test_vault_hardening.py — same monkeypatch +
``_reload_vault`` dance so DB_PATH / RESUME_VAULT_PATH / API_SECRET are
picked up at module-import time by both ``storage.resume_vault`` and
``routes.vault_routes``.
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Smallest valid PDF header — the route doesn't parse beyond the magic
# bytes, so anything starting with %PDF- is fine for the download path.
_VALID_PDF = b"%PDF-1.4\n%fake content for download test\n"


def _reload_vault(monkeypatch, *, db_path: str, vault_dir: str, api_secret: str = ""):
    """Reload routes.vault_routes + storage.resume_vault with patched env.

    DB_PATH, RESUME_VAULT_PATH, and API_SECRET are read at import time, so
    we delete + re-import to refresh them.
    """
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("RESUME_VAULT_PATH", vault_dir)
    if api_secret:
        monkeypatch.setenv("API_SECRET", api_secret)
    else:
        monkeypatch.delenv("API_SECRET", raising=False)

    for mod in ["storage.resume_vault", "routes.vault_routes", "server"]:
        if mod in sys.modules:
            del sys.modules[mod]

    import storage.resume_vault as rv  # noqa: F401
    import routes.vault_routes as vr  # noqa: F401
    return vr, rv


def _seed_vault(vault_dir: str, pdf_filename: str, pdf_bytes: bytes = _VALID_PDF) -> str:
    """Drop a PDF into <vault>/pdf/<pdf_filename> and return its path."""
    pdf_dir = os.path.join(vault_dir, "pdf")
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    path = os.path.join(pdf_dir, pdf_filename)
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return path


@pytest.fixture
def client_no_secret(tmp_path, monkeypatch):
    """API_SECRET unset — dev-mode pass-through."""
    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)

    from storage.db import init_db
    init_db(db_path)

    _reload_vault(monkeypatch, db_path=db_path, vault_dir=vault_dir)

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c, vault_dir


@pytest.fixture
def client_with_secret(tmp_path, monkeypatch):
    """API_SECRET=sekret — Bearer auth required."""
    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)

    from storage.db import init_db
    init_db(db_path)

    _reload_vault(monkeypatch, db_path=db_path, vault_dir=vault_dir, api_secret="sekret")

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c, vault_dir


# ─── Happy path ──────────────────────────────────────────────────────


def test_download_pdf_happy_path(client_no_secret):
    """Valid version_key → 200, application/pdf, attachment Content-Disposition."""
    c, vault_dir = client_no_secret
    # Seed a PDF whose parsed filename → version_key "meta_ml".
    _seed_vault(vault_dir, "Narendranath_Meta_ML.pdf")

    resp = c.get("/api/vault/version/meta_ml/pdf")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers["Content-Type"].startswith("application/pdf")
    cd = resp.headers.get("Content-Disposition", "")
    assert "attachment" in cd.lower()
    assert "Narendranath_Meta_ML.pdf" in cd
    # The streamed body is the file we wrote.
    assert resp.data.startswith(b"%PDF-")
    assert resp.data == _VALID_PDF


def test_download_pdf_returns_actual_bytes(client_no_secret):
    """Body must be the exact bytes on disk, not a JSON wrapper."""
    c, vault_dir = client_no_secret
    payload = b"%PDF-1.4\n" + b"BINARY-MARKER-XYZ" + b"\n%%EOF"
    _seed_vault(vault_dir, "Narendranath_Stripe.pdf", pdf_bytes=payload)

    resp = c.get("/api/vault/version/stripe/pdf")
    assert resp.status_code == 200
    assert resp.data == payload


# ─── 404 + malformed key ─────────────────────────────────────────────


def test_download_pdf_nonexistent_returns_404(client_no_secret):
    """version_key not in the vault → 404 with JSON error."""
    c, _ = client_no_secret
    resp = c.get("/api/vault/version/no_such_version/pdf")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Version not found"}


def test_download_pdf_empty_path_segment(client_no_secret):
    """An empty <version_key> segment doesn't route to our endpoint at all
    — Flask returns 404 for /api/vault/version//pdf. The key invariant is
    "never serves a file"."""
    c, _ = client_no_secret
    resp = c.get("/api/vault/version//pdf")
    assert resp.status_code in (308, 404)  # redirect or not-found, never 200
    if resp.status_code == 200:
        pytest.fail("Empty path segment must never serve a file")


@pytest.mark.parametrize("bad_key", [
    "..",
    "../..",
    "..%2F..",          # URL-encoded ../..
    "foo..bar",         # contains ".."
    "etc/passwd",       # Flask <string:> strips slashes, but defense in depth
    "foo\\bar",         # backslash
    "foo\x00bar",       # null byte
])
def test_download_pdf_traversal_keys_rejected(client_no_secret, bad_key):
    """Any traversal-shaped key → 400 or 404, but NEVER a file. The route
    explicitly rejects keys containing ``/``, ``\\``, ``..``, or NUL bytes
    with a 400 — and Flask's URL routing rejects literal slashes upstream
    of us, which surfaces as a 404."""
    c, vault_dir = client_no_secret
    # Seed a real file so a successful traversal would actually find
    # something to leak.
    _seed_vault(vault_dir, "Narendranath_Meta.pdf")

    resp = c.get(f"/api/vault/version/{bad_key}/pdf")
    assert resp.status_code in (400, 404), (
        f"key={bad_key!r} returned {resp.status_code}, expected 400/404"
    )
    # And whatever the status, the body MUST NOT be a PDF.
    assert not resp.data.startswith(b"%PDF-"), (
        f"key={bad_key!r} leaked PDF bytes — path traversal succeeded!"
    )


def test_download_pdf_symlink_escape_refused(tmp_path, monkeypatch):
    """A PDF whose realpath() escapes the vault root must be refused.

    We seed the vault with a symlink whose name parses to a valid
    version_key, but the symlink points OUTSIDE the vault. The realpath
    assertion in vault_version_pdf should catch this and return 400.
    """
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks not supported on this platform")

    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    outside_dir = str(tmp_path / "outside")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    os.makedirs(outside_dir, exist_ok=True)

    # Write a "secret" file outside the vault.
    secret_path = os.path.join(outside_dir, "secret.pdf")
    with open(secret_path, "wb") as f:
        f.write(b"%PDF-1.4\nSECRET-OUTSIDE-VAULT\n")

    # Symlink inside the vault → secret outside the vault.
    symlink_path = os.path.join(vault_dir, "pdf", "Narendranath_Evil.pdf")
    try:
        os.symlink(secret_path, symlink_path)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted in this environment")

    from storage.db import init_db
    init_db(db_path)

    _reload_vault(monkeypatch, db_path=db_path, vault_dir=vault_dir)

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        resp = c.get("/api/vault/version/evil/pdf")
        # 400 (route's realpath check) or 404 (list_vault filtered it).
        assert resp.status_code in (400, 404), (
            f"symlink escape returned {resp.status_code}, expected 400/404"
        )
        assert b"SECRET-OUTSIDE-VAULT" not in resp.data, (
            "symlink escape leaked outside-vault bytes!"
        )


# ─── Auth ────────────────────────────────────────────────────────────


def test_download_pdf_requires_auth_when_secret_set(client_with_secret):
    """API_SECRET set, no Authorization header → 401, even for valid key."""
    c, vault_dir = client_with_secret
    _seed_vault(vault_dir, "Narendranath_Meta.pdf")

    resp = c.get("/api/vault/version/meta/pdf")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "unauthorized"}


def test_download_pdf_with_bearer_returns_200(client_with_secret):
    """API_SECRET set, correct Bearer token → 200 + PDF body."""
    c, vault_dir = client_with_secret
    _seed_vault(vault_dir, "Narendranath_Meta.pdf")

    resp = c.get(
        "/api/vault/version/meta/pdf",
        headers={"Authorization": "Bearer sekret"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers["Content-Type"].startswith("application/pdf")
    assert resp.data == _VALID_PDF


def test_download_pdf_wrong_bearer_returns_401(client_with_secret):
    """API_SECRET set, wrong Bearer token → 401."""
    c, vault_dir = client_with_secret
    _seed_vault(vault_dir, "Narendranath_Meta.pdf")

    resp = c.get(
        "/api/vault/version/meta/pdf",
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401
