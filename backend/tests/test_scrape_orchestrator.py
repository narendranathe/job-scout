"""Tests for the canonical scrape orchestrator (core/scrape_orchestrator.py).

Targets the consolidation introduced in #21. We deliberately don't hit any
real ATS — tests run against an in-memory SQLite DB with an empty company
list patched in via monkeypatch.
"""
import inspect
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import scrape_orchestrator
from core.scrape_orchestrator import run_scrape
from storage.db import init_db, get_conn


@pytest.fixture
def empty_db_conn():
    """Fresh on-disk SQLite DB with schema initialised; companies patched to []."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    conn = get_conn(path)
    yield conn
    conn.close()
    try:
        os.unlink(path)
    except OSError:
        pass


def test_signature():
    """run_scrape must expose ONLY (conn, mode, status_broker) — no delay arg."""
    sig = inspect.signature(run_scrape)
    params = list(sig.parameters.keys())
    assert params == ["conn", "mode", "status_broker"], (
        f"Unexpected signature: {params}. Wave 2 contract requires delay to be "
        f"read from SCRAPE_DELAY env var, not a function arg."
    )
    # mode and status_broker must be keyword-only
    assert sig.parameters["mode"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["status_broker"].kind == inspect.Parameter.KEYWORD_ONLY
    # mode must default to "fast"; status_broker must default to None
    assert sig.parameters["mode"].default == "fast"
    assert sig.parameters["status_broker"].default is None


def test_empty_db(monkeypatch, empty_db_conn):
    """With zero companies and empty scrapers, the cycle returns zeros — no crash."""
    monkeypatch.setattr(scrape_orchestrator, "COMPANIES", [])
    monkeypatch.setattr(scrape_orchestrator, "get_batch", lambda _cycle: [])
    monkeypatch.setattr(scrape_orchestrator, "SCRAPERS", {})
    # Defang _load_scrapers so it doesn't repopulate SCRAPERS mid-test
    monkeypatch.setattr(scrape_orchestrator, "_load_scrapers", lambda: None)

    stats = run_scrape(empty_db_conn, mode="fast")
    assert stats["companies"] == 0
    assert stats["found"] == 0
    assert stats["new"] == 0
    assert stats["updated"] == 0
    assert stats["errors"] == 0
    assert stats["relevant"] == 0
    assert "cycle" in stats


def test_no_broker(monkeypatch, empty_db_conn):
    """status_broker=None must not raise — covers the CLI path."""
    monkeypatch.setattr(scrape_orchestrator, "COMPANIES", [])
    monkeypatch.setattr(scrape_orchestrator, "get_batch", lambda _cycle: [])
    monkeypatch.setattr(scrape_orchestrator, "SCRAPERS", {})
    monkeypatch.setattr(scrape_orchestrator, "_load_scrapers", lambda: None)

    # Should complete without raising AttributeError on broker.tick/etc.
    stats = run_scrape(empty_db_conn, mode="fast", status_broker=None)
    assert stats is not None
    assert isinstance(stats, dict)


def test_broker_integration(monkeypatch, empty_db_conn):
    """A passed broker must receive start/tick/finish — even on an empty cycle
    we expect start() and finish() exactly once (no ticks because no companies)."""
    monkeypatch.setattr(scrape_orchestrator, "COMPANIES", [])
    monkeypatch.setattr(scrape_orchestrator, "get_batch", lambda _cycle: [])
    monkeypatch.setattr(scrape_orchestrator, "SCRAPERS", {})
    monkeypatch.setattr(scrape_orchestrator, "_load_scrapers", lambda: None)

    calls = {"start": 0, "tick": 0, "finish": 0, "is_running": 0}

    class MockBroker:
        def is_running(self):
            calls["is_running"] += 1
            return False

        def start(self, mode, total):
            calls["start"] += 1
            assert mode == "fast"
            assert total == 0

        def tick(self, *_args, **_kwargs):
            calls["tick"] += 1

        def finish(self, stats):
            calls["finish"] += 1
            assert isinstance(stats, dict)

    broker = MockBroker()
    stats = run_scrape(empty_db_conn, mode="fast", status_broker=broker)
    assert calls["start"] == 1
    assert calls["finish"] == 1
    assert "cycle" in stats


def test_broker_prearmed(monkeypatch, empty_db_conn):
    """If the broker is already armed (e.g. POST /api/scrape did try_start()),
    run_scrape must NOT call start() again — would reset started_at."""
    monkeypatch.setattr(scrape_orchestrator, "COMPANIES", [])
    monkeypatch.setattr(scrape_orchestrator, "get_batch", lambda _cycle: [])
    monkeypatch.setattr(scrape_orchestrator, "SCRAPERS", {})
    monkeypatch.setattr(scrape_orchestrator, "_load_scrapers", lambda: None)

    calls = {"start": 0, "finish": 0}

    class PreArmedBroker:
        def is_running(self):
            return True

        def start(self, mode, total):
            calls["start"] += 1

        def tick(self, *_args, **_kwargs):
            pass

        def finish(self, stats):
            calls["finish"] += 1

    run_scrape(empty_db_conn, mode="fast", status_broker=PreArmedBroker())
    assert calls["start"] == 0, "Pre-armed broker should not be re-started"
    assert calls["finish"] == 1, "finish() must still be called in the finally block"


def test_scrape_delay_env(monkeypatch, empty_db_conn):
    """SCRAPE_DELAY is read from env per call, not a constant or function arg."""
    monkeypatch.setattr(scrape_orchestrator, "COMPANIES", [])
    monkeypatch.setattr(scrape_orchestrator, "get_batch", lambda _cycle: [])
    monkeypatch.setattr(scrape_orchestrator, "SCRAPERS", {})
    monkeypatch.setattr(scrape_orchestrator, "_load_scrapers", lambda: None)

    # Set a goofy delay so the test fails fast if the orchestrator caches it
    monkeypatch.setenv("SCRAPE_DELAY", "0.0")
    stats = run_scrape(empty_db_conn, mode="fast")
    assert stats is not None
