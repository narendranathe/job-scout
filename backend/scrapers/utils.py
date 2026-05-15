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


# Range separator: hyphen, en-dash, em-dash, or "to"
_SEP = r'(?:\s*[-–—]\s*|\s+to\s+)'
_HOURS_PER_YEAR = 2080  # 40 hrs/wk × 52 wk — standard FTE annualization

# Each pattern is (regex, kind). All patterns must be anchored on a literal $ or
# K/k suffix to avoid matching unrelated numeric strings (referral bonuses,
# equity grants, year counts). Quantifiers are bounded — no catastrophic backtracking.
SALARY_PATTERNS = [
    # 1. K-suffix range: $180K - $250K, $200K to $280K, $200K–$280K
    (r'\$(\d{2,3})\s*[Kk]' + _SEP + r'\$?(\d{2,3})\s*[Kk]', 'k_range'),
    # 2. Comma format range: $80,000 - $120,000, $200,000 to $280,000
    (r'\$(\d{2,3}),(\d{3})' + _SEP + r'\$?(\d{2,3}),(\d{3})', 'comma_range'),
    # 3. K-suffix with USD/per year suffix: 180K-250K USD
    (r'(\d{2,3})\s*[Kk]' + _SEP + r'(\d{2,3})\s*[Kk]\s*(?:USD|per\s+year)', 'k_usd'),
    # 4. Hourly range: $50-$70/hr, $50 to $70 per hour → annualize × 2080
    (r'\$(\d{2,3})' + _SEP + r'\$?(\d{2,3})\s*(?:/|\s*per\s+)(?:hr|hour)\b', 'hourly_range'),
    # 5. Hourly single: $50/hr, $50 per hour → both min and max get the same value
    (r'\$(\d{1,3})\s*(?:/|\s*per\s+)(?:hr|hour)\b', 'hourly_single'),
]

# Words appearing immediately before a $-amount that indicate it's NOT base salary.
# Catches: "signing bonus of $25,000 to $50,000", "equity grant $200,000 to $400,000",
# "tuition cap $10,500 - $15,000", "referral bonus of $5,000", "401(k) match up to $X".
# Lower-cased; "equity" alone is not here because "Salary $200K plus equity" is common
# and the negative cue follows the match, not precedes it.
_NEGATIVE_CONTEXT_WORDS = (
    'bonus', 'rsu', 'grant', 'stipend', 'tuition', 'reimbursement',
    'referral', '401(k)', '401k', 'sign-on', 'signing', 'scholarship',
    'severance', 'relocation', 'equity grant', 'stock grant',
)


def _has_negative_context_before(text: str, match_start: int, window: int = 30) -> bool:
    """True if a non-salary qualifier appears in the `window` chars before the match.
    Only the leading context is inspected — trailing words like 'plus equity' after a
    legitimate base-salary range must not cause rejection.
    """
    before = text[max(0, match_start - window):match_start].lower()
    return any(kw in before for kw in _NEGATIVE_CONTEXT_WORDS)


def parse_salary(text: str) -> tuple:
    """Extract (salary_min, salary_max) from JD text. Returns (0, 0) if no range found.

    Handles K-suffix ranges, full-number ranges (with optional 2-digit prefix
    like $80,000-$120,000), and hourly rates (annualized as rate × 2080).
    Non-monetary or vague phrases ("competitive", "equity only") naturally
    fall through to (0, 0) because no pattern matches.

    Matches with a non-salary qualifier in the preceding 30 chars (signing bonus,
    equity grant, tuition cap, 401(k) match, etc.) are rejected — without that
    filter, ranges like "$25,000 to $50,000 signing bonus" would pollute salary.

    First valid match wins. Multi-region postings ("Bay Area: $300K-$400K,
    NYC: $280K-$350K") take the first cited range; pickle-the-max behavior
    is a future enhancement (see PR notes).
    """
    if not text:
        return 0, 0

    for pattern, kind in SALARY_PATTERNS:
        for m in re.finditer(pattern, text):
            if _has_negative_context_before(text, m.start()):
                continue
            try:
                if kind in ('k_range', 'k_usd'):
                    lo = int(m.group(1)) * 1000
                    hi = int(m.group(2)) * 1000
                elif kind == 'comma_range':
                    lo = int(m.group(1)) * 1000 + int(m.group(2))
                    hi = int(m.group(3)) * 1000 + int(m.group(4))
                elif kind == 'hourly_range':
                    lo = int(m.group(1)) * _HOURS_PER_YEAR
                    hi = int(m.group(2)) * _HOURS_PER_YEAR
                elif kind == 'hourly_single':
                    lo = hi = int(m.group(1)) * _HOURS_PER_YEAR
                else:
                    continue
            except (ValueError, IndexError):
                continue

            # Sanity bounds: realistic FTE salary ($10k–$1M annualized).
            # Rejects mis-parses like a 4-digit year or contractor flat fees.
            if 10_000 <= lo <= hi <= 1_000_000:
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
