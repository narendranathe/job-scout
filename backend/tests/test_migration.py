import sqlite3, tempfile, os, pytest, gc

def _fresh_db(path):
    """Minimal schema matching production tables — enough to test migration."""
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY,
                pin_hash TEXT DEFAULT '',
                onboarded_at TEXT,
                tracked_companies TEXT DEFAULT '[]'
            );
            INSERT INTO user_profile (pin_hash) VALUES ('');

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY,
                external_id TEXT,
                status TEXT DEFAULT 'saved'
            );

            CREATE TABLE IF NOT EXISTS resume_versions (
                id INTEGER PRIMARY KEY,
                filename TEXT,
                skills TEXT DEFAULT '[]'
            );
        """)

def test_migration_adds_user_id_columns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        _fresh_db(db_path)
        from storage.migrate_add_user_id import migrate
        migrate(db_path)
        with sqlite3.connect(db_path) as conn:
            for table in ("user_profile", "applications", "resume_versions"):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                assert "user_id" in cols, f"{table} missing user_id column"
            row = conn.execute("SELECT user_id FROM user_profile").fetchone()
            assert row[0] == "legacy"
    finally:
        gc.collect()
        try:
            os.unlink(db_path)
        except:
            pass

def test_migration_is_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        _fresh_db(db_path)
        from storage.migrate_add_user_id import migrate
        migrate(db_path)
        migrate(db_path)  # must not raise
    finally:
        gc.collect()
        try:
            os.unlink(db_path)
        except:
            pass

def test_migration_adds_priority_columns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        _fresh_db(db_path)
        from storage.migrate_add_user_id import migrate
        migrate(db_path)
        with sqlite3.connect(db_path) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(user_profile)").fetchall()]
            assert "priority_companies" in cols
            assert "priority_mode" in cols
            assert "score_weights" in cols
    finally:
        gc.collect()
        try:
            os.unlink(db_path)
        except:
            pass
