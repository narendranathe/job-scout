import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_platinum_boost_applied():
    from core.relevance import RelevanceEngine
    engine = RelevanceEngine()
    job_base = {"title": "Senior Data Engineer", "description": "Python, Spark, Kafka, ETL, data pipeline", "location": "Remote", "is_remote": True, "tier": "tier1"}
    job_platinum = {**job_base, "tier": "platinum"}
    score_base, _ = engine.score(job_base)
    score_platinum, _ = engine.score(job_platinum)
    assert score_platinum > score_base
    assert score_platinum <= 1.0


def test_platinum_boost_magnitude():
    from core.relevance import RelevanceEngine, PLATINUM_BOOST
    engine = RelevanceEngine()
    job = {"title": "Data Engineer", "description": "Python Spark", "location": "Dallas TX", "is_remote": False, "tier": "tier1"}
    score_base, _ = engine.score(job)
    job_plat = {**job, "tier": "platinum"}
    score_plat, _ = engine.score(job_plat)
    expected = min(1.0, round(score_base + PLATINUM_BOOST, 4))
    assert round(score_plat, 4) == expected


# ── v2 scoring overhaul ─────────────────────────────────────────────

def test_weights_sum_to_one():
    from core.relevance import (
        CORE_WEIGHT, SECONDARY_WEIGHT, TITLE_WEIGHT,
        LOCATION_WEIGHT, EXPERIENCE_WEIGHT, SPONSORSHIP_WEIGHT, SALARY_WEIGHT,
    )
    total = (
        CORE_WEIGHT + SECONDARY_WEIGHT + TITLE_WEIGHT
        + LOCATION_WEIGHT + EXPERIENCE_WEIGHT + SPONSORSHIP_WEIGHT + SALARY_WEIGHT
    )
    assert abs(total - 1.0) < 1e-9


def test_salary_score_tiers():
    from core.relevance import salary_score
    assert salary_score({"salary_max": 350_000}) == 1.00
    assert salary_score({"salary_max": 250_000}) == 0.75
    assert salary_score({"salary_max": 220_000}) == 0.75
    assert salary_score({"salary_max": 180_000}) == 0.50
    assert salary_score({"salary_max": 110_000}) == 0.25
    assert salary_score({"salary_max": 80_000}) == 0.0
    # Falls back to salary_min when max is missing
    assert salary_score({"salary_min": 230_000}) == 0.75
    # Missing salary → neutral 0 (no boost, no penalty)
    assert salary_score({}) == 0.0
    assert salary_score({"salary_max": 0}) == 0.0


def test_salary_tier_boost_in_score():
    from core.relevance import RelevanceEngine, SALARY_WEIGHT
    engine = RelevanceEngine()
    base_job = {
        "title": "Data Engineer",
        "description": "Python Spark Kafka ETL",
        "location": "Remote",
        "is_remote": True,
        "tier": "tier1",
    }
    score_no_sal, _ = engine.score(base_job)
    score_top_sal, _ = engine.score({**base_job, "salary_max": 320_000})
    score_low_sal, _ = engine.score({**base_job, "salary_max": 110_000})
    # Top tier should add a full SALARY_WEIGHT; low tier should add only 25%
    assert round(score_top_sal - score_no_sal, 4) == round(SALARY_WEIGHT, 4)
    assert round(score_low_sal - score_no_sal, 4) == round(SALARY_WEIGHT * 0.25, 4)


def test_sponsorship_weight_rebalance():
    """Issue #11: sponsorship weight bumped 0.05 → 0.08, symmetric."""
    from core.relevance import RelevanceEngine, SPONSORSHIP_WEIGHT
    assert SPONSORSHIP_WEIGHT == 0.08
    engine = RelevanceEngine()
    base = {
        "title": "Data Engineer",
        "description": "Python Spark Kafka",
        "location": "Dallas TX",
        "is_remote": False,
        "tier": "tier1",
    }
    score_base, _ = engine.score(base)
    score_pos, _ = engine.score({**base, "description": base["description"] + " H1B visa sponsor"})
    # Phrasing avoids the substring "sponsorship available" so the positive
    # matcher doesn't pre-empt the negative branch.
    score_neg, _ = engine.score({**base, "description": base["description"] + " We do not sponsor visas; US citizen only."})
    assert round(score_pos - score_base, 4) == round(SPONSORSHIP_WEIGHT, 4)
    # Penalty is symmetric (caps at 0 once score floor is reached, but here we're well above)
    assert round(score_base - score_neg, 4) == round(SPONSORSHIP_WEIGHT, 4)


def test_tfidf_booster_dormant_without_resume():
    """No resume → core score is unaffected; engine matches the pre-#7 behavior."""
    from core.relevance import RelevanceEngine
    job = {
        "title": "Data Engineer",
        "description": "Python Spark Kafka ETL data pipeline",
        "location": "Remote",
        "is_remote": True,
        "tier": "tier1",
    }
    score_no_resume, _ = RelevanceEngine().score(job)
    assert score_no_resume > 0
    # Recompute to confirm determinism (no resume = pure keyword scoring)
    score_again, _ = RelevanceEngine().score(job)
    assert score_no_resume == score_again


def test_tfidf_booster_modulates_core():
    """With a resume loaded, core score is multiplied by a factor in [0.85, 1.0]."""
    from core.relevance import RelevanceEngine
    job = {
        "title": "Data Engineer",
        "description": "Python Spark Kafka ETL data pipeline distributed systems airflow",
        "location": "Remote",
        "is_remote": True,
        "tier": "tier1",
    }
    # A resume that overlaps heavily with the job description
    matching_resume = (
        "Experienced data engineer skilled in Python, Spark, Kafka, ETL, "
        "data pipeline construction, Airflow scheduling, and distributed "
        "systems on AWS. Built streaming pipelines with Kafka and Spark."
    )
    # A resume with very little overlap
    offtopic_resume = (
        "Frontend developer specialised in React, TypeScript, CSS animations, "
        "and accessibility audits. Built design systems for mobile-first SPAs."
    )

    matching_engine = RelevanceEngine(resume_text=matching_resume)
    offtopic_engine = RelevanceEngine(resume_text=offtopic_resume)
    plain_engine = RelevanceEngine()

    s_match, _ = matching_engine.score(job)
    s_off, _ = offtopic_engine.score(job)
    s_plain, _ = plain_engine.score(job)

    # A well-matched resume should score at least as high as the off-topic one,
    # and the off-topic resume should never push above the plain (no-resume)
    # score (TF-IDF factor is capped at 1.0).
    assert s_match >= s_off
    assert s_off <= s_plain + 1e-9
