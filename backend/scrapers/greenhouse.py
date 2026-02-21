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

log = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
DETAIL_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
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

            # Build description text (strip HTML tags roughly)
            content = job.get("content", "")
            description = _strip_html(content)

            # Detect remote
            is_remote = _is_remote(location, job.get("title", ""), description)

            # Build apply URL
            job_id = job.get("id", "")
            apply_url = f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"

            yield {
                "external_id": f"gh-{slug}-{job_id}",
                "title": job.get("title", "").strip(),
                "company": name,
                "location": location,
                "department": department,
                "description": description[:5000],  # Truncate for storage
                "url": apply_url,
                "ats": "greenhouse",
                "is_remote": is_remote,
                "posted_at": (job.get("updated_at") or job.get("first_published_at") or "")[:19],
                "salary_min": 0,
                "salary_max": 0,
            }
        except Exception as e:
            log.warning("Greenhouse [%s] job parse error: %s", name, e)
            continue


def _strip_html(html: str) -> str:
    """Rough HTML tag removal for description text."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_remote(location: str, title: str, description: str) -> bool:
    """Detect if job is remote from location/title/description."""
    combined = f"{location} {title} {description[:500]}".lower()
    return any(kw in combined for kw in ["remote", "anywhere", "distributed", "work from home"])
