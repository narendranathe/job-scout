"""
Playwright-based scraper for quant/HFT firms that block standard HTTP scrapers.

These companies use custom career portals (not Greenhouse/Lever/Ashby) and
require a real browser session to render job listings.

Usage:
    from scrapers.playwright_scraper import scrape_all_playwright
    jobs = scrape_all_playwright()
"""
import hashlib
import logging
import re
from typing import Generator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Target company definitions
# ---------------------------------------------------------------------------

PLAYWRIGHT_TARGETS = [
    {
        "name": "Jane Street",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.janestreet.com/join-jane-street/open-roles/",
        "job_container": ".opportunity-row, .job-listing, [data-role]",
        "title_selector": ".opportunity-title, .job-title, h3",
        "link_selector": "a[href]",
    },
    {
        "name": "Two Sigma",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://careers.twosigma.com/careers/JobList",
        "job_container": ".job-list-item, .career-row, tr[data-job]",
        "title_selector": ".job-title, td.position, a.job-link",
        "link_selector": "a[href]",
    },
    {
        "name": "HRT",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.hudsonrivertrading.com/careers/",
        "job_container": ".job-item, .opening-row, .career-position",
        "title_selector": ".job-title, .position-title, h3",
        "link_selector": "a[href]",
    },
    {
        "name": "D.E. Shaw",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.deshaw.com/careers/choose-your-path",
        "job_container": ".position-item, .job-card, .opening",
        "title_selector": ".position-title, .job-name, h4",
        "link_selector": "a[href]",
    },
    {
        "name": "AQR",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://careers.aqr.com/jobs",
        "job_container": ".job-result, .position-row, li.opening",
        "title_selector": ".job-title, .position-name, a.job-link",
        "link_selector": "a[href]",
    },
    {
        "name": "Jump Trading",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.jumptrading.com/careers/",
        "job_container": ".job-row, .career-item, .opening-card",
        "title_selector": ".job-title, .role-title, h3",
        "link_selector": "a[href]",
    },
]

# ---------------------------------------------------------------------------
# Relevance pre-filter (same spirit as greenhouse.py EXCLUDE_TITLE_KEYWORDS)
# ---------------------------------------------------------------------------

RELEVANT_PATTERNS = re.compile(
    r"(data\s+engineer|ml\s+engineer|machine\s+learning|quantitative|"
    r"quant\s+researcher|quant\s+developer|platform\s+engineer|"
    r"data\s+scientist|data\s+platform|data\s+infra|software\s+engineer|"
    r"sre|reliability|devops|data\s+analyst|analytics\s+engineer|"
    r"research\s+engineer|applied\s+scientist)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_external_id(company_name: str, title: str, url: str) -> str:
    """Generate a stable, deterministic external_id for a Playwright-scraped job.

    Format: pw-<company-slug>-<8-char-hash>
    The hash is computed from (company, title, url) so the same job always
    gets the same id across scrape runs, enabling deduplication via upsert.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    payload = f"{company_name.lower()}|{title.lower()}|{url.lower()}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:8]
    return f"pw-{slug}-{digest}"


# ---------------------------------------------------------------------------
# Core scrape functions
# ---------------------------------------------------------------------------


def scrape_playwright_company(target: dict) -> list[dict]:
    """Scrape one company's career page using Playwright.

    Returns a list of raw job dicts (not yet scored).
    Raises ImportError if playwright is not installed.
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    jobs: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(target["url"], timeout=30_000, wait_until="networkidle")
            page.wait_for_timeout(2_000)  # let JS finish rendering

            containers = page.query_selector_all(target["job_container"])
            if not containers:
                log.warning("[%s] No job containers found with selector: %s",
                            target["name"], target["job_container"])

            for container in containers:
                # Extract title
                title_el = container.query_selector(target["title_selector"])
                title = (title_el.inner_text().strip() if title_el else "").strip()
                if not title:
                    continue

                # Pre-filter by relevance before constructing full record
                if not RELEVANT_PATTERNS.search(title):
                    continue

                # Extract URL
                link_el = container.query_selector(target["link_selector"])
                href = ""
                if link_el:
                    href = link_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        from urllib.parse import urlparse  # noqa: PLC0415
                        parsed = urlparse(target["url"])
                        href = f"{parsed.scheme}://{parsed.netloc}{href}"

                job_url = href or target["url"]
                ext_id = _make_external_id(target["name"], title, job_url)

                jobs.append({
                    "external_id": ext_id,
                    "title": title,
                    "company": target["name"],
                    "location": "Remote / On-site",
                    "department": "",
                    "description": title,  # full description requires a second page load
                    "url": job_url,
                    "ats": target["ats"],
                    "tier": target["tier"],
                    "is_remote": 0,
                    "posted_at": None,
                    "salary_min": 0,
                    "salary_max": 0,
                })

        except Exception as exc:
            log.error("[%s] Playwright error: %s", target["name"], exc)
        finally:
            browser.close()

    log.info("[%s] scraped %d relevant jobs", target["name"], len(jobs))
    return jobs


def scrape_all_playwright(targets: list[dict] | None = None) -> list[dict]:
    """Scrape all Playwright targets and return a flat list of raw job dicts.

    Args:
        targets: Override the default PLAYWRIGHT_TARGETS list (useful for tests).

    Returns:
        List of raw job dicts ready for scoring + upsert.

    Note:
        If playwright is not installed this raises ImportError immediately —
        the caller in main.py wraps this in try/except and logs a warning.
    """
    targets = targets if targets is not None else PLAYWRIGHT_TARGETS
    all_jobs: list[dict] = []
    for target in targets:
        try:
            jobs = scrape_playwright_company(target)
            all_jobs.extend(jobs)
        except Exception as exc:
            log.error("[%s] failed: %s", target.get("name", "?"), exc)
    return all_jobs
