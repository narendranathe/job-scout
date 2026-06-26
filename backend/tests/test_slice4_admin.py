"""Tests for Slice 4 backend additions.

PRD #89 Slice 4:
* POST /api/admin/reset-onboarding clears onboarded_at + skip_pin_acknowledged
* GET /api/admin/doctor returns the 3 new onboarding counters
* notify_unscraped_tracking is rate-limited + batches names
* POST /api/profile fires the notification only for newly-tracked,
  unscraped names (diff against prior state)
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "slice4.db")
    from storage.db import init_db
    from storage.profile_manager import init_profile_tables
    init_db(db_path)
    init_profile_tables(db_path)

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.delenv("API_SECRET", raising=False)

    for mod in list(sys.modules):
        if mod == "server" or mod.startswith("routes.") or mod == "core.config":
            del sys.modules[mod]

    import server
    from core import config as _config
    _config.DB_PATH = db_path
    server.DB_PATH = db_path

    import routes.admin_routes as ar
    ar.DB_PATH = db_path
    ar.API_SECRET = ""

    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c, db_path


# ─── /api/admin/reset-onboarding ─────────────────────────────────────────

def test_reset_onboarding_clears_flags(client):
    c, db_path = client
    # Seed: mark onboarded + acknowledge skip-PIN
    from storage.profile_manager import update_profile
    update_profile(
        updates={"onboarded_at": "2026-05-17T10:00:00+00:00",
                 "skip_pin_acknowledged": True},
        db_path=db_path,
    )

    resp = c.post("/api/admin/reset-onboarding")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "reset"

    from storage.profile_manager import get_profile
    p = get_profile(db_path=db_path)
    assert p["onboarded_at"] is None
    assert p["skip_pin_acknowledged"] is False


def test_reset_onboarding_preserves_roles_companies(client):
    """Reset must NOT touch roles, dream_companies, vault, or PIN."""
    c, db_path = client
    from storage.profile_manager import update_profile, set_pin
    update_profile(
        updates={
            "dream_role_keywords": ["data engineer"],
            "dream_companies": ["Anthropic"],
            "tracked_companies": ["Acme Corp"],
            "onboarded_at": "2026-05-17T10:00:00+00:00",
        },
        db_path=db_path,
    )
    set_pin(pin="9999", db_path=db_path)

    c.post("/api/admin/reset-onboarding")

    from storage.profile_manager import get_profile
    p = get_profile(db_path=db_path)
    assert p["onboarded_at"] is None
    assert p["dream_role_keywords"] == ["data engineer"]
    assert p["dream_companies"] == ["Anthropic"]
    assert p["tracked_companies"] == ["Acme Corp"]
    assert p["has_pin"] is True


def test_reset_onboarding_options_passes(client):
    c, _ = client
    resp = c.open("/api/admin/reset-onboarding", method="OPTIONS")
    assert resp.status_code in (200, 204)


# ─── Doctor counters ─────────────────────────────────────────────────────

def test_doctor_includes_three_new_counters(client):
    c, _ = client
    data = c.get("/api/admin/doctor").get_json()
    names = {chk["name"] for chk in data["checks"]}
    assert "onboarded_users" in names
    assert "wizard_steps_skipped" in names
    assert "tracked_but_unscraped_companies_count" in names


def test_doctor_onboarded_users_counter_increments(client):
    c, db_path = client
    initial = next(
        (chk for chk in c.get("/api/admin/doctor").get_json()["checks"]
         if chk["name"] == "onboarded_users"),
        None,
    )
    assert initial["detail"] == "0"

    from storage.profile_manager import update_profile
    update_profile(updates={"onboarded_at": "2026-05-17T10:00:00+00:00"}, db_path=db_path)

    after = next(
        (chk for chk in c.get("/api/admin/doctor").get_json()["checks"]
         if chk["name"] == "onboarded_users"),
        None,
    )
    assert after["detail"] == "1"


def test_doctor_tracked_but_unscraped_counts_only_unknown(client):
    c, db_path = client
    from storage.profile_manager import update_profile
    # Anthropic IS scraped (in COMPANIES); Acme Corp is NOT.
    update_profile(
        updates={"tracked_companies": ["Anthropic", "Acme Corp", "Beta Inc"]},
        db_path=db_path,
    )

    chk = next(
        (chk for chk in c.get("/api/admin/doctor").get_json()["checks"]
         if chk["name"] == "tracked_but_unscraped_companies_count"),
        None,
    )
    # 2 unknown (Acme Corp, Beta Inc), 1 known (Anthropic).
    assert chk["detail"] == "2"


# ─── notify_unscraped_tracking ───────────────────────────────────────────

def test_notify_unscraped_returns_false_when_no_webhook(monkeypatch):
    """No webhook → no-op, returns False, but pending queue cleared."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    # Force module re-import so DISCORD_WEBHOOK picks up the unset env.
    for m in list(sys.modules):
        if m.startswith("alerts."):
            del sys.modules[m]
    from alerts import notifier
    notifier._unscraped_state["last_sent_at"] = 0
    notifier._unscraped_state["pending_names"].clear()

    assert notifier.notify_unscraped_tracking(["Acme"]) is False
    # Queue cleared so it doesn't grow unboundedly across restarts.
    assert notifier._unscraped_state["pending_names"] == set()


def test_notify_unscraped_rate_limited(monkeypatch):
    """Second call within the window returns False; queue accumulates."""
    sent = []

    def fake_post(url, json=None, timeout=None):
        sent.append(json or {})

        class _R:
            status_code = 204
            text = ""
        return _R()

    for m in list(sys.modules):
        if m.startswith("alerts."):
            del sys.modules[m]
    from alerts import notifier
    # DISCORD_WEBHOOK is a module-level constant captured at import time
    # (matches the existing notifier pattern). Patch it directly.
    monkeypatch.setattr(notifier, "DISCORD_WEBHOOK", "https://discord.example/webhook")
    monkeypatch.setattr(notifier, "requests", type("R", (), {"post": staticmethod(fake_post)}))
    notifier._unscraped_state["last_sent_at"] = 0
    notifier._unscraped_state["pending_names"].clear()

    assert notifier.notify_unscraped_tracking(["Acme"]) is True
    assert len(sent) == 1
    assert "Acme" in sent[0]["content"]

    # Second call within the window: queued, not sent.
    assert notifier.notify_unscraped_tracking(["Beta"]) is False
    assert len(sent) == 1
    assert "Beta" in notifier._unscraped_state["pending_names"]

    # Fast-forward past the rate-limit window and try again — both names
    # should go out in the same batch.
    notifier._unscraped_state["last_sent_at"] = time.time() - notifier._UNSCRAPED_RATE_LIMIT_SECONDS - 1
    assert notifier.notify_unscraped_tracking(["Beta"]) is True
    assert len(sent) == 2
    assert "Beta" in sent[1]["content"]


def test_notify_unscraped_empty_input_returns_false(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    for m in list(sys.modules):
        if m.startswith("alerts."):
            del sys.modules[m]
    from alerts import notifier
    assert notifier.notify_unscraped_tracking([]) is False
    assert notifier.notify_unscraped_tracking(["", "   ", None]) is False


# ─── /api/profile diff-and-ping integration ─────────────────────────────

def test_profile_update_fires_ping_only_for_novel_unscraped(client, monkeypatch):
    """tracked_companies POST diff fires ping only for new unscraped names."""
    c, db_path = client
    fired = []

    def fake_notify(names):
        fired.append(list(names))
        return True

    # Patch notify_unscraped_tracking in the profile route, since profile_routes
    # imports it lazily at call time via ``from alerts.notifier import ...``.
    import alerts.notifier as nm
    monkeypatch.setattr(nm, "notify_unscraped_tracking", fake_notify)

    # First POST: tracking 2 unscraped names → ping fires with both.
    c.post(
        "/api/profile",
        json={"tracked_companies": ["Acme Corp", "Beta Inc"]},
    )
    assert fired and set(fired[-1]) == {"Acme Corp", "Beta Inc"}

    # Second POST: same set → diff is empty → no new ping.
    fired.clear()
    c.post(
        "/api/profile",
        json={"tracked_companies": ["Acme Corp", "Beta Inc"]},
    )
    assert fired == []

    # Third POST: adds Gamma → only Gamma fires.
    c.post(
        "/api/profile",
        json={"tracked_companies": ["Acme Corp", "Beta Inc", "Gamma LLC"]},
    )
    assert fired and fired[-1] == ["Gamma LLC"]
