"""
Health Monitor — async HTTP server for liveness probes and dashboard API.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from aiohttp import web

from config.settings import MonitorConfig
from storage.database import JobDatabase

logger = logging.getLogger(__name__)


class HealthMonitor:

    def __init__(self, config: MonitorConfig, db: JobDatabase):
        self.config = config
        self.db = db
        self._app = web.Application()
        self._runner = None
        self._orchestrator = None
        self._app.router.add_get("/health", self._health)
        self._app.router.add_get("/api/dashboard", self._dashboard)
        self._app.router.add_get("/api/jobs", self._jobs)
        self._app.router.add_get("/api/runs", self._runs)
        self._app.router.add_get("/api/metrics", self._metrics)

    def set_orchestrator(self, orch):
        self._orchestrator = orch

    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "0.0.0.0", self.config.health_check_port).start()
        logger.info("📡 Monitor on http://0.0.0.0:%d", self.config.health_check_port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def _health(self, req):
        return web.json_response({"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()})

    async def _dashboard(self, req):
        if not self._orchestrator:
            return web.json_response({"error": "not ready"}, status=503)
        return web.json_response(self._orchestrator.get_dashboard_data(), dumps=lambda o: json.dumps(o, default=str))

    async def _jobs(self, req):
        limit = int(req.query.get("limit", "25"))
        return web.json_response({"jobs": self.db.get_top_jobs(limit)}, dumps=lambda o: json.dumps(o, default=str))

    async def _runs(self, req):
        return web.json_response({"runs": self.db.get_recent_runs(30)}, dumps=lambda o: json.dumps(o, default=str))

    async def _metrics(self, req):
        name = req.query.get("name", "cycle_duration")
        hours = int(req.query.get("hours", "24"))
        return web.json_response({"data": self.db.get_metrics(name, hours)}, dumps=lambda o: json.dumps(o, default=str))
