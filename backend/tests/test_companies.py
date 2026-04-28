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
