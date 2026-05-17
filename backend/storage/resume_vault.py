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
    """Create vault directory if it doesn't exist."""
    os.makedirs(VAULT_DIR, exist_ok=True)
    os.makedirs(os.path.join(VAULT_DIR, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(VAULT_DIR, "text"), exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  NAMING CONVENTION PARSER
# ═══════════════════════════════════════════════════════════════════

# Company alias map (your filenames → canonical names)
COMPANY_ALIASES = {
    "gs": "Goldman Sachs", "gsjc": "Goldman Sachs",
    "jpmc": "JPMorgan Chase", "jpmorgan": "JPMorgan Chase",
    "bofa": "Bank of America", "bankofamerica": "Bank of America",
    "ms": "Morgan Stanley", "morganstanley": "Morgan Stanley",
    "aexp": "American Express", "americanexpress": "American Express",
    "capitalone": "Capital One", "capital_one": "Capital One",
    "wellsfargo": "Wells Fargo",
    "meta": "Meta", "facebook": "Meta",
    "disney": "Disney", "walt_disney": "Disney",
    "sf": "Salesforce", "salesforce": "Salesforce",
    "qt": "Quantitative Trading",
    "sams": "Sam's Club",
    "at&t": "AT&T", "att": "AT&T",
    "ibm": "IBM", "ea": "Electronic Arts",
    "cvs": "CVS Health",
}

# Role alias map (filename suffixes → canonical role names)
ROLE_ALIASES = {
    "de": "Data Engineer", "data": "Data Engineer",
    "ml": "ML Engineer", "ai": "AI Engineer",
    "sde": "Software Engineer", "se": "Software Engineer", "be": "Backend Engineer",
    "ds": "Data Scientist", "dq": "Data Quality",
    "ae": "Analytics Engineer",
    "quant": "Quant Strategist", "aiq": "AI Quant",
}


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
    clean = stem
    used_naren_prefix = False  # Naren_ has role-first pattern
    for prefix in ["Narendranath_Edara_", "Narendranath_", "NarendranathE_",
                    "NarenML_", "Narendra_", "Resume_"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    else:
        # Check Naren_ separately (role-first: Naren_DE_affirm)
        if clean.startswith("Naren_"):
            clean = clean[len("Naren_"):]
            used_naren_prefix = True

    # Split on underscores
    parts = [p.strip() for p in clean.split("_") if p.strip()]
    if not parts:
        # Fallback for files like "bloomberg ai.pdf"
        parts = [p.strip() for p in clean.split() if p.strip()]
    if not parts:
        parts = ["unknown"]

    # ─── Multi-word company detection ────────────────────
    # Known multi-word companies that appear as consecutive parts
    MULTI_WORD = {
        ("goldman", "sachs"): "Goldman Sachs",
        ("capital", "one"): "Capital One",
        ("bank", "of", "america"): "Bank of America",
        ("morgan", "stanley"): "Morgan Stanley",
        ("american", "express"): "American Express",
        ("wells", "fargo"): "Wells Fargo",
        ("walt", "disney"): "Disney",
        ("goldman", "sachs", "ai"): None,  # don't merge 3-word, let role pick up "ai"
    }

    company_parts = []
    role_parts = []
    company_done = False
    i = 0

    # Check for 2-word company match at start
    if len(parts) >= 2:
        two = (parts[0].lower(), parts[1].lower())
        if two in MULTI_WORD:
            company_parts = [MULTI_WORD[two]]
            i = 2
            company_done = True

    if not company_done:
        # Naren_ prefix: first part is role if it's a known role abbreviation
        if used_naren_prefix and len(parts) >= 2 and parts[0].lower() in ROLE_ALIASES:
            role_parts = [parts[0]]
            company_parts = [parts[1]]
            i = 2
            company_done = True
            # Remaining parts go to role
            role_parts.extend(parts[i:])
            i = len(parts)
        else:
            company_parts = [parts[0]]
            i = 1
            company_done = True

    # Everything after company is role
    if i < len(parts):
        role_parts.extend(parts[i:])

    # ─── Resolve aliases ─────────────────────────────────
    company_raw = "_".join(company_parts)
    role_raw = "_".join(role_parts) if role_parts else None

    # Company alias (check both original and lowered)
    company = company_raw
    if company_raw.lower() in COMPANY_ALIASES:
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
        from pypdf import PdfReader
    except ImportError:
        log.error("pypdf not installed — run: pip install pypdf")
        return ""

    try:
        reader = PdfReader(pdf_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        text = "\n\n".join(text_parts)
        log.info("Extracted %d chars from %s (%d pages)", len(text), pdf_path, len(reader.pages))
        return text
    except Exception as e:
        log.error("Failed to extract text from %s: %s", pdf_path, e)
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

    _ensure_vault()

    # Generate canonical filename (sanitizes company/role internally —
    # raises ValueError if either resolves to an empty string).
    fname = canonical_filename(company, role, ".pdf")
    vault_path = os.path.join(VAULT_DIR, "pdf", fname)

    # Issue #35: realpath assertion. Even if canonical_filename were buggy
    # and let a "../" slip through, os.path.realpath of the destination
    # must stay strictly under the realpath of the vault directory. We
    # compare with a trailing separator so /tmp/vault_evil isn't accepted
    # as a sub-path of /tmp/vault.
    vault_pdf_dir = os.path.realpath(os.path.join(VAULT_DIR, "pdf"))
    resolved = os.path.realpath(vault_path)
    if not (resolved == vault_pdf_dir or
            resolved.startswith(vault_pdf_dir + os.sep)):
        raise ValueError(
            f"refusing to write outside vault: {resolved!r} not under {vault_pdf_dir!r}"
        )

    # Write PDF
    with open(vault_path, "wb") as f:
        f.write(pdf_bytes)
    log.info("Saved PDF: %s (%d bytes)", vault_path, len(pdf_bytes))

    # Extract text
    text = extract_text_from_pdf(vault_path)
    meta = parse_resume_filename(fname)
    version_key = meta["version_key"]

    # Save extracted text
    text_path = os.path.join(VAULT_DIR, "text", f"{version_key}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

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
    """List all files in the vault with metadata."""
    _ensure_vault()
    pdf_dir = os.path.join(VAULT_DIR, "pdf")
    results = []

    for fname in sorted(os.listdir(pdf_dir)):
        if not fname.lower().endswith(".pdf"):
            continue
        fpath = os.path.join(pdf_dir, fname)
        meta = parse_resume_filename(fname)
        stat = os.stat(fpath)
        meta["size_bytes"] = stat.st_size
        meta["size_kb"] = round(stat.st_size / 1024, 1)
        meta["modified_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        meta["vault_path"] = fpath
        results.append(meta)

    return results


def _safe_unlink_in_vault(path: str) -> bool:
    """
    Delete a file only if its resolved (realpath) location is inside VAULT_DIR.

    Defense against path-traversal: even if `path` was built from user input
    that included `..` or symlinks, realpath() collapses those — if the result
    escapes the vault directory, we refuse to unlink.

    Returns True if a file was deleted, False if it did not exist.
    Raises ValueError if the resolved path is outside the vault.
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

    # Block obvious traversal attempts at the key level before touching disk.
    # Flask's default <string:> converter already strips '/', but URL-encoded
    # variants or future routing changes could let them through.
    if "/" in version_key or "\\" in version_key or ".." in version_key:
        raise ValueError(f"Invalid version_key: {version_key!r}")

    _ensure_vault()

    if not db_path:
        db_path = os.environ.get(
            "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
        )

    pdf_dir = os.path.join(VAULT_DIR, "pdf")
    text_dir = os.path.join(VAULT_DIR, "text")

    # Locate the PDF whose parsed filename → this version_key.
    pdf_path = None
    try:
        for fname in os.listdir(pdf_dir):
            if not fname.lower().endswith(".pdf"):
                continue
            meta = parse_resume_filename(fname)
            if meta.get("version_key") == version_key:
                pdf_path = os.path.join(pdf_dir, fname)
                break
    except FileNotFoundError:
        pdf_path = None

    text_path = os.path.join(text_dir, f"{version_key}.txt")

    # Round 2 Fix #3: propagate OSError so the DB row stays put when an
    # unlink fails. The previous behaviour (swallow + log warning + still
    # delete the row) directly contradicted the docstring's "filesystem
    # failure does not orphan the row" promise — the row was orphaned the
    # OTHER way: file on disk, row gone, vault permanently un-listable.
    pdf_deleted = False
    if pdf_path:
        pdf_deleted = _safe_unlink_in_vault(pdf_path)

    text_deleted = _safe_unlink_in_vault(text_path)

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
    _ensure_vault()
    source = Path(source_dir)
    if not source.exists():
        return {"error": f"Directory not found: {source_dir}", "imported": 0}

    from storage.profile_manager import extract_skills_from_resume

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

            # Copy PDF to vault
            if fpath.suffix.lower() == ".pdf":
                dest = os.path.join(VAULT_DIR, "pdf", fpath.name)
                if not os.path.exists(dest):
                    shutil.copy2(str(fpath), dest)

                # Extract text
                text = extract_text_from_pdf(dest)
            elif fpath.suffix.lower() == ".docx":
                # Extract text from docx (don't copy to pdf vault)
                text = extract_text_from_docx(str(fpath))
            else:
                stats["skipped"] += 1
                continue

            if not text.strip():
                log.warning("No text extracted from %s — skipping DB", fpath.name)
                stats["skipped"] += 1
                continue

            # Save extracted text
            text_path = os.path.join(VAULT_DIR, "text", f"{version_key}.txt")
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(text)

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
    _ensure_vault()
    text_dir = os.path.join(VAULT_DIR, "text")
    files = sorted(f for f in os.listdir(text_dir) if f.lower().endswith(".txt"))

    docs: list[list[str]] = []
    indexed = 0
    for name in files:
        try:
            with open(os.path.join(text_dir, name), "r",
                      encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            tokens = _tokenize(text)
            if tokens:
                docs.append(tokens)
                indexed += 1
        except Exception as e:
            log.warning("rebuild_index: skipping %s (%s)", name, e.__class__.__name__)

    if docs:
        _build_tfidf(docs)  # exercise the matrix build; result discarded
    log.info("Vault reindex: %d/%d files indexed", indexed, len(files))
    return {"indexed": indexed, "files_scanned": len(files)}


# ═══════════════════════════════════════════════════════════════════
#  VAULT STATS
# ═══════════════════════════════════════════════════════════════════

def vault_stats(db_path: str = None) -> dict:
    """Summary stats about the resume vault."""
    _ensure_vault()
    pdf_dir = os.path.join(VAULT_DIR, "pdf")
    text_dir = os.path.join(VAULT_DIR, "text")

    pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    texts = [f for f in os.listdir(text_dir) if f.lower().endswith(".txt")]

    total_size = sum(os.path.getsize(os.path.join(pdf_dir, f)) for f in pdfs)

    # Parse companies from filenames
    companies = set()
    for f in pdfs:
        meta = parse_resume_filename(f)
        companies.add(meta["company"])

    # DB stats
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
        "vault_path": VAULT_DIR,
        "pdf_count": len(pdfs),
        "text_count": len(texts),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "unique_companies": len(companies),
        "companies": sorted(companies),
        "db_versions": db_versions,
    }
