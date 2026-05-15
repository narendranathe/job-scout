"""
export_data.py — Reads SQLite → writes api-data.json for the dashboard.
Called after every scrape cycle.
"""

import json
import re
import sqlite3
import os
import logging
from datetime import datetime, timezone
from collections import Counter
from statistics import quantiles

try:
    from config.profile import RARE_SKILLS_WATCH
except ImportError:
    from backend.config.profile import RARE_SKILLS_WATCH

log = logging.getLogger(__name__)

# Pre-compiled word-boundary regex per rare-skill term. Word boundaries keep
# short terms like "mcp" from matching inside unrelated words.
_RARE_PATTERNS = [
    (term, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE))
    for term in RARE_SKILLS_WATCH
]


def _find_rare_hits(job: dict) -> list[str]:
    haystack = f"{job.get('title') or ''} {job.get('description') or ''}"
    if not haystack.strip():
        return []
    hits = []
    for term, pat in _RARE_PATTERNS:
        if pat.search(haystack):
            hits.append(term)
    return hits

# Matches a naive ISO-8601 timestamp emitted by greenhouse.py / ashby.py /
# bamboohr.py (they slice the source ATS string with `[:19]`, dropping any
# trailing Z/offset). The frontend's `new Date(str)` parses such strings as
# LOCAL time per ECMAScript, which mis-ages jobs by up to a full day for
# non-UTC users. We pin them to UTC here so the dashboard sees one timezone.
_NAIVE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def _normalize_to_utc(s: str) -> str:
    """Append +00:00 to a naive ISO timestamp; pass-through anything else.

    A string with an existing offset or `Z` is left untouched. Empty / non-ISO
    strings (e.g. legacy `YYYY-MM-DD HH:MM:SS` rows from very old data) are
    returned as-is — they were already broken for `Date()` parsing and the
    frontend treats them as null-age (passes the 30-day cap, no decay).
    """
    if s and _NAIVE_ISO_RE.match(s):
        return s + "+00:00"
    return s

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "api-data.json")


def _parse_skills(val: str) -> list[str]:
    """Parse matched_skills stored as JSON (new) or comma-separated (legacy)."""
    if not val:
        return []
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return [s.strip() for s in val.split(",") if s.strip()]


def export(db_path: str = DB_PATH, output_path: str = None, cycle_counter: int = 0) -> dict:
    if not os.path.exists(db_path):
        log.warning("No DB at %s", db_path)
        return _empty()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # LEFT JOIN applications so the dashboard knows which jobs the user already
    # applied to. Match by external_id OR content_hash — content_hash catches
    # the case where Greenhouse/Lever republishes the same req with a new ID.
    # Priority-based aggregation (applied > saved > others) so a job matched
    # by BOTH a 'saved' row (old external_id) and an 'applied' row (content_hash)
    # surfaces as 'applied' — MAX() over the status string sorts 'saved' first
    # lexicographically, which would silently defeat the dedup.
    rows = conn.execute("""
        SELECT j.*,
               CASE
                 WHEN SUM(CASE WHEN a.status = 'applied' THEN 1 ELSE 0 END) > 0 THEN 'applied'
                 WHEN SUM(CASE WHEN a.status = 'saved'   THEN 1 ELSE 0 END) > 0 THEN 'saved'
                 ELSE NULL
               END AS application_status,
               MAX(CASE WHEN a.status = 'applied' THEN a.applied_at END) AS application_applied_at
        FROM jobs j
        LEFT JOIN applications a
               ON (a.external_id = j.external_id
                   OR (a.content_hash IS NOT NULL
                       AND a.content_hash = j.content_hash))
              AND a.status != 'removed'
        WHERE j.is_active = 1
        GROUP BY j.id
        ORDER BY j.relevance_score DESC
        LIMIT 500
    """).fetchall()

    jobs = []
    for r in rows:
        j = dict(r)
        if isinstance(j.get("matched_skills"), str):
            j["matched_skills"] = _parse_skills(j["matched_skills"])
        # Single age signal the frontend consumes. posted_at is preferred (it's
        # the ATS-reported date) but is missing for Playwright targets and weak
        # for Workday. first_seen_at is our discovery timestamp — always set, so
        # it bounds the worst-case age estimate at "first time JobScout saw it".
        # Naive timestamps from greenhouse/ashby/bamboohr get pinned to UTC here
        # so the frontend's Date() parser doesn't reinterpret them as local time.
        posted = (j.get("posted_at") or "").strip()
        first_seen = (j.get("first_seen_at") or "").strip()
        j["effective_date"] = _normalize_to_utc(posted if posted else first_seen)
        j["rare_skill_hits"] = _find_rare_hits(j)
        jobs.append(j)

    total = len(jobs)

    # HIGH MATCH = top 10% by relevance, recalibrated each cycle.
    # Falls back to 0.70 only when corpus is too small to compute a stable percentile.
    score_pool = [j["relevance_score"] for j in jobs if j.get("relevance_score")]
    if len(score_pool) >= 10:
        high_match_threshold = float(quantiles(score_pool, n=10)[8])
    else:
        high_match_threshold = 0.7
    high = sum(1 for j in jobs if (j.get("relevance_score") or 0) >= high_match_threshold)

    remote_n = sum(1 for j in jobs if j.get("is_remote"))
    salaries = [j["salary_max"] for j in jobs if j.get("salary_max") and j["salary_max"] > 0]
    avg_sal = round(sum(salaries) / len(salaries)) if salaries else 0
    h1b_n = sum(1 for j in jobs if j.get("sponsorship"))
    rare_n = sum(1 for j in jobs if j.get("rare_skill_hits"))

    ats_c = Counter(j.get("ats", "unknown") for j in jobs)
    city_c = Counter()
    for j in jobs:
        if j.get("is_remote"): city_c["Remote"] += 1
        elif j.get("location"): city_c[j["location"].split(",")[0].strip()] += 1
    co_c = Counter(j.get("company", "?") for j in jobs)
    date_c = Counter(j.get("posted_at", "")[:10] for j in jobs if j.get("posted_at"))

    sal_bk = []
    for label, lo, hi in [("<$130K",0,130000),("$130-160K",130000,160000),("$160-200K",160000,200000),("$200-250K",200000,250000),("$250-300K",250000,300000),("$300K+",300000,9e9)]:
        sal_bk.append({"range": label, "count": sum(1 for s in salaries if lo <= s < hi)})

    runs = []
    try:
        runs = [dict(r) for r in conn.execute("SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 20").fetchall()]
    except Exception as e:
        log.warning("Could not load scrape_runs: %s", e)

    conn.close()

    data = {
        "jobs": jobs,
        "stats": {
            "total_jobs": total, "high_match": high,
            "high_match_threshold": round(high_match_threshold, 3),
            "remote_pct": round(remote_n/total*100) if total else 0,
            "avg_salary": avg_sal,
            "h1b_pct": round(h1b_n/total*100) if total else 0,
            "rare_skills": rare_n,
            "companies_tracked": len(co_c),
        },
        "distributions": {
            "ats": [{"name":k,"value":v} for k,v in ats_c.most_common()],
            "cities": [{"name":k,"value":v} for k,v in city_c.most_common(15)],
            "salary_buckets": sal_bk,
        },
        "top_companies": [{"name":k,"count":v} for k,v in co_c.most_common(25)],
        "trend": sorted([{"date":k,"count":v} for k,v in date_c.items()], key=lambda x: x["date"])[-30:],
        "runs": runs,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "cycle_counter": cycle_counter,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "jobs_total": total,
        },
    }

    if output_path:
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, default=str, separators=(",", ":"))
        log.info("Exported %d jobs → %s", total, output_path)
    return data


def _empty():
    return {"jobs":[],"stats":{"total_jobs":0,"high_match":0,"remote_pct":0,"avg_salary":0,"h1b_pct":0,"rare_skills":0,"companies_tracked":0},"distributions":{"ats":[],"cities":[],"salary_buckets":[]},"top_companies":[],"trend":[],"runs":[],"exported_at":datetime.now(timezone.utc).isoformat()}
