"""
Workday ATS scraper.

Workday jobs API pattern:
  POST https://{slug}.{instance}.myworkdayjobs.com/wday/cxs/{slug}/{board}/jobs
  Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

Company dict must include:
  ats:         "workday"
  slug:        "goldmansachs"              # company identifier in Workday URL
  wd_instance: "wd1"                       # wd1, wd3, wd5 (from their careers URL)
  wd_board:    "GS"                        # board name from their careers URL
"""

import requests
import logging
import re
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

TIMEOUT = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# Search terms to find data/engineering roles
SEARCH_TERMS = [
    "data engineer",
    "data scientist",
    "machine learning engineer",
    "analytics engineer",
    "software engineer data",
    "platform engineer",
    "data platform",
    "mlops",
]


def _parse_posted_date(posted_str: str) -> str:
    """Parse Workday posted date formats to ISO 8601."""
    if not posted_str:
        return ""
    # Format: "01/15/2024"
    if re.match(r"\d{2}/\d{2}/\d{4}", posted_str):
        try:
            return datetime.strptime(posted_str, "%m/%d/%Y").replace(
                tzinfo=timezone.utc
            ).isoformat()
        except Exception:
            pass
    # Format: "Posted 2 Days Ago"
    m = re.search(r"(\d+)\s+day", posted_str.lower())
    if m:
        days = int(m.group(1))
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    # Format: "Posted Today"
    if "today" in posted_str.lower():
        return datetime.now(timezone.utc).isoformat()
    return ""


def scrape(company: dict):
    """Scrape Workday job board, yielding normalized job dicts."""
    slug = company.get("slug", "")
    instance = company.get("wd_instance", "wd5")
    board = company.get("wd_board", "External_Career_Site")
    name = company.get("name", slug)

    base_url = f"https://{slug}.{instance}.myworkdayjobs.com"
    api_url = f"{base_url}/wday/cxs/{slug}/{board}/jobs"

    seen_ids: set[str] = set()
    total = 0

    for search_term in SEARCH_TERMS:
        offset = 0
        limit = 20

        while True:
            try:
                payload = {
                    "appliedFacets": {},
                    "limit": limit,
                    "offset": offset,
                    "searchText": search_term,
                }
                resp = requests.post(
                    api_url, json=payload, headers=HEADERS, timeout=TIMEOUT
                )

                if resp.status_code == 404:
                    log.warning("Workday %s: board not found (%s)", name, api_url)
                    return  # This company config is wrong — stop entirely

                if resp.status_code != 200:
                    log.warning(
                        "Workday %s: HTTP %d for term '%s'", name, resp.status_code, search_term
                    )
                    break

                data = resp.json()
                postings = data.get("jobPostings", [])
                if not postings:
                    break

                for p in postings:
                    job_path = p.get("externalPath", "")
                    raw_title = p.get("title", "")

                    # Stable unique ID from the path or title
                    id_source = (job_path or raw_title[:50]).replace(" ", "-")
                    ext_id = f"workday-{slug}-{id_source}"
                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)

                    location_text = p.get("locationsText", "")
                    is_remote = any(
                        w in location_text.lower()
                        for w in ["remote", "work from home", "anywhere"]
                    )

                    posted_iso = _parse_posted_date(p.get("postedOn", ""))
                    job_url = (
                        f"{base_url}/{board}{job_path}" if job_path else f"{base_url}/{board}"
                    )

                    yield {
                        "external_id": ext_id,
                        "title": raw_title,
                        "company": name,
                        "location": location_text,
                        "department": "",
                        "description": raw_title,  # full desc needs a 2nd fetch; title gives scoring signal
                        "url": job_url,
                        "ats": "workday",
                        "is_remote": is_remote,
                        "posted_at": posted_iso,
                        "salary_min": 0,
                        "salary_max": 0,
                    }
                    total += 1

                total_results = data.get("total", 0)
                offset += limit
                if offset >= total_results:
                    break

            except Exception as e:
                log.error("Workday %s error (term='%s'): %s", name, search_term, e)
                break

    log.info("Workday %s: %d unique jobs scraped", name, total)
