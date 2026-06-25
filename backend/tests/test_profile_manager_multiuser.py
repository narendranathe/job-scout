# backend/tests/test_profile_manager_multiuser.py
import gc
import tempfile
import os
import json
import pytest
import sqlite3


def _migrated_db():
    """Fresh DB with all tables initialized + migration applied."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    # init_db creates jobs, applications, resume_versions, scrape_runs
    from storage.db import init_db
    init_db(f.name)
    # init_profile_tables creates user_profile (idempotent if already exists)
    from storage.profile_manager import init_profile_tables
    init_profile_tables(f.name)
    # migrate adds user_id + priority columns to all three tables
    from storage.migrate_add_user_id import migrate
    migrate(f.name)
    return f.name


def _cleanup(db_path):
    """Windows-safe cleanup: GC first to release SQLite WAL handles."""
    gc.collect()
    try:
        os.unlink(db_path)
    except Exception:
        pass


def test_get_profile_creates_row_for_new_user():
    db = _migrated_db()
    try:
        from storage.profile_manager import get_profile
        p = get_profile("user-new", db_path=db)
        assert isinstance(p, dict)
        # New user gets default priority_mode
        assert p.get("priority_mode") == "score_boost"
    finally:
        _cleanup(db)


def test_two_users_isolated():
    db = _migrated_db()
    try:
        from storage.profile_manager import get_profile, update_profile
        update_profile("user-a", {"tracked_companies": ["Acme"]}, db_path=db)
        update_profile("user-b", {"tracked_companies": ["Globex"]}, db_path=db)
        a = get_profile("user-a", db_path=db)
        b = get_profile("user-b", db_path=db)
        # tracked_companies is deserialized to list by get_profile
        assert "Acme" in a["tracked_companies"]
        assert "Globex" in b["tracked_companies"]
        assert "Globex" not in a["tracked_companies"]
    finally:
        _cleanup(db)


def test_priority_fields_round_trip():
    db = _migrated_db()
    try:
        from storage.profile_manager import get_profile, update_profile
        companies = [{"name": "Anthropic", "status": "active"}]
        weights = {"skills": 60, "role_fit": 20, "logistics": 15, "company_tier": 5}
        update_profile("user-x", {
            "priority_companies": json.dumps(companies),
            "priority_mode": "hard_sort",
            "score_weights": json.dumps(weights),
        }, db_path=db)
        p = get_profile("user-x", db_path=db)
        assert p["priority_mode"] == "hard_sort"
        assert p["priority_companies"] == companies
        assert p["score_weights"] == weights
    finally:
        _cleanup(db)


def test_legacy_user_still_works():
    """Existing single-user row (user_id='legacy') must remain accessible."""
    db = _migrated_db()
    try:
        from storage.profile_manager import get_profile, update_profile
        # legacy user already exists from init_profile_tables + migration
        p = get_profile("legacy", db_path=db)
        assert isinstance(p, dict)
        update_profile("legacy", {"onboarded_at": "2024-01-01T00:00:00Z"}, db_path=db)
        p2 = get_profile("legacy", db_path=db)
        assert p2["onboarded_at"] == "2024-01-01T00:00:00Z"
    finally:
        _cleanup(db)
