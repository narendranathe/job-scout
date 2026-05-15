"""
Destructive DB maintenance helpers — called by routes/admin_routes.py.

Keeps the actual SQL + connection-management ceremony out of the route
handlers so they stay a thin auth/broker/JSON shell. Lives next to
storage/db.py rather than inside it because db.py is on the scrape hot
path; isolating one-shot operator ops here means a maintenance change
can't accidentally regress the scraper.
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def purge_inactive_jobs(db_path: str, hours: int) -> int:
    """DELETE jobs that have been is_active=0 with last_seen_at older than
    `hours`. Returns the rowcount.

    Critical detail: `jobs.last_seen_at` is written by `upsert_job` via
    `datetime.now(timezone.utc).isoformat()` — which produces
    `2026-05-15T12:26:34.834925+00:00` (note the `T` separator). SQLite's
    own `datetime('now', '-? hours')` returns `2026-05-15 16:26:34`
    (space separator). Comparing those as TEXT lex-orders the `T` (ASCII
    84) AFTER the space (ASCII 32), so ISO timestamps on the same
    calendar day as the cutoff appear "newer" than the cutoff and would
    be silently skipped.

    Match the format `storage.db.mark_stale_jobs` already uses — compute
    the cutoff in Python with `.isoformat()` and compare both sides as
    ISO strings.
    """
    from .db import get_conn  # local import keeps db_admin importable in tests that stub db.py
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).isoformat()
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM jobs WHERE is_active = 0 AND last_seen_at < ?",
            (cutoff,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def vacuum_db(db_path: str, on_before_vacuum=None) -> tuple[int, int]:
    """Run VACUUM and return `(size_before_bytes, size_after_bytes)`.

    `on_before_vacuum`, when provided, is invoked just before the VACUUM
    statement — used by the route handler to close any worker-cached
    sqlite3.Connection so it can't be holding an implicit transaction
    that would otherwise make sqlite reject VACUUM with
    "cannot VACUUM from within a transaction".

    VACUUM must execute on a connection in true autocommit mode
    (isolation_level=None) and resets `journal_mode` to the default
    (delete). We re-apply `PRAGMA journal_mode=WAL` afterward so the
    rest of the app keeps its WAL-mode concurrency guarantees without
    relying on the next get_conn() call to fix it.
    """
    size_before = os.path.getsize(db_path)

    if on_before_vacuum is not None:
        try:
            on_before_vacuum()
        except Exception:
            log.exception("on_before_vacuum hook raised — continuing with VACUUM anyway")

    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("VACUUM")
        # VACUUM rewrites the DB header and reverts journal_mode to 'delete'.
        # Reassert WAL so subsequent writers don't get rolled back to the
        # old rollback-journal locking model.
        conn.execute("PRAGMA journal_mode=WAL")
    finally:
        conn.close()

    size_after = os.path.getsize(db_path)
    return size_before, size_after
