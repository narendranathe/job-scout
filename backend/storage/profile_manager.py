"""
Profile manager — stores user profile, PIN, and resume in SQLite.

Provides skill extraction from resume text so the relevance engine can
personalise job scoring based on YOUR actual resume.

Endpoints (added to server.py):
  GET  /api/profile          — get profile (skills, preferences, dream config)
  POST /api/profile          — update preferences
  POST /api/resume           — upload resume text → extract skills
  POST /api/verify-pin       — check PIN (for dashboard lock)
  POST /api/set-pin          — set/change access PIN
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db")
)

# Iterations for pbkdf2_hmac — fast enough for a personal dashboard, slow enough
# to resist brute-force if the DB file is ever leaked.
_PIN_ITERATIONS = 200_000
_PIN_SALT = b"jobscout-pin-v1"  # fixed per-app salt (not per-user, but beats bare SHA256)

# ─── Skill extraction patterns ────────────────────────────────────
# Covers 50+ common data/ML/engineering skills
SKILL_PATTERNS = {
    # Core data engineering
    "python": r"\bpython\b",
    "sql": r"\bsql\b",
    "spark": r"\bapache\s+spark\b|\bpyspark\b|\bspark\b",
    "kafka": r"\bapache\s+kafka\b|\bkafka\b",
    "airflow": r"\bapache\s+airflow\b|\bairflow\b",
    "dbt": r"\bdbt\b",
    "snowflake": r"\bsnowflake\b",
    "databricks": r"\bdatabricks\b",
    "redshift": r"\bredshift\b",
    "bigquery": r"\bbigquery\b",
    "pandas": r"\bpandas\b",
    "numpy": r"\bnumpy\b",
    "etl": r"\betl\b|\bdata\s+pipeline\b",
    "data lake": r"\bdata\s+lake\b",
    "data warehouse": r"\bdata\s+warehouse\b",
    # Cloud
    "aws": r"\baws\b|\bamazon\s+web\s+services\b",
    "azure": r"\bazure\b|\bmicrosoft\s+azure\b",
    "gcp": r"\bgcp\b|\bgoogle\s+cloud\b",
    # ML / AI
    "pytorch": r"\bpytorch\b",
    "tensorflow": r"\btensorflow\b",
    "scikit-learn": r"\bscikit[\s\-]learn\b|\bsklearn\b",
    "machine learning": r"\bmachine\s+learning\b",
    "deep learning": r"\bdeep\s+learning\b",
    "llm": r"\bllm\b|\blarge\s+language\s+model\b",
    "mlops": r"\bmlops\b",
    # DevOps / Platform
    "docker": r"\bdocker\b",
    "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "terraform": r"\bterraform\b",
    "git": r"\bgit\b",
    "fastapi": r"\bfastapi\b",
    "flask": r"\bflask\b",
    "java": r"\bjava\b",
    "scala": r"\bscala\b",
    "go": r"\bgolang\b|\bgo\s+programming\b",
    # Visualization
    "tableau": r"\btableau\b",
    "powerbi": r"\bpower\s*bi\b",
    "looker": r"\blooker\b",
    # Streaming
    "flink": r"\bapache\s+flink\b|\bflink\b",
    "kinesis": r"\bkinesis\b",
    # Databases
    "postgresql": r"\bpostgresql\b|\bpostgres\b",
    "mysql": r"\bmysql\b",
    "mongodb": r"\bmongodb\b",
    "redis": r"\bredis\b",
    "cassandra": r"\bcassandra\b",
    "elasticsearch": r"\belasticsearch\b",
    # Formats
    "parquet": r"\bparquet\b",
    "avro": r"\bavro\b",
    "rest api": r"\brest\s+api\b|\brestful\b",
    "graphql": r"\bgraphql\b",
}


# ─── DB helpers ───────────────────────────────────────────────────

def get_conn(db_path: str = DB_PATH):
    """Get a DB connection — delegates to db.py so WAL mode and row_factory are consistent."""
    from storage.db import get_conn as _get_conn
    return _get_conn(db_path)


def init_profile_tables(db_path: str = DB_PATH):
    """Create user_profile table if it doesn't exist."""
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY,
            pin_hash TEXT DEFAULT '',
            resume_text TEXT DEFAULT '',
            extracted_skills TEXT DEFAULT '[]',
            custom_skills TEXT DEFAULT '[]',
            preferred_locations TEXT DEFAULT '[]',
            dream_companies TEXT DEFAULT '[]',
            dream_role_keywords TEXT DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO user_profile (id, created_at, updated_at)
        VALUES (1, datetime('now'), datetime('now'));
    """)
    conn.commit()
    conn.close()
    log.info("Profile tables ready")


# ─── Public API ──────────────────────────────────────────────────

def get_profile(db_path: str = DB_PATH) -> dict:
    """Return profile dict (PIN hash excluded)."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {}
    p = dict(row)
    p.pop("pin_hash", None)
    for field in ["extracted_skills", "custom_skills", "preferred_locations",
                  "dream_companies", "dream_role_keywords"]:
        if isinstance(p.get(field), str):
            try:
                p[field] = json.loads(p[field])
            except Exception:
                p[field] = []
    return p


def update_profile(updates: dict, db_path: str = DB_PATH):
    """Update allowed profile fields."""
    ALLOWED = [
        "custom_skills", "preferred_locations",
        "dream_companies", "dream_role_keywords",
    ]
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).isoformat()
    sets, values = [], []
    for key in ALLOWED:
        if key in updates:
            sets.append(f"{key} = ?")
            val = updates[key]
            values.append(json.dumps(val) if isinstance(val, list) else val)
    if sets:
        sets.append("updated_at = ?")
        values.append(now)
        values.append(1)
        conn.execute(f"UPDATE user_profile SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()
    conn.close()


def verify_pin(pin: str, db_path: str = DB_PATH) -> bool:
    """Verify PIN. Returns True if no PIN is set (open access)."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT pin_hash FROM user_profile WHERE id = 1").fetchone()
    conn.close()
    if not row or not row["pin_hash"]:
        return True  # No PIN set — open access
    return _hash_pin(pin) == row["pin_hash"]


def set_pin(pin: str, db_path: str = DB_PATH):
    """Set or change the access PIN."""
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE user_profile SET pin_hash = ?, updated_at = ? WHERE id = 1",
        (_hash_pin(pin), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    log.info("PIN updated")


def upload_resume(resume_text: str, db_path: str = DB_PATH) -> list[str]:
    """Store resume text and extract skills. Returns extracted skill list."""
    skills = extract_skills_from_resume(resume_text)
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE user_profile SET resume_text = ?, extracted_skills = ?, updated_at = ? WHERE id = 1",
        (resume_text, json.dumps(skills), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    log.info("Resume stored — %d skills extracted: %s", len(skills), skills)
    return skills


def extract_skills_from_resume(text: str) -> list[str]:
    """Extract known tech skills from resume text via regex patterns."""
    text_lower = text.lower()
    found = []
    for skill_name, pattern in SKILL_PATTERNS.items():
        if re.search(pattern, text_lower):
            found.append(skill_name)
    return found


def get_all_skills(db_path: str = DB_PATH) -> list[str]:
    """Combined skill list: resume-extracted + manually added (deduplicated)."""
    profile = get_profile(db_path)
    extracted = profile.get("extracted_skills", [])
    custom = profile.get("custom_skills", [])
    return list(dict.fromkeys(extracted + custom))


# ─── Resume version CRUD ─────────────────────────────────────────

def save_resume_version(data: dict, db_path: str = DB_PATH) -> list[str]:
    """Store a resume version and extract skills. Returns extracted skill list."""
    from storage.db import upsert_resume_version

    version_key = data.get("version_key", "").strip()
    display_name = data.get("display_name", version_key).strip() or version_key
    resume_text = data.get("resume_text", "").strip()
    target_companies = data.get("target_companies", [])
    notes = data.get("notes", "")

    skills = extract_skills_from_resume(resume_text) if resume_text else []

    # Infer target_roles from display_name / version_key when not provided
    target_roles = data.get("target_roles", [])
    if not target_roles:
        lower = display_name.lower()
        if any(k in lower for k in ("data eng", "_de", "de ", "etl")):
            target_roles = ["data engineer", "senior data engineer"]
        elif any(k in lower for k in ("ml", "machine learn")):
            target_roles = ["ml engineer", "machine learning engineer"]
        elif any(k in lower for k in ("ai ", " ai", "artificial")):
            target_roles = ["ai engineer"]
        elif any(k in lower for k in ("analytic", "_ae")):
            target_roles = ["analytics engineer"]
        elif any(k in lower for k in ("software", "swe", "_se")):
            target_roles = ["software engineer"]

    conn = get_conn(db_path)
    upsert_resume_version(conn, version_key, display_name, resume_text,
                          skills, target_roles, target_companies, notes)
    conn.commit()
    conn.close()
    log.info("Resume version '%s' stored — %d skills extracted", version_key, len(skills))
    return skills


def get_resume_version(version_key: str, db_path: str = DB_PATH) -> dict:
    """Get a resume version by key (returns {} if not found)."""
    from storage.db import get_resume_version as _get_rv
    conn = get_conn(db_path)
    result = _get_rv(conn, version_key)
    conn.close()
    return result or {}


def list_resume_versions(db_path: str = DB_PATH) -> list[dict]:
    """List all resume versions ordered by updated_at."""
    from storage.db import list_resume_versions as _list_rv
    conn = get_conn(db_path)
    result = _list_rv(conn)
    conn.close()
    return result


def delete_resume_version(version_key: str, db_path: str = DB_PATH):
    """Delete a resume version by key."""
    conn = get_conn(db_path)
    conn.execute("DELETE FROM resume_versions WHERE version_key = ?", (version_key,))
    conn.commit()
    conn.close()
    log.info("Resume version '%s' deleted", version_key)


def get_company_application_history(company_name: str, db_path: str = DB_PATH) -> dict:
    """Get all applications for a company (case-insensitive match)."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM applications WHERE LOWER(company) = LOWER(?) ORDER BY updated_at DESC",
        (company_name,)
    ).fetchall()
    conn.close()
    applications = [dict(r) for r in rows]
    applied = any(a["status"] in ("applied", "interview", "offer") for a in applications)
    return {
        "company": company_name,
        "applied": applied,
        "applications": applications,
    }


# ─── Internal ────────────────────────────────────────────────────

def _hash_pin(pin: str) -> str:
    """Hash PIN with pbkdf2_hmac — significantly harder to brute-force than bare SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.strip().encode(),
        _PIN_SALT,
        _PIN_ITERATIONS,
    ).hex()
