import sqlite3
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from storage.db import init_db, upsert_job, get_conn


def make_job(ext_id="test-1"):
    return {
        "external_id": ext_id,
        "title": "Senior Data Engineer",
        "company": "Test Co",
        "location": "Remote",
        "department": "",
        "description": "Python, Spark, Kafka",
        "url": "https://example.com/job/1",
        "ats": "greenhouse",
        "is_remote": True,
        "posted_at": "2026-04-27",
        "salary_min": 200000,
        "salary_max": 280000,
        "relevance_score": 0.85,
        "matched_skills": ["python", "spark"],
        "sponsorship": False,
        "tier": "platinum",
    }


def test_tier_column_exists_after_init():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()
        assert "tier" in cols, f"tier column missing from jobs; got: {cols}"


def test_upsert_job_stores_tier():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        init_db(db_path)
        conn = get_conn(db_path)
        result = upsert_job(conn, make_job("test-1"))
        conn.commit()
        row = conn.execute("SELECT tier FROM jobs WHERE external_id = 'test-1'").fetchone()
        conn.close()
        assert result == "new"
        assert row[0] == "platinum"


def test_upsert_job_updates_tier_on_rescrape():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        init_db(db_path)
        conn = get_conn(db_path)
        # First insert with tier1
        job = make_job("test-update")
        job["tier"] = "tier1"
        upsert_job(conn, job)
        conn.commit()
        # Re-scrape same job but now Platinum
        job["tier"] = "platinum"
        result = upsert_job(conn, job)
        conn.commit()
        row = conn.execute("SELECT tier FROM jobs WHERE external_id = 'test-update'").fetchone()
        conn.close()
        assert result == "updated"
        assert row[0] == "platinum"
