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
    """If started_at is older than WATCHDOG_SECONDS, is_running() returns False
    even if the internal flag is still True (auto-reset)."""
    b = StatusBroker()
    b.start("fast", total=5)
    assert b.is_running() is True

    # Backdate started_at to just past the watchdog window.
    stale = datetime.now(timezone.utc) - timedelta(seconds=WATCHDOG_SECONDS + 30)
    with b._lock:
        b._state["started_at"] = stale.isoformat()
        # Keep the flag True to prove the watchdog overrides it.
        assert b._state["is_running"] is True

    assert b.is_running() is False
    # The watchdog should also have flipped the underlying flag.
    snap = b.snapshot()
    assert snap["is_running"] is False
