"""
Lever ATS scraper.
Endpoint: GET https://api.lever.co/v0/postings/{slug}
Returns JSON array of all public job postings.
No authentication required.
"""

import logging
import requests
from typing import Generator

log = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{slug}"
TIMEOUT = 30


def scrape(company: dict) -> Generator[dict, None, None]:
    slug = company["slug"]
    name = company["name"]

    try:
        resp = requests.get(
            BASE_URL.format(slug=slug),
            params={"mode": "json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        jobs = resp.json()
    except requests.RequestException as e:
        log.error("Lever [%s] failed: %s", name, e)
        return

    if not isinstance(jobs, list):
        log.warning("Lever [%s] unexpected response type: %s", name, type(jobs))
        return

    log.info("Lever [%s] → %d jobs", name, len(jobs))

    for job in jobs:
        try:
            location = job.get("categories", {}).get("location", "") or ""
            department = job.get("categories", {}).get("department", "") or ""
            team = job.get("categories", {}).get("team", "") or ""

            description = job.get("descriptionPlain", "") or ""
            if not description:
                # Fallback to lists
                parts = []
                for lst in job.get("lists", []):
                    parts.append(lst.get("text", ""))
                    parts.append(lst.get("content", ""))
                description = " ".join(parts)

            title = job.get("text", "").strip()
            is_remote = _is_remote(location, title, description)

            yield {
                "external_id": f"lv-{slug}-{job.get('id', '')}",
                "title": title,
                "company": name,
                "location": location,
                "department": department or team,
                "description": description[:5000],
                "url": job.get("hostedUrl", "") or job.get("applyUrl", ""),
                "ats": "lever",
                "is_remote": is_remote,
                "posted_at": _epoch_to_iso(job.get("createdAt")),
                "salary_min": _parse_salary(job, "min"),
                "salary_max": _parse_salary(job, "max"),
            }
        except Exception as e:
            log.warning("Lever [%s] job parse error: %s", name, e)
            continue


def _epoch_to_iso(ms: int | None) -> str:
    if not ms:
        return ""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_salary(job: dict, bound: str) -> int:
    """Try to extract salary from Lever's salaryRange field."""
    try:
        salary = job.get("salaryRange", {})
        if salary and bound in salary:
            return int(salary[bound])
    except (TypeError, ValueError):
        pass
    return 0


def _is_remote(location: str, title: str, description: str) -> bool:
    combined = f"{location} {title} {description[:500]}".lower()
    return any(kw in combined for kw in ["remote", "anywhere", "distributed", "work from home"])
