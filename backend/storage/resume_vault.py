"""
Resume Vault — local PDF storage, text extraction, and semantic similarity.

Your naming convention:
    Narendranath_{Company}.pdf
    Narendranath_{Company}_{Role}.pdf
    Narendranath_{Company}_{Role_Detail}.pdf

Examples from your Resume Easy folder:
    Narendranath_GS_data.pdf          → company="Goldman Sachs", role="data"
    Narendranath_Meta_ML.pdf          → company="Meta", role="ML"
    Narendranath_bloomberg.pdf        → company="Bloomberg", role=None
    Narendranath_Edara_Disney_Ad_Platforms.docx  → company="Disney", role="Ad Platforms"

Features:
    1. Save uploaded PDFs to local vault following YOUR naming convention
    2. Extract text from PDFs (pypdf)
    3. TF-IDF cosine similarity between any two resume versions
    4. Bulk import from an existing directory (e.g., your Resume Easy folder)
    5. Compare resume vs job description for fit scoring
    6. Track which resume was sent to which company

All data integrates with the existing resume_versions table in SQLite.
"""

import json
import logging
import math
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ─── Vault config ────────────────────────────────────────────────
# Default vault path: backend/resume_vault/
# Override with RESUME_VAULT_PATH env var
VAULT_DIR = os.environ.get(
    "RESUME_VAULT_PATH",
    os.path.join(os.path.dirname(__file__), "..", "resume_vault"),
)


def _ensure_vault():
    """Initialize the configured vault backend.

    Kept as a function-level call so existing callers don't break, but
    the actual work moved into ``vault_backend.get_vault_backend()`` —
    which is idempotent and handles both filesystem (``makedirs``) and
    R2 (no-op) initialization.
    """
    get_vault_backend()


# ═══════════════════════════════════════════════════════════════════
#  NAMING CONVENTION PARSER
# ═══════════════════════════════════════════════════════════════════

# Canonical alias source. The dicts live in company_rules.py so they can
# be edited without touching parser logic, and so the AutoApply repo's
# canonical maps and JobScout's legacy maps stay merged in one place.
from storage.company_rules import (
    COMPANY_ALIASES,
    ROLE_ALIASES,
    MULTI_WORD_COMPANIES,
    is_job_id,
)

# Pluggable storage. ``get_vault_backend()`` returns LocalVaultBackend
# by default (current behavior) and R2VaultBackend when VAULT_BACKEND=r2
# — see storage/vault_backend.py for env-var configuration. This is the
# single seam through which every PDF/text read or write must pass.
from storage.vault_backend import get_vault_backend


def parse_resume_filename(filename: str) -> dict:
    """
    Parse your resume filename into structured metadata.

    Handles patterns:
        Narendranath_{Company}.pdf
        Narendranath_{Company}_{Role}.pdf
        Narendranath_Edara_{Company}_{Role}.pdf
        Naren_DE_{Company}.docx         (role before company)
        NarenML_{Company}.pdf
        bloomberg ai.pdf                (no prefix)

    Returns:
        {
            "original_filename": "Narendranath_GS_data.pdf",
            "company": "Goldman Sachs",
            "role": "Data Engineer",
            "version_key": "gs_data",
            "display_name": "Goldman Sachs — Data Engineer",
            "extension": ".pdf",
        }
    """
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()

    # Normalize: remove common prefixes
    # ─── Strip the leading name prefix ───────────────────
    # Longest-prefix-wins. Entries that *don't* end in an underscore
    # also match the "glued" form (NarendranathGS, NarenDE), but only
    # when there's content after them — otherwise ``Naren.pdf`` would
    # collapse to "unknown".
    # ``used_naren_prefix`` flags the Naren-family forms: when a Naren
    # prefix matches, the next token is treated as a role abbreviation
    # (role-first pattern), e.g. ``Naren_DE_affirm`` → role=DE,
    # company=Affirm; ``NarenML.pdf`` → role-only template.
    _NAME_PREFIXES = sorted(
        [
            ("Narendranath_Edara_", False),
            ("Edara_Narendranath_", False),
            ("Edara_NarendraNath_", False),
            ("EdaraNarendranath", False),
            ("NarendranathEdara", False),
            ("ENarendranath_", False),
            ("ENarendranath", False),
            ("NarendranathE_", False),
            ("Narendranath_", False),
            ("NarendraNath_", False),
            ("Narendranath", False),    # glued: NarendranathGS, NarendranathE
            ("Narendra_", False),
            ("Narendra", False),         # glued: NarendraN
            ("Naren_", True),            # role-first: Naren_DE_affirm
            ("Naren", True),             # role-first glued: NarenDE, NarenML
            ("Resume_", False),
        ],
        key=lambda p: -len(p[0]),
    )

    clean = stem
    used_naren_prefix = False
    for prefix, is_naren in _NAME_PREFIXES:
        if not clean.startswith(prefix):
            continue
        rest = clean[len(prefix):]
        # Glued (no-trailing-underscore) prefixes only fire when the
        # remainder *looks like a tag*, not a continuation of the name.
        # Two guards:
        #   1. must have content after the prefix; and
        #   2. that content must start with an uppercase letter or
        #      digit — so ``NarendranathGS`` strips ("GS" starts upper),
        #      but ``Narendra`` matched against ``Narendranath`` (rest
        #      = "nath") and ``Narendranath`` matched against
        #      ``Narendranath Edara_…`` (rest = " Edara…") do not.
        if not prefix.endswith("_"):
            stripped = rest.lstrip("_-")
            if not stripped or not stripped[0].isalnum() or not stripped[0].isupper() and not stripped[0].isdigit():
                continue
        clean = rest.lstrip("_-")
        used_naren_prefix = is_naren
        break

    # Split on underscores
    parts = [p.strip() for p in clean.split("_") if p.strip()]
    if not parts:
        # Fallback for files like "bloomberg ai.pdf"
        parts = [p.strip() for p in clean.split() if p.strip()]
    if not parts:
        parts = ["unknown"]

    # ─── Multi-word company detection ────────────────────
    # Canonical table lives in company_rules.MULTI_WORD_COMPANIES.
    company_parts = []
    role_parts = []
    company_done = False
    # ``multi_word_hit`` is True when the company name came from the
    # canonical multi-word table — in that case the value is already
    # the final display name and the alias / title-case pass below must
    # not re-touch it (else "JPMorgan Chase" becomes "Jpmorgan Chase").
    multi_word_hit = False
    i = 0

    # Check for 3-word and 2-word company match at start; longest first
    # so ("jp","morgan","chase") wins over ("jp","morgan").
    if not company_done and len(parts) >= 3:
        three = (parts[0].lower(), parts[1].lower(), parts[2].lower())
        if three in MULTI_WORD_COMPANIES:
            merged = MULTI_WORD_COMPANIES[three]
            if merged is not None:
                company_parts = [merged]
                i = 3
                company_done = True
                multi_word_hit = True
            # When merged is None (e.g. ("goldman","sachs","ai")) we
            # deliberately fall through so the 2-word match below picks
            # up the company and the trailing word becomes the role.
    if not company_done and len(parts) >= 2:
        two = (parts[0].lower(), parts[1].lower())
        if two in MULTI_WORD_COMPANIES:
            merged = MULTI_WORD_COMPANIES[two]
            if merged is not None:
                company_parts = [merged]
                i = 2
                company_done = True
                multi_word_hit = True

    if not company_done:
        # Naren-family prefix: first part is a role abbreviation.
        if used_naren_prefix and parts[0].lower() in ROLE_ALIASES:
            if len(parts) == 1:
                # Role-only template — Naren_DE.pdf, NarenML.pdf, etc.
                # There's no company tag in the filename, so the file
                # represents the generic version of that role. Tag the
                # company as "Standard" so all role templates land in a
                # single predictable bucket in the vault.
                # multi_word_hit short-circuits the alias / title-case
                # pass below so the literal string "Standard" is kept.
                company_parts = ["Standard"]
                role_parts = [parts[0]]
                i = 1
                company_done = True
                multi_word_hit = True
            else:
                # Existing role-first form: Naren_DE_affirm → role=DE,
                # company=Affirm. Anything after position 1 trails into
                # the role (Naren_DE_Cap_One could in principle yield
                # role=DE, company=Cap_One; that's an edge case).
                role_parts = [parts[0]]
                company_parts = [parts[1]]
                i = 2
                company_done = True
                role_parts.extend(parts[i:])
                i = len(parts)
        else:
            company_parts = [parts[0]]
            i = 1
            company_done = True

    # Everything after company is role
    if i < len(parts):
        role_parts.extend(parts[i:])

    # ─── Peel off trailing JobID (AutoApply grammar) ─────
    # AutoApply tags can end in ``_{JobID}`` (e.g. ``..._DE_JOB123``)
    # and Workday-saved files end in ``_YYYYMMDD``. Both should land in
    # ``job_id`` rather than being mis-tagged as the role.
    # ``is_job_id`` is conservative — requires uppercase + a digit (so
    # role tokens like DE, SWE, AI never match) or all-digits length≥3.
    # That conservativeness is what lets us peel off even a single-token
    # role_parts (e.g. ``Narendranath_MS_240`` → company=Morgan Stanley,
    # role=None, job_id=240).
    job_id = None
    if role_parts and is_job_id(role_parts[-1]):
        job_id = role_parts[-1]
        role_parts = role_parts[:-1]

    # ─── Resolve aliases ─────────────────────────────────
    company_raw = "_".join(company_parts)
    role_raw = "_".join(role_parts) if role_parts else None

    # Company alias (check both original and lowered). When the
    # multi-word table already produced a canonical name, use it
    # verbatim — title-casing would mangle mixed-case names like
    # "JPMorgan Chase".
    company = company_raw
    if multi_word_hit:
        company = company_parts[0]
    elif company_raw.lower() in COMPANY_ALIASES:
        company = COMPANY_ALIASES[company_raw.lower()]
    elif len(company_parts) == 1:
        company = COMPANY_ALIASES.get(company_parts[0].lower(), company_raw.replace("_", " ").title())

    # Role alias
    role = None
    if role_raw:
        role = ROLE_ALIASES.get(role_raw.lower(), role_raw.replace("_", " ").title())

    # ─── Build outputs ───────────────────────────────────
    # Version key (lowercase, underscored, no spaces)
    vk_company = company_raw.lower().replace(" ", "_")
    vk_parts = [vk_company]
    if role_raw:
        vk_parts.append(role_raw.lower())
    version_key = "_".join(vk_parts)

    display_name = company
    if role:
        display_name += f" — {role}"

    return {
        "original_filename": filename,
        "company": company,
        "role": role,
        "version_key": version_key,
        "display_name": display_name,
        "extension": ext,
        "job_id": job_id,
    }


# Whitelist regex for filename-safe characters (issue #35). Anything outside
# this set is stripped *after* the standard space->underscore mapping is
# applied. Matches admin_routes / canonical naming convention: ASCII letters,
# digits, underscore, hyphen. Dots are deliberately excluded so attackers
# can't smuggle in ".." segments via a sanitized-looking input.
_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _sanitize_path_component(raw: str) -> str:
    """Strip everything outside [A-Za-z0-9_-] after collapsing whitespace
    to underscores. Returns "" if nothing safe remains."""
    if not raw:
        return ""
    # Collapse whitespace runs to a single underscore before stripping so
    # "Goldman   Sachs" doesn't become "GoldmanSachs".
    collapsed = re.sub(r"\s+", "_", raw.strip())
    return _FILENAME_SAFE_RE.sub("", collapsed)


def canonical_filename(company: str, role: str = None, ext: str = ".pdf") -> str:
    """
    Generate filename following YOUR convention.

    >>> canonical_filename("Goldman Sachs", "Data Engineer")
    'Narendranath_Goldman_Sachs_DE.pdf'
    >>> canonical_filename("Meta")
    'Narendranath_Meta.pdf'

    Security (issue #35): both ``company`` and ``role`` are sanitized down
    to ``[A-Za-z0-9_-]``. Inputs that resolve to an empty string after
    sanitization (e.g. ``"../../"``) raise ``ValueError`` so we never
    silently write to ``Narendranath_.pdf`` or worse, somewhere off-vault.
    """
    safe_company = _sanitize_path_component(company)
    if not safe_company:
        raise ValueError(
            f"company sanitizes to empty string (input: {company!r}); "
            f"only [A-Za-z0-9_-] characters are allowed"
        )

    # Reverse role alias for short suffix
    role_short = None
    if role:
        # Look up the alias *before* sanitizing — "Data Engineer" should
        # still map to "DE" rather than being mangled to "Data_Engineer".
        rev_aliases = {v.lower(): k.upper() for k, v in ROLE_ALIASES.items()}
        alias = rev_aliases.get(role.lower())
        if alias:
            role_short = _sanitize_path_component(alias)
        else:
            role_short = _sanitize_path_component(role.replace(" ", "_"))
        if not role_short:
            raise ValueError(
                f"role sanitizes to empty string (input: {role!r}); "
                f"only [A-Za-z0-9_-] characters are allowed"
            )

    parts = ["Narendranath", safe_company]
    if role_short:
        parts.append(role_short)

    return "_".join(parts) + ext


# ═══════════════════════════════════════════════════════════════════
#  PDF TEXT EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract plain text from a PDF file using pypdf."""
    try:
        with open(pdf_path, "rb") as f:
            return extract_text_from_pdf_bytes(f.read(), source=pdf_path)
    except OSError as e:
        log.error("Failed to read %s: %s", pdf_path, e)
        return ""


def extract_text_from_pdf_bytes(pdf_bytes: bytes, source: str = "<bytes>") -> str:
    """Extract plain text from an in-memory PDF using pypdf.

    Single source of truth for PDF→text in the project — the upload route
    (server.py) and the on-disk vault both go through here. ``source`` is
    only used for logs/errors so we know what produced empty output.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error("pypdf not installed — run: pip install pypdf")
        return ""

    import io
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = [p.extract_text() or "" for p in reader.pages]
        text = "\n\n".join(t for t in text_parts if t)
        log.info("Extracted %d chars from %s (%d pages)", len(text), source, len(reader.pages))
        return text
    except Exception as e:
        log.error("Failed to extract text from %s: %s", source, e)
        return ""


def extract_text_from_docx(docx_path: str) -> str:
    """Extract plain text from a .docx file."""
    try:
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(docx_path, "r") as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = tree.findall(".//w:p", ns)
        text_parts = []
        for p in paragraphs:
            texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
            if texts:
                text_parts.append("".join(texts))
        return "\n".join(text_parts)
    except Exception as e:
        log.error("Failed to extract text from %s: %s", docx_path, e)
        return ""


# ═══════════════════════════════════════════════════════════════════
#  VAULT OPERATIONS — Save, List, Import
# ═══════════════════════════════════════════════════════════════════

# Issue #36: 10 MB hard cap on stored PDFs. Mirrors MAX_PDF_BYTES in
# routes/vault_routes.py so direct callers (CLI, tests) get the same limit.
MAX_PDF_BYTES = 10_000_000


def save_pdf_to_vault(
    pdf_bytes: bytes,
    company: str,
    role: str = None,
    original_filename: str = None,
    db_path: str = None,
    submitted_at: str = None,
) -> dict:
    """
    Save a PDF to the local vault + extract text + register in DB.

    Args:
        pdf_bytes: Raw PDF file content
        company: Target company name
        role: Target role (optional)
        original_filename: Original upload filename
        db_path: Path to SQLite database

    Returns:
        {
            "vault_path": "/path/to/Narendranath_Goldman_Sachs_DE.pdf",
            "text_path": "/path/to/gs_de.txt",
            "version_key": "goldman_sachs_de",
            "skills": [...],
            "char_count": 4521,
        }

    Raises:
        ValueError: ``pdf_bytes`` exceeds ``MAX_PDF_BYTES``, lacks the
            ``%PDF-`` magic header, the company/role inputs sanitize to
            empty, or the resolved write path escapes ``VAULT_DIR``.
    """
    # Issue #36: cheap size + magic-byte checks first, before we touch the
    # filesystem at all. Order is intentional — size check before magic so
    # a 1 GB junk payload can't burn cycles on the .startswith() scan.
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(
            f"PDF too large: {len(pdf_bytes)} bytes (max {MAX_PDF_BYTES})"
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("not a PDF (missing %PDF- magic bytes)")

    backend = get_vault_backend()

    # Generate canonical filename (sanitizes company/role internally —
    # raises ValueError if either resolves to an empty string).
    # Backend.write_pdf adds its own path-traversal guard on the filename,
    # so the explicit realpath check the local-only code used to do is
    # now redundant — moved inside LocalVaultBackend.
    fname = canonical_filename(company, role, ".pdf")

    # Resolve submitted_at to a Unix timestamp once; both write_pdf and
    # write_text accept it as the mtime stamp. Local backend uses os.utime,
    # R2 backend stores it as ``submitted-at`` custom metadata so the
    # dashboard's ``modified_at`` field still reflects the original date
    # after the vault round-trips through object storage.
    ts: float | None = None
    if submitted_at:
        try:
            ts = datetime.fromisoformat(submitted_at.replace("Z", "+00:00")).timestamp()
        except ValueError as e:
            log.warning("Ignoring malformed submitted_at=%r: %s", submitted_at, e)

    backend.write_pdf(fname, pdf_bytes, mtime=ts)
    log.info("Saved PDF: %s (%d bytes)", fname, len(pdf_bytes))

    # Extract text from the bytes we already have in memory — avoids a
    # second round-trip (download from R2 just to re-read what we just
    # uploaded). Single source of truth for PDF→text in the project.
    text = extract_text_from_pdf_bytes(pdf_bytes, source=fname)
    meta = parse_resume_filename(fname)
    version_key = meta["version_key"]

    backend.write_text(version_key, text, mtime=ts)

    # ``vault_path`` is the absolute filesystem path when the local
    # backend is in use (so existing tests + tooling can ``os.path.exists``
    # it), and the backend key when the R2 backend is active. Same for
    # ``text_path``.
    vault_path = backend.pdf_local_path(fname) or fname
    text_path = backend.text_local_path(version_key) or f"{version_key}.txt"

    # Extract skills
    from storage.profile_manager import extract_skills_from_resume
    skills = extract_skills_from_resume(text)

    # Register in DB
    if db_path:
        from storage.db import get_conn, upsert_resume_version
        conn = get_conn(db_path)
        upsert_resume_version(
            conn,
            version_key=version_key,
            display_name=meta["display_name"],
            resume_text=text,
            skills=skills,
            target_roles=[role] if role else [],
            target_companies=[company],
            notes=f"Uploaded from: {original_filename or fname}",
            submitted_at=submitted_at,
        )
        conn.commit()
        conn.close()

    return {
        "vault_path": vault_path,
        "text_path": text_path,
        "version_key": version_key,
        "display_name": meta["display_name"],
        "company": company,
        "role": role,
        "skills": skills,
        "skill_count": len(skills),
        "char_count": len(text),
        "filename": fname,
    }


def list_vault() -> list[dict]:
    """List all files in the vault with metadata.

    Goes through the configured backend, so this works against either
    the local filesystem or R2 with identical output shape. ``vault_path``
    is the backend key (filename for local, object key for R2) — the
    PDF stream route uses it via ``backend.read_pdf(key)``, not as a
    filesystem path.
    """
    backend = get_vault_backend()
    results = []
    for entry in backend.list_pdfs():
        fname = entry["key"]
        meta = parse_resume_filename(fname)
        meta["size_bytes"] = entry["size"]
        meta["size_kb"] = round(entry["size"] / 1024, 1)
        meta["modified_at"] = entry["mtime"]
        meta["vault_path"] = fname
        results.append(meta)
    return results


def _safe_unlink_in_vault(path: str) -> bool:
    """Delete a file only if its resolved location is inside ``VAULT_DIR``.

    Defense against path-traversal: even if ``path`` was built from user
    input that included ``..`` or symlinks, ``realpath()`` collapses
    those — if the result escapes the vault directory, we refuse to
    unlink.

    Returns ``True`` if a file was deleted, ``False`` if it did not
    exist. Raises ``ValueError`` if the resolved path is outside the
    vault.

    Production code paths route through ``VaultBackend.delete_pdf`` /
    ``delete_text``; this helper is retained as a standalone primitive
    for tests + ad-hoc cleanup scripts that work directly against the
    on-disk vault layout.
    """
    vault_root = os.path.realpath(VAULT_DIR)
    target = os.path.realpath(path)
    if not (target == vault_root or target.startswith(vault_root + os.sep)):
        raise ValueError(
            f"Refusing to delete path outside vault: {target!r} not under {vault_root!r}"
        )
    if not os.path.exists(target):
        return False
    os.remove(target)
    return True


def delete_vault_version(version_key: str, db_path: str = None) -> dict:
    """
    Fully delete a resume version: the PDF file, the extracted text file,
    AND the DB row. Handles partial-state vaults gracefully — a missing file
    or missing DB row is not an error; we reconcile whatever exists.

    This fixes issue #37: previously the route only removed the DB row, but
    list_vault() reads the filesystem, so the entry resurrected on refresh.

    Returns:
        {
            "version_key": str,
            "db_row_deleted": bool,
            "pdf_deleted": bool,
            "text_deleted": bool,
            "pdf_path": str | None,   # path attempted (None if no PDF found)
            "text_path": str,
        }

    Raises:
        ValueError if version_key is empty, contains path-traversal sequences,
        or resolves to a path outside VAULT_DIR.
        OSError if a vault file exists but cannot be removed. In that case
        the DB row is NOT deleted — callers should surface the error so the
        client can retry, rather than orphaning a row whose file is still
        on disk. (Round 2 Fix #3: code now matches docstring guarantee.)
    """
    if not version_key or not isinstance(version_key, str):
        raise ValueError("version_key is required")

    # Block obvious traversal attempts at the key level before touching
    # the backend. Flask's default <string:> converter already strips '/',
    # but URL-encoded variants or future routing changes could let them
    # through. The backend re-validates on its own (defense-in-depth)
    # via vault_backend._validate_key.
    if "/" in version_key or "\\" in version_key or ".." in version_key:
        raise ValueError(f"Invalid version_key: {version_key!r}")

    backend = get_vault_backend()

    if not db_path:
        db_path = os.environ.get(
            "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
        )

    # Locate the PDF whose parsed filename → this version_key.
    pdf_filename = None
    for entry in backend.list_pdfs():
        if parse_resume_filename(entry["key"]).get("version_key") == version_key:
            pdf_filename = entry["key"]
            break

    # Round 2 Fix #3: propagate failures (raise, don't swallow) so the
    # DB row stays put when a delete fails — keeps the vault listable
    # rather than leaving a row pointing at a gone file (or vice versa).
    pdf_deleted = backend.delete_pdf(pdf_filename) if pdf_filename else False
    text_deleted = backend.delete_text(version_key)
    pdf_path = pdf_filename
    text_path = f"{version_key}.txt"

    # Delete DB row last (so a filesystem failure doesn't orphan the row).
    from storage.db import get_conn
    conn = get_conn(db_path)
    cur = conn.execute(
        "DELETE FROM resume_versions WHERE version_key = ?", (version_key,)
    )
    db_row_deleted = cur.rowcount > 0
    conn.commit()
    conn.close()

    log.info(
        "Vault delete '%s': pdf=%s text=%s db=%s",
        version_key, pdf_deleted, text_deleted, db_row_deleted,
    )

    return {
        "version_key": version_key,
        "db_row_deleted": db_row_deleted,
        "pdf_deleted": pdf_deleted,
        "text_deleted": text_deleted,
        "pdf_path": pdf_path,
        "text_path": text_path,
    }


def bulk_import(
    source_dir: str,
    db_path: str = None,
    extensions: tuple = (".pdf", ".docx"),
) -> dict:
    """
    Import all resume files from a directory into the vault.

    Scans source_dir for .pdf and .docx files matching your naming convention,
    copies them to the vault, extracts text, and registers in the DB.

    Args:
        source_dir: Path to your Resume Easy folder
        db_path: Path to SQLite database
        extensions: File extensions to import

    Returns:
        {"imported": 42, "skipped": 3, "errors": 1, "files": [...]}
    """
    source = Path(source_dir)
    if not source.exists():
        return {"error": f"Directory not found: {source_dir}", "imported": 0}

    from storage.profile_manager import extract_skills_from_resume

    backend = get_vault_backend()
    conn = None
    if db_path:
        from storage.db import get_conn, upsert_resume_version
        conn = get_conn(db_path)

    stats = {"imported": 0, "skipped": 0, "errors": 0, "files": []}

    for fpath in sorted(source.iterdir()):
        if fpath.suffix.lower() not in extensions:
            continue
        if fpath.is_dir():
            continue

        try:
            meta = parse_resume_filename(fpath.name)
            version_key = meta["version_key"]

            # Read the source file once, then route via the backend.
            if fpath.suffix.lower() == ".pdf":
                with open(fpath, "rb") as fh:
                    pdf_bytes = fh.read()
                src_mtime = fpath.stat().st_mtime
                if not backend.exists_pdf(fpath.name):
                    backend.write_pdf(fpath.name, pdf_bytes, mtime=src_mtime)
                text = extract_text_from_pdf_bytes(pdf_bytes, source=fpath.name)
            elif fpath.suffix.lower() == ".docx":
                # docx files don't go to the PDF vault — only their text.
                text = extract_text_from_docx(str(fpath))
                src_mtime = fpath.stat().st_mtime
            else:
                stats["skipped"] += 1
                continue

            if not text.strip():
                log.warning("No text extracted from %s — skipping DB", fpath.name)
                stats["skipped"] += 1
                continue

            backend.write_text(version_key, text, mtime=src_mtime)

            # Extract skills
            skills = extract_skills_from_resume(text)

            # Register in DB
            if conn:
                upsert_resume_version(
                    conn,
                    version_key=version_key,
                    display_name=meta["display_name"],
                    resume_text=text,
                    skills=skills,
                    target_roles=[meta["role"]] if meta.get("role") else [],
                    target_companies=[meta["company"]] if meta.get("company") else [],
                    notes=f"Imported from: {fpath.name}",
                )

            stats["imported"] += 1
            stats["files"].append({
                "filename": fpath.name,
                "version_key": version_key,
                "company": meta["company"],
                "role": meta.get("role"),
                "skills_found": len(skills),
                "chars": len(text),
            })

        except Exception as e:
            log.error("Failed to import %s: %s", fpath.name, e)
            stats["errors"] += 1

    if conn:
        conn.commit()
        conn.close()

    log.info(
        "Bulk import: %d imported, %d skipped, %d errors from %s",
        stats["imported"], stats["skipped"], stats["errors"], source_dir,
    )
    return stats


# ═══════════════════════════════════════════════════════════════════
#  TF-IDF COSINE SIMILARITY — Pure Python, no sklearn needed
# ═══════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """Lowercase tokenize, remove short words and stopwords."""
    STOP = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "not", "no", "this", "that",
        "these", "those", "it", "its", "i", "my", "me", "we", "our", "you",
        "your", "he", "she", "they", "them", "their", "as", "if", "then",
        "than", "so", "such", "very", "also", "just", "about", "into",
        "over", "after", "before", "between", "through", "during", "up",
        "out", "all", "each", "every", "both", "few", "more", "most",
        "other", "some", "any", "only", "same", "new", "well", "etc",
        "using", "used", "use", "including", "across", "per",
    }
    words = re.findall(r"[a-z][a-z0-9+#.-]{1,30}", text.lower())
    return [w for w in words if w not in STOP]


def _build_tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    """
    Compute TF-IDF vectors for a list of tokenized documents.
    Returns list of {term: tfidf_weight} dicts.
    """
    n_docs = len(docs)
    if n_docs == 0:
        return []

    # Document frequency
    df = Counter()
    for doc in docs:
        df.update(set(doc))

    # IDF
    idf = {}
    for term, count in df.items():
        idf[term] = math.log((n_docs + 1) / (count + 1)) + 1  # smooth IDF

    # TF-IDF per document
    vectors = []
    for doc in docs:
        tf = Counter(doc)
        total = len(doc) or 1
        vec = {}
        for term, count in tf.items():
            vec[term] = (count / total) * idf.get(term, 1.0)
        vectors.append(vec)

    return vectors


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    # Dot product
    common = set(a.keys()) & set(b.keys())
    dot = sum(a[k] * b[k] for k in common)

    # Magnitudes
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def compare_resumes(
    version_key_a: str,
    version_key_b: str,
    db_path: str = None,
) -> dict:
    """
    Compare two resume versions using TF-IDF cosine similarity.

    Returns:
        {
            "similarity": 0.847,
            "version_a": "gs_data",
            "version_b": "meta_ml",
            "shared_skills": ["python", "sql", "spark"],
            "only_a": ["kafka", "azure"],
            "only_b": ["pytorch", "tensorflow"],
            "interpretation": "Very similar (85%) — minor skill differences"
        }
    """
    if not db_path:
        db_path = os.environ.get(
            "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
        )

    from storage.db import get_conn, get_resume_version
    conn = get_conn(db_path)
    rv_a = get_resume_version(conn, version_key_a)
    rv_b = get_resume_version(conn, version_key_b)
    conn.close()

    if not rv_a:
        return {"error": f"Resume version '{version_key_a}' not found"}
    if not rv_b:
        return {"error": f"Resume version '{version_key_b}' not found"}

    text_a = rv_a.get("resume_text", "")
    text_b = rv_b.get("resume_text", "")

    if not text_a or not text_b:
        return {"error": "One or both resumes have no text content"}

    # Tokenize and compute TF-IDF
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    vectors = _build_tfidf([tokens_a, tokens_b])
    sim = round(_cosine_sim(vectors[0], vectors[1]), 4)

    # Skill diff
    skills_a = set(rv_a.get("extracted_skills", []))
    skills_b = set(rv_b.get("extracted_skills", []))

    # Top differentiating terms (highest TF-IDF delta)
    all_terms = set(vectors[0].keys()) | set(vectors[1].keys())
    deltas = []
    for term in all_terms:
        va = vectors[0].get(term, 0)
        vb = vectors[1].get(term, 0)
        if abs(va - vb) > 0.005:
            deltas.append({"term": term, "weight_a": round(va, 4), "weight_b": round(vb, 4), "delta": round(va - vb, 4)})
    deltas.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # Interpretation
    if sim >= 0.90:
        interp = f"Near identical ({sim*100:.0f}%) — these are minor variants"
    elif sim >= 0.75:
        interp = f"Very similar ({sim*100:.0f}%) — tailored sections differ"
    elif sim >= 0.55:
        interp = f"Moderately similar ({sim*100:.0f}%) — significant customization"
    elif sim >= 0.35:
        interp = f"Different ({sim*100:.0f}%) — substantially different focus"
    else:
        interp = f"Very different ({sim*100:.0f}%) — likely different roles/formats"

    return {
        "similarity": sim,
        "similarity_pct": round(sim * 100, 1),
        "version_a": {
            "key": version_key_a,
            "display": rv_a.get("display_name", version_key_a),
            "skills": sorted(skills_a),
            "char_count": len(text_a),
            "word_count": len(tokens_a),
        },
        "version_b": {
            "key": version_key_b,
            "display": rv_b.get("display_name", version_key_b),
            "skills": sorted(skills_b),
            "char_count": len(text_b),
            "word_count": len(tokens_b),
        },
        "shared_skills": sorted(skills_a & skills_b),
        "only_a": sorted(skills_a - skills_b),
        "only_b": sorted(skills_b - skills_a),
        "top_differences": deltas[:20],
        "interpretation": interp,
    }


def compare_resume_to_job(
    version_key: str,
    job_description: str,
    db_path: str = None,
) -> dict:
    """
    Compare a resume version against a job description.

    Returns fit score + missing skills + keyword gaps.
    """
    if not db_path:
        db_path = os.environ.get(
            "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
        )

    from storage.db import get_conn, get_resume_version
    from storage.profile_manager import extract_skills_from_resume

    conn = get_conn(db_path)
    rv = get_resume_version(conn, version_key)
    conn.close()

    if not rv:
        return {"error": f"Resume version '{version_key}' not found"}

    resume_text = rv.get("resume_text", "")
    if not resume_text:
        return {"error": "Resume has no text content"}

    # TF-IDF similarity
    tokens_resume = _tokenize(resume_text)
    tokens_job = _tokenize(job_description)
    vectors = _build_tfidf([tokens_resume, tokens_job])
    sim = round(_cosine_sim(vectors[0], vectors[1]), 4)

    # Skill gap analysis
    resume_skills = set(rv.get("extracted_skills", []))
    job_skills = set(extract_skills_from_resume(job_description))

    matched = resume_skills & job_skills
    missing = job_skills - resume_skills
    extra = resume_skills - job_skills

    # Keywords in job but not in resume (beyond formal skills)
    job_terms = set(tokens_job)
    resume_terms = set(tokens_resume)
    keyword_gaps = sorted(job_terms - resume_terms)[:30]

    # Fit interpretation
    match_pct = round(len(matched) / max(len(job_skills), 1) * 100)
    if match_pct >= 80:
        fit = f"Strong fit ({match_pct}% skill match)"
    elif match_pct >= 60:
        fit = f"Good fit ({match_pct}% skill match) — address {len(missing)} gaps"
    elif match_pct >= 40:
        fit = f"Moderate fit ({match_pct}% skill match) — customize resume"
    else:
        fit = f"Weak fit ({match_pct}% skill match) — consider different version"

    return {
        "tfidf_similarity": sim,
        "skill_match_pct": match_pct,
        "fit": fit,
        "resume_version": version_key,
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "extra_skills": sorted(extra),
        "keyword_gaps": keyword_gaps[:20],
        "recommendation": (
            "This resume version is a good match."
            if match_pct >= 70
            else f"Consider adding: {', '.join(sorted(missing)[:5])}"
        ),
    }


def find_best_resume_for_job(
    job_description: str,
    db_path: str = None,
) -> list[dict]:
    """
    Rank all resume versions against a job description.
    Returns sorted list: best fit first.
    """
    if not db_path:
        db_path = os.environ.get(
            "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
        )

    from storage.db import get_conn, list_resume_versions
    from storage.profile_manager import extract_skills_from_resume

    conn = get_conn(db_path)
    versions = list_resume_versions(conn)
    conn.close()

    if not versions:
        return []

    job_skills = set(extract_skills_from_resume(job_description))
    tokens_job = _tokenize(job_description)

    results = []
    all_docs = [_tokenize(v.get("resume_text", "")) for v in versions] + [tokens_job]
    tfidf_vecs = _build_tfidf(all_docs)
    job_vec = tfidf_vecs[-1]

    for i, v in enumerate(versions):
        resume_skills = set(v.get("extracted_skills", []))
        matched = resume_skills & job_skills
        missing = job_skills - resume_skills
        sim = round(_cosine_sim(tfidf_vecs[i], job_vec), 4)

        # Combined score: 60% skill match + 40% TF-IDF
        skill_pct = len(matched) / max(len(job_skills), 1)
        combined = round(0.6 * skill_pct + 0.4 * sim, 4)

        results.append({
            "version_key": v["version_key"],
            "display_name": v.get("display_name", v["version_key"]),
            "combined_score": combined,
            "tfidf_similarity": sim,
            "skill_match_pct": round(skill_pct * 100),
            "matched_skills": sorted(matched),
            "missing_skills": sorted(missing),
        })

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════════
#  REINDEX — rebuild TF-IDF matrix from disk
# ═══════════════════════════════════════════════════════════════════

def rebuild_index() -> dict:
    """
    Re-read every .txt file in resume_vault/text/, retokenize, and recompute
    the TF-IDF matrix. The vault has no persistent in-memory cache today
    (every compare/best-match call rebuilds on demand), so this primarily
    serves as a non-destructive warmup + sanity check after bulk-importing
    new PDFs.

    Returns {"indexed": N, "files_scanned": M}.
    """
    backend = get_vault_backend()
    text_entries = backend.list_texts()

    docs: list[list[str]] = []
    indexed = 0
    for entry in text_entries:
        version_key = entry["key"][:-len(".txt")] if entry["key"].endswith(".txt") else entry["key"]
        try:
            text = backend.read_text(version_key) or ""
            tokens = _tokenize(text)
            if tokens:
                docs.append(tokens)
                indexed += 1
        except Exception as e:
            log.warning("rebuild_index: skipping %s (%s)", entry["key"], e.__class__.__name__)

    if docs:
        _build_tfidf(docs)  # exercise the matrix build; result discarded
    log.info("Vault reindex: %d/%d files indexed", indexed, len(text_entries))
    return {"indexed": indexed, "files_scanned": len(text_entries)}


# ═══════════════════════════════════════════════════════════════════
#  VAULT STATS
# ═══════════════════════════════════════════════════════════════════

def vault_stats(db_path: str = None) -> dict:
    """Summary stats about the resume vault."""
    backend = get_vault_backend()
    pdfs = backend.list_pdfs()
    texts = backend.list_texts()
    total_size = sum(p["size"] for p in pdfs)

    # Parse companies from filenames
    companies = set()
    for entry in pdfs:
        meta = parse_resume_filename(entry["key"])
        companies.add(meta["company"])

    # DB stats — only meaningful when the metadata DB is up. On
    # ephemeral hosts (Render free tier) this can be 0 while the
    # backend still has files, which is the signal for a lazy
    # rehydrate (see ``rehydrate_metadata_from_vault``).
    db_versions = 0
    if db_path:
        try:
            from storage.db import get_conn, list_resume_versions
            conn = get_conn(db_path)
            db_versions = len(list_resume_versions(conn))
            conn.close()
        except Exception:
            pass

    return {
        **backend.describe(),
        "pdf_count": len(pdfs),
        "text_count": len(texts),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "unique_companies": len(companies),
        "companies": sorted(companies),
        "db_versions": db_versions,
        # Back-compat alias — callers used to read ``vault_path``.
        "vault_path": backend.describe().get("vault_dir") or backend.describe().get("bucket", ""),
    }


# ═══════════════════════════════════════════════════════════════════
#   METADATA REHYDRATION (ephemeral-DB recovery)
# ═══════════════════════════════════════════════════════════════════

def rehydrate_metadata_from_vault(db_path: str = None) -> dict:
    """Rebuild ``resume_versions`` rows from the vault backend.

    On Render's free tier the SQLite database is wiped on every cold
    start, but the R2 vault survives. This function walks the backend's
    PDF + text listings and re-creates one ``resume_versions`` row per
    file, sourcing text from the matching ``text/<key>.txt`` blob (or
    re-extracting from the PDF if the text blob is missing).

    Idempotent: existing rows are upserted with the same content, so
    re-running on a warm DB is a no-op aside from updating
    ``updated_at`` to the file's mtime.

    Intended call sites:
      * Server startup hook (when ``VAULT_BACKEND=r2``)
      * ``/api/vault/rehydrate`` admin endpoint (TODO if needed)

    Returns ``{"rehydrated": N, "skipped": M, "errors": K}``.
    """
    if not db_path:
        db_path = os.environ.get(
            "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
        )

    from storage.db import get_conn, upsert_resume_version
    from storage.profile_manager import extract_skills_from_resume

    backend = get_vault_backend()
    conn = get_conn(db_path)
    rehydrated, skipped, errors = 0, 0, 0

    for entry in backend.list_pdfs():
        fname = entry["key"]
        try:
            meta = parse_resume_filename(fname)
            version_key = meta["version_key"]

            text = backend.read_text(version_key)
            if text is None:
                # Text blob missing — fall back to re-extracting from
                # the PDF. Costlier (one extra GET + pypdf parse per
                # entry) but resilient against partial writes.
                pdf_bytes = backend.read_pdf(fname)
                text = extract_text_from_pdf_bytes(pdf_bytes, source=fname)
                if text.strip():
                    backend.write_text(version_key, text, mtime=None)

            if not text.strip():
                log.warning("rehydrate: empty text for %s, skipping", fname)
                skipped += 1
                continue

            skills = extract_skills_from_resume(text)
            upsert_resume_version(
                conn,
                version_key=version_key,
                display_name=meta["display_name"],
                resume_text=text,
                skills=skills,
                target_roles=[meta["role"]] if meta.get("role") else [],
                target_companies=[meta["company"]] if meta.get("company") else [],
                notes=f"Rehydrated from vault: {fname}",
                submitted_at=entry["mtime"],
            )
            rehydrated += 1
        except Exception as e:
            log.error("rehydrate: failed on %s: %s", fname, e)
            errors += 1

    conn.commit()
    conn.close()
    log.info("Vault rehydrate: %d rehydrated, %d skipped, %d errors",
             rehydrated, skipped, errors)
    return {"rehydrated": rehydrated, "skipped": skipped, "errors": errors}
