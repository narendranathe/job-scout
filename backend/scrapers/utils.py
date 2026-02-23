"""
Shared utilities for all ATS scrapers.
"""

import re

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
