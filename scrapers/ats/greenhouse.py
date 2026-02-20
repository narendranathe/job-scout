"""
Greenhouse ATS Scraper.
Uses the FREE public Boards API — no authentication required.

API Docs: https://developers.greenhouse.io/job-board.html
Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
"""

import logging
from typing import Optional

from config.settings import ScraperConfig
from config.company_registry import Company
from scrapers.base import BaseScraper, NormalizedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseScraper(BaseScraper):
    """Scrapes jobs from Greenhouse public Boards API."""

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        """
        Fetch all jobs from a Greenhouse board.
        API returns JSON with { jobs: [ { id, title, location, ... } ] }
        """
        url = f"{BASE_URL}/{company.board_slug}/jobs"
        params = {"content": "true"}  # include job description HTML

        try:
            resp = await self._rate_limited_get(url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.error("Greenhouse %s failed: %s", company.name, exc)
            raise

        jobs = []
        for raw in data.get("jobs", []):
            job = self._normalize(raw, company)
            if job:
                jobs.append(job)

        logger.info("Greenhouse %s: %d jobs fetched", company.name, len(jobs))
        return jobs

    def _normalize(self, raw: dict, company: Company) -> Optional[NormalizedJob]:
        """Convert Greenhouse API response to NormalizedJob."""
        title = raw.get("title", "")
        if not title:
            return None

        location_obj = raw.get("location", {})
        location = location_obj.get("name", "") if isinstance(location_obj, dict) else str(location_obj)

        # Build the apply URL
        job_id = raw.get("id", "")
        url = raw.get("absolute_url", "")
        if not url and job_id:
            url = f"https://boards.greenhouse.io/{company.board_slug}/jobs/{job_id}"

        # Extract description text from HTML content
        content = raw.get("content", "")
        description = self._strip_html(content)

        # Departments
        departments = raw.get("departments", [])
        department = departments[0].get("name", "") if departments else ""

        return NormalizedJob(
            fingerprint=NormalizedJob.make_fingerprint(title, company.name, location),
            source=company.board_slug,
            ats="greenhouse",
            title=title,
            company=company.name,
            location=location,
            url=url,
            description=description,
            department=department,
            posted_at=raw.get("updated_at", ""),
            is_remote=self.detect_remote(location, title, description),
            raw_data=raw,
        )

    @staticmethod
    def _strip_html(html: str) -> str:
        """Quick HTML tag removal for description text."""
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]  # Cap description length
