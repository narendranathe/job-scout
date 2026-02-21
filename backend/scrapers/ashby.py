"""
Ashby ATS scraper.
Endpoint: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
Returns JSON with 'jobs' array.
No authentication required.
"""

import logging
import requests
from typing import Generator

log = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
TIMEOUT = 30


def scrape(company: dict) -> Generator[dict, None, None]:
    slug = company["slug"]
    name = company["name"]

    try:
        resp = requests.get(BASE_URL.format(slug=slug), timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.error("Ashby [%s] failed: %s", name, e)
        return

    jobs = data.get("jobs", [])
    log.info("Ashby [%s] → %d jobs", name, len(jobs))

    for job in jobs:
        try:
            location = job.get("location", "") or ""
            if isinstance(location, dict):
                location = location.get("name", "")

            department = job.get("department", "") or ""
            if isinstance(department, dict):
                department = department.get("name", "")

            description = job.get("descriptionPlain", "") or job.get("description", "") or ""
            title = job.get("title", "").strip()
            is_remote = job.get("isRemote", False) or _is_remote(location, title, description)

            apply_url = job.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{slug}/{job.get('id', '')}"

            yield {
                "external_id": f"ab-{slug}-{job.get('id', '')}",
                "title": title,
                "company": name,
                "location": location,
                "department": department,
                "description": description[:5000],
                "url": apply_url,
                "ats": "ashby",
                "is_remote": is_remote,
                "posted_at": (job.get("publishedAt") or job.get("updatedAt") or "")[:19],
                "salary_min": _extract_salary(job, "min"),
                "salary_max": _extract_salary(job, "max"),
            }
        except Exception as e:
            log.warning("Ashby [%s] job parse error: %s", name, e)
            continue


def _extract_salary(job: dict, bound: str) -> int:
    comp = job.get("compensation", {})
    if not comp:
        return 0
    try:
        ranges = comp.get("ranges", [{}])
        if ranges:
            val = ranges[0].get(f"{bound}Value", 0) or ranges[0].get(bound, 0)
            return int(val) if val else 0
    except (TypeError, ValueError, IndexError):
        pass
    return 0


def _is_remote(location: str, title: str, description: str) -> bool:
    combined = f"{location} {title} {description[:500]}".lower()
    return any(kw in combined for kw in ["remote", "anywhere", "distributed", "work from home"])
