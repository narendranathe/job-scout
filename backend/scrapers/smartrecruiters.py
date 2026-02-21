"""
SmartRecruiters ATS scraper.
Endpoint: GET https://api.smartrecruiters.com/v1/companies/{slug}/postings
Returns JSON with 'content' array + pagination.
No authentication required.
"""

import logging
import requests
from typing import Generator

log = logging.getLogger(__name__)

BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
TIMEOUT = 30
MAX_PAGES = 5  # Safety limit


def scrape(company: dict) -> Generator[dict, None, None]:
    slug = company["slug"]
    name = company["name"]
    offset = 0
    limit = 100
    total_yielded = 0

    for page in range(MAX_PAGES):
        try:
            resp = requests.get(
                BASE_URL.format(slug=slug),
                params={"offset": offset, "limit": limit},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.error("SmartRecruiters [%s] page %d failed: %s", name, page, e)
            return

        jobs = data.get("content", [])
        if not jobs:
            break

        log.info("SmartRecruiters [%s] page %d → %d jobs", name, page, len(jobs))

        for job in jobs:
            try:
                loc = job.get("location", {})
                city = loc.get("city", "")
                region = loc.get("region", "")
                country = loc.get("country", "")
                location = ", ".join(filter(None, [city, region, country]))

                department = ""
                dept_obj = job.get("department", {})
                if isinstance(dept_obj, dict):
                    department = dept_obj.get("label", "")

                # SmartRecruiters doesn't give full description in listing
                # but gives a short description
                description = job.get("name", "") + " " + (job.get("customField", [{}])[0].get("valueLabel", "") if job.get("customField") else "")

                title = job.get("name", "").strip()
                is_remote = job.get("location", {}).get("remote", False) or _is_remote(location, title, description)

                ref = job.get("ref", "") or job.get("id", "")
                apply_url = job.get("ref", f"https://jobs.smartrecruiters.com/{slug}/{job.get('id', '')}")
                if not apply_url.startswith("http"):
                    apply_url = f"https://jobs.smartrecruiters.com/{slug}/{ref}"

                posted = (job.get("releasedDate") or job.get("createdOn") or "")[:19]

                yield {
                    "external_id": f"sr-{slug}-{job.get('id', '')}",
                    "title": title,
                    "company": name,
                    "location": location,
                    "department": department,
                    "description": description[:5000],
                    "url": apply_url,
                    "ats": "smartrecruiters",
                    "is_remote": is_remote,
                    "posted_at": posted,
                    "salary_min": 0,
                    "salary_max": 0,
                }
                total_yielded += 1
            except Exception as e:
                log.warning("SmartRecruiters [%s] parse error: %s", name, e)
                continue

        # Check pagination
        total_found = data.get("totalFound", 0)
        offset += limit
        if offset >= total_found:
            break

    log.info("SmartRecruiters [%s] total: %d jobs", name, total_yielded)


def _is_remote(location: str, title: str, description: str) -> bool:
    combined = f"{location} {title} {description[:500]}".lower()
    return any(kw in combined for kw in ["remote", "anywhere", "distributed", "work from home"])
