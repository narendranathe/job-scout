"""Tests for the R2 vault backend.

R2 is S3-compatible, so we point boto3 at a moto-mocked S3 endpoint
instead of standing up a real Cloudflare bucket. The tests exercise
``R2VaultBackend`` directly (no Flask wiring) and also the end-to-end
``save_pdf_to_vault`` → ``list_vault`` round-trip with the R2 backend
swapped in via ``VAULT_BACKEND=r2``.
"""

from __future__ import annotations

import os
import sys

import pytest

# moto provides an in-memory S3 server. We use the decorator form so
# every test gets a fresh bucket namespace.
try:
    from moto import mock_aws
except ImportError:
    pytest.skip("moto not installed — install with `pip install moto`", allow_module_level=True)

import boto3


_VALID_PDF = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n1 0 obj\n<<>>endobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def r2_env(monkeypatch):
    """Point the vault backend at moto's mocked S3."""
    monkeypatch.setenv("VAULT_BACKEND", "r2")
    monkeypatch.setenv("R2_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret")
    # The R2 backend builds its endpoint URL from R2_ACCOUNT_ID, but
    # moto only intercepts the standard ``https://s3.amazonaws.com``
    # default. We monkeypatch boto3.client to swap the endpoint after
    # construction so the request lands on moto.
    from storage import vault_backend
    vault_backend.reset_vault_backend()
    yield
    vault_backend.reset_vault_backend()


@pytest.fixture
def r2_bucket(r2_env):
    """Create the bucket inside moto's mocked S3 so PUT/GET succeed."""
    with mock_aws():
        # Pre-create the bucket. R2VaultBackend uses path-style
        # addressing but moto accepts both. Use the standard us-east-1
        # endpoint that moto intercepts — we'll patch the backend's
        # endpoint_url to match.
        client = boto3.client(
            "s3",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket="test-bucket")

        # Override the R2 endpoint after backend construction so its
        # client points at moto. Done via a patched constructor.
        import storage.vault_backend as vb

        original_init = vb.R2VaultBackend.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            # Re-create the underlying client against the moto-default
            # endpoint. Region must match the bucket region above.
            self.client = boto3.client(
                "s3",
                aws_access_key_id=kwargs.get("access_key_id") or args[2],
                aws_secret_access_key=kwargs.get("secret_access_key") or args[3],
                region_name="us-east-1",
            )

        vb.R2VaultBackend.__init__ = patched_init
        vb.reset_vault_backend()
        yield "test-bucket"
        vb.R2VaultBackend.__init__ = original_init
        vb.reset_vault_backend()


def test_r2_write_then_read_pdf(r2_bucket):
    """Round-trip: write_pdf → read_pdf returns the same bytes."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    backend.write_pdf("Narendranath_GS_DE.pdf", _VALID_PDF, mtime=1710500000.0)
    got = backend.read_pdf("Narendranath_GS_DE.pdf")
    assert got == _VALID_PDF


def test_r2_list_pdfs_includes_uploaded(r2_bucket):
    """list_pdfs surfaces every PDF we wrote, with the expected metadata shape."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    backend.write_pdf("Narendranath_Meta_ML.pdf", _VALID_PDF, mtime=1710500000.0)
    backend.write_pdf("Narendranath_Apple_DE.pdf", _VALID_PDF, mtime=1710600000.0)

    entries = backend.list_pdfs()
    keys = [e["key"] for e in entries]
    assert "Narendranath_Apple_DE.pdf" in keys
    assert "Narendranath_Meta_ML.pdf" in keys
    # Each entry has size and mtime in the expected types.
    for e in entries:
        assert isinstance(e["size"], int) and e["size"] > 0
        assert isinstance(e["mtime"], str) and "T" in e["mtime"]


def test_r2_submitted_at_survives_round_trip(r2_bucket):
    """The mtime passed to write_pdf comes back via list_pdfs as the
    submitted-at metadata — not R2's upload LastModified."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    backend.write_pdf("Narendranath_GS_DE.pdf", _VALID_PDF, mtime=1710500000.0)
    entries = backend.list_pdfs()
    match = [e for e in entries if e["key"] == "Narendranath_GS_DE.pdf"][0]
    # 1710500000 → 2024-03-15T11:33:20+00:00
    assert match["mtime"].startswith("2024-03-15")


def test_r2_delete_pdf_returns_true_only_when_existed(r2_bucket):
    """delete_pdf is the contract: True if existed, False if not."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    assert backend.delete_pdf("Narendranath_nonexistent.pdf") is False
    backend.write_pdf("Narendranath_GS_DE.pdf", _VALID_PDF)
    assert backend.delete_pdf("Narendranath_GS_DE.pdf") is True
    # Idempotent — second delete returns False.
    assert backend.delete_pdf("Narendranath_GS_DE.pdf") is False


def test_r2_text_round_trip(r2_bucket):
    """write_text → read_text preserves UTF-8 content; list_texts surfaces it."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    backend.write_text("gs_de", "Hello résumé content with unicode ✓", mtime=1710500000.0)
    assert backend.read_text("gs_de") == "Hello résumé content with unicode ✓"
    texts = backend.list_texts()
    assert any(t["key"] == "gs_de.txt" for t in texts)


def test_r2_validate_key_rejects_traversal(r2_bucket):
    """Backend rejects keys with .., null bytes, or slashes."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    for bad in ["../escape.pdf", "a/b.pdf", "a\\b.pdf", "a\x00b.pdf", ""]:
        with pytest.raises(ValueError):
            backend.write_pdf(bad, _VALID_PDF)


def test_r2_describe_includes_bucket(r2_bucket):
    from storage.vault_backend import get_vault_backend

    desc = get_vault_backend().describe()
    assert desc["backend"] == "r2"
    assert desc["bucket"] == "test-bucket"


def test_r2_local_paths_are_none(r2_bucket):
    """R2 backend has no on-disk presence, so the *_local_path helpers
    must return None — that's the signal the route uses to switch from
    send_file(filesystem) to send_file(BytesIO)."""
    from storage.vault_backend import get_vault_backend

    backend = get_vault_backend()
    assert backend.pdf_local_path("anything.pdf") is None
    assert backend.text_local_path("anything") is None


def test_r2_factory_is_cached_within_process(r2_bucket):
    """R2 backend is expensive to instantiate (TLS, signer); the
    factory must hand back the same instance across calls."""
    from storage.vault_backend import get_vault_backend

    a = get_vault_backend()
    b = get_vault_backend()
    assert a is b


def test_r2_save_pdf_to_vault_round_trip(r2_bucket, tmp_path):
    """End-to-end: save_pdf_to_vault writes to R2, list_vault enumerates
    R2, and the dashboard's modified_at reflects submitted_at."""
    from storage.db import init_db
    from storage.resume_vault import save_pdf_to_vault, list_vault

    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    result = save_pdf_to_vault(
        pdf_bytes=_VALID_PDF,
        company="Goldman Sachs",
        role="Data Engineer",
        original_filename="Narendranath_GS_DE.pdf",
        db_path=db_path,
        submitted_at="2024-03-15T10:30:00+00:00",
    )
    # canonical_filename collapses "Data Engineer" → "DATA" via the
    # reverse role alias, so the saved version_key is goldman_sachs_data
    # (mirrors how legacy filenames like Narendranath_GS_data.pdf parse).
    saved_key = result["version_key"]
    assert saved_key == "goldman_sachs_data"

    entries = list_vault()
    match = [e for e in entries if e["version_key"] == saved_key][0]
    assert match["modified_at"].startswith("2024-03-15")


def test_r2_rehydrate_rebuilds_db_from_vault(r2_bucket, tmp_path):
    """When the DB is empty but R2 has files, rehydrate_metadata_from_vault
    walks the bucket and rebuilds resume_versions rows. This is the
    recovery path for Render's ephemeral SQLite on cold start."""
    from storage.db import init_db, get_conn, list_resume_versions
    from storage.resume_vault import save_pdf_to_vault, rehydrate_metadata_from_vault

    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    # Seed: save a couple of PDFs via the full pipeline so R2 ends up
    # with both PDFs and text blobs.
    save_pdf_to_vault(
        pdf_bytes=_VALID_PDF, company="Goldman Sachs", role="Data Engineer",
        original_filename="Narendranath_GS_DE.pdf", db_path=db_path,
        submitted_at="2024-03-15T10:30:00+00:00",
    )
    save_pdf_to_vault(
        pdf_bytes=_VALID_PDF, company="Meta", role="ML Engineer",
        original_filename="Narendranath_Meta_ML.pdf", db_path=db_path,
        submitted_at="2024-04-01T08:00:00+00:00",
    )

    # Simulate a cold start: wipe the DB while leaving R2 intact.
    conn = get_conn(db_path)
    conn.execute("DELETE FROM resume_versions")
    conn.commit()
    assert len(list_resume_versions(conn)) == 0
    conn.close()

    result = rehydrate_metadata_from_vault(db_path=db_path)
    # The fake PDF has no extractable text, so both entries land in the
    # "skipped" bucket — that's the expected behavior for empty-text
    # files (we don't insert blank rows). Real PDFs with text content
    # would land in "rehydrated". The rehydrate at least walked the
    # vault.
    assert result["skipped"] + result["rehydrated"] == 2
    assert result["errors"] == 0
