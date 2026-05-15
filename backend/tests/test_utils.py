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
