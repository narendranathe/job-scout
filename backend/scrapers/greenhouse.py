"""
Greenhouse ATS scraper.
API docs: https://developers.greenhouse.io/job-board.html

Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
Returns JSON array of all public job postings.
No authentication required — this is a public API.
"""

import logging
import requests
from typing import Generator

from .utils import is_remote, strip_html

log = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
TIMEOUT = 30


def scrape(company: dict) -> Generator[dict, None, None]:
    """
    Scrape all jobs from a Greenhouse board.

    Args:
        company: dict with keys 'name', 'ats', 'slug'

    Yields:
        Normalized job dicts ready for storage.
    """
    slug = company["slug"]
    name = company["name"]
    url = BASE_URL.format(slug=slug)

    try:
        resp = requests.get(url, params={"content": "true"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.error("Greenhouse [%s] failed: %s", name, e)
        return

    jobs = data.get("jobs", [])
    log.info("Greenhouse [%s] → %d jobs", name, len(jobs))

    for job in jobs:
        try:
            # Extract location
            location = ""
            loc_obj = job.get("location", {})
            if isinstance(loc_obj, dict):
                location = loc_obj.get("name", "")
            elif isinstance(loc_obj, str):
                location = loc_obj

            # Extract department
            departments = job.get("departments", [])
            department = departments[0].get("name", "") if departments else ""

            # Build description text (strip HTML tags)
            content = job.get("content", "")
            description = strip_html(content)

            # Detect remote
            title_str = job.get("title", "")
            remote = is_remote(location, title_str, description)

            # Build apply URL
            job_id = job.get("id", "")
            apply_url = f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"

            yield {
                "external_id": f"gh-{slug}-{job_id}",
                "title": title_str.strip(),
                "company": name,
                "location": location,
                "department": department,
                "description": description[:5000],
                "url": apply_url,
                "ats": "greenhouse",
                "is_remote": remote,
                "posted_at": (job.get("updated_at") or job.get("first_published_at") or "")[:19],
                "salary_min": 0,
                "salary_max": 0,
            }
        except Exception as e:
            log.warning("Greenhouse [%s] job parse error: %s", name, e)
            continue


