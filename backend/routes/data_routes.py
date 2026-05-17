"""Read-only data endpoints — extracted from server.py (4/8 server split).

Five routes, all unauthenticated, all GET. Grouped here because they share
a contract (no write side effects, no auth, served as the public read
surface of the API):

    GET /              — Self-describing root, auto-discovers app.url_map
    GET /ping          — Keepalive (GitHub Actions / UptimeRobot hits this)
    GET /api/data      — Full JSON cache for the dashboard
    GET /api/health    — Uptime + cycle counters
    GET /api/stats     — Quick DB stats

The cache rebuild on /api/data cold-start is the only side effect, and
it's idempotent.
"""
from flask import Blueprint, Response, current_app, jsonify

from core.config import DB_PATH
from core.scrape_loop import build_cache
from core.state import state
from storage.db import get_stats

data_bp = Blueprint("data", __name__)


@data_bp.route("/ping")
def ping():
    """Keepalive — GitHub Actions / UptimeRobot hits this every 14 min."""
    return "ok", 200


@data_bp.route("/api/data")
def api_data():
    """Full JSON export for dashboard."""
    cached = state.get_cache()
    if not cached:
        build_cache()
        cached = state.get_cache()
    if cached:
        return Response(cached, mimetype="application/json", headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=60",
        })
    return jsonify({"error": "No data yet — first scrape in progress"}), 503


@data_bp.route("/api/health")
def api_health():
    return jsonify(state.health()), 200, {"Access-Control-Allow-Origin": "*"}


@data_bp.route("/api/stats")
def api_stats():
    try:
        return jsonify(get_stats(DB_PATH)), 200, {"Access-Control-Allow-Origin": "*"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@data_bp.route("/")
def index():
    """Self-describing root. Auto-discovers routes from the live url_map
    so this list never drifts when new blueprints register (PR #51
    introduced this; we preserve it here)."""
    # current_app vs the bare ``app`` we used in server.py: identical
    # behavior inside a request, but works from a Blueprint without
    # importing the app object back from server (which would create
    # a circular import).
    endpoints = sorted({
        r.rule for r in current_app.url_map.iter_rules()
        if not r.rule.startswith("/static")
        and r.endpoint != "static"
    })
    return jsonify({
        "service":   "JobScout API",
        "version":   "3.1",
        "endpoints": endpoints,
        "endpoint_count": len(endpoints),
        **state.health(),
    }), 200, {"Access-Control-Allow-Origin": "*"}
