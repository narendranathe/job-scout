"""
Lever ATS Scraper.
Uses the FREE public Postings API — no authentication required.

API Docs: https://github.com/lever/postings-api
Endpoint: GET https://api.lever.co/v0/postings/{company}?mode=json
"""

import logging
from typing import Optional

from config.settings import ScraperConfig
from config.company_registry import Company
from scrapers.base import BaseScraper, NormalizedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings"


class LeverScraper(BaseScraper):
    """Scrapes jobs from Lever public Postings API."""

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        url = f"{BASE_URL}/{company.board_slug}"
        params = {"mode": "json"}

        try:
            resp = await self._rate_limited_get(url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.error("Lever %s failed: %s", company.name, exc)
            raise

        # Lever returns a flat JSON array
        raw_jobs = data if isinstance(data, list) else []

        jobs = []
        for raw in raw_jobs:
            job = self._normalize(raw, company)
            if job:
                jobs.append(job)

        logger.info("Lever %s: %d jobs fetched", company.name, len(jobs))
        return jobs

    def _normalize(self, raw: dict, company: Company) -> Optional[NormalizedJob]:
        title = raw.get("text", "")
        if not title:
            return None

        # Lever categories
        categories = raw.get("categories", {})
        location = categories.get("location", "")
        department = categories.get("department", "")
        team = categories.get("team", "")

        # Description from lists
        desc_parts = []
        for section in raw.get("lists", []):
            desc_parts.append(section.get("text", ""))
            desc_parts.append(section.get("content", ""))
        description = " ".join(desc_parts)

        # Additional description
        desc_plain = raw.get("descriptionPlain", "")
        if desc_plain:
            description = f"{desc_plain} {description}"

        # Lever provides apply URL directly
        url = raw.get("hostedUrl", raw.get("applyUrl", ""))

        return NormalizedJob(
            fingerprint=NormalizedJob.make_fingerprint(title, company.name, location),
            source=company.board_slug,
            ats="lever",
            title=title,
            company=company.name,
            location=location,
            url=url,
            description=self._clean_text(description),
            department=department or team,
            posted_at=str(raw.get("createdAt", "")),
            is_remote=self.detect_remote(location, title, description),
            raw_data=raw,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]
