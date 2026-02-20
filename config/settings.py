"""
Configuration management for JobScout.
Environment-variable driven, zero third-party API keys required for core scraping.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScraperConfig:
    """HTTP scraping settings."""
    max_concurrent: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT", "5")))
    request_timeout: int = 30
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    rate_limit_per_domain: float = 2.0  # seconds between requests to same domain
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


@dataclass(frozen=True)
class DatabaseConfig:
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("DB_PATH", str(Path.home() / ".job_scout" / "jobs.db"))
        )
    )
    wal_mode: bool = True


@dataclass(frozen=True)
class NotificationConfig:
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    recipient_email: str = field(default_factory=lambda: os.getenv("RECIPIENT_EMAIL", ""))
    min_score_for_email: float = 0.65
    min_score_for_log: float = 0.40
    cooldown_seconds: int = 300


@dataclass(frozen=True)
class MonitorConfig:
    health_check_port: int = field(
        default_factory=lambda: int(os.getenv("HEALTH_PORT", "8089"))
    )
    metrics_retention_hours: int = 72
    max_consecutive_failures: int = 5


@dataclass(frozen=True)
class SchedulerConfig:
    scrape_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("SCRAPE_INTERVAL", "30"))
    )
    stagger_seconds: float = 1.5  # delay between companies
    quiet_hours_start: int = 23
    quiet_hours_end: int = 6
    priority_filter: int = field(
        default_factory=lambda: int(os.getenv("PRIORITY_FILTER", "2"))
    )  # 1=top only, 2=top+medium, 3=all


@dataclass
class AppConfig:
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    def validate(self) -> list[str]:
        warnings = []
        if not self.notification.smtp_user:
            warnings.append("SMTP_USER not set — email notifications disabled")
        if not self.notification.recipient_email:
            warnings.append("RECIPIENT_EMAIL not set — email notifications disabled")
        return warnings
