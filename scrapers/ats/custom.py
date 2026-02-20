"""
Custom scrapers for major tech companies with proprietary career APIs.
Each company has its own JSON endpoint powering their career page.
"""

import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from config.settings import ScraperConfig
from config.company_registry import Company
from scrapers.base import BaseScraper, NormalizedJob

logger = logging.getLogger(__name__)


class CustomScraper(BaseScraper):
    """
    Routes to company-specific scraping logic.
    Falls back to career page URL if no custom handler exists.
    """

    def __init__(self, config: ScraperConfig):
        super().__init__(config)
        self._handlers = {
            "google": self._scrape_google,
            "amazon": self._scrape_amazon,
            "apple": self._scrape_apple,
            "microsoft": self._scrape_microsoft,
            "meta": self._scrape_meta,
            "bloomberg": self._scrape_bloomberg,
        }

    async def scrape_company(self, company: Company) -> list[NormalizedJob]:
        handler = self._handlers.get(company.board_slug)
        if handler:
            return await handler(company)

        logger.info("No custom handler for %s — skipping", company.name)
        return []

    # ── Google ──
    async def _scrape_google(self, company: Company) -> list[NormalizedJob]:
        """Google Careers JSON API."""
        url = "https://careers.google.com/api/v3/search/"
        all_jobs = []

        for query in ["data engineer", "ml engineer", "data platform"]:
            params = {
                "q": query,
                "location": "United States",
                "page_size": 50,
                "page": 1,
            }
            try:
                resp = await self._rate_limited_get(url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.warning("Google search '%s' failed: %s", query, exc)
                continue

            for raw in data.get("search_results", []):
                job_data = raw.get("job", {})
                title = job_data.get("title", "")
                locations = job_data.get("locations", [])
                location = locations[0].get("display", "") if locations else ""
                job_id = job_data.get("id", "")

                if title:
                    all_jobs.append(NormalizedJob(
                        fingerprint=NormalizedJob.make_fingerprint(title, "Google", location),
                        source="google", ats="custom",
                        title=title, company="Google", location=location,
                        url=f"https://www.google.com/about/careers/applications/jobs/results/{job_id}",
                        description=job_data.get("description", "")[:5000],
                        department=job_data.get("department", ""),
                        posted_at=job_data.get("publish_date", ""),
                        is_remote=self.detect_remote(location, title),
                        raw_data=raw,
                    ))

        logger.info("Google: %d jobs fetched", len(all_jobs))
        return all_jobs

    # ── Amazon ──
    async def _scrape_amazon(self, company: Company) -> list[NormalizedJob]:
        """Amazon Jobs JSON API."""
        url = "https://www.amazon.jobs/en/search.json"
        all_jobs = []

        for query in ["data engineer", "ML engineer"]:
            params = {
                "base_query": query,
                "loc_query": "United States",
                "result_limit": 50,
                "sort": "recent",
            }
            try:
                resp = await self._rate_limited_get(url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.warning("Amazon search '%s' failed: %s", query, exc)
                continue

            for raw in data.get("jobs", []):
                title = raw.get("title", "")
                location = raw.get("normalized_location", raw.get("location", ""))
                job_id = raw.get("id_icims", "")

                if title:
                    all_jobs.append(NormalizedJob(
                        fingerprint=NormalizedJob.make_fingerprint(title, "Amazon", location),
                        source="amazon", ats="custom",
                        title=title, company="Amazon", location=location,
                        url=f"https://www.amazon.jobs/en/jobs/{job_id}",
                        description=raw.get("description", raw.get("basic_qualifications", ""))[:5000],
                        department=raw.get("job_category", ""),
                        posted_at=raw.get("posted_date", ""),
                        is_remote=self.detect_remote(location, title),
                        raw_data=raw,
                    ))

        logger.info("Amazon: %d jobs fetched", len(all_jobs))
        return all_jobs

    # ── Apple ──
    async def _scrape_apple(self, company: Company) -> list[NormalizedJob]:
        """Apple Jobs search API."""
        url = "https://jobs.apple.com/api/role/search"
        all_jobs = []

        for query in ["data engineer", "machine learning engineer"]:
            params = {"query": query, "location": "united-states-USA", "page": 1}
            try:
                resp = await self._rate_limited_get(url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.warning("Apple search '%s' failed: %s", query, exc)
                continue

            for raw in data.get("searchResults", []):
                posting = raw.get("postingTitle", "")
                locations = raw.get("locations", [])
                location = ", ".join(loc.get("name", "") for loc in locations[:2])
                position_id = raw.get("positionId", "")

                if posting:
                    all_jobs.append(NormalizedJob(
                        fingerprint=NormalizedJob.make_fingerprint(posting, "Apple", location),
                        source="apple", ats="custom",
                        title=posting, company="Apple", location=location,
                        url=f"https://jobs.apple.com/en-us/details/{position_id}",
                        description=raw.get("postingDescription", "")[:5000],
                        department=raw.get("team", {}).get("teamName", ""),
                        posted_at=raw.get("postDateInGMT", ""),
                        is_remote=self.detect_remote(location, posting),
                        raw_data=raw,
                    ))

        logger.info("Apple: %d jobs fetched", len(all_jobs))
        return all_jobs

    # ── Microsoft ──
    async def _scrape_microsoft(self, company: Company) -> list[NormalizedJob]:
        """Microsoft Careers API."""
        url = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
        all_jobs = []

        for query in ["data engineer", "ML engineer"]:
            params = {
                "q": query,
                "l": "en_us",
                "pg": 1,
                "pgSz": 50,
                "o": "Recent",
                "flt": "true",
            }
            try:
                resp = await self._rate_limited_get(url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.warning("Microsoft search '%s' failed: %s", query, exc)
                continue

            for raw in data.get("operationResult", {}).get("result", {}).get("jobs", []):
                props = raw.get("properties", {})
                title = props.get("title", "")
                location = props.get("primaryLocation", "")
                job_id = raw.get("jobId", "")

                if title:
                    all_jobs.append(NormalizedJob(
                        fingerprint=NormalizedJob.make_fingerprint(title, "Microsoft", location),
                        source="microsoft", ats="custom",
                        title=title, company="Microsoft", location=location,
                        url=f"https://jobs.careers.microsoft.com/global/en/job/{job_id}",
                        description=props.get("description", "")[:5000],
                        department=props.get("discipline", ""),
                        posted_at=props.get("datePosted", ""),
                        is_remote=self.detect_remote(location, title),
                        raw_data=raw,
                    ))

        logger.info("Microsoft: %d jobs fetched", len(all_jobs))
        return all_jobs

    # ── Meta ──
    async def _scrape_meta(self, company: Company) -> list[NormalizedJob]:
        """Meta Careers — scrapes the careers page JSON."""
        url = "https://www.metacareers.com/graphql"
        all_jobs = []

        # Meta uses GraphQL — try their public search endpoint instead
        search_url = "https://www.metacareers.com/jobs"
        params = {
            "q": "data engineer",
            "location[0]": "United States",
            "is_leadership": "false",
            "is_in_page": "true",
            "results_per_page": 50,
        }

        try:
            resp = await self._rate_limited_get(search_url, params=params)
            # Try to extract JSON data from the page
            text = resp.text
            # Meta embeds job data in script tags
            import json
            json_matches = re.findall(r'"jobData":\s*(\[.*?\])\s*[,}]', text)
            if json_matches:
                for match in json_matches:
                    try:
                        jobs_data = json.loads(match)
                        for raw in jobs_data:
                            title = raw.get("title", "")
                            location = raw.get("location", "")
                            if title:
                                all_jobs.append(NormalizedJob(
                                    fingerprint=NormalizedJob.make_fingerprint(title, "Meta", location),
                                    source="meta", ats="custom",
                                    title=title, company="Meta", location=location,
                                    url=raw.get("url", "https://www.metacareers.com/jobs/"),
                                    description=raw.get("description", "")[:5000],
                                    is_remote=self.detect_remote(location, title),
                                    raw_data=raw,
                                ))
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning("Meta scrape failed: %s", exc)

        logger.info("Meta: %d jobs fetched", len(all_jobs))
        return all_jobs

    # ── Bloomberg ──
    async def _scrape_bloomberg(self, company: Company) -> list[NormalizedJob]:
        """Bloomberg Careers API."""
        url = "https://careers.bloomberg.com/job/search"
        params = {"q": "data engineer", "limit": 50}

        all_jobs = []
        try:
            resp = await self._rate_limited_get(url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.warning("Bloomberg failed: %s", exc)
            return all_jobs

        for raw in data if isinstance(data, list) else data.get("hits", data.get("jobs", [])):
            title = raw.get("title", raw.get("name", ""))
            location = raw.get("location", "")
            if isinstance(location, list):
                location = ", ".join(location)

            if title:
                all_jobs.append(NormalizedJob(
                    fingerprint=NormalizedJob.make_fingerprint(title, "Bloomberg", location),
                    source="bloomberg", ats="custom",
                    title=title, company="Bloomberg", location=location,
                    url=raw.get("url", "https://careers.bloomberg.com/"),
                    description=raw.get("description", "")[:5000],
                    is_remote=self.detect_remote(location, title),
                    raw_data=raw,
                ))

        logger.info("Bloomberg: %d jobs fetched", len(all_jobs))
        return all_jobs
