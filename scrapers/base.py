"""
Base scraper with shared HTTP client, retry logic, rate limiting,
and the standard normalized job schema.
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from config.settings import ScraperConfig
from config.company_registry import Company

logger = logging.getLogger(__name__)


@dataclass
class NormalizedJob:
    """Standard job schema produced by all scrapers."""
    fingerprint: str
    source: str        # company slug
    ats: str           # greenhouse, lever, etc.
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    department: str = ""
    posted_at: str = ""
    is_remote: bool = False
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def make_fingerprint(title: str, company: str, location: str = "") -> str:
        """Deterministic dedup key."""
        raw = f"{title.lower().strip()}-{company.lower().strip()}-{location.lower().strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


class BaseScraper(ABC):
    """
    Abstract base for all ATS/board scrapers.
    Provides: HTTP client, retry with backoff, domain rate limiting.
    """

    def __init__(self, config: ScraperConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._domain_last_request: dict[str, float] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.request_timeout),
                headers={
                    "User-Agent": self.config.user_agent,
                    "Accept": "application/json, text/html",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
                http2=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limited_get(
        self, url: str, params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        """GET with domain-level rate limiting and retry."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc

        # Rate limit per domain
        now = time.monotonic()
        last = self._domain_last_request.get(domain, 0)
        wait = self.config.rate_limit_per_domain - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)

        client = await self._get_client()

        for attempt in range(1, self.config.max_retries + 1):
            try:
                self._domain_last_request[domain] = time.monotonic()
                resp = await client.get(url, params=params, headers=headers)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "30"))
                    logger.warning("Rate limited on %s, waiting %ds", domain, retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp

            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                backoff = self.config.retry_backoff_base ** attempt
                logger.warning(
                    "Attempt %d/%d failed for %s: %s (backoff %.1fs)",
                    attempt, self.config.max_retries, url, exc, backoff,
                )
                if attempt == self.config.max_retries:
                    raise
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Exhausted retries for {url}")

    async def _rate_limited_post(
        self, url: str, json_data: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        """POST with domain-level rate limiting and retry."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc

        now = time.monotonic()
        last = self._domain_last_request.get(domain, 0)
        wait = self.config.rate_limit_per_domain - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)

        client = await self._get_client()

        for attempt in range(1, self.config.max_retries + 1):
            try:
                self._domain_last_request[domain] = time.monotonic()
                resp = await client.post(url, json=json_data, headers=headers)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "30"))
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp

            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                backoff = self.config.retry_backoff_base ** attempt
                if attempt == self.config.max_retries:
                    raise
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Exhausted retries for {url}")

    @abstractmethod
    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        """Scrape all jobs from a company. Subclasses implement this."""
        ...

    @staticmethod
    def detect_remote(location: str, title: str = "", description: str = "") -> bool:
        combined = f"{location} {title} {description}".lower()
        signals = ["remote", "work from home", "wfh", "anywhere", "distributed"]
        return any(s in combined for s in signals)

    @staticmethod
    def parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
        """Extract min/max salary from text."""
        if not text:
            return None, None
        import re
        amounts = re.findall(r"\$?([\d,]+(?:\.\d+)?)\s*[Kk]?", text)
        if not amounts:
            return None, None
        parsed = []
        for amt in amounts:
            val = float(amt.replace(",", ""))
            if val < 1000:
                val *= 1000
            parsed.append(int(val))
        if len(parsed) >= 2:
            return min(parsed), max(parsed)
        return parsed[0], parsed[0]
