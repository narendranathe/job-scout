"""Scrape control endpoints — extracted from server.py (5/8 server split).

Two routes, both auth-gated when API_SECRET is set:

    POST /api/scrape         — Manual trigger (returns 202 with live snapshot)
    GET  /api/scrape/status  — Poll snapshot for the in-flight or last cycle

Both use the StatusBroker for atomic check-and-arm so concurrent POSTs and
the background loop can't double-trigger the same cycle.
"""
import logging
import threading

from flask import Blueprint, jsonify, request

from core.config import check_api_secret
# Import the module rather than the function so monkeypatch.setattr on
# core.scrape_loop.run_scrape_async actually reaches us. (Tests that
# stub the worker — see test_concurrent_scrape_requests — rely on this.)
from core import scrape_loop
from core.scrape_status import broker

log = logging.getLogger("jobscout")

scrape_bp = Blueprint("scrape", __name__)


@scrape_bp.route("/api/scrape", methods=["POST", "OPTIONS"])
def api_trigger_scrape():
    """Trigger an immediate scrape in a background daemon thread.

    Returns 202 with a status snapshot so the dashboard can poll
    /api/scrape/status for live progress. A 409 is returned if a scrape is
    already in flight (per the broker's 10-min watchdog).
    """
    if request.method == "OPTIONS":
        return "", 204

    if not check_api_secret(request):
        return jsonify({"error": "unauthorized"}), 401

    # Atomic check-and-arm: closes the race where two concurrent POSTs both
    # pass is_running() and spawn two scrape threads. The broker is armed
    # synchronously before we return 202, so the embedded snapshot already
    # shows is_running=True — no false "scrape complete" on the first poll.
    if not broker.try_start("fast", scrape_loop.count_fast_companies()):
        return jsonify({
            "started":  False,
            "reason":   "scrape_in_progress",
            "snapshot": broker.snapshot(),
        }), 409

    threading.Thread(
        target=scrape_loop.run_scrape_async,
        args=("fast",),
        daemon=True,
        name="scrape-worker",
    ).start()

    return jsonify({
        "started":  True,
        "snapshot": broker.snapshot(),
    }), 202


@scrape_bp.route("/api/scrape/status", methods=["GET"])
def api_scrape_status():
    """Live progress snapshot for the in-flight scrape (or last finished run).

    Auth-gated symmetrically with POST /api/scrape: if API_SECRET is set, a
    matching Bearer token is required. This prevents the snapshot leaking
    cadence/company-name info to anonymous pollers in deployments that have
    locked down the trigger.
    """
    if not check_api_secret(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(broker.snapshot()), 200, {"Access-Control-Allow-Origin": "*"}
