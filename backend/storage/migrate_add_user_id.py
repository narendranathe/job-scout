import sqlite3, sys

def _col_names(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None

def migrate(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()

        # user_profile — add user_id + priority columns.
        # Skip entirely on a fresh DB: profile_manager creates the table
        # with all columns already present, so ALTER TABLE is only needed
        # when upgrading an existing instance that pre-dates this migration.
        if _table_exists(conn, "user_profile"):
            cols = _col_names(conn, "user_profile")
            if "user_id" not in cols:
                cur.execute("ALTER TABLE user_profile ADD COLUMN user_id TEXT NOT NULL DEFAULT 'legacy'")
            if "priority_companies" not in cols:
                cur.execute("ALTER TABLE user_profile ADD COLUMN priority_companies TEXT DEFAULT '[]'")
            if "priority_mode" not in cols:
                cur.execute("ALTER TABLE user_profile ADD COLUMN priority_mode TEXT DEFAULT 'score_boost'")
            if "score_weights" not in cols:
                cur.execute(
                    "ALTER TABLE user_profile ADD COLUMN score_weights TEXT "
                    "DEFAULT '{\"skills\":53,\"role_fit\":25,\"logistics\":22,\"company_tier\":8}'"
                )
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profile_user_id ON user_profile(user_id)")

        # applications
        if _table_exists(conn, "applications"):
            if "user_id" not in _col_names(conn, "applications"):
                cur.execute("ALTER TABLE applications ADD COLUMN user_id TEXT NOT NULL DEFAULT 'legacy'")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id)")

        # resume_versions
        if _table_exists(conn, "resume_versions"):
            if "user_id" not in _col_names(conn, "resume_versions"):
                cur.execute("ALTER TABLE resume_versions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'legacy'")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_resume_versions_user_id ON resume_versions(user_id)")

        conn.commit()
    print(f"[migrate] done: {db_path}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/jobscout.db"
    migrate(path)
