"""
JobScout — Self-recovering job pipeline. Zero third-party API keys.

Usage:
    python main.py                  # Continuous scraping
    python main.py --once           # Single cycle
    python main.py --stats          # Print stats
    python main.py --companies      # List tracked companies
    python main.py --dashboard-only # Monitoring server only
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import AppConfig
from core.orchestrator import Orchestrator
from monitors.health_monitor import HealthMonitor


def setup_logging(level: str = "INFO") -> None:
    data_dir = Path.home() / ".job_scout"
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s │ %(levelname)-8s │ %(name)-28s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(data_dir / "scout.log", mode="a"),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def run_continuous(config: AppConfig) -> None:
    orch = Orchestrator(config)
    monitor = HealthMonitor(config.monitor, orch.db)
    monitor.set_orchestrator(orch)

    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    await monitor.start()
    task = asyncio.create_task(orch.start())
    await shutdown.wait()

    await orch.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await monitor.stop()


async def run_once(config: AppConfig) -> None:
    orch = Orchestrator(config)
    stats = await orch.run_once()
    print(json.dumps(stats, indent=2))


def print_stats(config: AppConfig) -> None:
    from storage.database import JobDatabase
    db = JobDatabase(config.database.db_path)
    s = db.get_job_stats()
    print(f"\n📊 JobScout Stats")
    print("─" * 45)
    print(f"  Total tracked:       {s['total_jobs']}")
    print(f"  Today:               {s['today_jobs']}")
    print(f"  Avg relevance:       {s['avg_relevance']:.1%}")
    print(f"  High relevance:      {s['high_relevance_count']}")
    print(f"\n  By ATS:")
    for ats, cnt in s.get("by_ats", {}).items():
        print(f"    {ats:20s} {cnt}")
    print(f"\n  Top companies:")
    for co, cnt in list(s.get("by_company", {}).items())[:15]:
        print(f"    {(co or '?'):25s} {cnt}")

    top = db.get_top_jobs(10, 7)
    if top:
        print(f"\n🏆 Top 10 (7 days)")
        print("─" * 60)
        for j in top:
            print(f"  [{j['relevance_score']:.0%}] {j['title'][:35]:35s} @ {(j.get('company') or '?')[:20]}")
    print()


def list_companies(config: AppConfig) -> None:
    from config.company_registry import COMPANY_REGISTRY, get_companies_by_priority
    companies = get_companies_by_priority(config.scheduler.priority_filter)
    print(f"\n📋 Tracking {len(companies)} companies (priority ≤ {config.scheduler.priority_filter})")
    print("─" * 65)
    from collections import Counter
    by_ats = Counter(c.ats.value for c in companies)
    for ats, cnt in by_ats.most_common():
        print(f"\n  {ats.upper()} ({cnt}):")
        for c in sorted([x for x in companies if x.ats.value == ats], key=lambda x: x.name):
            p = "★" * c.priority + "☆" * (3 - c.priority)
            print(f"    {p} {c.name:25s} ({c.board_slug})")
    print()


def main():
    parser = argparse.ArgumentParser(description="JobScout — Self-recovering job pipeline")
    parser.add_argument("--once", action="store_true", help="Single scraping cycle")
    parser.add_argument("--stats", action="store_true", help="Print statistics")
    parser.add_argument("--companies", action="store_true", help="List tracked companies")
    parser.add_argument("--dashboard-only", action="store_true", help="Monitor server only")
    parser.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    Path.home().joinpath(".job_scout").mkdir(parents=True, exist_ok=True)
    config = AppConfig()
    setup_logging(args.log_level or config.log_level)

    if args.stats:
        print_stats(config)
    elif args.companies:
        list_companies(config)
    elif args.once:
        asyncio.run(run_once(config))
    elif args.dashboard_only:
        async def _dash():
            from storage.database import JobDatabase
            db = JobDatabase(config.database.db_path)
            m = HealthMonitor(config.monitor, db)
            await m.start()
            await asyncio.Event().wait()
        asyncio.run(_dash())
    else:
        asyncio.run(run_continuous(config))


if __name__ == "__main__":
    main()
