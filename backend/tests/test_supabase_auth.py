import os, sys, time, pytest, jwt as pyjwt, flask
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-32-chars-minimum-len!")
from middleware.supabase_auth import require_auth

def _make_app():
    app = flask.Flask(__name__)
    @app.route("/protected")
    @require_auth
    def protected():
        return flask.jsonify({"user_id": flask.g.user_id, "email": flask.g.email})
    return app

def _token(sub="user-abc", email="a@b.com", secret="test-secret-32-chars-minimum-len!", aud="authenticated", exp_offset=3600):
    return pyjwt.encode(
        {"sub": sub, "email": email, "aud": aud, "exp": int(time.time()) + exp_offset},
        secret, algorithm="HS256",
    )

def test_valid_supabase_jwt():
    with _make_app().test_client() as c:
        resp = c.get("/protected", headers={"Authorization": f"Bearer {_token()}"})
        assert resp.status_code == 200
        assert resp.json["user_id"] == "user-abc"
        assert resp.json["email"] == "a@b.com"

def test_missing_authorization_header():
    with _make_app().test_client() as c:
        resp = c.get("/protected")
        assert resp.status_code == 401
        assert "error" in resp.json

def test_expired_token():
    with _make_app().test_client() as c:
        token = _token(exp_offset=-1)
        resp = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json["error"] == "token expired"

def test_invalid_token():
    with _make_app().test_client() as c:
        resp = c.get("/protected", headers={"Authorization": "Bearer garbage.token.here"})
        assert resp.status_code == 401

def test_api_secret_passthrough(monkeypatch):
    monkeypatch.setenv("API_SECRET", "my-scraper-secret")
    with _make_app().test_client() as c:
        resp = c.get("/protected", headers={"Authorization": "Bearer my-scraper-secret"})
        assert resp.status_code == 200
        assert resp.json["user_id"] == "scraper"
