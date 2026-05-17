"""Tests for the bytes-based PDF text extractor — CLAUDE.md tech-debt #3.

Standardizing on pypdf (the vault module already used it) and retiring
pdfplumber (used only by server.api_upload_resume_version_pdf). The
extractor in storage.resume_vault is now the single source of truth;
both code paths (vault on-disk and server.py upload-from-form) call it.

These tests pin the contract so a future "let's swap PDF libs again"
attempt has guardrails:
- Valid PDF bytes are parsed without raising
- Invalid/empty bytes return "" and log (no exceptions propagate)
- The path-based variant delegates to the bytes-based variant
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_blank_pdf_bytes():
    """Generate a valid single-page PDF in-memory using pypdf itself.

    No on-disk fixture required — the test is portable and any future pypdf
    version that breaks PdfWriter is its own bug to surface here.
    """
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)  # US Letter
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_from_valid_pdf_bytes_returns_string():
    """Happy path: real PDF bytes → str result, no exception."""
    from storage.resume_vault import extract_text_from_pdf_bytes
    pdf = _make_blank_pdf_bytes()
    assert pdf.startswith(b"%PDF-"), "fixture should be a real PDF"
    text = extract_text_from_pdf_bytes(pdf, source="test:blank")
    # Blank page has no extractable text — that's fine; we care about no crash.
    assert isinstance(text, str)


def test_extract_from_invalid_bytes_returns_empty(caplog):
    """Garbage in → "" out (with an error log). No exception propagates."""
    from storage.resume_vault import extract_text_from_pdf_bytes
    with caplog.at_level("ERROR"):
        text = extract_text_from_pdf_bytes(b"NOT A PDF AT ALL", source="test:garbage")
    assert text == ""


def test_extract_from_empty_bytes_returns_empty():
    """Zero-length input → "" out. Edge case for "user uploaded nothing"."""
    from storage.resume_vault import extract_text_from_pdf_bytes
    text = extract_text_from_pdf_bytes(b"", source="test:empty")
    assert text == ""


def test_extract_from_pdf_path_delegates_to_bytes(tmp_path):
    """The on-disk variant must produce the same result as the bytes
    variant given the same content — they share the same code path now."""
    from storage.resume_vault import extract_text_from_pdf, extract_text_from_pdf_bytes
    pdf = _make_blank_pdf_bytes()
    p = tmp_path / "blank.pdf"
    p.write_bytes(pdf)
    assert extract_text_from_pdf(str(p)) == extract_text_from_pdf_bytes(pdf, source=str(p))


def test_extract_from_missing_file_returns_empty(tmp_path, caplog):
    """Path that doesn't exist → "" + error log. No crash."""
    from storage.resume_vault import extract_text_from_pdf
    with caplog.at_level("ERROR"):
        text = extract_text_from_pdf(str(tmp_path / "does-not-exist.pdf"))
    assert text == ""


def test_pdfplumber_no_longer_imported_anywhere():
    """Regression guard for CLAUDE.md tech-debt #3 (standardize on pypdf).

    If anyone re-introduces pdfplumber to the project, this test fails so
    we have an explicit decision point before the project goes back to two
    PDF libraries.
    """
    import pathlib
    backend_root = pathlib.Path(__file__).parent.parent
    offenders = []
    for py in backend_root.rglob("*.py"):
        if "__pycache__" in str(py) or "tests/" in str(py).replace("\\", "/"):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        # Match real imports, not the string "pdfplumber" appearing in a comment.
        for line in text.splitlines():
            stripped = line.strip()
            if (stripped.startswith("import pdfplumber")
                or stripped.startswith("from pdfplumber")):
                offenders.append(f"{py.relative_to(backend_root)}: {stripped}")
    assert not offenders, (
        "pdfplumber was retired in favor of pypdf (CLAUDE.md tech-debt #3). "
        "If you genuinely need it back, update CLAUDE.md and remove this test. "
        "Offending imports:\n  " + "\n  ".join(offenders)
    )
