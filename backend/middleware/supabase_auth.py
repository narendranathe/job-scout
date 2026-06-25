import os, functools, flask, jwt

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = flask.request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return flask.jsonify({"error": "authorization required"}), 401
        token = auth_header[7:]
        api_secret = os.environ.get("API_SECRET")
        if api_secret and token == api_secret:
            flask.g.user_id = "scraper"
            flask.g.email = "scraper@internal"
            return f(*args, **kwargs)
        supabase_secret = os.environ.get("SUPABASE_JWT_SECRET")
        if not supabase_secret:
            return flask.jsonify({"error": "server misconfigured: missing SUPABASE_JWT_SECRET"}), 500
        try:
            payload = jwt.decode(token, supabase_secret, algorithms=["HS256"], audience="authenticated")
            flask.g.user_id = payload["sub"]
            flask.g.email = payload.get("email", "")
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return flask.jsonify({"error": "token expired"}), 401
        except jwt.InvalidTokenError:
            return flask.jsonify({"error": "invalid token"}), 401
    return decorated
