import json
import sqlite3
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _seed_db(db_path):
    from storage.db import init_db, upsert_job, get_conn
    init_db(db_path)
    conn = get_conn(db_path)
    upsert_job(conn, {
        "external_id": "gh-test-1",
        "title": "Senior Data Engineer",
        "company": "Jane Street",
        "location": "Remote",
        "department": "",
        "description": "Python Spark",
        "url": "https://janestreet.com/apply",
        "ats": "playwright",
        "is_remote": True,
        "posted_at": "2026-04-27",
        "salary_min": 220000,
        "salary_max": 350000,
        "relevance_score": 0.91,
        "matched_skills": ["python", "spark"],
        "sponsorship": False,
        "tier": "platinum",
    })
    conn.commit()
    conn.close()


def test_export_includes_tier_in_jobs():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        out_path = os.path.join(d, "api-data.json")
        _seed_db(db_path)
        from export_data import export
        export(db_path, out_path, cycle_counter=1)
        with open(out_path) as f:
            data = json.load(f)
        assert len(data["jobs"]) == 1
        job = data["jobs"][0]
        assert job.get("tier") == "platinum", f"Expected tier='platinum', got: {job.get('tier')}"
        assert job.get("salary_max") == 350000
