"""Tests for the 5 onboarding-wizard columns added to user_profile.

PRD #89 Slice 1. The migration must be idempotent (running init twice
should not raise), and the new columns must survive a get/update/get
round-trip with the right Python types.
"""
import sqlite3

import pytest

from storage.profile_manager import (
    init_profile_tables,
    get_profile,
    update_profile,
    ProfileValidationError,
)


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "profile.db")
    init_profile_tables(db_path)
    return db_path


def test_fresh_db_has_all_five_new_columns(db):
    """CREATE TABLE path: every column present on first install."""
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_profile)")}
    conn.close()
    for col in [
        "tracked_companies", "min_total_comp", "show_unsalaried",
        "onboarded_at", "skip_pin_acknowledged",
    ]:
        assert col in cols, f"missing column {col}"


def test_pre_existing_db_gets_columns_added(tmp_path):
    """ALTER TABLE path: legacy DB without the wizard columns gets upgraded."""
    db_path = str(tmp_path / "legacy.db")
    # Simulate a DB from before this migration: only the original columns.
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE user_profile (
            id INTEGER PRIMARY KEY,
            pin_hash TEXT DEFAULT '',
            resume_text TEXT DEFAULT '',
            extracted_skills TEXT DEFAULT '[]',
            custom_skills TEXT DEFAULT '[]',
            preferred_locations TEXT DEFAULT '[]',
            dream_companies TEXT DEFAULT '[]',
            dream_role_keywords TEXT DEFAULT '[]',
            created_at TEXT, updated_at TEXT
        );
        INSERT INTO user_profile (id, created_at, updated_at)
        VALUES (1, datetime('now'), datetime('now'));
    """)
    conn.commit()
    conn.close()

    init_profile_tables(db_path)

    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_profile)")}
    conn.close()
    for col in [
        "tracked_companies", "min_total_comp", "show_unsalaried",
        "onboarded_at", "skip_pin_acknowledged", "default_resume_version",
    ]:
        assert col in cols


def test_migration_is_idempotent(db):
    """Running init_profile_tables twice is a no-op, not an error."""
    init_profile_tables(db)
    init_profile_tables(db)  # second call should not raise


def test_get_profile_returns_new_field_defaults(db):
    p = get_profile(db_path=db)
    assert p["tracked_companies"] == []
    assert p["min_total_comp"] == 0
    assert p["show_unsalaried"] is True  # coerced from SQLite int
    assert p["skip_pin_acknowledged"] is False
    assert p["onboarded_at"] is None
    assert p["has_pin"] is False  # no PIN set on fresh install
    assert "pin_hash" not in p  # NEVER leak the hash


def test_update_tracked_companies_round_trip(db):
    update_profile(
        updates={"tracked_companies": ["Acme Corp", "Beta Inc"]}, db_path=db
    )
    p = get_profile(db_path=db)
    assert p["tracked_companies"] == ["Acme Corp", "Beta Inc"]


def test_update_min_total_comp_validates_negative(db):
    with pytest.raises(ProfileValidationError, match=r"min_total_comp.*>= 0"):
        update_profile(updates={"min_total_comp": -1}, db_path=db)


def test_update_min_total_comp_validates_non_integer(db):
    with pytest.raises(ProfileValidationError):
        update_profile(updates={"min_total_comp": "twelve"}, db_path=db)


def test_update_min_total_comp_accepts_int_string(db):
    """JSON sends numbers as numbers, but sloppy clients send strings."""
    update_profile(updates={"min_total_comp": "150000"}, db_path=db)
    assert get_profile(db_path=db)["min_total_comp"] == 150000


def test_update_show_unsalaried_bool_coercion(db):
    update_profile(updates={"show_unsalaried": False}, db_path=db)
    assert get_profile(db_path=db)["show_unsalaried"] is False
    update_profile(updates={"show_unsalaried": 1}, db_path=db)
    assert get_profile(db_path=db)["show_unsalaried"] is True
    update_profile(updates={"show_unsalaried": "false"}, db_path=db)
    assert get_profile(db_path=db)["show_unsalaried"] is False


def test_update_onboarded_at_stores_iso_timestamp(db):
    iso = "2026-05-17T12:34:56+00:00"
    update_profile(updates={"onboarded_at": iso}, db_path=db)
    assert get_profile(db_path=db)["onboarded_at"] == iso


def test_update_onboarded_at_can_be_cleared(db):
    update_profile(updates={"onboarded_at": "2026-05-17T12:00:00+00:00"}, db_path=db)
    update_profile(updates={"onboarded_at": None}, db_path=db)
    assert get_profile(db_path=db)["onboarded_at"] is None


def test_skip_pin_acknowledged_flag(db):
    update_profile(updates={"skip_pin_acknowledged": True}, db_path=db)
    assert get_profile(db_path=db)["skip_pin_acknowledged"] is True


def test_has_pin_flips_true_after_set_pin(db):
    from storage.profile_manager import set_pin
    set_pin(pin="1234", db_path=db)
    p = get_profile(db_path=db)
    assert p["has_pin"] is True
    assert "pin_hash" not in p
