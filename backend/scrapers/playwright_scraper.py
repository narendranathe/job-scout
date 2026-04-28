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
    # ── Expanded quant/HFT/market-maker coverage ──
    {
        "name": "Citadel Securities",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.citadelsecurities.com/careers/open-positions/",
        "job_container": ".job-listing, .position-card, [data-job], .opportunity-item",
        "title_selector": ".job-title, .position-title, h3, h4",
        "link_selector": "a[href]",
    },
    {
        "name": "SIG",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://careers.sig.com/job-search",
        "job_container": ".job-result, .career-listing, .vacancy-row, tr[class*='job']",
        "title_selector": ".job-title, .position-name, h3, td.title",
        "link_selector": "a[href]",
    },
    {
        "name": "IMC Trading",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://careers.imc.com/us/en/search-results",
        "job_container": ".job-listing, .phenom-card, li[class*='job'], .job-item",
        "title_selector": ".job-title, .card-title, h3, .position-title",
        "link_selector": "a[href]",
    },
    {
        "name": "Bridgewater Associates",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.bridgewater.com/career-opportunities/open-roles",
        "job_container": ".job-card, .role-card, .opening-row, [class*='position']",
        "title_selector": ".job-title, .role-title, h3, h4",
        "link_selector": "a[href]",
    },
    {
        "name": "Flow Traders",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.flowtraders.com/careers/vacancies",
        "job_container": ".vacancy-item, .job-listing, .career-item, article[class*='job']",
        "title_selector": ".vacancy-title, .job-title, h3, h2",
        "link_selector": "a[href]",
    },
    {
        "name": "Tower Research Capital",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.tower-research.com/open-positions",
        "job_container": ".position-row, tr.job-row, .opening-item, li[class*='position']",
        "title_selector": "td.position-title, .job-title, a, h3",
        "link_selector": "a[href]",
    },
    {
        "name": "Millennium Management",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.mlp.com/careers/",
        "job_container": ".job-listing, .vacancy-card, .position-item, [class*='career']",
        "title_selector": ".job-title, .position-title, h3, h4",
        "link_selector": "a[href]",
    },
    # ── Non-Workday finance firms ──
    {
        "name": "Optiver",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://optiver.com/working-at-optiver/career-opportunities/",
        "job_container": ".job-listing, .vacancy-item, [class*='job'], article[class*='position']",
        "title_selector": ".job-title, h3, .vacancy-title, .position-title",
        "link_selector": "a[href]",
    },
    {
        "name": "BlackRock",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://careers.blackrock.com/job-search",
        "job_container": ".job-result, .job-card, [class*='job-listing'], li[class*='job']",
        "title_selector": ".job-title, h3, h2, .position-title",
        "link_selector": "a[href]",
    },
    {
        "name": "Morgan Stanley",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.morganstanley.com/people-opportunities/careers",
        "job_container": ".job-listing, .opportunity-card, [class*='position'], li[class*='job']",
        "title_selector": ".job-title, h3, h4, .position-title",
        "link_selector": "a[href]",
    },
    # ── Big Tech (proprietary portals) ──
    {
        "name": "Apple",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://jobs.apple.com/en-us/search?team=apps-and-frameworks-SFTWR-AF,machine-learning-and-ai-MLAI,devops-and-site-reliability-DOPS",
        "job_container": "[class*='table-col'], .table-row, [data-row-id], li[class*='result']",
        "title_selector": "[class*='table-col-1'] a, .job-title, h3",
        "link_selector": "a[href*='/details/']",
    },
    {
        "name": "Google",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.google.com/about/careers/applications/jobs/results/?q=data+engineer&employment_type=FULL_TIME",
        "job_container": "li[class*='lLd3Je'], .sMn82b, [jsname='N818Id']",
        "title_selector": "h3[class*='QJPWVe'], .job-title, h3",
        "link_selector": "a[href*='/jobs/results/']",
    },
    {
        "name": "Amazon",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.amazon.jobs/en/search?base_query=data+engineer&category%5B%5D=software-development",
        "job_container": ".job-tile, [class*='job-tile'], .result",
        "title_selector": "h3.job-title, .job-title, h3",
        "link_selector": "a[href*='/jobs/']",
    },
    {
        "name": "Meta",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.metacareers.com/jobs/?offices[]=Remote&q=data+engineer",
        "job_container": "._9ata, [class*='_8g0h'], div[role='listitem']",
        "title_selector": "._8muv, .job-title, h2, h3",
        "link_selector": "a[href*='/jobs/']",
    },
    {
        "name": "Goldman Sachs",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://www.goldmansachs.com/careers/students/programs-and-internships",
        "job_container": ".program-card, .career-card, [class*='program'], li[class*='result']",
        "title_selector": ".program-title, .card-title, h3, h4",
        "link_selector": "a[href]",
    },
    {
        "name": "Bloomberg",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://careers.bloomberg.com/job/search?category=Engineering",
        "job_container": ".job-listing, .job-item, [class*='job-result'], li[class*='job']",
        "title_selector": ".job-title, h3, h2, .position-title",
        "link_selector": "a[href*='/job/']",
    },
    {
        "name": "JP Morgan Chase",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://jobs.jpmorganchase.com/search?keyword=data+engineer",
        "job_container": ".job-listing, .opportunity-row, [class*='job-card'], li[class*='job']",
        "title_selector": ".job-title, h3, .position-title",
        "link_selector": "a[href*='/job/']",
    },
    {
        "name": "OpenAI",
        "ats": "custom",
        "tier": "tier1",
        "url": "https://openai.com/careers/",
        "job_container": "[class*='PostingCard'], .job-listing, [data-id], li[class*='job']",
        "title_selector": "[class*='PostingTitle'], h3, .job-title",
        "link_selector": "a[href*='/careers/']",
    },
]

# ---------------------------------------------------------------------------
# Relevance pre-filter (same spirit as greenhouse.py EXCLUDE_TITLE_KEYWORDS)
# ---------------------------------------------------------------------------

RELEVANT_PATTERNS = re.compile(
    r"(data\s+engineer|ml\s+engineer|machine\s+learning|quantitative|"
    r"quant\s+researcher|quant\s+developer|quant\s+analyst|quant\s+strat|"
    r"platform\s+engineer|data\s+scientist|data\s+platform|data\s+infra|"
    r"software\s+engineer|sre|reliability|devops|"
    r"data\s+analyst|analytics\s+engineer|research\s+engineer|applied\s+scientist|"
    r"systematic\s+researcher|trading\s+engineer|low\s+latency|"
    r"financial\s+engineer|risk\s+engineer|execution\s+engineer|"
    r"portfolio\s+analyst|algorithmic\s+trader|electronic\s+trading|strats)",
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
