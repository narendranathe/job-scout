"""
SQLite storage — persists scraped + scored jobs with deduplication.
"""

import hashlib
import json
import sqlite3
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "jobscout.db"))


def compute_content_hash(title, company, salary_max, description):
    """Stable identity for a job that survives external_id churn (Greenhouse/Lever
    re-publish). Title+company+salary+leading description are what a human would
    recognize as 'the same job'."""
    payload = f"{(title or '').lower().strip()}|{(company or '').lower().strip()}|{salary_max or 0}|{(description or '')[:200]}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


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
            is_active INTEGER DEFAULT 1,
            tier TEXT DEFAULT 'tier1'
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
    # One-time migration: add tier if existing DB lacks it
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN tier TEXT DEFAULT 'tier1'")
        conn.commit()
    except Exception:
        pass  # Column already exists — safe to ignore
    # content_hash columns enable applied-job dedup that survives external_id churn.
    for ddl in (
        "ALTER TABLE jobs ADD COLUMN content_hash TEXT",
        "ALTER TABLE applications ADD COLUMN content_hash TEXT",
        # cycles_missing: counts consecutive scrape cycles where a job's external_id
        # was NOT seen. Used to distinguish "scraper hiccup" from "really removed".
        "ALTER TABLE jobs ADD COLUMN cycles_missing INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            pass  # Column already exists — safe to ignore
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_app_content_hash ON applications(content_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs(content_hash)")
        conn.commit()
    except Exception:
        pass
    conn.close()
    log.info("Database initialized at %s", db_path)


def upsert_job(conn: sqlite3.Connection, job: dict) -> str:
    """
    Insert or update a job. Returns 'new', 'updated', or 'unchanged'.
    Deduplicates by external_id.
    """
    now = datetime.now(timezone.utc).isoformat()
    content_hash = compute_content_hash(
        job.get("title"), job.get("company"),
        job.get("salary_max", 0), job.get("description"),
    )

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
                sponsorship, first_seen_at, last_seen_at, is_active, tier,
                content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
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
            job.get("tier", "tier1"),
            content_hash,
        ))
        return "new"
    else:
        # Update last_seen and any changed fields. Reset cycles_missing on every
        # sighting — a job that reappears after vanishing is treated as live again.
        conn.execute("""
            UPDATE jobs SET
                title = ?, location = ?, department = ?,
                description = ?, url = ?, is_remote = ?,
                salary_min = ?, salary_max = ?,
                relevance_score = ?, matched_skills = ?,
                sponsorship = ?, last_seen_at = ?, is_active = 1,
                tier = ?, content_hash = ?, cycles_missing = 0
            WHERE external_id = ?
        """, (
            job["title"], job.get("location", ""), job.get("department", ""),
            job.get("description", ""), job.get("url", ""),
            int(job.get("is_remote", False)),
            job.get("salary_min", 0), job.get("salary_max", 0),
            job.get("relevance_score", 0.0),
            json.dumps(job.get("matched_skills", [])),
            int(job.get("sponsorship", False)),
            now, job.get("tier", "tier1"), content_hash, job["external_id"],
        ))
        return "updated"


def mark_stale_jobs(conn: sqlite3.Connection, hours: int = 72):
    """Mark jobs not seen in the last N hours as inactive (likely taken down).

    This is the time-based fallback; for cycle-driven scrapes prefer
    increment_cycles_missing() which understands "missed N scrapes in a row"."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = conn.execute(
        "UPDATE jobs SET is_active = 0 WHERE last_seen_at < ? AND is_active = 1",
        (cutoff,)
    )
    if result.rowcount > 0:
        log.info("Marked %d stale jobs as inactive", result.rowcount)


def increment_cycles_missing(
    conn: sqlite3.Connection,
    seen_external_ids: set,
    scraped_companies: set | None = None,
    threshold: int = 3,
) -> dict:
    """Cycle-absence inference for active jobs.

    For every is_active=1 job whose external_id is NOT in `seen_external_ids`,
    bump `cycles_missing` by 1. Jobs that reach `threshold` consecutive misses
    are flipped to is_active=0 (assumed taken down). A job that reappears in a
    later cycle has its counter reset by upsert_job() — including jobs already
    deactivated, which re-activate cleanly on the next sighting.

    Args:
        conn: open DB connection (caller owns commit).
        seen_external_ids: external_ids observed in the just-finished cycle.
        scraped_companies: company names whose scrapers actually ran this cycle.
            Jobs from OTHER companies are left alone (they're on a rotating
            schedule — see config.companies.get_batch). When None, all active
            jobs are eligible for the penalty (callers must guarantee a full
            sweep ran; partial sweeps will incorrectly penalise out-of-batch
            jobs).
        threshold: consecutive misses before deactivation. Default 3 — at one
            full sweep per hour that's ≥2h of disappearance, which absorbs
            transient ATS errors while still retiring genuinely removed posts.

    Returns:
        {"incremented": N, "deactivated": M} for logging.
    """
    if not isinstance(seen_external_ids, (set, frozenset)):
        seen_external_ids = set(seen_external_ids or [])
    if scraped_companies is not None and not isinstance(
        scraped_companies, (set, frozenset)
    ):
        scraped_companies = set(scraped_companies or [])

    # Run the increment + deactivate as one transaction. SQLite is single-writer
    # under WAL — if a second writer (manual /api/scrape, parallel Actions run)
    # is mid-write, `BEGIN IMMEDIATE` fails fast with SQLITE_BUSY instead of
    # letting the two passes interleave and leave counters partially advanced.
    # The `with conn:` block commits on clean exit and rolls back on exception,
    # so a crash between the two UPDATEs cannot leave the table half-updated.
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as e:
        log.warning("Cycle absence skipped — DB busy: %s", e)
        return {"incremented": 0, "deactivated": 0}

    try:
        # Pull active jobs along with company so we can scope penalties to the
        # companies that actually ran this cycle. Avoid a single giant NOT IN
        # (...) against external_ids (SQLite var limit ~999) by diffing in
        # Python.
        active_rows = conn.execute(
            "SELECT external_id, company FROM jobs WHERE is_active = 1"
        ).fetchall()

        if scraped_companies is not None:
            candidate_rows = [r for r in active_rows if r[1] in scraped_companies]
        else:
            candidate_rows = active_rows

        missing_ids = [r[0] for r in candidate_rows if r[0] not in seen_external_ids]
        if not missing_ids:
            conn.commit()
            return {"incremented": 0, "deactivated": 0}

        incremented = 0
        CHUNK = 500
        for i in range(0, len(missing_ids), CHUNK):
            batch = missing_ids[i:i + CHUNK]
            placeholders = ",".join("?" * len(batch))
            cur = conn.execute(
                f"UPDATE jobs SET cycles_missing = COALESCE(cycles_missing, 0) + 1 "
                f"WHERE external_id IN ({placeholders}) AND is_active = 1",
                batch,
            )
            incremented += cur.rowcount

        cur = conn.execute(
            "UPDATE jobs SET is_active = 0 "
            "WHERE is_active = 1 AND COALESCE(cycles_missing, 0) >= ?",
            (threshold,)
        )
        deactivated = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    if incremented or deactivated:
        log.info(
            "Cycle absence: %d jobs incremented, %d deactivated (threshold=%d)",
            incremented, deactivated, threshold,
        )
    return {"incremented": incremented, "deactivated": deactivated}


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
