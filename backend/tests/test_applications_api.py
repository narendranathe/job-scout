"""Tests for application tracker API endpoints (GET / POST / PATCH / DELETE)."""
import json
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    from storage.db import init_db
    init_db(db_path)
    import server
    server.DB_PATH = db_path  # patch module-level var directly
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c
    importlib.reload(server)  # restore original state


def _seed(client):
    return client.post("/api/applications", json={
        "external_id": "gh-test-1",
        "title": "Senior Data Engineer",
        "company": "Anthropic",
        "url": "https://anthropic.com/job/1",
        "status": "saved",
        "relevance_score": 0.9,
        "salary_min": 250000,
        "salary_max": 350000,
        "location": "Remote",
    })


def test_get_applications_returns_dict(client):
    _seed(client)
    resp = client.get("/api/applications")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "applications" in data
    assert isinstance(data["applications"], list)
    assert len(data["applications"]) == 1
    assert data["applications"][0]["external_id"] == "gh-test-1"


def test_get_applications_excludes_removed_by_default(client):
    _seed(client)
    # Soft-delete the record
    client.delete("/api/applications/gh-test-1")
    resp = client.get("/api/applications")
    assert resp.status_code == 200
    apps = resp.get_json()["applications"]
    assert not any(a["external_id"] == "gh-test-1" for a in apps)


def test_get_applications_status_filter(client):
    _seed(client)
    resp = client.get("/api/applications?status=saved")
    assert resp.status_code == 200
    apps = resp.get_json()["applications"]
    assert all(a["status"] == "saved" for a in apps)


def test_patch_application_status(client):
    _seed(client)
    resp = client.patch("/api/applications/gh-test-1", json={"status": "applied"})
    assert resp.status_code == 200
    result = resp.get_json()
    assert result["status"] == "applied"
    assert result.get("applied_at") is not None


def test_patch_application_notes(client):
    _seed(client)
    resp = client.patch("/api/applications/gh-test-1", json={"notes": "Great role!"})
    assert resp.status_code == 200
    assert resp.get_json()["notes"] == "Great role!"


def test_patch_application_no_valid_fields(client):
    _seed(client)
    resp = client.patch("/api/applications/gh-test-1", json={"bogus_field": "value"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_patch_application_not_found(client):
    resp = client.patch("/api/applications/nonexistent-id", json={"status": "applied"})
    # Row doesn't exist so UPDATE affects 0 rows; SELECT returns None → 404
    assert resp.status_code == 404


def test_delete_soft_deletes(client):
    _seed(client)
    resp = client.delete("/api/applications/gh-test-1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("removed") == "gh-test-1"
    # Verify it's excluded from default GET
    list_resp = client.get("/api/applications")
    apps = list_resp.get_json()["applications"]
    assert not any(a["external_id"] == "gh-test-1" for a in apps)


def test_delete_shows_with_status_filter(client):
    """A soft-deleted record IS visible when ?status=removed is specified."""
    _seed(client)
    client.delete("/api/applications/gh-test-1")
    resp = client.get("/api/applications?status=removed")
    assert resp.status_code == 200
    apps = resp.get_json()["applications"]
    assert any(a["external_id"] == "gh-test-1" for a in apps)
