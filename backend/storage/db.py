"""
SQLite storage — persists scraped + scored jobs with deduplication.
"""

import json
import sqlite3
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db"))


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = DB_PATH):
    """Create all tables if they don't exist."""
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT DEFAULT '',
            department TEXT DEFAULT '',
            description TEXT DEFAULT '',
            url TEXT DEFAULT '',
            ats TEXT DEFAULT '',
            is_remote INTEGER DEFAULT 0,
            posted_at TEXT DEFAULT '',
            salary_min INTEGER DEFAULT 0,
            salary_max INTEGER DEFAULT 0,
            relevance_score REAL DEFAULT 0.0,
            matched_skills TEXT DEFAULT '',
            sponsorship INTEGER DEFAULT 0,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_score   ON jobs(relevance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_jobs_active  ON jobs(is_active);

        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            companies_scraped INTEGER DEFAULT 0,
            jobs_found INTEGER DEFAULT 0,
            new_jobs INTEGER DEFAULT 0,
            updated_jobs INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        );

        -- Application tracker: remembers every job you've interacted with
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT NOT NULL,          -- links to jobs.external_id
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT DEFAULT '',
            status TEXT DEFAULT 'saved',        -- saved | applied | interview | offer | rejected
            relevance_score REAL DEFAULT 0.0,
            salary_min INTEGER DEFAULT 0,
            salary_max INTEGER DEFAULT 0,
            location TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            resume_version TEXT DEFAULT '',     -- which resume you used (e.g. "data-eng-v2")
            saved_at TEXT NOT NULL,
            applied_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_extid ON applications(external_id);
        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company);

        -- Resume versions: stores each resume variant + extracted skills
        CREATE TABLE IF NOT EXISTS resume_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_key TEXT UNIQUE NOT NULL,       -- "_DE", "_GS", "standard"
            display_name TEXT NOT NULL,             -- "Data Engineering", "Goldman Sachs"
            resume_text TEXT DEFAULT '',            -- full plain text of the resume
            extracted_skills TEXT DEFAULT '[]',     -- JSON: skills auto-extracted from text
            target_roles TEXT DEFAULT '[]',         -- JSON: ["data engineer","senior data engineer"]
            target_companies TEXT DEFAULT '[]',     -- JSON: companies this version was sent to
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_resume_versions_key ON resume_versions(version_key);
    """)
    conn.commit()
    conn.close()
    log.info("Database initialized at %s", db_path)


def upsert_job(conn: sqlite3.Connection, job: dict) -> str:
    """
    Insert or update a job. Returns 'new', 'updated', or 'unchanged'.
    Deduplicates by external_id.
    """
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT id, relevance_score, last_seen_at FROM jobs WHERE external_id = ?",
        (job["external_id"],)
    ).fetchone()

    if existing is None:
        conn.execute("""
            INSERT INTO jobs (
                external_id, title, company, location, department,
                description, url, ats, is_remote, posted_at,
                salary_min, salary_max, relevance_score, matched_skills,
                sponsorship, first_seen_at, last_seen_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            job["external_id"], job["title"], job["company"],
            job.get("location", ""), job.get("department", ""),
            job.get("description", ""), job.get("url", ""),
            job.get("ats", ""), int(job.get("is_remote", False)),
            job.get("posted_at", ""),
            job.get("salary_min", 0), job.get("salary_max", 0),
            job.get("relevance_score", 0.0),
            json.dumps(job.get("matched_skills", [])),
            int(job.get("sponsorship", False)),
            now, now,
        ))
        return "new"
    else:
        # Update last_seen and any changed fields
        conn.execute("""
            UPDATE jobs SET
                title = ?, location = ?, department = ?,
                description = ?, url = ?, is_remote = ?,
                salary_min = ?, salary_max = ?,
                relevance_score = ?, matched_skills = ?,
                sponsorship = ?, last_seen_at = ?, is_active = 1
            WHERE external_id = ?
        """, (
            job["title"], job.get("location", ""), job.get("department", ""),
            job.get("description", ""), job.get("url", ""),
            int(job.get("is_remote", False)),
            job.get("salary_min", 0), job.get("salary_max", 0),
            job.get("relevance_score", 0.0),
            json.dumps(job.get("matched_skills", [])),
            int(job.get("sponsorship", False)),
            now, job["external_id"],
        ))
        return "updated"


def mark_stale_jobs(conn: sqlite3.Connection, hours: int = 72):
    """Mark jobs not seen in the last N hours as inactive (likely taken down)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = conn.execute(
        "UPDATE jobs SET is_active = 0 WHERE last_seen_at < ? AND is_active = 1",
        (cutoff,)
    )
    if result.rowcount > 0:
        log.info("Marked %d stale jobs as inactive", result.rowcount)


def start_run(conn: sqlite3.Connection) -> int:
    """Record start of a scrape run. Returns run_id."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO scrape_runs (started_at) VALUES (?)", (now,)
    )
    conn.commit()
    return cursor.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, stats: dict):
    """Record completion of a scrape run."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        UPDATE scrape_runs SET
            finished_at = ?, companies_scraped = ?, jobs_found = ?,
            new_jobs = ?, updated_jobs = ?, errors = ?, status = ?
        WHERE id = ?
    """, (
        now, stats.get("companies", 0), stats.get("found", 0),
        stats.get("new", 0), stats.get("updated", 0),
        stats.get("errors", 0), "complete", run_id,
    ))
    conn.commit()


def get_stats(db_path: str = DB_PATH) -> dict:
    """Get summary stats for display."""
    conn = get_conn(db_path)
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN relevance_score >= 0.7 THEN 1 ELSE 0 END) as high_match,
            SUM(CASE WHEN is_remote THEN 1 ELSE 0 END) as remote,
            AVG(CASE WHEN salary_max > 0 THEN salary_max ELSE NULL END) as avg_salary,
            COUNT(DISTINCT company) as companies
        FROM jobs WHERE is_active = 1
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


# ─── Resume version helpers ───────────────────────────────────────

def upsert_resume_version(
    conn: sqlite3.Connection,
    version_key: str,
    display_name: str,
    resume_text: str = "",
    skills: list = None,
    target_roles: list = None,
    target_companies: list = None,
    notes: str = "",
) -> str:
    """Insert or update a resume version. Returns 'new' or 'updated'."""
    now = datetime.now(timezone.utc).isoformat()
    skills = skills or []
    target_roles = target_roles or []
    target_companies = target_companies or []

    existing = conn.execute(
        "SELECT id FROM resume_versions WHERE version_key = ?", (version_key,)
    ).fetchone()

    if existing is None:
        conn.execute("""
            INSERT INTO resume_versions
                (version_key, display_name, resume_text, extracted_skills,
                 target_roles, target_companies, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            version_key, display_name, resume_text,
            json.dumps(skills), json.dumps(target_roles), json.dumps(target_companies),
            notes, now, now,
        ))
        return "new"
    else:
        conn.execute("""
            UPDATE resume_versions SET
                display_name = ?, resume_text = ?, extracted_skills = ?,
                target_roles = ?, target_companies = ?, notes = ?, updated_at = ?
            WHERE version_key = ?
        """, (
            display_name, resume_text,
            json.dumps(skills), json.dumps(target_roles), json.dumps(target_companies),
            notes, now, version_key,
        ))
        return "updated"


def _parse_rv_row(row) -> dict:
    d = dict(row)
    for field in ["extracted_skills", "target_roles", "target_companies"]:
        try:
            d[field] = json.loads(d[field])
        except Exception:
            d[field] = []
    return d


def get_resume_version(conn: sqlite3.Connection, version_key: str) -> dict | None:
    """Get a single resume version by key."""
    row = conn.execute(
        "SELECT * FROM resume_versions WHERE version_key = ?", (version_key,)
    ).fetchone()
    return _parse_rv_row(row) if row else None


def list_resume_versions(conn: sqlite3.Connection) -> list[dict]:
    """List all resume versions ordered by updated_at."""
    rows = conn.execute(
        "SELECT * FROM resume_versions ORDER BY updated_at DESC"
    ).fetchall()
    return [_parse_rv_row(r) for r in rows]
