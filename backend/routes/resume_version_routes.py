"""Resume version endpoints — server.py split (8/8, final extraction).

Five routes that manage the named, on-disk resume versions used by the
Tracker tab (separate from the vault, which is a content-addressed PDF
library):

    GET    /api/resume/versions                 — list all named versions
    POST   /api/resume/versions                 — save/update from text + skills
    POST   /api/resume/versions/upload          — upload PDF, extract via pypdf, save
    GET    /api/resume/versions/compare?a=&b=   — TF-IDF-free skill-overlap diff
    GET    /api/resume/versions/<key>           — fetch full text + metadata
    DELETE /api/resume/versions/<key>           — close #44: routes through
                                                  delete_vault_version for consistency
"""
import logging
import os

from flask import Blueprint, jsonify, request

from core import config as _config

log = logging.getLogger("jobscout")

resume_version_bp = Blueprint("resume_version", __name__)


@resume_version_bp.route("/api/resume/versions", methods=["GET"])
def api_list_resume_versions():
    """List all saved resume versions."""
    try:
        from storage.profile_manager import init_profile_tables, list_resume_versions
        init_profile_tables(_config.DB_PATH)
        return jsonify(list_resume_versions(_config.DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resume_version_bp.route("/api/resume/versions", methods=["POST", "OPTIONS"])
def api_save_resume_version():
    """Save/update a resume version and extract skills from resume_text."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, save_resume_version
        init_profile_tables(_config.DB_PATH)
        data = request.get_json() or {}
        if not data.get("version_key"):
            return jsonify({"error": "version_key required"}), 400
        skills = save_resume_version(data, _config.DB_PATH)
        return jsonify({
            "status": "ok",
            "version_key": data["version_key"],
            "skills_extracted": len(skills),
            "skills": skills,
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resume_version_bp.route("/api/resume/versions/upload", methods=["POST", "OPTIONS"])
def api_upload_resume_version_pdf():
    """Upload a PDF resume → extract text → save as a named version."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.profile_manager import init_profile_tables, save_resume_version
        init_profile_tables(_config.DB_PATH)

        version_key = request.form.get("version_key", "").strip()
        if not version_key:
            return jsonify({"error": "version_key required"}), 400
        if "file" not in request.files:
            return jsonify({"error": "PDF file required (field name: file)"}), 400

        file = request.files["file"]
        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only PDF files are supported"}), 400

        # Standardized on pypdf (CLAUDE.md tech-debt #3): one PDF library
        # across the whole project. Same extractor as the vault uses on disk.
        try:
            from storage.resume_vault import extract_text_from_pdf_bytes
            pdf_bytes = file.read()
            text = extract_text_from_pdf_bytes(
                pdf_bytes,
                source=f"upload:{file.filename or version_key}",
            ).strip()
        except Exception as e:
            return jsonify({"error": f"PDF extraction failed: {e}"}), 500

        if not text:
            return jsonify({"error": "Could not extract text — try pasting resume text instead"}), 422

        data = {
            "version_key": version_key,
            "display_name": request.form.get("display_name", version_key),
            "resume_text": text,
            "notes": request.form.get("notes", ""),
            "target_companies": [],
        }
        skills = save_resume_version(data, _config.DB_PATH)
        return jsonify({
            "status": "ok",
            "version_key": version_key,
            "skills_extracted": len(skills),
            "skills": skills,
            "text_length": len(text),
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resume_version_bp.route("/api/resume/versions/compare", methods=["GET"])
def api_compare_resume_versions():
    """Compare two resume versions — returns skill overlap + diffs.
    Query: ?a=<version_key>&b=<version_key>
    """
    a_key = request.args.get("a", "").strip()
    b_key = request.args.get("b", "").strip()
    if not a_key or not b_key:
        return jsonify({"error": "Query params ?a=<key>&b=<key> required"}), 400
    try:
        from storage.profile_manager import get_resume_version
        a = get_resume_version(a_key, _config.DB_PATH)
        b = get_resume_version(b_key, _config.DB_PATH)
        if not a:
            return jsonify({"error": f"Version '{a_key}' not found"}), 404
        if not b:
            return jsonify({"error": f"Version '{b_key}' not found"}), 404

        a_skills = set(a.get("extracted_skills", []))
        b_skills = set(b.get("extracted_skills", []))
        shared   = sorted(a_skills & b_skills)
        only_a   = sorted(a_skills - b_skills)
        only_b   = sorted(b_skills - a_skills)
        total    = len(a_skills | b_skills)
        similarity_pct = round(len(shared) / total * 100) if total else 0

        return jsonify({
            "a": {"version_key": a_key, "display_name": a.get("display_name", a_key), "skill_count": len(a_skills)},
            "b": {"version_key": b_key, "display_name": b.get("display_name", b_key), "skill_count": len(b_skills)},
            "similarity_pct": similarity_pct,
            "shared": shared,
            "only_a": only_a,
            "only_b": only_b,
        }), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resume_version_bp.route("/api/resume/versions/<version_key>", methods=["GET"])
def api_get_resume_version(version_key):
    """Get a specific resume version including full resume text."""
    try:
        from storage.profile_manager import get_resume_version
        v = get_resume_version(version_key, _config.DB_PATH)
        if not v:
            return jsonify({"error": "not found"}), 404
        return jsonify(v), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resume_version_bp.route("/api/resume/versions/<version_key>", methods=["DELETE", "OPTIONS"])
def api_delete_resume_version(version_key):
    """Delete a resume version by key.

    Issue #44: routes through the same ``delete_vault_version`` helper as
    ``/api/vault/version/<key>``. Previously this called the legacy
    ``profile_manager.delete_resume_version`` which only removed the DB row,
    orphaning the PDF + text files on disk — entries resurrected on the
    next vault refresh because ``list_vault()`` reads disk.

    Behavior matches the vault endpoint: malformed keys → 400, missing →
    200 with ``already_gone: true`` (idempotent for retried DELETEs),
    filesystem errors → 500 (DB row preserved so caller can retry).
    """
    if request.method == "OPTIONS":
        return "", 204

    # Reject obviously malformed keys BEFORE touching disk. Identical guard
    # to the vault DELETE branch (routes/vault_routes.py).
    if (
        not version_key
        or "\x00" in version_key
        or "/" in version_key
        or "\\" in version_key
        or ".." in version_key
    ):
        return jsonify({"error": f"Invalid version_key: {version_key!r}"}), 400, \
            {"Access-Control-Allow-Origin": "*"}

    from storage.db import get_conn, get_resume_version
    from storage.resume_vault import delete_vault_version, list_vault

    # Idempotency: if neither a DB row nor a PDF on disk maps to this key,
    # treat as success (already gone). Mirrors the vault endpoint contract.
    conn = get_conn(_config.DB_PATH)
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
        }), 200, {"Access-Control-Allow-Origin": "*"}

    try:
        result = delete_vault_version(version_key, db_path=_config.DB_PATH)
    except ValueError as e:
        # Don't leak filesystem paths from storage-layer messages.
        log.warning("Legacy delete '%s' rejected: %s", version_key, e)
        return jsonify({"error": "Invalid version_key"}), 400, \
            {"Access-Control-Allow-Origin": "*"}
    except OSError as e:
        log.error("Legacy delete '%s' filesystem error: %s", version_key, e)
        return jsonify({"error": "Filesystem error while deleting version"}), 500, \
            {"Access-Control-Allow-Origin": "*"}

    # Drop absolute paths from response; keep only basename for UX.
    pdf_path = result.pop("pdf_path", None)
    result.pop("text_path", None)
    result["pdf_filename"] = os.path.basename(pdf_path) if pdf_path else None
    return jsonify({"status": "deleted", **result}), 200, \
        {"Access-Control-Allow-Origin": "*"}
