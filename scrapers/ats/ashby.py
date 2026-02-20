"""
Ashby ATS Scraper.
Uses the public Job Board API — no authentication required.

Endpoint: POST https://api.ashbyhq.com/posting-api/job-board/{slug}
"""

import logging
from typing import Optional

from config.settings import ScraperConfig
from config.company_registry import Company
from scrapers.base import BaseScraper, NormalizedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyScraper(BaseScraper):

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        url = f"{BASE_URL}/{company.board_slug}"

        try:
            resp = await self._rate_limited_post(url)
            data = resp.json()
        except Exception as exc:
            logger.error("Ashby %s failed: %s", company.name, exc)
            raise

        jobs = []
        for raw in data.get("jobs", []):
            job = self._normalize(raw, company)
            if job:
                jobs.append(job)

        logger.info("Ashby %s: %d jobs fetched", company.name, len(jobs))
        return jobs

    def _normalize(self, raw: dict, company: Company) -> Optional[NormalizedJob]:
        title = raw.get("title", "")
        if not title:
            return None

        location = raw.get("location", "")
        if isinstance(location, dict):
            location = location.get("name", "")

        department = raw.get("department", "")
        url = raw.get("jobUrl", raw.get("applyUrl", ""))
        description = raw.get("descriptionPlain", raw.get("description", ""))

        import re
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()[:5000]

        return NormalizedJob(
            fingerprint=NormalizedJob.make_fingerprint(title, company.name, location),
            source=company.board_slug,
            ats="ashby",
            title=title,
            company=company.name,
            location=location,
            url=url,
            description=description,
            department=department,
            posted_at=raw.get("publishedAt", ""),
            is_remote=self.detect_remote(location, title, description),
            raw_data=raw,
        )
