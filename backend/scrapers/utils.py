"""
Shared utilities for all ATS scrapers.
"""

import re
import time
import logging

log = logging.getLogger(__name__)

REMOTE_KEYWORDS = [
    "remote", "anywhere", "distributed", "work from home",
    "fully remote", "100% remote", "remote-first", "wfh",
    "telecommute", "virtual",
]


def is_remote(location: str, title: str, description: str) -> bool:
    """Return True if any remote signal appears in location, title, or description."""
    combined = f"{location} {title} {description[:500]}".lower()
    return any(kw in combined for kw in REMOTE_KEYWORDS)


def strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


SALARY_PATTERNS = [
    r'\$(\d{2,3})[Kk][\s\-]+\$?(\d{2,3})[Kk]',           # $180K - $250K
    r'\$(\d{3},\d{3})[\s\-]+\$?(\d{3},\d{3})',             # $180,000 - $250,000
    r'(\d{2,3})[Kk][\s\-]+(\d{2,3})[Kk]\s*(?:USD|per year)',  # 180K-250K USD
]


def parse_salary(text: str) -> tuple:
    """Extract (salary_min, salary_max) from description text. Returns (0, 0) if not found."""
    for pattern in SALARY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            lo, hi = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            if lo < 1000:
                lo *= 1000
            if hi < 1000:
                hi *= 1000
            return lo, hi
    return 0, 0


def scrape_with_retry(fn, company_name: str, max_attempts: int = 3, base_delay: float = 2.0) -> list:
    """
    Call fn() up to max_attempts times with exponential backoff.
    Returns [] and logs error if all attempts fail — never raises.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                log.error("x %s — all %d attempts failed: %s", company_name, max_attempts, e)
                return []
            delay = base_delay * (2 ** attempt)  # 2s, 4s
            log.warning("x %s — attempt %d failed (%s), retrying in %.0fs",
                        company_name, attempt + 1, e, delay)
            time.sleep(delay)
    return []
