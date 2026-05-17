"""Public roster endpoints — fuel for the onboarding wizard pickers.

PRD #89 Slice 1. Three read-only endpoints, no auth required (the data
is already public via ``/api/data`` and ``config/companies.py``):

    GET /api/role-taxonomy    — canonical role list (~16 entries)
    GET /api/companies-roster — all scraped companies + tier + 30d job count
    GET /api/locations-roster — distinct locations seen in the last 30 days

The wizard's chip clouds (Steps 2/3/4) bind directly to these. Keeping
them in their own blueprint instead of bolting onto ``data_routes`` so
the cache + CORS rules for the heavy ``/api/data`` payload don't
accidentally swallow these much smaller lookups.
"""
from __future__ import annotations

import logging
import time

from flask import Blueprint, jsonify, request

from core import config as _config

log = logging.getLogger(__name__)

roster_bp = Blueprint("roster", __name__)

# 5-minute in-process cache. The roster data changes only when the
# scraper runs or someone edits ``config/companies.py``. Refreshing every
# 5 minutes keeps the picker showing reasonable job counts without
# hammering the DB on every wizard step navigation.
_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, object]] = {}

# Cap locations to keep the payload under a few KB and the picker fast.
# 200 was the PRD's acceptance criterion ("returns ≤ 200 entries").
_MAX_LOCATIONS = 200


def _cors_headers() -> dict:
    """Match the public CORS posture of /api/data.

    These endpoints are unauthenticated reads, so a wildcard origin is
    fine. The blueprint-level skip in server.py's ``add_cors`` does NOT
    apply to ``/api/`` prefixes other than ``vault/`` and ``admin/`` —
    but we set them here explicitly so the response shape is the same
    whether the dashboard talks to us directly or through a proxy.
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=300",
    }


def _cached(key: str, builder):
    """Tiny TTL cache so repeated wizard navigations don't re-hit SQLite."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_SECONDS:
        return hit[1]
    val = builder()
    _cache[key] = (now, val)
    return val


@roster_bp.route("/api/role-taxonomy", methods=["GET", "OPTIONS"])
def role_taxonomy():
    """Return the canonical role list for the wizard's Step 2 chip cloud.

    Shape per entry: ``{key, label, abbrevs, skills_core}``. Stable order
    matches the registration order in ``config/role_taxonomy.ROLES``.
    """
    if request.method == "OPTIONS":
        return "", 204
    from config.role_taxonomy import ROLES
    return jsonify({"roles": ROLES}), 200, _cors_headers()


@roster_bp.route("/api/companies-roster", methods=["GET", "OPTIONS"])
def companies_roster():
    """Return every scraped company + tier + recent job count.

    The job count is computed from ``jobs.is_active = 1 AND posted_at >=
    now - 30d`` so it matches what the dashboard would actually surface
    if the user picked this company in the filter. A company with zero
    matches still appears — the wizard wants the full roster, not just
    the currently-yielding ones.
    """
    if request.method == "OPTIONS":
        return "", 204
    try:
        from config.companies import COMPANIES
        from storage.db import get_conn

        def build():
            counts: dict[str, int] = {}
            try:
                conn = get_conn(_config.DB_PATH)
                rows = conn.execute(
                    """
                    SELECT company, COUNT(*) AS n
                    FROM jobs
                    WHERE is_active = 1
                      AND (
                        posted_at IS NULL
                        OR posted_at >= datetime('now', '-30 days')
                      )
                    GROUP BY company
                    """
                ).fetchall()
                conn.close()
                counts = {(r["company"] or "").lower(): int(r["n"]) for r in rows}
            except Exception as e:
                # Empty DB / fresh container — log + degrade. The wizard
                # can still render with zero counts, which is better than
                # a 500 that blocks onboarding entirely.
                log.warning("companies-roster job-count probe failed: %s", e)

            out = []
            for c in COMPANIES:
                name = c.get("name", "")
                out.append({
                    "name": name,
                    "ats": c.get("ats", ""),
                    "tier": int(c.get("tier", 3)),
                    "tier_label": _tier_label(c.get("tier", 3)),
                    "job_count_30d": counts.get(name.lower(), 0),
                })
            return out

        roster = _cached("companies", build)
        return jsonify({"companies": roster, "total": len(roster)}), 200, _cors_headers()
    except Exception as e:
        return jsonify({"error": str(e)}), 500, _cors_headers()


@roster_bp.route("/api/locations-roster", methods=["GET", "OPTIONS"])
def locations_roster():
    """Return distinct job locations seen in the last 30 days.

    Capped at ``_MAX_LOCATIONS`` (200) by frequency desc so the wizard
    autocomplete dropdown stays snappy even on a populated DB. Blank /
    null locations are filtered out — they'd render as empty chips.
    """
    if request.method == "OPTIONS":
        return "", 204
    try:
        from storage.db import get_conn

        def build():
            try:
                conn = get_conn(_config.DB_PATH)
                rows = conn.execute(
                    """
                    SELECT location, COUNT(*) AS n
                    FROM jobs
                    WHERE is_active = 1
                      AND location IS NOT NULL
                      AND TRIM(location) != ''
                      AND (
                        posted_at IS NULL
                        OR posted_at >= datetime('now', '-30 days')
                      )
                    GROUP BY location
                    ORDER BY n DESC
                    LIMIT ?
                    """,
                    (_MAX_LOCATIONS,),
                ).fetchall()
                conn.close()
                return [
                    {"location": r["location"], "job_count": int(r["n"])}
                    for r in rows
                ]
            except Exception as e:
                log.warning("locations-roster probe failed: %s", e)
                return []

        locations = _cached("locations", build)
        return jsonify({"locations": locations, "total": len(locations)}), 200, _cors_headers()
    except Exception as e:
        return jsonify({"error": str(e)}), 500, _cors_headers()


def _tier_label(tier) -> str:
    """Map int tier → human-readable bucket for the picker UI.

    The wizard groups companies under three headers (Dream / Top /
    Stretch) per the PRD. We expose the label here so the frontend
    doesn't have to ship its own mapping that could drift from the
    backend's understanding.
    """
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 3
    return {0: "Platinum", 1: "Dream", 2: "Top", 3: "Stretch"}.get(t, "Stretch")
