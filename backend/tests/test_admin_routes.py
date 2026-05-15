"""Tests for /api/admin/doctor health-check endpoint and admin maintenance ops."""
import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    from storage.db import init_db
    init_db(db_path)

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.delenv("API_SECRET", raising=False)

    # Force re-import so DB_PATH/API_SECRET pick up the patched env.
    for mod in ["routes.admin_routes", "server"]:
        if mod in sys.modules:
            del sys.modules[mod]

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


def test_doctor_returns_200(client):
    resp = client.get("/api/admin/doctor")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data.get("checks"), list)
    assert isinstance(data.get("overall"), str)
    assert data["overall"] in {"pass", "warn", "fail"}


def test_doctor_minimum_checks(client):
    resp = client.get("/api/admin/doctor")
    data = resp.get_json()
    assert len(data["checks"]) >= 6
    for c in data["checks"]:
        assert set(c.keys()) >= {"name", "status", "detail"}
        assert c["status"] in {"pass", "warn", "fail"}
        assert isinstance(c["name"], str) and c["name"]
        assert isinstance(c["detail"], str)


def test_doctor_status_aggregation(client, monkeypatch):
    import routes.admin_routes as ar

    def all_pass():
        return [
            lambda: ar._check("a", "pass", "ok"),
            lambda: ar._check("b", "pass", "ok"),
        ]

    def with_warn():
        return [
            lambda: ar._check("a", "pass", "ok"),
            lambda: ar._check("b", "warn", "soft"),
        ]

    def with_fail():
        return [
            lambda: ar._check("a", "pass", "ok"),
            lambda: ar._check("b", "warn", "soft"),
            lambda: ar._check("c", "fail", "broken"),
        ]

    monkeypatch.setattr(ar, "DOCTOR_CHECKS", all_pass())
    assert client.get("/api/admin/doctor").get_json()["overall"] == "pass"

    monkeypatch.setattr(ar, "DOCTOR_CHECKS", with_warn())
    assert client.get("/api/admin/doctor").get_json()["overall"] == "warn"

    monkeypatch.setattr(ar, "DOCTOR_CHECKS", with_fail())
    assert client.get("/api/admin/doctor").get_json()["overall"] == "fail"


def test_doctor_auth_optional(client, monkeypatch):
    monkeypatch.delenv("API_SECRET", raising=False)
    import routes.admin_routes as ar
    ar.API_SECRET = ""
    resp = client.get("/api/admin/doctor")
    assert resp.status_code == 200


def test_doctor_check_crash_does_not_500(client, monkeypatch):
    """A single misbehaving check should fail-closed inside its own entry, not crash the route."""
    import routes.admin_routes as ar

    def boom():
        raise RuntimeError("simulated probe failure")

    monkeypatch.setattr(ar, "DOCTOR_CHECKS", [boom, lambda: ar._check("ok", "pass", "fine")])
    resp = client.get("/api/admin/doctor")
    assert resp.status_code == 200
    data = resp.get_json()
    statuses = [c["status"] for c in data["checks"]]
    assert "fail" in statuses
    assert data["overall"] == "fail"


# ─── Purge-stale + Clear-cache (#23) ─────────────────────────────────


def _insert_job(conn, ext_id, *, is_active, hours_ago):
    """Test helper: insert a row with last_seen_at = N hours before now (UTC).

    Writes the timestamp in the exact same ISO format that the real
    `storage.db.upsert_job` uses (`datetime.now(tz).isoformat()`, with a
    `T` separator and microseconds). Using SQLite's `datetime('now', ...)`
    here would produce a space-separated string and the test would pass
    even against a buggy lex-comparison purge query.
    """
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    conn.execute(
        "INSERT INTO jobs (external_id, title, company, is_active, "
        "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ext_id, f"Title {ext_id}", "Test Co", is_active, ts, ts),
    )


def _idle_broker(monkeypatch):
    """Force broker.is_running() → False regardless of module-level state."""
    import routes.admin_routes as ar
    monkeypatch.setattr(ar.broker, "is_running", lambda: False)


def _busy_broker(monkeypatch):
    """Force broker.is_running() → True to simulate an active scrape."""
    import routes.admin_routes as ar
    monkeypatch.setattr(ar.broker, "is_running", lambda: True)


def test_purge_stale_basic(client, monkeypatch):
    """Five jobs >200h old + is_active=0 → all five purged."""
    _idle_broker(monkeypatch)
    import routes.admin_routes as ar
    from storage.db import get_conn

    conn = get_conn(ar.DB_PATH)
    for i in range(5):
        _insert_job(conn, f"stale_{i}", is_active=0, hours_ago=200)
    conn.commit()
    conn.close()

    resp = client.post("/api/admin/purge-stale", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["purged"] == 5
    assert data["hours_threshold"] == 96

    conn = get_conn(ar.DB_PATH)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE is_active = 0"
    ).fetchone()[0]
    conn.close()
    assert remaining == 0


def test_purge_stale_respects_threshold(client, monkeypatch):
    """Three inactive jobs (50h, 100h, 200h). hours=96 → 2 purged (100h, 200h)."""
    _idle_broker(monkeypatch)
    import routes.admin_routes as ar
    from storage.db import get_conn

    conn = get_conn(ar.DB_PATH)
    _insert_job(conn, "young",  is_active=0, hours_ago=50)
    _insert_job(conn, "middle", is_active=0, hours_ago=100)
    _insert_job(conn, "old",    is_active=0, hours_ago=200)
    conn.commit()
    conn.close()

    resp = client.post("/api/admin/purge-stale", json={"hours": 96})
    assert resp.status_code == 200
    assert resp.get_json()["purged"] == 2

    conn = get_conn(ar.DB_PATH)
    rows = conn.execute("SELECT external_id FROM jobs").fetchall()
    conn.close()
    assert [r["external_id"] for r in rows] == ["young"]


def test_purge_stale_ignores_active_jobs(client, monkeypatch):
    """Active jobs (is_active=1) must never be purged even when ancient."""
    _idle_broker(monkeypatch)
    import routes.admin_routes as ar
    from storage.db import get_conn

    conn = get_conn(ar.DB_PATH)
    _insert_job(conn, "ancient_active",   is_active=1, hours_ago=500)
    _insert_job(conn, "ancient_inactive", is_active=0, hours_ago=500)
    conn.commit()
    conn.close()

    resp = client.post("/api/admin/purge-stale", json={"hours": 96})
    assert resp.status_code == 200
    assert resp.get_json()["purged"] == 1

    conn = get_conn(ar.DB_PATH)
    rows = [r["external_id"] for r in conn.execute("SELECT external_id FROM jobs").fetchall()]
    conn.close()
    assert rows == ["ancient_active"]


def test_purge_stale_during_scrape(client, monkeypatch):
    """While broker.is_running() is True, purge-stale must 409 (no DB write)."""
    _busy_broker(monkeypatch)
    import routes.admin_routes as ar
    from storage.db import get_conn

    conn = get_conn(ar.DB_PATH)
    _insert_job(conn, "would_be_purged", is_active=0, hours_ago=200)
    conn.commit()
    conn.close()

    resp = client.post("/api/admin/purge-stale", json={"hours": 96})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"] == "scrape_in_progress"
    assert isinstance(data.get("retry_after_seconds"), int)

    # Critical: confirm we did NOT touch the table.
    conn = get_conn(ar.DB_PATH)
    cnt = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active=0").fetchone()[0]
    conn.close()
    assert cnt == 1


def test_purge_stale_rejects_zero_hours(client, monkeypatch):
    """hours=0 would wipe every inactive row ever — must be rejected outright."""
    _idle_broker(monkeypatch)
    resp = client.post("/api/admin/purge-stale", json={"hours": 0})
    assert resp.status_code == 400


def test_purge_stale_matches_production_iso_format(client, monkeypatch):
    """Regression: `last_seen_at` is written by upsert_job() as ISO
    (`2026-05-15T12:26:34.834925+00:00`). An earlier version of the
    purge query compared that against SQLite's `datetime('now', ...)`
    space-separated format — lexically, the `T` (84) sorted after the
    space (32), so a same-calendar-day cutoff treated stale rows as
    "newer" and skipped them. Drive the test through the real
    upsert_job() path to lock this in."""
    from datetime import datetime, timedelta, timezone
    from storage.db import upsert_job, get_conn
    import routes.admin_routes as ar

    _idle_broker(monkeypatch)

    conn = get_conn(ar.DB_PATH)
    upsert_job(conn, {"external_id": "iso_row", "title": "T", "company": "Co", "description": ""})
    # Mark inactive and backdate 5h using the real ISO format.
    backdate = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    conn.execute(
        "UPDATE jobs SET is_active=0, last_seen_at=? WHERE external_id=?",
        (backdate, "iso_row"),
    )
    conn.commit()
    conn.close()

    # 1h threshold — the 5h-old row must be purged.
    resp = client.post("/api/admin/purge-stale", json={"hours": 1})
    assert resp.status_code == 200
    assert resp.get_json()["purged"] == 1


def test_clear_cache_returns_bytes(client, monkeypatch):
    """Insert + delete bulk rows to inflate the freelist, then VACUUM must
    reclaim a non-negative byte count and return both before/after sizes."""
    _idle_broker(monkeypatch)
    import routes.admin_routes as ar
    from storage.db import get_conn

    conn = get_conn(ar.DB_PATH)
    # 100 rows with a chunky description column to make the page-level
    # reclaim measurable even on a freshly-init'd DB.
    bulk_desc = "x" * 4096
    for i in range(100):
        conn.execute(
            "INSERT INTO jobs (external_id, title, company, description, "
            "is_active, first_seen_at, last_seen_at) "
            "VALUES (?, ?, 'Co', ?, 1, datetime('now'), datetime('now'))",
            (f"bulk_{i}", f"Job {i}", bulk_desc),
        )
    conn.commit()
    conn.execute("DELETE FROM jobs WHERE external_id LIKE 'bulk_%'")
    conn.commit()
    conn.close()

    resp = client.post("/api/admin/clear-cache")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "bytes_reclaimed" in data
    assert "db_size_before"  in data
    assert "db_size_after"   in data
    assert data["bytes_reclaimed"] >= 0
    assert data["db_size_after"] <= data["db_size_before"]
    # On a 100×4KB-description insert+delete, VACUUM should reclaim
    # something. If the build's SQLite is so aggressive it auto-vacuumed,
    # the assertion still holds at 0 — but in CI it consistently >0.
    assert data["bytes_reclaimed"] > 0


def test_clear_cache_during_scrape(client, monkeypatch):
    """clear-cache must refuse with 409 while a scrape is running."""
    _busy_broker(monkeypatch)
    resp = client.post("/api/admin/clear-cache")
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "scrape_in_progress"


# ─── /api/admin/reextract-skills ────────────────────────────────────


def _seed_resume_versions(db_path, rows):
    """Insert raw resume_versions rows with empty extracted_skills."""
    from storage.db import get_conn
    conn = get_conn(db_path)
    for key, text in rows:
        conn.execute(
            "INSERT INTO resume_versions (version_key, display_name, resume_text, "
            "extracted_skills, target_roles, target_companies, notes) "
            "VALUES (?, ?, ?, '[]', '[]', '[]', '')",
            (key, key, text),
        )
    conn.commit()
    conn.close()


def test_reextract_skills_updates_all(client):
    import routes.admin_routes as ar
    _seed_resume_versions(ar.DB_PATH, [
        ("rv_de",  "Senior Data Engineer with Python, SQL, Spark, Kafka, Airflow, AWS."),
        ("rv_ml",  "ML engineer fluent in PyTorch, TensorFlow, scikit-learn, MLOps."),
        ("rv_min", "Built REST APIs with Flask and Docker on GCP."),
    ])

    resp = client.post("/api/admin/reextract-skills")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"updated": 3, "total": 3, "errors": 0}

    # Each row's extracted_skills must now be a JSON-encoded non-empty list.
    from storage.db import get_conn
    conn = get_conn(ar.DB_PATH)
    rows = conn.execute(
        "SELECT version_key, extracted_skills FROM resume_versions ORDER BY version_key"
    ).fetchall()
    conn.close()
    assert len(rows) == 3
    for r in rows:
        parsed = json.loads(r["extracted_skills"])
        assert isinstance(parsed, list)
        assert len(parsed) > 0, f"{r['version_key']} got empty skills"

    by_key = {r["version_key"]: json.loads(r["extracted_skills"]) for r in rows}
    assert "python" in by_key["rv_de"] and "spark" in by_key["rv_de"]
    assert "pytorch" in by_key["rv_ml"]
    assert "flask" in by_key["rv_min"] and "docker" in by_key["rv_min"]


def test_reextract_skills_handles_errors(client, monkeypatch):
    import routes.admin_routes as ar
    _seed_resume_versions(ar.DB_PATH, [
        ("rv_ok_1", "Python and SQL."),
        ("rv_bad",  "this row will explode"),
        ("rv_ok_2", "Spark and Kafka."),
    ])

    from storage import profile_manager
    real = profile_manager.extract_skills_from_resume

    def flaky(text):
        if "explode" in text:
            raise RuntimeError("boom")
        return real(text)

    # Patch the symbol where reextract_skills() imports it.
    monkeypatch.setattr(profile_manager, "extract_skills_from_resume", flaky)

    resp = client.post("/api/admin/reextract-skills")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert data["updated"] == 2
    assert data["errors"] == 1


def test_reextract_skills_empty_table(client):
    """No resume_versions rows → 0/0/0, no crash."""
    resp = client.post("/api/admin/reextract-skills")
    assert resp.status_code == 200
    assert resp.get_json() == {"updated": 0, "total": 0, "errors": 0}


# ─── /api/admin/vault-reindex ───────────────────────────────────────


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    """Override the resume_vault path to a tmp dir so reindex is hermetic."""
    root = tmp_path / "resume_vault"
    (root / "text").mkdir(parents=True)
    (root / "pdf").mkdir()
    # Patch the module-level VAULT_DIR after import so rebuild_index() picks it up.
    if "storage.resume_vault" in sys.modules:
        del sys.modules["storage.resume_vault"]
    import storage.resume_vault as rv
    monkeypatch.setattr(rv, "VAULT_DIR", str(root))
    return root


def test_vault_reindex_returns_count(client, vault_dir):
    text_dir = vault_dir / "text"
    for i in range(5):
        (text_dir / f"resume_{i}.txt").write_text(
            f"Data engineer #{i} with Python, SQL, Spark, Airflow.",
            encoding="utf-8",
        )

    resp = client.post("/api/admin/vault-reindex")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["indexed"] == 5
    assert data["files_scanned"] == 5
    assert isinstance(data["duration_ms"], int)
    assert data["duration_ms"] >= 0


def test_vault_reindex_empty(client, vault_dir):
    """Empty text/ dir → indexed=0, no error."""
    resp = client.post("/api/admin/vault-reindex")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["indexed"] == 0
    assert data["files_scanned"] == 0
    assert isinstance(data["duration_ms"], int)


def test_vault_reindex_skips_non_txt(client, vault_dir):
    """Non-.txt files in text/ are ignored by files_scanned."""
    text_dir = vault_dir / "text"
    (text_dir / "a.txt").write_text("python sql spark", encoding="utf-8")
    (text_dir / "b.txt").write_text("kafka airflow dbt", encoding="utf-8")
    (text_dir / "ignored.md").write_text("not a resume", encoding="utf-8")

    resp = client.post("/api/admin/vault-reindex")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["files_scanned"] == 2
    assert data["indexed"] == 2
