"""
Workday Scraper.
Workday career pages are SPAs that call internal JSON APIs.
We hit the same API their frontend uses — no auth needed.

Pattern: POST https://{company}.wd{N}.myworkdayjobs.com/wday/cxs/{company}/{board}/jobs
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from config.settings import ScraperConfig
from config.company_registry import Company
from scrapers.base import BaseScraper, NormalizedJob

logger = logging.getLogger(__name__)


class WorkdayScraper(BaseScraper):
    """
    Scrapes Workday career sites via their internal CXS JSON API.
    The `notes` field on each Company should contain the base URL like:
        https://disney.wd5.myworkdayjobs.com/en-US/disneycareer
    """

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        base_url = company.notes or company.career_url
        if not base_url:
            logger.warning("Workday %s: no base URL configured", company.name)
            return []

        api_url, board_path = self._build_api_url(base_url)
        if not api_url:
            logger.warning("Workday %s: couldn't parse API URL from %s", company.name, base_url)
            return []

        all_jobs: list[NormalizedJob] = []
        offset = 0
        limit = 20

        while True:
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "",
            }

            try:
                resp = await self._rate_limited_post(
                    api_url, json_data=payload,
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json()
            except Exception as exc:
                logger.error("Workday %s failed: %s", company.name, exc)
                raise

            postings = data.get("jobPostings", [])
            total = data.get("total", 0)

            for raw in postings:
                job = self._normalize(raw, company, base_url, board_path)
                if job:
                    all_jobs.append(job)

            offset += len(postings)
            if offset >= total or not postings:
                break

            # Safety cap to avoid runaway pagination
            if offset > 500:
                logger.info("Workday %s: capping at 500 results", company.name)
                break

        logger.info("Workday %s: %d jobs fetched", company.name, len(all_jobs))
        return all_jobs

    def _build_api_url(self, base_url: str) -> tuple[str, str]:
        """
        Convert a Workday career page URL into the CXS API endpoint.
        Input:  https://disney.wd5.myworkdayjobs.com/en-US/disneycareer
        Output: https://disney.wd5.myworkdayjobs.com/wday/cxs/disney/disneycareer/jobs
        """
        try:
            parsed = urlparse(base_url.rstrip("/"))
            host = parsed.netloc  # e.g., disney.wd5.myworkdayjobs.com
            path_parts = [p for p in parsed.path.split("/") if p and p != "en-US"]

            if not path_parts:
                return "", ""

            # Extract company subdomain and board name
            subdomain = host.split(".")[0]  # disney
            board = path_parts[-1]  # disneycareer

            api_url = f"https://{host}/wday/cxs/{subdomain}/{board}/jobs"
            return api_url, board

        except Exception as exc:
            logger.error("Failed to parse Workday URL %s: %s", base_url, exc)
            return "", ""

    def _normalize(
        self, raw: dict, company: Company,
        base_url: str, board_path: str,
    ) -> Optional[NormalizedJob]:
        title = raw.get("title", "")
        if not title:
            return None

        # Location
        bullet_fields = raw.get("bulletFields", [])
        location = bullet_fields[0] if bullet_fields else ""

        # Build full job URL from external path
        external_path = raw.get("externalPath", "")
        parsed_base = urlparse(base_url)
        url = f"https://{parsed_base.netloc}/en-US{external_path}" if external_path else ""

        # Posted date
        posted_on = raw.get("postedOn", "")

        return NormalizedJob(
            fingerprint=NormalizedJob.make_fingerprint(title, company.name, location),
            source=company.board_slug,
            ats="workday",
            title=title,
            company=company.name,
            location=location,
            url=url,
            description="",  # Workday list API doesn't include descriptions
            posted_at=posted_on,
            is_remote=self.detect_remote(location, title),
            raw_data=raw,
        )
