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
"""

import base64
import logging
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

vault_bp = Blueprint("vault", __name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db"))


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

    if not company:
        return jsonify({"error": "company is required"}), 400

    result = save_pdf_to_vault(
        pdf_bytes=pdf_bytes,
        company=company,
        role=role,
        original_filename=filename,
        db_path=DB_PATH,
    )
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

    result = compare_resume_to_job(vk, jd, db_path=DB_PATH)
    return jsonify(result), 200


@vault_bp.route("/api/vault/best-match", methods=["POST", "OPTIONS"])
def vault_best_match():
    """
    Rank all resume versions against a job description. Best fit first.

    JSON body:
        {"job_description": "We are looking for a Senior Data Engineer..."}
    """
    if request.method == "OPTIONS":
        return "", 200

    from storage.resume_vault import find_best_resume_for_job

    data = request.get_json(force=True)
    jd = data.get("job_description", "").strip()
    if not jd:
        return jsonify({"error": "job_description required"}), 400

    results = find_best_resume_for_job(jd, db_path=DB_PATH)
    return jsonify({"count": len(results), "rankings": results}), 200


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
        from storage.profile_manager import delete_resume_version
        delete_resume_version(version_key, db_path=DB_PATH)
        return jsonify({"status": "deleted", "version_key": version_key}), 200


@vault_bp.after_request
def vault_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response
