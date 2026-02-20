"""
Persistence layer using SQLite with WAL mode.
Handles job deduplication, metrics storage, and run history.
"""

import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)


class JobDatabase:

    def __init__(self, db_path: Path, wal_mode: bool = True):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._wal_mode = wal_mode
        self._init_schema()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if self._wal_mode:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    ats TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    url TEXT,
                    salary_min INTEGER,
                    salary_max INTEGER,
                    description TEXT,
                    department TEXT DEFAULT '',
                    relevance_score REAL NOT NULL DEFAULT 0.0,
                    matched_skills TEXT,
                    matched_title TEXT,
                    is_remote INTEGER DEFAULT 0,
                    is_notified INTEGER DEFAULT 0,
                    is_applied INTEGER DEFAULT 0,
                    posted_at TEXT,
                    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
                    raw_data TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_fp ON jobs(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_jobs_rel ON jobs(relevance_score DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_disc ON jobs(discovered_at DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_notif ON jobs(is_notified);
                CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);

                CREATE TABLE IF NOT EXISTS scrape_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    ats TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    jobs_found INTEGER DEFAULT 0,
                    jobs_new INTEGER DEFAULT 0,
                    jobs_relevant INTEGER DEFAULT 0,
                    error_message TEXT,
                    duration_seconds REAL,
                    started_at TEXT NOT NULL DEFAULT (datetime('now')),
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    tags TEXT,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_metrics ON system_metrics(metric_name, recorded_at DESC);

                CREATE TABLE IF NOT EXISTS circuit_breaker (
                    source TEXT PRIMARY KEY,
                    consecutive_failures INTEGER DEFAULT 0,
                    last_failure_at TEXT,
                    is_open INTEGER DEFAULT 0,
                    half_open_at TEXT
                );
            """)

    def job_exists(self, fingerprint: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM jobs WHERE fingerprint = ?", (fingerprint,)).fetchone() is not None

    def insert_job(self, job_data: dict[str, Any]) -> Optional[int]:
        if self.job_exists(job_data["fingerprint"]):
            return None
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO jobs (
                    fingerprint, source, ats, title, company, location, url,
                    salary_min, salary_max, description, department, relevance_score,
                    matched_skills, matched_title, is_remote, posted_at, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_data["fingerprint"], job_data.get("source", ""), job_data.get("ats", ""),
                job_data["title"], job_data.get("company"), job_data.get("location"),
                job_data.get("url"), job_data.get("salary_min"), job_data.get("salary_max"),
                job_data.get("description"), job_data.get("department", ""),
                job_data.get("relevance_score", 0.0),
                json.dumps(job_data.get("matched_skills", [])),
                job_data.get("matched_title"),
                1 if job_data.get("is_remote") else 0,
                job_data.get("posted_at"),
                json.dumps(job_data.get("raw_data", {})),
            ))
            return cursor.lastrowid if cursor.rowcount > 0 else None

    def get_unnotified_jobs(self, min_score: float = 0.0) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs WHERE is_notified = 0 AND relevance_score >= ?
                ORDER BY relevance_score DESC LIMIT 50
            """, (min_score,)).fetchall()
            return [dict(r) for r in rows]

    def mark_notified(self, job_ids: list[int]) -> None:
        if not job_ids:
            return
        ph = ",".join("?" * len(job_ids))
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET is_notified = 1 WHERE id IN ({ph})", job_ids)

    def get_top_jobs(self, limit: int = 25, days: int = 7) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM jobs WHERE discovered_at >= ? AND relevance_score >= 0.4
                ORDER BY relevance_score DESC LIMIT ?
            """, (cutoff, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_job_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_count = conn.execute("SELECT COUNT(*) FROM jobs WHERE discovered_at >= ?", (today,)).fetchone()[0]
            avg = conn.execute("SELECT AVG(relevance_score) FROM jobs WHERE relevance_score > 0").fetchone()[0] or 0
            high = conn.execute("SELECT COUNT(*) FROM jobs WHERE relevance_score >= 0.7").fetchone()[0]
            sources = conn.execute("SELECT company, COUNT(*) as cnt FROM jobs GROUP BY company ORDER BY cnt DESC LIMIT 20").fetchall()
            by_ats = conn.execute("SELECT ats, COUNT(*) as cnt FROM jobs GROUP BY ats").fetchall()
            return {
                "total_jobs": total, "today_jobs": today_count,
                "avg_relevance": round(avg, 3), "high_relevance_count": high,
                "by_company": {r["company"]: r["cnt"] for r in sources},
                "by_ats": {r["ats"]: r["cnt"] for r in by_ats},
            }

    def start_run(self, source: str, ats: str = "") -> int:
        with self._connect() as conn:
            c = conn.execute("INSERT INTO scrape_runs (source, ats, status) VALUES (?, ?, 'started')", (source, ats))
            return c.lastrowid

    def complete_run(self, run_id: int, found: int, new: int, relevant: int, dur: float) -> None:
        with self._connect() as conn:
            conn.execute("""
                UPDATE scrape_runs SET status='completed', jobs_found=?, jobs_new=?,
                jobs_relevant=?, duration_seconds=?, completed_at=datetime('now') WHERE id=?
            """, (found, new, relevant, dur, run_id))

    def fail_run(self, run_id: int, error: str, dur: float) -> None:
        with self._connect() as conn:
            conn.execute("""
                UPDATE scrape_runs SET status='failed', error_message=?, duration_seconds=?,
                completed_at=datetime('now') WHERE id=?
            """, (error, dur, run_id))

    def get_recent_runs(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]

    def record_failure(self, source: str, max_failures: int = 5) -> bool:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO circuit_breaker (source, consecutive_failures, last_failure_at)
                VALUES (?, 1, datetime('now'))
                ON CONFLICT(source) DO UPDATE SET
                    consecutive_failures = consecutive_failures + 1,
                    last_failure_at = datetime('now')
            """, (source,))
            row = conn.execute("SELECT consecutive_failures FROM circuit_breaker WHERE source = ?", (source,)).fetchone()
            if row and row[0] >= max_failures:
                conn.execute("""
                    UPDATE circuit_breaker SET is_open = 1, half_open_at = datetime('now', '+15 minutes')
                    WHERE source = ?
                """, (source,))
                return True
            return False

    def record_success(self, source: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO circuit_breaker (source) VALUES (?)", (source,))
            conn.execute("UPDATE circuit_breaker SET consecutive_failures = 0, is_open = 0, half_open_at = NULL WHERE source = ?", (source,))

    def is_circuit_open(self, source: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT is_open, half_open_at FROM circuit_breaker WHERE source = ?", (source,)).fetchone()
            if not row or not row[0]:
                return False
            if row[1] and datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
                return False
            return True

    def record_metric(self, name: str, value: float, tags: Optional[dict] = None) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO system_metrics (metric_name, metric_value, tags) VALUES (?, ?, ?)",
                         (name, value, json.dumps(tags) if tags else None))

    def get_metrics(self, name: str, hours: int = 24) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM system_metrics WHERE metric_name = ? AND recorded_at >= ? ORDER BY recorded_at",
                (name, cutoff)).fetchall()]

    def cleanup_old_metrics(self, hours: int = 72) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            return conn.execute("DELETE FROM system_metrics WHERE recorded_at < ?", (cutoff,)).rowcount
