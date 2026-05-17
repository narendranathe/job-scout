"""Tests for the canonical role taxonomy + the derived ROLE_ALIASES dict.

PRD #89 Slice 1. The taxonomy is the single source of truth for:

* The wizard's role-picker (consumed via GET /api/role-taxonomy)
* Resume filename parsing (storage/company_rules.ROLE_ALIASES)
* Eventually, role-specific skill weighting in relevance.py

If the taxonomy changes shape, the wizard picker breaks. If a role's
abbrev list changes silently, the filename parser drifts and every
"Naren_GS_DE.pdf" stops parsing. The snapshot tests below pin both.
"""
from config.role_taxonomy import (
    ROLES,
    role_by_key,
    all_labels,
    all_abbrevs,
    alias_map,
)


def test_taxonomy_has_at_least_8_roles():
    """PRD acceptance criterion: ≥ 8 roles in the taxonomy."""
    assert len(ROLES) >= 8


def test_every_entry_has_required_keys():
    """Schema check — the wizard frontend relies on these four fields."""
    for r in ROLES:
        assert set(r.keys()) >= {"key", "label", "abbrevs", "skills_core"}, r
        assert isinstance(r["key"], str) and r["key"]
        assert isinstance(r["label"], str) and r["label"]
        assert isinstance(r["abbrevs"], list) and r["abbrevs"]
        assert isinstance(r["skills_core"], list) and r["skills_core"]


def test_keys_are_unique_snake_case():
    """Stable identifiers — the wizard persists role keys to user_profile."""
    keys = [r["key"] for r in ROLES]
    assert len(keys) == len(set(keys)), f"duplicate keys: {keys}"
    for k in keys:
        assert k == k.lower(), f"{k!r} is not lowercase"
        assert " " not in k, f"{k!r} contains a space"


def test_abbrevs_are_unique_across_all_roles():
    """Filename parser ambiguity guard.

    parse_resume_filename does a lowercase lookup in ROLE_ALIASES; two
    roles claiming the same abbrev would silently make one of them win
    (whichever was registered last) and the other unreachable.
    """
    seen = {}
    for r in ROLES:
        for a in r["abbrevs"]:
            assert a not in seen, (
                f"abbrev {a!r} claimed by {r['key']!r} and {seen[a]!r}"
            )
            seen[a] = r["key"]


def test_role_by_key_finds_known():
    assert role_by_key("data_engineer")["label"] == "Data Engineer"
    assert role_by_key("ml_engineer")["label"] == "ML Engineer"


def test_role_by_key_returns_none_for_unknown():
    assert role_by_key("not_a_role") is None
    assert role_by_key("") is None


def test_all_labels_preserves_order():
    """The wizard renders chips in registration order."""
    labels = all_labels()
    assert labels[0] == "Data Engineer"
    assert "ML Engineer" in labels
    assert len(labels) == len(ROLES)


def test_all_abbrevs_collects_every_abbrev():
    abbrevs = all_abbrevs()
    assert "DE" in abbrevs
    assert "MLE" in abbrevs
    assert "SWE" in abbrevs
    assert len(abbrevs) >= len(ROLES)  # at least one per role


def test_alias_map_round_trip_matches_legacy_dict():
    """Pin the resulting ROLE_ALIASES against the legacy hard-coded dict.

    The dict below is the exact pre-refactor content from
    storage.company_rules.ROLE_ALIASES (before commit X swapped it for
    ``_role_alias_map()``). If a taxonomy edit changes a key/value here,
    the filename parser's behaviour drifts — failing this test forces
    the human to confirm the change is intentional + update the snapshot.
    """
    legacy = {
        # JobScout legacy
        "de": "Data Engineer", "data": "Data Engineer",
        "ml": "ML Engineer", "ai": "AI Engineer",
        "sde": "Software Engineer", "se": "Software Engineer",
        "be": "Backend Engineer",
        "ds": "Data Scientist", "dq": "Data Quality",
        "ae": "Analytics Engineer",
        "quant": "Quant Strategist", "aiq": "AI Quant",
        # AutoApply canonical abbrevs
        "swe": "Software Engineer",
        "mle": "ML Engineer",
        "da": "Data Analyst",
        "pe": "Platform Engineer",
        "pm": "Product Manager",
        "sa": "Solutions Architect",
        "sre": "Site Reliability Engineer",
        "as": "Applied Scientist",
    }
    derived = alias_map()
    # Every legacy entry must still resolve to the same label.
    for short, label in legacy.items():
        assert derived.get(short) == label, (
            f"{short!r} legacy → {label!r} but taxonomy now → "
            f"{derived.get(short)!r}"
        )


def test_company_rules_role_aliases_uses_taxonomy():
    """Ensure storage.company_rules.ROLE_ALIASES is the derived dict."""
    from storage.company_rules import ROLE_ALIASES
    assert ROLE_ALIASES.get("de") == "Data Engineer"
    assert ROLE_ALIASES.get("mle") == "ML Engineer"
    assert ROLE_ALIASES.get("swe") == "Software Engineer"


def test_resume_filename_parser_still_works():
    """End-to-end smoke: the filename parser uses ROLE_ALIASES.

    A regression in the alias map would surface here as the company /
    role fields coming back wrong.
    """
    from storage.resume_vault import parse_resume_filename
    parsed = parse_resume_filename("Narendranath_GS_DE.pdf")
    assert parsed["company"] == "Goldman Sachs"
    assert parsed["role"] == "Data Engineer"

    parsed = parse_resume_filename("Narendranath_Meta_MLE.pdf")
    assert parsed["company"] == "Meta"
    assert parsed["role"] == "ML Engineer"
