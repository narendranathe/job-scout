"""Tests for the 3 public roster endpoints.

PRD #89 Slice 1 acceptance criteria:

* /api/role-taxonomy → ≥ 8 roles with shape {key, label, abbrevs, skills_core}
* /api/companies-roster → 153 entries (matches len(COMPANIES)), each with
  {name, ats, tier, tier_label, job_count_30d}
* /api/locations-roster → ≤ 200 entries, distinct, only last-30-day jobs
"""
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

    for mod in list(sys.modules):
        if mod == "server" or mod.startswith("routes.") or mod == "core.config":
            del sys.modules[mod]

    import server
    # The new roster + profile routes read DB_PATH off ``core.config`` at
    # call time, not import time, so patch it directly here in case the
    # re-import didn't pick up the env (e.g. cached attribute on a parent
    # package). Belt-and-suspenders.
    from core import config as _config
    _config.DB_PATH = db_path
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True

    # Wipe the roster cache between tests — its 5-min TTL would otherwise
    # leak job counts from one test into the next.
    from routes import roster_routes
    roster_routes._cache.clear()

    with server.app.test_client() as c:
        yield c, db_path


def _seed_jobs(db_path, jobs):
    """Insert ``jobs`` (list of dicts) into the test DB."""
    from storage.db import get_conn
    conn = get_conn(db_path)
    for j in jobs:
        conn.execute(
            """
            INSERT INTO jobs (external_id, title, company, location,
                              department, description, url, ats,
                              is_remote, posted_at, first_seen_at, last_seen_at,
                              is_active)
            VALUES (?, ?, ?, ?, '', '', '', ?, 0, ?, ?, ?, 1)
            """,
            (
                j["external_id"], j["title"], j["company"], j.get("location", ""),
                j.get("ats", "greenhouse"),
                j.get("posted_at", "2026-05-15T00:00:00"),
                j.get("first_seen_at", "2026-05-15T00:00:00"),
                j.get("last_seen_at", "2026-05-15T00:00:00"),
            ),
        )
    conn.commit()
    conn.close()


# ─── /api/role-taxonomy ────────────────────────────────────────────────────

def test_role_taxonomy_returns_200_no_auth(client):
    c, _ = client
    resp = c.get("/api/role-taxonomy")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "roles" in data
    assert len(data["roles"]) >= 8


def test_role_taxonomy_entry_shape(client):
    c, _ = client
    data = c.get("/api/role-taxonomy").get_json()
    for r in data["roles"]:
        assert set(r.keys()) >= {"key", "label", "abbrevs", "skills_core"}


def test_role_taxonomy_includes_cache_header(client):
    c, _ = client
    resp = c.get("/api/role-taxonomy")
    assert "max-age" in resp.headers.get("Cache-Control", "")


# ─── /api/companies-roster ─────────────────────────────────────────────────

def test_companies_roster_matches_companies_len(client):
    c, _ = client
    from config.companies import COMPANIES
    resp = c.get("/api/companies-roster")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == len(COMPANIES)
    assert len(data["companies"]) == len(COMPANIES)


def test_companies_roster_entry_shape(client):
    c, _ = client
    data = c.get("/api/companies-roster").get_json()
    for entry in data["companies"][:5]:
        assert set(entry.keys()) >= {
            "name", "ats", "tier", "tier_label", "job_count_30d"
        }
        assert isinstance(entry["tier"], int)
        assert entry["tier_label"] in {"Platinum", "Dream", "Top", "Stretch"}


def test_companies_roster_job_count_reflects_db(client):
    c, db_path = client
    # Anthropic is in COMPANIES — add 3 active jobs for it.
    _seed_jobs(db_path, [
        {"external_id": "a1", "title": "DE", "company": "Anthropic"},
        {"external_id": "a2", "title": "MLE", "company": "Anthropic"},
        {"external_id": "a3", "title": "SWE", "company": "Anthropic"},
    ])
    # Bust the in-memory cache so the next call re-queries the DB.
    from routes import roster_routes
    roster_routes._cache.clear()

    data = c.get("/api/companies-roster").get_json()
    anthropic = next(e for e in data["companies"] if e["name"] == "Anthropic")
    assert anthropic["job_count_30d"] == 3


def test_companies_roster_excludes_jobs_older_than_30d(client):
    c, db_path = client
    _seed_jobs(db_path, [
        {"external_id": "old1", "title": "DE", "company": "Stripe",
         "posted_at": "2025-01-01T00:00:00"},
    ])
    from routes import roster_routes
    roster_routes._cache.clear()

    data = c.get("/api/companies-roster").get_json()
    stripe = next(e for e in data["companies"] if e["name"] == "Stripe")
    assert stripe["job_count_30d"] == 0


# ─── /api/locations-roster ─────────────────────────────────────────────────

def test_locations_roster_empty_when_no_jobs(client):
    c, _ = client
    data = c.get("/api/locations-roster").get_json()
    assert data["total"] == 0
    assert data["locations"] == []


def test_locations_roster_distinct_with_counts(client):
    c, db_path = client
    _seed_jobs(db_path, [
        {"external_id": "l1", "title": "DE", "company": "Stripe",
         "location": "San Francisco, CA"},
        {"external_id": "l2", "title": "DE", "company": "Stripe",
         "location": "San Francisco, CA"},
        {"external_id": "l3", "title": "DE", "company": "Anthropic",
         "location": "Remote"},
    ])
    from routes import roster_routes
    roster_routes._cache.clear()

    data = c.get("/api/locations-roster").get_json()
    locs = {entry["location"]: entry["job_count"] for entry in data["locations"]}
    assert locs.get("San Francisco, CA") == 2
    assert locs.get("Remote") == 1


def test_locations_roster_ignores_blank(client):
    c, db_path = client
    _seed_jobs(db_path, [
        {"external_id": "b1", "title": "DE", "company": "Stripe",
         "location": ""},
        {"external_id": "b2", "title": "DE", "company": "Stripe",
         "location": "   "},
        {"external_id": "b3", "title": "DE", "company": "Stripe",
         "location": "NYC"},
    ])
    from routes import roster_routes
    roster_routes._cache.clear()

    data = c.get("/api/locations-roster").get_json()
    locs = [entry["location"] for entry in data["locations"]]
    assert "" not in locs
    assert "   " not in locs
    assert "NYC" in locs


def test_locations_roster_capped(client, monkeypatch):
    c, db_path = client
    # Seed 250 distinct locations; the route should cap at 200.
    from routes import roster_routes
    monkeypatch.setattr(roster_routes, "_MAX_LOCATIONS", 200)
    _seed_jobs(db_path, [
        {"external_id": f"loc{i}", "title": "DE", "company": "Stripe",
         "location": f"City-{i:03d}"}
        for i in range(250)
    ])
    roster_routes._cache.clear()

    data = c.get("/api/locations-roster").get_json()
    assert data["total"] <= 200


# ─── Thread-safety regression (#cache lock) ────────────────────────────────

    """Two threads race the same key. Even with a deliberately-slow
    builder, only ONE invocation should happen — the lock blocks the
    second thread until the first has populated the cache.
    """
    import threading as _threading
    import time as _time
    from routes import roster_routes

    roster_routes._cache.clear()

    call_count = {"n": 0}
    call_lock = _threading.Lock()

    def slow_builder():
        with call_lock:
            call_count["n"] += 1
        _time.sleep(0.05)  # plenty of window for a racing thread to enter
        return f"val-{call_count['n']}"

    results = {}

    def call(tag):
        results[tag] = roster_routes._cached("race-key-2", slow_builder)

    t1 = _threading.Thread(target=call, args=("a",))
    t2 = _threading.Thread(target=call, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert call_count["n"] == 1, (
        f"builder was called {call_count['n']} times — the lock didn't "
        "coalesce the concurrent misses"
    )
    # Both threads must see the same value (no torn read).
    assert results["a"] == results["b"] == "val-1"


def test_cache_hit_path_is_thread_safe_under_contention(client):
    """Many threads hammering a cached key should never raise. Without
    the lock, dict mutation during iteration (e.g. if any helper ever
    walks the cache) could ``RuntimeError``. This pins the read path."""
    import threading as _threading
    from routes import roster_routes

    roster_routes._cache.clear()
    # Pre-populate so subsequent calls hit the fast path.
    roster_routes._cached("hot-key", lambda: "hot-val")

    errors = []

    def hammer():
        try:
            for _ in range(50):
                assert roster_routes._cached("hot-key", lambda: "should-not-call") == "hot-val"
        except Exception as e:  # pragma: no cover — the test asserts this stays empty
            errors.append(e)

    threads = [_threading.Thread(target=hammer) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3)

    assert not errors, f"hit-path race produced exceptions: {errors[:3]}"
