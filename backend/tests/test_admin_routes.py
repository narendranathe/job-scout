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
