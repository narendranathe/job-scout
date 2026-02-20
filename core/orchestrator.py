"""
Scraper Orchestrator — coordinates all direct ATS/board scrapers.
Self-recovery: circuit breakers, concurrent scraping with semaphore,
graceful degradation, automatic metric recording.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from config.settings import AppConfig
from config.profile import UserProfile
from config.company_registry import COMPANY_REGISTRY, Company, get_companies_by_priority
from core.relevance_engine import RelevanceEngine
from scrapers.factory import ScraperFactory
from storage.database import JobDatabase
from notifiers.email_notifier import EmailNotifier

logger = logging.getLogger(__name__)


class Orchestrator:

    def __init__(self, config: AppConfig):
        self.config = config
        self.profile = UserProfile()
        self.db = JobDatabase(config.database.db_path, config.database.wal_mode)
        self.factory = ScraperFactory(config.scraper)
        self.relevance = RelevanceEngine(self.profile)
        self.email = EmailNotifier(config.notification)
        self._running = False
        self._cycle_count = 0
        self._semaphore = asyncio.Semaphore(config.scraper.max_concurrent)

    async def start(self) -> None:
        """Start continuous scraping loop."""
        self._running = True
        logger.info(
            "🚀 JobScout starting — %d companies, every %d min, priority ≤ %d",
            len(self._get_companies()), self.config.scheduler.scrape_interval_minutes,
            self.config.scheduler.priority_filter,
        )
        for w in self.config.validate():
            logger.warning("Config: %s", w)

        try:
            while self._running:
                self._cycle_count += 1
                if self._is_quiet_hours():
                    logger.info("🌙 Quiet hours — skipping cycle %d", self._cycle_count)
                else:
                    await self._run_cycle()
                self.db.record_metric("heartbeat", 1.0, {"cycle": self._cycle_count})
                if self._cycle_count % 10 == 0:
                    self.db.cleanup_old_metrics(self.config.monitor.metrics_retention_hours)
                await asyncio.sleep(self.config.scheduler.scrape_interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("Cancelled — shutting down")
        finally:
            await self.factory.close_all()
            self._running = False

    async def stop(self):
        self._running = False

    async def run_once(self) -> dict:
        """Single cycle for testing."""
        try:
            return await self._run_cycle()
        finally:
            await self.factory.close_all()

    async def _run_cycle(self) -> dict:
        cycle_start = time.monotonic()
        companies = self._get_companies()
        stats = {"total_found": 0, "total_new": 0, "total_relevant": 0,
                 "succeeded": 0, "failed": 0, "skipped": 0}

        logger.info("━━━ Cycle %d: scraping %d companies ━━━", self._cycle_count, len(companies))

        # Scrape all companies concurrently (bounded by semaphore)
        tasks = [self._scrape_one(company, stats) for company in companies]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Post-cycle notifications
        await self._send_notifications()

        duration = time.monotonic() - cycle_start
        stats["duration_seconds"] = round(duration, 2)

        self.db.record_metric("cycle_duration", duration)
        self.db.record_metric("cycle_jobs_found", stats["total_found"])
        self.db.record_metric("cycle_jobs_new", stats["total_new"])

        logger.info(
            "━━━ Cycle %d done: %d found, %d new, %d relevant, %d ok / %d fail / %d skip (%.1fs) ━━━",
            self._cycle_count, stats["total_found"], stats["total_new"],
            stats["total_relevant"], stats["succeeded"], stats["failed"],
            stats["skipped"], duration,
        )
        return stats

    async def _scrape_one(self, company: Company, stats: dict) -> None:
        """Scrape a single company with semaphore concurrency control."""
        # Circuit breaker check
        if self.db.is_circuit_open(company.board_slug):
            logger.debug("⚡ Circuit open: %s — skipping", company.name)
            stats["skipped"] += 1
            return

        async with self._semaphore:
            run_id = self.db.start_run(company.name, company.ats.value)
            start = time.monotonic()

            try:
                raw_jobs = await self.factory.scrape(company)
                duration = time.monotonic() - start

                new_count, relevant_count = 0, 0
                for job in raw_jobs:
                    job_dict = job.to_dict()
                    job_dict = self.relevance.enrich_job(job_dict)

                    inserted = self.db.insert_job(job_dict)
                    if inserted is not None:
                        new_count += 1
                        if job_dict["relevance_score"] >= self.config.notification.min_score_for_log:
                            relevant_count += 1
                            logger.info(
                                "✨ [%.0f%%] %s @ %s (%s) — %s",
                                job_dict["relevance_score"] * 100,
                                job_dict["title"], company.name,
                                company.ats.value,
                                ", ".join(job_dict.get("matched_skills", [])[:5]),
                            )

                self.db.complete_run(run_id, len(raw_jobs), new_count, relevant_count, duration)
                self.db.record_success(company.board_slug)

                stats["total_found"] += len(raw_jobs)
                stats["total_new"] += new_count
                stats["total_relevant"] += relevant_count
                stats["succeeded"] += 1

                if raw_jobs:
                    logger.info("✅ %s: %d found, %d new", company.name, len(raw_jobs), new_count)

            except Exception as exc:
                duration = time.monotonic() - start
                self.db.fail_run(run_id, str(exc), duration)
                circuit_opened = self.db.record_failure(
                    company.board_slug, self.config.monitor.max_consecutive_failures
                )
                if circuit_opened:
                    logger.critical("🔴 Circuit OPEN for %s", company.name)
                else:
                    logger.warning("❌ %s failed: %s", company.name, exc)
                stats["failed"] += 1

            # Stagger between companies
            await asyncio.sleep(self.config.scheduler.stagger_seconds)

    async def _send_notifications(self) -> None:
        jobs = self.db.get_unnotified_jobs(self.config.notification.min_score_for_email)
        if not jobs:
            return
        logger.info("📬 Notifying about %d jobs", len(jobs))
        try:
            if await self.email.send_job_digest(jobs):
                self.db.mark_notified([j["id"] for j in jobs])
        except Exception as exc:
            logger.error("Notification error: %s", exc)

    def _get_companies(self) -> list[Company]:
        return get_companies_by_priority(self.config.scheduler.priority_filter)

    def _is_quiet_hours(self) -> bool:
        hour = datetime.now(timezone.utc).hour
        s, e = self.config.scheduler.quiet_hours_start, self.config.scheduler.quiet_hours_end
        return hour >= s or hour < e if s > e else s <= hour < e

    def get_dashboard_data(self) -> dict:
        return {
            "job_stats": self.db.get_job_stats(),
            "recent_runs": self.db.get_recent_runs(30),
            "top_jobs": self.db.get_top_jobs(25, days=7),
            "cycle_count": self._cycle_count,
            "is_running": self._running,
            "total_companies": len(self._get_companies()),
        }
