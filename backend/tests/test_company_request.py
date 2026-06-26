import os
import json
import time
import unittest.mock as mock

import pytest
import flask
import jwt as pyjwt

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-32-chars-minimum-len!")
os.environ.setdefault("GITHUB_TOKEN", "fake-token")

from routes.company_request_routes import company_request_bp


def _token(sub="u1", secret="test-secret-32-chars-minimum-len!"):
    return pyjwt.encode(
        {"sub": sub, "email": "u@test.com", "aud": "authenticated", "exp": int(time.time()) + 3600},
        secret,
        algorithm="HS256",
    )


def _app():
    app = flask.Flask(__name__)
    app.register_blueprint(company_request_bp)
    return app


def test_missing_company_name():
    """Returns 400 when company_name is absent."""
    with _app().test_client() as c:
        resp = c.post(
            "/api/companies/request",
            json={},
            headers={"Authorization": f"Bearer {_token()}"},
        )
        assert resp.status_code == 400
        assert "error" in resp.get_json()


def test_files_github_issue(monkeypatch):
    """Returns 201 with issue_url when GitHub API responds successfully."""
    fake_response = mock.MagicMock()
    fake_response.read.return_value = json.dumps(
        {"html_url": "https://github.com/narendranathe/job-scout/issues/99"}
    ).encode()
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch("routes.company_request_routes.urllib.request.urlopen", return_value=fake_response):
        with _app().test_client() as c:
            resp = c.post(
                "/api/companies/request",
                json={"company_name": "Stripe"},
                headers={"Authorization": f"Bearer {_token()}"},
            )
    assert resp.status_code == 201
    assert "github.com" in resp.get_json()["issue_url"]


def test_requires_auth():
    """Returns 401 when no token is provided."""
    with _app().test_client() as c:
        resp = c.post("/api/companies/request", json={"company_name": "Stripe"})
    assert resp.status_code == 401
