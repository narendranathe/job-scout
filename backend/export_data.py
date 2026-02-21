"""
export_data.py — Reads SQLite → writes api-data.json for the dashboard.
Called after every scrape cycle.
"""

import json
import sqlite3
import os
import logging
from datetime import datetime, timezone
from collections import Counter

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "jobscout.db"))
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "api-data.json")


def export(db_path: str = DB_PATH, output_path: str = None) -> dict:
    if not os.path.exists(db_path):
        log.warning("No DB at %s", db_path)
        return _empty()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM jobs WHERE is_active = 1 ORDER BY relevance_score DESC LIMIT 500"
    ).fetchall()

    jobs = []
    for r in rows:
        j = dict(r)
        if isinstance(j.get("matched_skills"), str):
            j["matched_skills"] = [s.strip() for s in j["matched_skills"].split(",") if s.strip()]
        jobs.append(j)

    total = len(jobs)
    high = sum(1 for j in jobs if (j.get("relevance_score") or 0) >= 0.7)
    remote_n = sum(1 for j in jobs if j.get("is_remote"))
    salaries = [j["salary_max"] for j in jobs if j.get("salary_max") and j["salary_max"] > 0]
    avg_sal = round(sum(salaries) / len(salaries)) if salaries else 0
    h1b_n = sum(1 for j in jobs if j.get("sponsorship"))

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
    except: pass

    conn.close()

    data = {
        "jobs": jobs,
        "stats": {
            "total_jobs": total, "high_match": high,
            "remote_pct": round(remote_n/total*100) if total else 0,
            "avg_salary": avg_sal,
            "h1b_pct": round(h1b_n/total*100) if total else 0,
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
    }

    if output_path:
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, default=str, separators=(",", ":"))
        log.info("Exported %d jobs → %s", total, output_path)
    return data


def _empty():
    return {"jobs":[],"stats":{"total_jobs":0,"high_match":0,"remote_pct":0,"avg_salary":0,"h1b_pct":0,"companies_tracked":0},"distributions":{"ats":[],"cities":[],"salary_buckets":[]},"top_companies":[],"trend":[],"runs":[],"exported_at":datetime.now(timezone.utc).isoformat()}
