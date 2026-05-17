import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_platinum_companies_in_every_batch():
    from config.companies import get_batch, COMPANIES
    platinum = [c for c in COMPANIES if c.get("tier") == 0]
    assert len(platinum) >= 5, f"Expected at least 5 Platinum companies, got {len(platinum)}"
    for cycle in [1, 2, 3, 4, 5, 100]:
        batch = get_batch(cycle)
        batch_names = [c["name"] for c in batch]
        for co in platinum:
            assert co["name"] in batch_names, (
                f"Platinum company {co['name']} missing from cycle {cycle} batch"
            )


def test_fast_mode_includes_platinum():
    from config.companies import COMPANIES
    fast_companies = [c for c in COMPANIES if c.get("tier", 3) in (0, 1)]
    platinum = [c for c in COMPANIES if c.get("tier") == 0]
    assert len(platinum) >= 5
    for co in platinum:
        assert co in fast_companies


# ─── Workday entries must carry the URL triple the scraper needs ───
# Without slug + wd_instance + wd_board the Workday POST URL is malformed
# and every scrape attempt logs a 404. Catch missing fields at import time
# instead of in production logs.

def test_workday_companies_have_complete_url_triple():
    from config.companies import COMPANIES
    workday = [c for c in COMPANIES if c.get("ats") == "workday"]
    assert len(workday) > 0, "expected at least one workday entry"
    missing = []
    for co in workday:
        required = ("slug", "wd_instance", "wd_board")
        gaps = [k for k in required if not co.get(k)]
        if gaps:
            missing.append(f"{co.get('name', '?')}: missing {gaps}")
    assert not missing, "Workday entries with incomplete URL fields:\n  " + "\n  ".join(missing)


def test_workday_wd_instance_is_valid_subdomain():
    """Workday hosts companies under wd1.../wd2.../wd3.../wd5.../wd6.../wd103. ...
    A typo'd instance produces an unreachable DNS name. Restrict to the
    set that's actually been observed in the wild to make typos loud."""
    from config.companies import COMPANIES
    valid = {"wd1", "wd2", "wd3", "wd5", "wd6", "wd101", "wd102", "wd103", "wd104", "wd105"}
    bad = [
        f"{c.get('name')}: wd_instance={c.get('wd_instance')!r}"
        for c in COMPANIES
        if c.get("ats") == "workday" and c.get("wd_instance") not in valid
    ]
    assert not bad, (
        "Workday entries with unrecognized wd_instance — if Workday added a "
        "new instance prefix, extend the `valid` set in this test:\n  "
        + "\n  ".join(bad)
    )


def test_no_duplicate_company_names():
    """Catches the failure mode where a company is added to the list twice
    under different ATSes (e.g. Salesforce on playwright AND workday).
    Each name should appear exactly once."""
    from collections import Counter
    from config.companies import COMPANIES
    counts = Counter(c["name"] for c in COMPANIES)
    dupes = {n: c for n, c in counts.items() if c > 1}
    assert not dupes, f"Duplicate company names: {dupes}"
