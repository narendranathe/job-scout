"""Tests for /api/vault/* hardening: auth + CORS (#34), path traversal (#35),
PDF magic-byte + size validation (#36).

These tests reuse the same monkeypatch + re-import dance as
test_admin_routes.py so the module-level ``API_SECRET`` / ``DB_PATH`` /
``VAULT_DIR`` constants pick up the patched environment without needing
the surrounding server.py imports to be torn down.
"""
import base64
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Smallest possible payload that satisfies our magic-byte check. Real PDFs
# have a tail (xref, trailer, %%EOF) but we never parse it in these
# happy-path tests — pypdf is best-effort on broken PDFs and just returns
# "" for the extracted text, which our route accepts.
_VALID_PDF_HEADER = b"%PDF-1.4\n%fake content for tests\n"


def _reload_vault(monkeypatch, *, db_path: str, vault_dir: str, api_secret: str = ""):
    """Reload routes.vault_routes + storage.resume_vault with patched env.

    The two modules read env vars at import time (DB_PATH, API_SECRET,
    VAULT_DIR), so we delete + re-import to refresh them. Returns a tuple
    of the reloaded ``routes.vault_routes`` and ``storage.resume_vault``
    modules.
    """
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("RESUME_VAULT_PATH", vault_dir)
    if api_secret:
        monkeypatch.setenv("API_SECRET", api_secret)
    else:
        monkeypatch.delenv("API_SECRET", raising=False)

    for mod in [
        "storage.resume_vault",
        "routes.vault_routes",
        "server",
    ]:
        if mod in sys.modules:
            del sys.modules[mod]

    import storage.resume_vault as rv  # noqa: F401
    import routes.vault_routes as vr  # noqa: F401
    return vr, rv


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
        yield c


@pytest.fixture
def client_with_secret(tmp_path, monkeypatch):
    """API_SECRET set to 'sekret' — Bearer auth required."""
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
        yield c


# ─── Issue #34: Auth ──────────────────────────────────────────────────


def test_auth_missing_header_returns_401(client_with_secret):
    """No Authorization header + API_SECRET set → 401."""
    resp = client_with_secret.get("/api/vault/list")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "unauthorized"}


def test_auth_wrong_bearer_returns_401(client_with_secret):
    """Wrong Bearer token + API_SECRET set → 401."""
    resp = client_with_secret.get(
        "/api/vault/list",
        headers={"Authorization": "Bearer not-the-secret"},
    )
    assert resp.status_code == 401


def test_auth_correct_bearer_returns_200(client_with_secret):
    """Correct Bearer token + API_SECRET set → 200."""
    resp = client_with_secret.get(
        "/api/vault/list",
        headers={"Authorization": "Bearer sekret"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "files" in body
    assert "count" in body


def test_auth_dev_mode_passthrough(client_no_secret):
    """No Authorization + API_SECRET unset → 200 (dev mode)."""
    resp = client_no_secret.get("/api/vault/list")
    assert resp.status_code == 200


def test_auth_options_always_passes(client_with_secret):
    """OPTIONS preflight should never be 401 — browsers send them with no
    Authorization header before the real request."""
    resp = client_with_secret.options("/api/vault/upload")
    # Flask's automatic OPTIONS handling for routes that list OPTIONS in
    # their methods returns 200; the key invariant is "not 401".
    assert resp.status_code != 401
    assert resp.status_code in (200, 204)


def test_auth_post_endpoint_also_gated(client_with_secret):
    """The before_request hook must cover POST endpoints too, not just GET."""
    resp = client_with_secret.post(
        "/api/vault/best-match",
        json={"job_description": "Senior Data Engineer"},
    )
    assert resp.status_code == 401


# ─── Round 2 hardening: timing-safe + parser edge cases ───────────────


def test_auth_wrong_scheme_basic_returns_401(client_with_secret):
    """Authorization: Basic <token> is not Bearer — must be 401 even if the
    token value happens to equal the secret."""
    resp = client_with_secret.get(
        "/api/vault/list",
        headers={"Authorization": "Basic sekret"},
    )
    assert resp.status_code == 401


def test_auth_lowercase_bearer_returns_200(client_with_secret):
    """RFC 7235: auth scheme is case-insensitive. 'bearer' must work."""
    resp = client_with_secret.get(
        "/api/vault/list",
        headers={"Authorization": "bearer sekret"},
    )
    assert resp.status_code == 200


def test_auth_uppercase_bearer_returns_200(client_with_secret):
    """RFC 7235: 'BEARER' must also work (full case-insensitive)."""
    resp = client_with_secret.get(
        "/api/vault/list",
        headers={"Authorization": "BEARER sekret"},
    )
    assert resp.status_code == 200


def test_auth_empty_token_after_bearer_returns_401(client_with_secret):
    """'Authorization: Bearer ' (trailing space, no token) → 401."""
    resp = client_with_secret.get(
        "/api/vault/list",
        headers={"Authorization": "Bearer "},
    )
    assert resp.status_code == 401


def test_auth_whitespace_in_env_is_stripped(tmp_path, monkeypatch):
    """API_SECRET=' secret ' (with whitespace) should .strip() and accept
    the un-padded token at request time. This protects against silent
    failures when the operator copy-pastes the secret with a trailing
    newline from a .env file."""
    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    from storage.db import init_db
    init_db(db_path)

    # Note: leading + trailing spaces around "secret"
    _reload_vault(monkeypatch, db_path=db_path, vault_dir=vault_dir, api_secret=" secret ")

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        resp = c.get(
            "/api/vault/list",
            headers={"Authorization": "Bearer secret"},
        )
        assert resp.status_code == 200


# ─── Issue #34: CORS ──────────────────────────────────────────────────


def test_cors_headers_include_authorization(client_no_secret):
    """Allow-Headers must list Authorization so Bearer works in browsers."""
    resp = client_no_secret.get("/api/vault/list")
    assert "Authorization" in resp.headers.get("Access-Control-Allow-Headers", "")


def test_cors_default_origin_is_star(client_no_secret):
    """With ALLOWED_ORIGINS unset, we keep the legacy '*' for back-compat."""
    resp = client_no_secret.get("/api/vault/list")
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"


def test_cors_restricted_to_allowlist(tmp_path, monkeypatch):
    """With ALLOWED_ORIGINS set, only listed origins get echoed back."""
    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    from storage.db import init_db
    init_db(db_path)

    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com,https://other.example.com")
    _reload_vault(monkeypatch, db_path=db_path, vault_dir=vault_dir)

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        # Origin on the allowlist → echoed.
        r1 = c.get("/api/vault/list", headers={"Origin": "https://app.example.com"})
        assert r1.headers.get("Access-Control-Allow-Origin") == "https://app.example.com"
        # Origin not on the allowlist → header missing (browser blocks).
        r2 = c.get("/api/vault/list", headers={"Origin": "https://evil.example.com"})
        assert r2.headers.get("Access-Control-Allow-Origin") is None


def test_cors_credentials_only_with_specific_origin(tmp_path, monkeypatch):
    """Browsers REJECT responses combining Allow-Credentials:true with
    Allow-Origin:*. The blueprint must only emit Allow-Credentials when
    echoing a specific allowlisted origin."""
    db_path = str(tmp_path / "test.db")
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    from storage.db import init_db
    init_db(db_path)

    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    _reload_vault(monkeypatch, db_path=db_path, vault_dir=vault_dir)

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        # Allowlisted origin → credentials header present.
        r1 = c.get("/api/vault/list", headers={"Origin": "https://app.example.com"})
        assert r1.headers.get("Access-Control-Allow-Credentials") == "true"
        # Non-allowlisted origin → NO Allow-Origin AND NO credentials.
        r2 = c.get("/api/vault/list", headers={"Origin": "https://evil.example.com"})
        assert r2.headers.get("Access-Control-Allow-Origin") is None
        assert r2.headers.get("Access-Control-Allow-Credentials") is None


def test_cors_wildcard_origin_omits_credentials(client_no_secret):
    """Dev-mode fallback (ALLOWED_ORIGINS unset) emits '*' — and must NOT
    emit Allow-Credentials, since browsers silently reject the combo."""
    resp = client_no_secret.get("/api/vault/list")
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"
    assert resp.headers.get("Access-Control-Allow-Credentials") is None


# ─── Issue #35: Path traversal ────────────────────────────────────────


def test_canonical_filename_strips_traversal():
    """canonical_filename should strip '../' segments to safe characters."""
    from storage.resume_vault import canonical_filename
    # "../../etc/passwd" sanitizes to "etcpasswd" — slashes + dots stripped.
    out = canonical_filename("../../etc/passwd")
    assert "/" not in out
    assert ".." not in out
    assert out.endswith(".pdf")
    assert "etcpasswd" in out


def test_canonical_filename_rejects_empty_after_sanitize():
    """A company that sanitizes to '' should raise ValueError."""
    from storage.resume_vault import canonical_filename
    with pytest.raises(ValueError, match="empty"):
        canonical_filename("../../")
    with pytest.raises(ValueError, match="empty"):
        canonical_filename("///")


def test_canonical_filename_rejects_empty_role():
    """A role that sanitizes to '' should also raise."""
    from storage.resume_vault import canonical_filename
    with pytest.raises(ValueError, match="empty"):
        canonical_filename("Meta", "...")


def test_upload_rejects_oversize_company(client_no_secret):
    """company >80 chars → 400 at route layer (before sanitize)."""
    pdf_b64 = base64.b64encode(_VALID_PDF_HEADER).decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "A" * 81, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 400
    assert "too long" in resp.get_json()["error"]


def test_upload_rejects_oversize_role(client_no_secret):
    """role >80 chars → 400 at route layer."""
    pdf_b64 = base64.b64encode(_VALID_PDF_HEADER).decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "Meta", "role": "x" * 81, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 400
    assert "too long" in resp.get_json()["error"]


def test_upload_rejects_traversal_company(client_no_secret):
    """company='../../' sanitizes to empty → 400 from canonical_filename."""
    pdf_b64 = base64.b64encode(_VALID_PDF_HEADER).decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "../../", "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 400
    assert "empty" in resp.get_json()["error"]


def test_save_pdf_realpath_assertion(tmp_path, monkeypatch):
    """Even if canonical_filename were monkeypatched to lie, the realpath
    check in save_pdf_to_vault must catch the escape attempt."""
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    monkeypatch.setenv("RESUME_VAULT_PATH", vault_dir)
    if "storage.resume_vault" in sys.modules:
        del sys.modules["storage.resume_vault"]
    import storage.resume_vault as rv

    # Replace canonical_filename with one that returns a traversal path.
    monkeypatch.setattr(
        rv,
        "canonical_filename",
        lambda c, r=None, ext=".pdf": "../../../evil.pdf",
    )

    with pytest.raises(ValueError, match="refusing to write outside vault"):
        rv.save_pdf_to_vault(
            pdf_bytes=_VALID_PDF_HEADER,
            company="Meta",
            role=None,
            db_path=None,
        )


# ─── Issue #36: PDF magic-byte + size validation ──────────────────────


def test_upload_rejects_non_pdf_bytes(client_no_secret):
    """Bytes without %PDF- magic header → 400 'not a PDF'."""
    pdf_b64 = base64.b64encode(b"this is definitely not a PDF").decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "Meta", "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 400
    assert "not a PDF" in resp.get_json()["error"]


def test_upload_rejects_oversize_pdf(client_no_secret):
    """PDF >10MB → 413 'too large'."""
    big = b"%PDF-" + b"x" * 10_000_001
    pdf_b64 = base64.b64encode(big).decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "Meta", "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 413
    err = resp.get_json()["error"]
    assert "too large" in err
    # Error message must include the actual offending size for debuggability.
    assert str(len(big)) in err


def test_upload_accepts_exact_size_boundary(client_no_secret):
    """Exactly MAX_PDF_BYTES (10_000_000) should PASS the size check —
    the cap is inclusive. One byte over (10_000_001) is already covered
    by test_upload_rejects_oversize_pdf above. This pins the boundary."""
    # Header (5 bytes) + filler to exactly 10_000_000 total.
    body = b"%PDF-" + b"x" * (10_000_000 - len(b"%PDF-"))
    assert len(body) == 10_000_000
    pdf_b64 = base64.b64encode(body).decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "Meta", "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 200


def test_upload_accepts_valid_pdf(client_no_secret):
    """Valid magic header + reasonable size → 200."""
    pdf_b64 = base64.b64encode(_VALID_PDF_HEADER).decode()
    resp = client_no_secret.post(
        "/api/vault/upload",
        json={"company": "Meta", "role": "ML Engineer", "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["company"] == "Meta"
    assert "vault_path" in body
    # And the file should actually exist on disk under the vault dir.
    assert os.path.exists(body["vault_path"])


def test_save_pdf_to_vault_rejects_non_pdf(tmp_path, monkeypatch):
    """The storage-layer check fires even when called directly (no route)."""
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    monkeypatch.setenv("RESUME_VAULT_PATH", vault_dir)
    if "storage.resume_vault" in sys.modules:
        del sys.modules["storage.resume_vault"]
    import storage.resume_vault as rv

    with pytest.raises(ValueError, match="not a PDF"):
        rv.save_pdf_to_vault(pdf_bytes=b"junk", company="Meta", db_path=None)


def test_save_pdf_to_vault_rejects_oversize(tmp_path, monkeypatch):
    """Storage-layer size check fires before any disk write."""
    vault_dir = str(tmp_path / "vault")
    os.makedirs(os.path.join(vault_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(vault_dir, "text"), exist_ok=True)
    monkeypatch.setenv("RESUME_VAULT_PATH", vault_dir)
    if "storage.resume_vault" in sys.modules:
        del sys.modules["storage.resume_vault"]
    import storage.resume_vault as rv

    big = b"%PDF-" + b"x" * (rv.MAX_PDF_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        rv.save_pdf_to_vault(pdf_bytes=big, company="Meta", db_path=None)
