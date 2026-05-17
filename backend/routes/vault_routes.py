"""
Resume Vault API — Flask Blueprint for resume vault endpoints.

Plug into your existing server.py with:
    from routes.vault_routes import vault_bp
    app.register_blueprint(vault_bp)

Endpoints:
    POST   /api/vault/upload        — Upload PDF + save to vault
    GET    /api/vault/list           — List all vault files with metadata
    POST   /api/vault/import         — Bulk import from a local directory
    POST   /api/vault/compare        — Compare two resume versions (TF-IDF)
    POST   /api/vault/job-fit        — Compare resume vs job description
    POST   /api/vault/best-match     — Rank all resumes against a job description
    GET    /api/vault/stats          — Vault summary stats
    GET    /api/vault/version/<key>  — Get a specific resume version details
    DELETE /api/vault/version/<key>  — Delete a resume version

Security (issues #34, #35, #36 + Round 2 hardening):
    - All endpoints require ``Authorization: Bearer <API_SECRET>`` when
      ``API_SECRET`` is set. When ``API_SECRET`` is unset the blueprint
      logs a startup warning and lets requests through so local dev keeps
      working unchanged.
    - Bearer scheme is case-insensitive (RFC 7235) and the token is
      compared with ``secrets.compare_digest`` to defeat timing attacks.
    - ``API_SECRET`` is ``.strip()``ed at import so trailing whitespace in
      ``.env`` files doesn't silently invalidate every request.
    - Auth failures are logged with the source IP + path (but NOT the
      offending token) so operators can detect brute-force attempts.
    - CORS origins are restricted to ``ALLOWED_ORIGINS`` (comma-separated
      env var) when configured; otherwise it falls back to ``*`` with a
      startup warning. ``Authorization`` is always advertised in
      ``Access-Control-Allow-Headers`` so the Bearer header survives
      preflight. ``Allow-Credentials: true`` is only emitted alongside a
      specific allowlisted origin — never with ``*`` (browsers reject
      that combination silently).
    - Upload payloads are size-capped (10 MB) and magic-byte validated
      (``%PDF-``) at the route layer before they ever hit the vault writer.
    - ``company`` / ``role`` strings are length-capped at 80 chars before
      reaching ``canonical_filename``; the helper itself sanitizes the
      remaining input down to ``[A-Za-z0-9_-]`` and ``save_pdf_to_vault``
      asserts ``realpath()`` stays inside the vault dir.
"""

import base64
import logging
import os
import re
import secrets

from flask import Blueprint, jsonify, request, send_file

log = logging.getLogger(__name__)

vault_bp = Blueprint("vault", __name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db"))
# .strip() so trailing whitespace from .env files / shell exports doesn't
# silently invalidate every auth attempt with a mysterious 401.
API_SECRET = os.environ.get("API_SECRET", "").strip()

# RFC 7235 says the auth scheme is case-insensitive ("Bearer" / "bearer"
# / "BEARER" are all valid). Pre-compiled so the per-request hot path is
# a single regex match against the header.
_BEARER_RE = re.compile(r"^Bearer\s+(\S+)\s*$", re.IGNORECASE)

# 10 MB cap matches save_pdf_to_vault's own limit; we enforce it here too so
# we never base64-decode + buffer a megabyte payload that we'd just reject.
MAX_PDF_BYTES = 10_000_000
# Defense-in-depth length cap; canonical_filename sanitizes the content,
# but rejecting early gives the caller a clearer error and avoids spending
# CPU on absurd inputs.
MAX_FIELD_LEN = 80
# Issue #41 — job_description payload cap.
# /api/vault/best-match runs TF-IDF over the whole vault (~95 resumes) +
# the JD, so its compute cost scales with len(jd). Without a cap, a single
# multi-megabyte string forces a full tokenization + TF-IDF rebuild +
# N cosine sims — the highest-leverage DoS vector against the free-tier
# Render dyno. 50_000 chars ≈ 10k tokens is roomy for any real JD
# (the longest staffing pages on the public ATSes top out around 8k chars).
MAX_JD_BYTES = 50_000

# Comma-separated list of allowed origins. Empty/unset = legacy "*" with warning.
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# Emit startup advisories exactly once so operators notice misconfigured envs.
if not API_SECRET:
    log.warning(
        "vault_routes: API_SECRET is unset — vault endpoints are UNAUTHENTICATED "
        "(dev mode). Set API_SECRET in production."
    )
if not ALLOWED_ORIGINS:
    log.warning(
        "vault_routes: ALLOWED_ORIGINS is unset — falling back to Access-Control-"
        "Allow-Origin: * for vault endpoints. Set ALLOWED_ORIGINS in production."
    )


def _check_auth() -> bool:
    """Bearer-token gate. Returns True when the request is allowed.

    Mirrors the helper in routes/admin_routes.py and server._check_api_secret:
    if API_SECRET is unset we accept everything (dev mode); otherwise the
    request must carry ``Authorization: Bearer <API_SECRET>``.

    Hardening (Round 2):
    - Token extracted via case-insensitive regex (RFC 7235 says the scheme
      is case-insensitive). ``Authorization: bearer foo`` is now valid.
    - Comparison uses ``secrets.compare_digest`` to defeat timing
      side-channel leaks. A naïve ``==`` returns as soon as the first
      mismatched byte is found, which over many requests reveals the
      secret one byte at a time.
    """
    if not API_SECRET:
        return True
    m = _BEARER_RE.match(request.headers.get("Authorization", ""))
    if not m:
        return False
    token = m.group(1)
    return secrets.compare_digest(token.encode("utf-8"), API_SECRET.encode("utf-8"))


@vault_bp.before_request
def _vault_require_auth():
    """Gate every vault endpoint behind the Bearer-token check.

    OPTIONS requests are allowed through unconditionally — browsers send
    them without the Authorization header during CORS preflight, so a 401
    here would break the dashboard before the real request ever leaves the
    browser. The actual POST/GET/DELETE that follows still hits this hook.
    """
    if request.method == "OPTIONS":
        return None
    if not _check_auth():
        # Log the failure so operators can detect brute-force attempts.
        # Deliberately DO NOT log the offending token — that would shovel
        # near-miss guesses into log aggregators, defeating the secret.
        log.warning(
            "vault auth rejected from %s for %s",
            request.remote_addr,
            request.path,
        )
        return jsonify({"error": "unauthorized"}), 401
    return None

_TOP_N_CAP = 50


def _parse_top_n(raw):
    """Return validated top_n int (1..cap), or None for "use default = all".

    Lenient on garbage types (bool, non-integral float, str, list, dict, <=0):
    callers get all rankings. Strict on overflow: ``raw > _TOP_N_CAP`` raises
    ``ValueError`` so the route can return 400.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, float):
        if not raw.is_integer():
            return None
        raw = int(raw)
    if not isinstance(raw, int) or raw <= 0:
        return None
    if raw > _TOP_N_CAP:
        raise ValueError(raw)
    return raw


@vault_bp.route("/api/vault/upload", methods=["POST", "OPTIONS"])
def vault_upload():
    """
    Upload a PDF resume to the vault.

    Accepts JSON:
        {
            "pdf_base64": "<base64 encoded PDF>",
            "company": "Goldman Sachs",
            "role": "Data Engineer",        // optional
            "filename": "original.pdf"      // optional
        }

    OR multipart form with file field "pdf" + form fields "company", "role".
    """
    if request.method == "OPTIONS":
        return "", 200

    from storage.resume_vault import save_pdf_to_vault

    if request.content_type and "multipart" in request.content_type:
        pdf_file = request.files.get("pdf")
        if not pdf_file:
            return jsonify({"error": "No PDF file provided"}), 400
        pdf_bytes = pdf_file.read()
        company = request.form.get("company", "").strip()
        role = request.form.get("role", "").strip() or None
        filename = pdf_file.filename
        submitted_at = request.form.get("submitted_at", "").strip() or None
    else:
        data = request.get_json(force=True)
        b64 = data.get("pdf_base64", "")
        if not b64:
            return jsonify({"error": "pdf_base64 required"}), 400
        try:
            pdf_bytes = base64.b64decode(b64)
        except Exception as e:
            return jsonify({"error": f"Invalid base64: {e}"}), 400
        company = data.get("company", "").strip()
        role = data.get("role", "").strip() or None
        filename = data.get("filename", "")
        submitted_at = (data.get("submitted_at") or "").strip() or None

    if not company:
        return jsonify({"error": "company is required"}), 400

    # Validate submitted_at: must be ISO 8601, year >= 2000, not in the
    # future (allow 1 day of clock skew). list_vault() returns this as
    # modified_at; bad values would pollute the dashboard's sort order.
    if submitted_at is not None:
        from datetime import datetime, timezone, timedelta
        try:
            dt = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": f"submitted_at must be ISO 8601 (got {submitted_at!r})"}), 400
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if dt > now + timedelta(days=1):
            return jsonify({"error": f"submitted_at is in the future: {submitted_at}"}), 400
        if dt < datetime(2000, 1, 1, tzinfo=timezone.utc):
            return jsonify({"error": f"submitted_at is before 2000: {submitted_at}"}), 400
        submitted_at = dt.isoformat()

    # Issue #35: length cap before the path is built. canonical_filename also
    # sanitizes, but capping at the route layer gives a clearer error and
    # avoids huge synthetic inputs.
    if len(company) > MAX_FIELD_LEN:
        return jsonify({
            "error": f"company too long (max {MAX_FIELD_LEN} chars, got {len(company)})"
        }), 400
    if role is not None and len(role) > MAX_FIELD_LEN:
        return jsonify({
            "error": f"role too long (max {MAX_FIELD_LEN} chars, got {len(role)})"
        }), 400

    # Issue #36: magic-byte + size validation before we hand bytes to
    # save_pdf_to_vault. Size first (cheapest), then magic bytes.
    if len(pdf_bytes) > MAX_PDF_BYTES:
        return jsonify({
            "error": f"PDF too large: {len(pdf_bytes)} bytes (max {MAX_PDF_BYTES})",
        }), 413
    if not pdf_bytes.startswith(b"%PDF-"):
        return jsonify({"error": "not a PDF (missing %PDF- magic bytes)"}), 400

    try:
        result = save_pdf_to_vault(
            pdf_bytes=pdf_bytes,
            company=company,
            role=role,
            original_filename=filename,
            db_path=DB_PATH,
            submitted_at=submitted_at,
        )
    except ValueError as e:
        # canonical_filename rejects fully-sanitized-to-empty names, and
        # save_pdf_to_vault raises ValueError if the realpath assertion fails.
        return jsonify({"error": str(e)}), 400
    return jsonify(result), 200


@vault_bp.route("/api/vault/list", methods=["GET"])
def vault_list():
    """List all PDFs in the vault with parsed metadata."""
    from storage.resume_vault import list_vault
    files = list_vault()
    return jsonify({"count": len(files), "files": files}), 200


@vault_bp.route("/api/vault/import", methods=["POST", "OPTIONS"])
def vault_import():
    """
    Bulk import resumes from a local directory.

    JSON body:
        {
            "source_dir": "C:\\\\Users\\\\naren\\\\OneDrive\\\\Desktop\\\\Resume Easy",
            "extensions": [".pdf", ".docx"]   // optional
        }
    """
    if request.method == "OPTIONS":
        return "", 200

    from storage.resume_vault import bulk_import

    data = request.get_json(force=True)
    source_dir = data.get("source_dir", "").strip()
    if not source_dir:
        return jsonify({"error": "source_dir is required"}), 400

    extensions = tuple(data.get("extensions", [".pdf", ".docx"]))
    result = bulk_import(source_dir=source_dir, db_path=DB_PATH, extensions=extensions)
    return jsonify(result), 200


@vault_bp.route("/api/vault/compare", methods=["POST", "OPTIONS"])
def vault_compare():
    """
    Compare two resume versions using TF-IDF cosine similarity.

    JSON body:
        {"version_a": "gs_data", "version_b": "meta_ml"}
    """
    if request.method == "OPTIONS":
        return "", 200

    from storage.resume_vault import compare_resumes

    data = request.get_json(force=True)
    va = data.get("version_a", "").strip()
    vb = data.get("version_b", "").strip()
    if not va or not vb:
        return jsonify({"error": "version_a and version_b required"}), 400

    result = compare_resumes(va, vb, db_path=DB_PATH)
    return jsonify(result), 200


@vault_bp.route("/api/vault/job-fit", methods=["POST", "OPTIONS"])
def vault_job_fit():
    """
    Compare a resume version against a job description.

    JSON body:
        {"version_key": "gs_data", "job_description": "We are looking for..."}
    """
    if request.method == "OPTIONS":
        return "", 200

    from storage.resume_vault import compare_resume_to_job

    data = request.get_json(force=True)
    vk = data.get("version_key", "").strip()
    jd = data.get("job_description", "").strip()
    if not vk or not jd:
        return jsonify({"error": "version_key and job_description required"}), 400
    # Issue #41 — refuse oversized payloads. 413 = Payload Too Large.
    if len(jd) > MAX_JD_BYTES:
        return jsonify({
            "error": f"job_description too long ({len(jd)} chars; max {MAX_JD_BYTES})"
        }), 413

    result = compare_resume_to_job(vk, jd, db_path=DB_PATH)
    return jsonify(result), 200


@vault_bp.route("/api/vault/best-match", methods=["POST", "OPTIONS"])
def vault_best_match():
    """
    Rank all resume versions against a job description. Best fit first.

    JSON body:
        {
            "job_description": "We are looking for a Senior Data Engineer...",
            "top_n": 5    // optional, positive int <= 50; slices the rankings
        }

    Response:
        {"count": <total resumes scanned>, "rankings": [... up to top_n entries ...]}

    `count` always reflects the total number of resumes scanned (not the
    sliced length), so callers can tell whether more results exist.
    """
    if request.method == "OPTIONS":
        return "", 200

    from storage.resume_vault import find_best_resume_for_job

    data = request.get_json(force=True)
    jd = data.get("job_description", "").strip()
    if not jd:
        return jsonify({"error": "job_description required"}), 400
    # Issue #41 — refuse oversized payloads. Best-match is the most expensive
    # vault endpoint (TF-IDF rebuild over all ~95 resumes + the JD), so the
    # JD cap matters most here. 413 = Payload Too Large.
    if len(jd) > MAX_JD_BYTES:
        return jsonify({
            "error": f"job_description too long ({len(jd)} chars; max {MAX_JD_BYTES})"
        }), 413

    raw_top_n = data.get("top_n")
    try:
        top_n = _parse_top_n(raw_top_n)
    except ValueError:
        return jsonify({
            "error": f"top_n must be <= {_TOP_N_CAP} (got {raw_top_n})"
        }), 400

    results = find_best_resume_for_job(jd, db_path=DB_PATH)
    rankings = results[:top_n] if top_n is not None else results
    return jsonify({"count": len(results), "rankings": rankings}), 200


@vault_bp.route("/api/vault/stats", methods=["GET"])
def vault_stats_route():
    """Get vault summary statistics."""
    from storage.resume_vault import vault_stats
    return jsonify(vault_stats(db_path=DB_PATH)), 200


@vault_bp.route("/api/vault/version/<version_key>", methods=["GET", "DELETE", "OPTIONS"])
def vault_version(version_key):
    """Get or delete a specific resume version."""
    if request.method == "OPTIONS":
        return "", 200

    if request.method == "GET":
        from storage.db import get_conn, get_resume_version
        conn = get_conn(DB_PATH)
        rv = get_resume_version(conn, version_key)
        conn.close()
        if not rv:
            return jsonify({"error": f"Version '{version_key}' not found"}), 404
        return jsonify(rv), 200

    elif request.method == "DELETE":
        # Issue #37: also remove the PDF + text file from disk, otherwise the
        # entry resurrects on next refresh because list_vault() reads disk.
        from storage.db import get_conn, get_resume_version
        from storage.resume_vault import delete_vault_version, list_vault

        # Reject path-traversal-shaped keys BEFORE the existence check so the
        # response is 400 (malformed) instead of 404 (not found). We also
        # reject null bytes here — os.path.realpath() raises ValueError on
        # embedded nulls, and we want a 400 (client error) not a 500.
        if (
            "\x00" in version_key
            or "/" in version_key
            or "\\" in version_key
            or ".." in version_key
        ):
            return jsonify({"error": f"Invalid version_key: {version_key!r}"}), 400

        # Idempotency (Round 2): if neither a DB row nor any PDF on disk maps
        # to this key, the resource is already gone. Return 200 with
        # already_gone:true so retried DELETE calls from queues/clients are
        # safe. We only 400 on malformed keys (handled above) — 404 is no
        # longer appropriate because DELETE's post-condition (resource does
        # not exist) is satisfied.
        conn = get_conn(DB_PATH)
        rv = get_resume_version(conn, version_key)
        conn.close()
        on_disk = any(f.get("version_key") == version_key for f in list_vault())
        if not rv and not on_disk:
            return jsonify({
                "status": "deleted",
                "version_key": version_key,
                "db_row_deleted": False,
                "pdf_deleted": False,
                "text_deleted": False,
                "already_gone": True,
            }), 200

        try:
            result = delete_vault_version(version_key, db_path=DB_PATH)
        except ValueError as e:
            # R3 Fix: storage-layer ValueError messages can include absolute
            # paths (e.g. "Path /opt/x escapes vault root /opt/vault"). Log
            # the detailed message server-side, but return a generic error
            # to the client. Matches the wording used for null-byte /
            # path-traversal rejections above.
            log.warning("Vault delete '%s' rejected: %s", version_key, e)
            return jsonify({"error": "Invalid version_key"}), 400
        except OSError as e:
            # Fix #3 Option A: filesystem failure should NOT proceed with DB
            # delete. Storage layer re-raises; we surface as 500 so the row
            # stays and the client can retry. Match the docstring's promise.
            #
            # R3 Fix: PermissionError / FileNotFoundError reprs include the
            # absolute filesystem path (e.g. [Errno 13] Permission denied:
            # '/opt/render/project/resume_vault/pdf/X.pdf'). Log it, but
            # don't leak it to the client.
            log.error("Vault delete '%s' filesystem error: %s", version_key, e)
            return jsonify({"error": "Filesystem error while deleting version"}), 500

        # Fix #1: omit absolute filesystem paths from the response. The
        # booleans pdf_deleted/text_deleted already carry the "did we delete
        # it" signal, and leaking server paths (e.g. /opt/render/project/...)
        # exposes internal structure to clients. Surface only the basename of
        # the PDF for UX (which file was removed), nothing else.
        pdf_path = result.pop("pdf_path", None)
        result.pop("text_path", None)
        result["pdf_filename"] = os.path.basename(pdf_path) if pdf_path else None
        return jsonify({"status": "deleted", **result}), 200


@vault_bp.route("/api/vault/version/<version_key>/pdf", methods=["GET", "OPTIONS"])
def vault_version_pdf(version_key):
    """Stream the canonical PDF for a vault version back to the client.

    Auth: covered by the blueprint's ``before_request`` Bearer-token check.

    Path-traversal hardening mirrors the DELETE branch:
    1. Reject obviously malformed keys (``/``, ``\\``, ``..``, null byte)
       BEFORE touching disk — the response is 400 (malformed), not 404.
       Flask's default <string:> converter strips ``/`` already, but URL
       decoding / future routing changes could let them through, and null
       bytes raise ``ValueError`` deep inside ``os.path.realpath`` if we
       don't catch them up front.
    2. Look up the canonical filename via ``list_vault()`` so we never
       trust user input as a filename — only filenames that actually
       parse to this version_key are eligible.
    3. ``os.path.realpath()`` assertion against ``VAULT_DIR`` BEFORE
       ``send_file()`` — same pattern as ``_safe_unlink_in_vault``. Even
       if the parsed filename were somehow malicious, the realpath check
       guarantees we only serve files under the vault root.
    """
    if request.method == "OPTIONS":
        return "", 200

    # Step 1: reject malformed keys early so the 400 vs 404 distinction is
    # clean. Identical to the DELETE branch above.
    if (
        not version_key
        or "\x00" in version_key
        or "/" in version_key
        or "\\" in version_key
        or ".." in version_key
    ):
        return jsonify({"error": f"Invalid version_key: {version_key!r}"}), 400

    from storage.resume_vault import VAULT_DIR, list_vault

    # Step 2: locate the PDF whose parsed filename → this version_key. We
    # use list_vault() rather than reconstructing the filename from the
    # key, because the canonical-name → version_key mapping isn't always
    # invertible (filename parser handles many real-world variants).
    # list_vault() returns parse_resume_filename(...) extended with disk
    # metadata. The original filename lives under "original_filename"; the
    # full on-disk path lives under "vault_path".
    pdf_filename = None
    pdf_path = None
    for entry in list_vault():
        if entry.get("version_key") == version_key:
            pdf_filename = entry.get("original_filename")
            pdf_path = entry.get("vault_path")
            break

    if not pdf_path or not pdf_filename:
        return jsonify({"error": "Version not found"}), 404

    # Step 3: realpath assertion. Defense-in-depth — even if list_vault()
    # returned a path outside the vault (it shouldn't, but symlinks/future
    # bugs could change that), we refuse to serve it.
    vault_root = os.path.realpath(VAULT_DIR)
    target = os.path.realpath(pdf_path)
    if not (target == vault_root or target.startswith(vault_root + os.sep)):
        log.warning(
            "Vault PDF download '%s' rejected: resolved path %r escapes vault %r",
            version_key,
            target,
            vault_root,
        )
        return jsonify({"error": "Invalid version_key"}), 400

    if not os.path.exists(target):
        return jsonify({"error": "Version not found"}), 404

    return send_file(
        target,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=pdf_filename,
    )


@vault_bp.after_request
def vault_cors(response):
    # If ALLOWED_ORIGINS is configured, only echo back origins on the
    # allowlist. We compare against the request Origin header so the
    # response is dynamic per caller (a fixed list value would break
    # browsers when more than one origin is whitelisted).
    #
    # Browser CORS rule: ``Access-Control-Allow-Credentials: true`` is
    # ONLY valid alongside a specific origin — combined with ``*`` the
    # browser silently rejects the entire response. So we only emit the
    # credentials header inside the allowlist branch.
    if ALLOWED_ORIGINS:
        origin = request.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        # If the origin isn't on the allowlist we deliberately do NOT set
        # Access-Control-Allow-Origin — the browser will then block the
        # response, which is what we want.
    else:
        # Dev-mode fallback: '*' is fine for browsers that do NOT need
        # credentials. We must NOT add Allow-Credentials here or the
        # combination becomes browser-rejected.
        response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response
