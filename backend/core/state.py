"""Shared mutable state for the JobScout server — extracted from server.py.

Two consumers in this codebase:
1. The background scrape loop (writes ``is_scraping``, ``record_cycle``,
   ``update_cache``).
2. Read-only route handlers (read ``health()`` for /api/health, ``get_cache``
   for /api/data).

Kept as a singleton imported from this module so routes split across
multiple Blueprint files can all reach the same object without circular
imports back through ``server``.

Thread-safety note: GIL serializes the attribute writes inside Python,
and the cycle counters are advisory rather than strictly accurate, so we
deliberately don't lock. The cache assignment is atomic at the
attribute-binding level. If a future test or production concern requires
hard accuracy, wrap mutations in a ``threading.Lock``.
"""
import json
from datetime import datetime, timezone

from config.companies import TOTAL_COMPANIES
from core.config import FAST_INTERVAL


class State:
    def __init__(self):
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.last_scrape_at = None
        self.last_duration = 0
        self.total_cycles = 0
        self.total_new = 0
        self.last_error = None
        self.is_scraping = False
        self._cached_json = None
        self._cached_at = None

    def update_cache(self, data: dict):
        self._cached_json = json.dumps(data, default=str, separators=(",", ":"))
        self._cached_at = datetime.now(timezone.utc).isoformat()

    def get_cache(self) -> str | None:
        return self._cached_json

    def record_cycle(self, duration: float, stats: dict, error: str = None):
        self.last_scrape_at = datetime.now(timezone.utc).isoformat()
        self.last_duration = round(duration, 1)
        self.total_cycles += 1
        self.total_new += stats.get("new", 0)
        self.last_error = error
        self.is_scraping = False

    def health(self) -> dict:
        return {
            "status":            "scraping" if self.is_scraping else "idle",
            "started_at":        self.started_at,
            "uptime_hours":      round(
                (datetime.now(timezone.utc) - datetime.fromisoformat(self.started_at)).total_seconds() / 3600, 1
            ),
            "last_scrape_at":    self.last_scrape_at,
            "last_duration_sec": self.last_duration,
            "total_cycles":      self.total_cycles,
            "total_new_jobs":    self.total_new,
            "last_error":        self.last_error,
            "cache_fresh_at":    self._cached_at,
            "companies_tracked": TOTAL_COMPANIES,
            "fast_interval_sec": FAST_INTERVAL,
        }


# Process-wide singleton. server.py re-exports this for backward compat.
state = State()
