"""Tests for the thread-safe scrape progress broker (core/scrape_status.py)."""
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.scrape_status import StatusBroker, WATCHDOG_SECONDS


def test_lifecycle():
    """start → 3 ticks → finish flips is_running correctly and records counters."""
    b = StatusBroker()
    assert b.is_running() is False

    b.start("fast", total=3)
    assert b.is_running() is True
    snap = b.snapshot()
    assert snap["mode"] == "fast"
    assert snap["companies_total"] == 3
    assert snap["companies_done"] == 0
    assert snap["started_at"] is not None

    b.tick("Anthropic", found_delta=10, new_delta=2)
    b.tick("OpenAI",    found_delta=8,  new_delta=1)
    b.tick("Stripe",    found_delta=12, new_delta=4)

    snap = b.snapshot()
    assert snap["companies_done"] == 3
    assert snap["found"] == 30
    assert snap["new"] == 7
    assert snap["current_company"] == "Stripe"

    b.finish({"companies": 3, "found": 30, "new": 7, "errors": 0})
    snap = b.snapshot()
    assert snap["is_running"] is False
    assert snap["finished_at"] is not None
    assert snap["final_stats"]["new"] == 7


def test_concurrent_ticks():
    """4 threads × 100 ticks each → broker counters must sum to 400 with no drops."""
    b = StatusBroker()
    b.start("fast", total=400)

    def worker(tag: str):
        for _ in range(100):
            b.tick(tag, found_delta=1, new_delta=0)

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = b.snapshot()
    assert snap["companies_done"] == 400
    assert snap["found"] == 400


def test_snapshot_during_write():
    """Reading snapshot() while another thread is calling tick() must not raise
    and must always return a self-consistent dict."""
    b = StatusBroker()
    b.start("fast", total=1000)

    stop = threading.Event()
    errors: list = []

    def writer():
        i = 0
        while not stop.is_set():
            b.tick(f"co-{i}", found_delta=1, new_delta=1)
            i += 1

    def reader():
        try:
            for _ in range(500):
                snap = b.snapshot()
                # companies_done can never exceed found in this test because
                # every tick increments both by 1 in lock-step.
                assert snap["companies_done"] <= snap["found"]
                assert isinstance(snap, dict)
                assert "is_running" in snap
        except Exception as e:
            errors.append(e)

    w = threading.Thread(target=writer)
    r = threading.Thread(target=reader)
    w.start(); r.start()
    r.join()
    stop.set()
    w.join()

    assert not errors, f"snapshot read raised: {errors}"


def test_finish_without_start():
    """finish() called with no prior start() must not raise; state stays not-running."""
    b = StatusBroker()
    # Should be a no-op (other than recording finished_at + final_stats)
    b.finish({"any": "stats"})
    snap = b.snapshot()
    assert snap["is_running"] is False
    # final_stats persisted even without a start
    assert snap["final_stats"] == {"any": "stats"}


def test_try_start_rejects_concurrent_starts():
    """try_start() must be atomic — only one of N concurrent callers wins."""
    b = StatusBroker()
    winners: list[bool] = []
    lock = threading.Lock()

    def attempt():
        ok = b.try_start("fast", total=10)
        with lock:
            winners.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one caller transitioned idle → running.
    assert sum(1 for w in winners if w) == 1
    assert b.is_running() is True


def test_try_start_after_finish():
    """try_start() must succeed again after a finish() — runs aren't one-shot."""
    b = StatusBroker()
    assert b.try_start("fast", 3) is True
    b.tick("a"); b.tick("b"); b.tick("c")
    b.finish({"new": 1})
    assert b.is_running() is False
    # Second run starts cleanly.
    assert b.try_start("full", 5) is True
    snap = b.snapshot()
    assert snap["mode"] == "full"
    assert snap["companies_total"] == 5
    assert snap["companies_done"] == 0   # counters reset


def test_watchdog_stale_reset():
    """If last_tick_at is older than WATCHDOG_SECONDS, is_running() returns
    False even if the internal flag is still True (auto-reset)."""
    b = StatusBroker()
    b.start("fast", total=5)
    assert b.is_running() is True

    # Backdate both timestamps to just past the watchdog window.
    stale = datetime.now(timezone.utc) - timedelta(seconds=WATCHDOG_SECONDS + 30)
    with b._lock:
        b._state["started_at"]   = stale.isoformat()
        b._state["last_tick_at"] = stale.isoformat()
        # Keep the flag True to prove the watchdog overrides it.
        assert b._state["is_running"] is True

    assert b.is_running() is False
    # The watchdog should also have flipped the underlying flag.
    snap = b.snapshot()
    assert snap["is_running"] is False


def test_watchdog_respects_recent_tick():
    """A scrape that started long ago but is still ticking must NOT be
    auto-killed — this protects healthy long runs from being treated as
    crashed. Regression test for the watchdog tracking last activity, not
    just started_at."""
    b = StatusBroker()
    b.start("fast", total=200)

    # Backdate started_at to well past the watchdog — but keep last_tick_at fresh.
    old = datetime.now(timezone.utc) - timedelta(seconds=WATCHDOG_SECONDS + 120)
    with b._lock:
        b._state["started_at"] = old.isoformat()
    # A real recent tick.
    b.tick("Anthropic", found_delta=1, new_delta=0)

    # Scrape is still alive — watchdog must NOT trip.
    assert b.is_running() is True


# ─── #20: server-level integration tests ────────────────────────────


def _make_test_client(tmp_path):
    """Spin up the Flask app with an isolated DB. Background scrape thread
    self-disables under pytest, so the only writer to the broker is the
    request thread spawned by /api/scrape."""
    import importlib
    db_path = str(tmp_path / "test.db")
    from storage.db import init_db
    init_db(db_path)
    import server
    importlib.reload(server)  # picks up fresh module state + DB_PATH override
    server.DB_PATH = db_path
    # Reset the shared broker so previous tests don't leak running state in.
    from core.scrape_status import broker as shared_broker
    shared_broker.__init__()
    server.app.config["TESTING"] = True
    return server, shared_broker


def test_concurrent_scrape_requests(tmp_path, monkeypatch):
    """Two POSTs /api/scrape in rapid succession: one wins with 202, the
    other is rejected with 409. The async worker is stubbed so the test
    stays hermetic — we only validate the broker gating and HTTP status
    codes. The first request arms the broker before returning, so a
    sequential second POST is sufficient to prove gating; we don't need
    concurrent threads sharing the test_client (which has known
    context-bleed problems across threads in Flask 3+)."""
    server, b = _make_test_client(tmp_path)

    started = threading.Event()
    release = threading.Event()

    def _slow_worker(mode="fast"):
        # Don't call broker.start() here — the route handler's try_start()
        # already armed it. Just hold the run open until the test releases us.
        started.set()
        release.wait(timeout=3)
        b.finish({"new": 0})

    monkeypatch.setattr(server, "_run_scrape_async", _slow_worker)

    c = server.app.test_client()
    # First POST: arms the broker synchronously inside try_start() and spawns
    # the (stubbed) worker that holds is_running=True.
    r1 = c.post("/api/scrape")
    # Worker has started — broker is now is_running=True
    assert started.wait(timeout=2), "worker thread never ran"

    # Second POST happens while the worker is still alive — must 409.
    r2 = c.post("/api/scrape")

    # Let the worker wind down so a stale daemon thread doesn't leak into
    # the next test.
    release.set()
    time.sleep(0.1)

    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [202, 409], f"expected [202, 409] got {codes}"
    body409 = (r1 if r1.status_code == 409 else r2).get_json()
    assert body409["started"] is False
    assert body409["reason"] == "scrape_in_progress"
    assert body409["snapshot"]["is_running"] is True


def test_background_thread_uses_broker(tmp_path):
    """The 5-min background scrape loop calls run_scrape(), which drives
    broker.start/tick/finish. Simulate that flow and assert the snapshot
    endpoint reflects intermediate progress."""
    server, b = _make_test_client(tmp_path)

    with server.app.test_client() as c:
        # Idle: snapshot has is_running=False
        r = c.get("/api/scrape/status")
        assert r.status_code == 200
        assert r.get_json()["is_running"] is False

        # Simulate the background thread starting a cycle and ticking
        # halfway through. The endpoint must surface the same state any
        # manual-trigger UI would see.
        b.start("fast", total=4)
        b.tick("Anthropic", found_delta=5, new_delta=1)
        b.tick("OpenAI",    found_delta=3, new_delta=0)

        r = c.get("/api/scrape/status")
        snap = r.get_json()
        assert snap["is_running"] is True
        assert snap["companies_done"] == 2
        assert snap["companies_total"] == 4
        assert snap["found"] == 8
        assert snap["new"] == 1
        assert snap["current_company"] == "OpenAI"
        assert snap["mode"] == "fast"

        # And a second POST /api/scrape during the background run must be
        # gated by the same broker — i.e. background and manual share state.
        r2 = c.post("/api/scrape")
        assert r2.status_code == 409
        body = r2.get_json()
        assert body["started"] is False
        assert body["reason"] == "scrape_in_progress"
        assert body["snapshot"]["is_running"] is True

        # Wind the cycle down — manual triggers should accept again.
        b.tick("Stripe", found_delta=2)
        b.tick("Databricks", found_delta=4, new_delta=2)
        b.finish({"companies": 4, "found": 14, "new": 3, "errors": 0})

        r = c.get("/api/scrape/status")
        snap = r.get_json()
        assert snap["is_running"] is False
        assert snap["final_stats"]["new"] == 3
