"""
SmartRecruiters Scraper.
Uses the public Job API — no authentication required.

Endpoint: GET https://api.smartrecruiters.com/v1/companies/{id}/postings
"""

import logging
from typing import Optional

from config.settings import ScraperConfig
from config.company_registry import Company
from scrapers.base import BaseScraper, NormalizedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://api.smartrecruiters.com/v1/companies"


class SmartRecruitersScraper(BaseScraper):

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        url = f"{BASE_URL}/{company.board_slug}/postings"
        params = {"limit": 100}

        all_jobs: list[NormalizedJob] = []
        offset = 0

        while True:
            params["offset"] = offset
            try:
                resp = await self._rate_limited_get(url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.error("SmartRecruiters %s failed: %s", company.name, exc)
                raise

            content = data.get("content", [])
            for raw in content:
                job = self._normalize(raw, company)
                if job:
                    all_jobs.append(job)

            # Pagination
            total = data.get("totalFound", 0)
            offset += len(content)
            if offset >= total or not content:
                break

        logger.info("SmartRecruiters %s: %d jobs fetched", company.name, len(all_jobs))
        return all_jobs

    def _normalize(self, raw: dict, company: Company) -> Optional[NormalizedJob]:
        title = raw.get("name", "")
        if not title:
            return None

        location_obj = raw.get("location", {})
        city = location_obj.get("city", "")
        region = location_obj.get("region", "")
        country = location_obj.get("country", "")
        location = ", ".join(filter(None, [city, region, country]))

        department_obj = raw.get("department", {})
        department = department_obj.get("label", "") if isinstance(department_obj, dict) else ""

        url = raw.get("ref", raw.get("applyUrl", ""))
        description = raw.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "")

        import re
        description = re.sub(r"<[^>]+>", " ", description)[:5000]

        return NormalizedJob(
            fingerprint=NormalizedJob.make_fingerprint(title, company.name, location),
            source=company.board_slug,
            ats="smartrecruiters",
            title=title,
            company=company.name,
            location=location,
            url=url,
            description=description,
            department=department,
            posted_at=raw.get("releasedDate", ""),
            is_remote=self.detect_remote(location, title, description),
            raw_data=raw,
        )
