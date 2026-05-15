"""Tests for /api/admin/doctor health-check endpoint."""
import importlib
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
