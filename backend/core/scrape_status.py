"""
Thread-safe scrape progress broker.

Module-level singleton `broker` shared by the manual-trigger handler and
the (future) background scrape thread. Tracks per-cycle progress so the
dashboard can poll GET /api/scrape/status for live company-by-company
status without coupling to the scraper internals.

Watchdog: is_running() auto-flips to False if started_at is older than
WATCHDOG_SECONDS (10 min) even when the internal flag is still set —
this protects against a scraper thread that crashes before calling
finish() and would otherwise wedge /api/scrape behind a 409 forever.
"""

import copy
import threading
from datetime import datetime, timezone

WATCHDOG_SECONDS = 600  # 10 minutes


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StatusBroker:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: dict = {
            "is_running":       False,
            "started_at":       None,
            "last_tick_at":     None,
            "finished_at":      None,
            "mode":             None,
            "companies_done":   0,
            "companies_total":  0,
            "current_company":  None,
            "found":            0,
            "new":              0,
            "errors":           0,
            "eta_seconds":      None,
            "final_stats":      None,
        }

    def start(self, mode: str, total: int) -> None:
        with self._lock:
            now = _now_iso()
            self._state.update({
                "is_running":      True,
                "started_at":      now,
                "last_tick_at":    now,
                "finished_at":     None,
                "mode":            mode,
                "companies_done":  0,
                "companies_total": max(int(total), 0),
                "current_company": None,
                "found":           0,
                "new":             0,
                "errors":          0,
                "eta_seconds":     None,
                "final_stats":     None,
            })

    def try_start(self, mode: str, total: int) -> bool:
        """Atomic check-and-start: returns True if we successfully transitioned
        from idle → running, False if a scrape was already running. The caller
        uses this to gate the POST /api/scrape handler so rapid concurrent POSTs
        can't both pass the is_running() check before either calls start()."""
        with self._lock:
            if self.is_running():
                return False
            self.start(mode, total)
            return True

    def tick(self, company: str, found_delta: int = 0, new_delta: int = 0,
             error_delta: int = 0) -> None:
        with self._lock:
            self._state["current_company"] = company
            self._state["companies_done"] += 1
            self._state["found"]          += int(found_delta)
            self._state["new"]            += int(new_delta)
            self._state["errors"]         += int(error_delta)
            # Liveness signal for the watchdog — without this, a long but
            # healthy scrape would be auto-killed at WATCHDOG_SECONDS even
            # though it's still making progress.
            self._state["last_tick_at"] = _now_iso()

            done  = self._state["companies_done"]
            total = self._state["companies_total"]
            started = self._state["started_at"]
            if done > 0 and total > done and started:
                try:
                    elapsed = (datetime.now(timezone.utc)
                               - datetime.fromisoformat(started)).total_seconds()
                    per_company = elapsed / done
                    self._state["eta_seconds"] = round(per_company * (total - done), 1)
                except Exception:
                    self._state["eta_seconds"] = None
            else:
                self._state["eta_seconds"] = 0 if total and done >= total else None

    def finish(self, stats: dict | None = None) -> None:
        with self._lock:
            self._state["is_running"]  = False
            self._state["finished_at"] = _now_iso()
            self._state["eta_seconds"] = 0
            if stats:
                self._state["final_stats"] = dict(stats)

    def is_running(self) -> bool:
        with self._lock:
            if not self._state["is_running"]:
                return False
            # Watchdog uses last_tick_at (set by tick()) so a healthy
            # long-running scrape can't be auto-killed — only one that has
            # gone silent for WATCHDOG_SECONDS counts as wedged. Falls back
            # to started_at for runs that haven't ticked yet.
            last = self._state.get("last_tick_at") or self._state.get("started_at")
            if not last:
                return False
            try:
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(last)).total_seconds()
            except Exception:
                return False
            if age > WATCHDOG_SECONDS:
                # Stale run — auto-reset so a crashed scrape thread doesn't
                # wedge the /api/scrape endpoint behind a permanent 409.
                self._state["is_running"]  = False
                self._state["finished_at"] = _now_iso()
                return False
            return True

    def snapshot(self) -> dict:
        with self._lock:
            snap = copy.deepcopy(self._state)
            snap["is_running"] = self.is_running()
            return snap


broker = StatusBroker()
