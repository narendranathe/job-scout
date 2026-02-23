"""
BambooHR ATS scraper.
Endpoint: GET https://{slug}.bamboohr.com/careers/list
Returns JSON job listings from their public API.
"""

import logging
import requests
from typing import Generator

from .utils import is_remote

log = logging.getLogger(__name__)
TIMEOUT = 30


def scrape(company: dict) -> Generator[dict, None, None]:
    slug = company["slug"]
    name = company["name"]

    # BambooHR has a JSON endpoint behind their careers page
    url = f"https://{slug}.bamboohr.com/careers/list"

    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.error("BambooHR [%s] failed: %s", name, e)
        return

    jobs = data.get("result", [])
    if not isinstance(jobs, list):
        log.warning("BambooHR [%s] unexpected format", name)
        return

    log.info("BambooHR [%s] → %d jobs", name, len(jobs))

    for job in jobs:
        try:
            location_parts = []
            loc = job.get("location", {})
            if isinstance(loc, dict):
                for key in ["city", "state", "country"]:
                    if loc.get(key):
                        location_parts.append(loc[key])
            elif isinstance(loc, str):
                location_parts.append(loc)
            location = ", ".join(location_parts) or ""

            department = job.get("departmentLabel", "") or job.get("department", "") or ""
            title = (job.get("jobOpeningName", "") or job.get("name", "")).strip()
            job_id = job.get("id", "")
            apply_url = f"https://{slug}.bamboohr.com/careers/{job_id}"

            remote = is_remote(location, title, "")

            yield {
                "external_id": f"bh-{slug}-{job_id}",
                "title": title,
                "company": name,
                "location": location,
                "department": department,
                "description": job.get("description", "")[:5000] or title,
                "url": apply_url,
                "ats": "bamboohr",
                "is_remote": remote,
                "posted_at": (job.get("dateCreated") or job.get("datePosted") or "")[:19],
                "salary_min": 0,
                "salary_max": 0,
            }
        except Exception as e:
            log.warning("BambooHR [%s] parse error: %s", name, e)
            continue


