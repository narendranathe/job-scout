import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_scrape_with_retry_returns_on_success():
    from scrapers.utils import scrape_with_retry
    calls = []
    def good_fn():
        calls.append(1)
        return [{"title": "Data Engineer"}]
    result = scrape_with_retry(good_fn, "TestCo")
    assert result == [{"title": "Data Engineer"}]
    assert len(calls) == 1


def test_scrape_with_retry_retries_on_failure():
    from scrapers.utils import scrape_with_retry
    calls = []
    def flaky_fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("timeout")
        return [{"title": "Data Engineer"}]
    result = scrape_with_retry(flaky_fn, "TestCo", max_attempts=3, base_delay=0)
    assert result == [{"title": "Data Engineer"}]
    assert len(calls) == 3


def test_scrape_with_retry_returns_empty_after_all_failures():
    from scrapers.utils import scrape_with_retry
    def bad_fn():
        raise ConnectionError("always fails")
    result = scrape_with_retry(bad_fn, "TestCo", max_attempts=3, base_delay=0)
    assert result == []


def test_parse_salary_k_notation():
    from scrapers.utils import parse_salary
    assert parse_salary("Compensation: $180K - $250K per year") == (180000, 250000)


def test_parse_salary_full_notation():
    from scrapers.utils import parse_salary
    assert parse_salary("Base salary $200,000 - $280,000") == (200000, 280000)


def test_parse_salary_returns_zeros_when_not_found():
    from scrapers.utils import parse_salary
    assert parse_salary("Competitive salary, no range listed") == (0, 0)


def test_parse_salary_k_range_with_to_separator():
    from scrapers.utils import parse_salary
    assert parse_salary("Salary range: $200K to $280K plus equity") == (200000, 280000)


def test_parse_salary_en_dash_separator():
    from scrapers.utils import parse_salary
    # En-dash (U+2013) — common in copy-pasted JDs from Word/Google Docs
    assert parse_salary("Pay: $150K–$210K") == (150000, 210000)


def test_parse_salary_two_digit_comma_prefix():
    from scrapers.utils import parse_salary
    assert parse_salary("Range: $80,000 - $120,000 USD") == (80000, 120000)


def test_parse_salary_hourly_range_annualized():
    from scrapers.utils import parse_salary
    # $50-$70/hr × 2080 hr/yr → $104,000 - $145,600
    assert parse_salary("Contract rate: $50-$70/hr") == (104000, 145600)


def test_parse_salary_hourly_single_annualized():
    from scrapers.utils import parse_salary
    # $75/hr × 2080 → $156,000
    assert parse_salary("Pays $75/hr for senior consultants") == (156000, 156000)


def test_parse_salary_equity_only_returns_zero():
    from scrapers.utils import parse_salary
    assert parse_salary("Equity only — no cash compensation") == (0, 0)


def test_parse_salary_empty_string():
    from scrapers.utils import parse_salary
    assert parse_salary("") == (0, 0)


def test_parse_salary_ignores_referral_bonus():
    from scrapers.utils import parse_salary
    # $5,000 referral bonus has only 1-digit prefix in comma format → rejected
    assert parse_salary("Earn a $5,000 referral bonus when you refer a friend.") == (0, 0)


def test_parse_salary_rejects_year_strings():
    from scrapers.utils import parse_salary
    # "2020-2024" is not a salary — no $ anchor, no K suffix → rejected
    assert parse_salary("Worked at Acme 2020-2024 on data pipelines.") == (0, 0)


def test_parse_salary_rejects_signing_bonus():
    from scrapers.utils import parse_salary
    # Signing bonus ranges must not be picked up as base salary
    assert parse_salary("Signing bonus of $25,000 to $50,000") == (0, 0)


def test_parse_salary_rejects_equity_grant():
    from scrapers.utils import parse_salary
    # Equity grant ranges in dollars must not be picked up as base salary
    assert parse_salary("Equity grant $200,000 to $400,000 over 4 years") == (0, 0)


def test_parse_salary_rejects_tuition_cap():
    from scrapers.utils import parse_salary
    assert parse_salary("Tuition reimbursement cap $10,500 - $15,000 per year") == (0, 0)


def test_parse_salary_finds_base_after_bonus():
    from scrapers.utils import parse_salary
    # Bonus first, then base salary — parser must skip the bonus and find the base
    txt = "Equity grant $300,000 to $500,000. Base salary $180K - $220K plus equity."
    assert parse_salary(txt) == (180000, 220000)


def test_parse_salary_allows_trailing_equity_mention():
    from scrapers.utils import parse_salary
    # "plus equity" AFTER a legitimate range must not cause rejection
    assert parse_salary("Salary $200K - $280K plus equity and benefits") == (200000, 280000)
