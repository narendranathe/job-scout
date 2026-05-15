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
