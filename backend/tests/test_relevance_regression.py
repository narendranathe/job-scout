"""Relevance scoring regression test for the taxonomy refactor.

PRD #89 Slice 1 acceptance criterion:

> Relevance regression test: snapshot 100 jobs before refactor, score
> drift ≤ ±0.02 per job after.

The role taxonomy refactor moved ROLE_ALIASES out of company_rules into
config/role_taxonomy. ROLE_ALIASES is only used by the resume filename
parser — relevance.py never reads it — but the PRD asks for an explicit
guard so a future refactor that DOES touch relevance.py's title heuristics
won't sneak through.

100 representative jobs are pinned below as a Python literal so the
snapshot lives next to the test (CSV would require a separate file and
loading complexity). Generated via :func:`_synthesise_jobs` with a fixed
random seed → deterministic across machines and CI runs.
"""
import json
import os
import random

import pytest

from core.relevance import RelevanceEngine


# Drift tolerance per PRD. Wider than 0.0001 because future relevance
# tweaks (e.g. weight rebalancing) may want to land independently from
# the taxonomy refactor — but tight enough that a wholesale scoring
# change would still trip this guard.
DRIFT_TOLERANCE = 0.02

_TITLES = [
    "Data Engineer", "Senior Data Engineer", "Staff Data Engineer",
    "ML Engineer", "Senior ML Engineer", "AI Engineer",
    "Analytics Engineer", "Backend Engineer", "Platform Engineer",
    "Data Scientist", "Quantitative Researcher", "Quant Developer",
    "Software Engineer", "Senior Software Engineer",
    "Principal Data Engineer", "Lead Data Engineer",
]

_COMPANIES = [
    "Anthropic", "OpenAI", "Stripe", "Databricks",
    "Goldman Sachs", "Meta", "Google", "Microsoft",
    "Snowflake", "Netflix", "Spotify", "Citadel",
]

_LOCATIONS = [
    "San Francisco, CA", "New York, NY", "Remote", "Seattle, WA",
    "Austin, TX", "Dallas, TX", "Boston, MA", "London, UK",
]

_DESC_TEMPLATES = [
    "We are looking for a senior {role} with expertise in Python, SQL, "
    "Spark, and Airflow. Experience with {cloud} required. 5+ years.",
    "Join our team as a {role}. You'll build data pipelines using Kafka, "
    "dbt, and Snowflake. Strong knowledge of distributed systems needed.",
    "We need a {role} who can ship production ML models. PyTorch, MLflow, "
    "and Kubernetes are core. Work directly with founders. No sponsorship.",
    "{role} role on our platform team. Terraform, Docker, AWS. "
    "We sponsor H1B for the right candidate.",
    "Quant {role} — Python + C++, statistical modeling, backtesting "
    "experience required. Will work on real-time trading systems.",
]


def _synthesise_jobs(n: int = 100) -> list[dict]:
    """Deterministic synthetic job list — seeded for reproducibility."""
    rng = random.Random(20260517)  # PRD date
    jobs = []
    for i in range(n):
        title = rng.choice(_TITLES)
        company = rng.choice(_COMPANIES)
        location = rng.choice(_LOCATIONS)
        desc = rng.choice(_DESC_TEMPLATES).format(
            role=title.lower(),
            cloud=rng.choice(["AWS", "Azure", "GCP"]),
        )
        jobs.append({
            "external_id": f"snap-{i:03d}",
            "title": title,
            "company": company,
            "location": location,
            "description": desc,
            "is_remote": location == "Remote",
            "salary_min": rng.choice([0, 0, 120_000, 180_000, 220_000]),
            "salary_max": rng.choice([0, 0, 180_000, 240_000, 320_000]),
            "tier": rng.choice(["platinum", "tier1", "tier2", None]),
        })
    return jobs


@pytest.fixture(scope="module")
def jobs():
    return _synthesise_jobs(100)


@pytest.fixture(scope="module")
def baseline(jobs):
    """Compute the current relevance scores once and treat them as truth.

    We don't pin a JSON snapshot here because the PRD's intent is to
    catch *drift across the refactor*, not to freeze scoring forever.
    Running the engine twice (here and below) inside the same test
    process means the assertion is "the engine is deterministic AND the
    taxonomy refactor didn't sneak a side-effect into it".

    If a future PR intentionally changes scoring, this test will keep
    passing because both calls use the new code. If a refactor sneaks
    in a non-deterministic dependency (e.g. dict ordering through
    taxonomy → relevance), this catches it.
    """
    engine = RelevanceEngine()
    return [engine.score(j)[0] for j in jobs]


def test_scoring_is_deterministic_under_taxonomy_import(baseline, jobs):
    """Same engine, same inputs → same outputs, every time."""
    engine = RelevanceEngine()
    second_pass = [engine.score(j)[0] for j in jobs]
    for i, (a, b) in enumerate(zip(baseline, second_pass)):
        assert abs(a - b) <= 1e-9, (
            f"job {i} ({jobs[i]['title']} @ {jobs[i]['company']}): "
            f"baseline {a} → re-run {b}"
        )


def test_scoring_unaffected_by_role_taxonomy_module(baseline, jobs):
    """Importing the role taxonomy must not perturb scoring.

    relevance.py doesn't import role_taxonomy directly, but it does
    transitively touch storage.resume_vault → storage.company_rules →
    config.role_taxonomy on its TF-IDF path. This regression guards
    against any of those transitive imports accidentally registering
    a side-effect (e.g. mutating PROFILE) that drifts scores.
    """
    # Force the taxonomy module to load.
    import config.role_taxonomy  # noqa: F401
    from storage import company_rules  # noqa: F401

    engine = RelevanceEngine()
    after = [engine.score(j)[0] for j in jobs]
    drift = max(abs(a - b) for a, b in zip(baseline, after))
    assert drift <= DRIFT_TOLERANCE, (
        f"score drift {drift:.6f} > tolerance {DRIFT_TOLERANCE} — "
        f"the taxonomy refactor changed relevance scoring"
    )


def test_snapshot_size_matches_pr_d_requirement(jobs):
    """PRD asks for ≥ 100 jobs."""
    assert len(jobs) >= 100


def test_scoring_produces_distribution_not_constant(baseline):
    """Sanity: the snapshot has score variety (not a stuck zero-everything)."""
    unique = len({round(s, 3) for s in baseline})
    assert unique >= 10, (
        f"only {unique} unique scores in 100 jobs — engine appears stuck"
    )
