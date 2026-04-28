"""Structural tests for the Playwright scraper module.

These tests do NOT make network calls — they only verify that the
module is correctly structured and the helper functions behave as expected.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_playwright_targets_have_required_keys():
    from scrapers.playwright_scraper import PLAYWRIGHT_TARGETS

    required = {"name", "ats", "tier", "url", "job_container", "title_selector", "link_selector"}
    for target in PLAYWRIGHT_TARGETS:
        missing = required - set(target.keys())
        assert not missing, f"{target['name']} missing keys: {missing}"


def test_playwright_targets_not_empty():
    from scrapers.playwright_scraper import PLAYWRIGHT_TARGETS

    assert len(PLAYWRIGHT_TARGETS) >= 1, "PLAYWRIGHT_TARGETS must have at least one entry"


def test_playwright_targets_known_companies():
    from scrapers.playwright_scraper import PLAYWRIGHT_TARGETS

    names = {t["name"] for t in PLAYWRIGHT_TARGETS}
    # Core 6 firms from initial launch — must always be present
    core_firms = {"Jane Street", "Two Sigma", "HRT", "D.E. Shaw", "AQR", "Jump Trading"}
    assert core_firms.issubset(names), f"Missing core firms: {core_firms - names}"


def test_playwright_targets_expanded_quant_firms():
    from scrapers.playwright_scraper import PLAYWRIGHT_TARGETS

    names = {t["name"] for t in PLAYWRIGHT_TARGETS}
    expanded = {
        "Citadel Securities", "SIG", "IMC Trading",
        "Bridgewater Associates", "Flow Traders",
        "Tower Research Capital", "Millennium Management",
    }
    assert expanded.issubset(names), f"Missing expanded firms: {expanded - names}"


def test_make_external_id_is_stable():
    from scrapers.playwright_scraper import _make_external_id

    id1 = _make_external_id("Jane Street", "Senior Data Engineer", "https://janestreet.com/123")
    id2 = _make_external_id("Jane Street", "Senior Data Engineer", "https://janestreet.com/123")
    assert id1 == id2


def test_make_external_id_starts_with_prefix():
    from scrapers.playwright_scraper import _make_external_id

    ext_id = _make_external_id("Jane Street", "Senior Data Engineer", "https://janestreet.com/123")
    assert ext_id.startswith("pw-jane-street-")


def test_make_external_id_differs_for_different_inputs():
    from scrapers.playwright_scraper import _make_external_id

    id1 = _make_external_id("Jane Street", "Senior Data Engineer", "https://janestreet.com/123")
    id2 = _make_external_id("Jane Street", "Data Scientist", "https://janestreet.com/456")
    assert id1 != id2


def test_make_external_id_company_slug():
    from scrapers.playwright_scraper import _make_external_id

    ext_id = _make_external_id("D.E. Shaw", "Quant Researcher", "https://deshaw.com/1")
    assert ext_id.startswith("pw-d-e-shaw-")


def test_relevant_patterns_match_data_engineering():
    from scrapers.playwright_scraper import RELEVANT_PATTERNS

    assert RELEVANT_PATTERNS.search("Senior Data Engineer")
    assert RELEVANT_PATTERNS.search("Staff ML Engineer")
    assert RELEVANT_PATTERNS.search("Data Platform Engineer")
    assert RELEVANT_PATTERNS.search("Analytics Engineer")


def test_relevant_patterns_match_quant():
    from scrapers.playwright_scraper import RELEVANT_PATTERNS

    assert RELEVANT_PATTERNS.search("Quantitative Researcher")
    assert RELEVANT_PATTERNS.search("Quant Developer - C++")
    assert RELEVANT_PATTERNS.search("Research Engineer, Trading Systems")


def test_relevant_patterns_match_niche_quant_roles():
    from scrapers.playwright_scraper import RELEVANT_PATTERNS

    assert RELEVANT_PATTERNS.search("Quant Analyst - Systematic Macro")
    assert RELEVANT_PATTERNS.search("Systematic Researcher, Equities")
    assert RELEVANT_PATTERNS.search("Trading Engineer - C++ Low Latency")
    assert RELEVANT_PATTERNS.search("Low Latency Software Engineer")
    assert RELEVANT_PATTERNS.search("Financial Engineer, Risk")
    assert RELEVANT_PATTERNS.search("Electronic Trading Developer")
    assert RELEVANT_PATTERNS.search("Quant Strat, FX")
    assert RELEVANT_PATTERNS.search("Portfolio Analyst - Data Science")
    assert RELEVANT_PATTERNS.search("Strats Developer, Equities")


def test_relevant_patterns_no_match_non_technical():
    from scrapers.playwright_scraper import RELEVANT_PATTERNS

    assert not RELEVANT_PATTERNS.search("Recruiter, Technology")
    assert not RELEVANT_PATTERNS.search("Office Manager")
    assert not RELEVANT_PATTERNS.search("Legal Counsel")
    assert not RELEVANT_PATTERNS.search("Financial Controller")


def test_scrape_all_playwright_returns_list_with_empty_targets():
    """With no targets, scrape_all_playwright returns an empty list (no network)."""
    from scrapers.playwright_scraper import scrape_all_playwright

    result = scrape_all_playwright(targets=[])
    assert result == []
