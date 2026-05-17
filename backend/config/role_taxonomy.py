"""Canonical role taxonomy — scaffolding for Slice 1 of issue #89.

Tracking: https://github.com/narendranathe/job-scout/issues/90
Parent PRD: https://github.com/narendranathe/job-scout/issues/89
Spec: docs/superpowers/specs/2026-05-17-first-run-onboarding-wizard.md

This file is the single source of truth for the role list that today
lives in three places:

  1. backend/core/relevance.py    — role-title heuristics + skill weights
  2. backend/storage/company_rules.py::ROLE_ALIASES  — filename abbrevs
  3. ad-hoc JD parsing scattered through scrapers

Slice 1 of issue #89 migrates those three consumers to import from here.
Until that migration ships, this module is unused — callers continue
using their inline definitions. Don't delete the inline copies before
the migration PR lands or relevance scoring will silently regress.

Regression-test contract (see issue #90 acceptance criteria):
  Snapshot ``relevance_score`` for 100 representative jobs from the
  current DB before the refactor. After importing role data from this
  module, the same 100 jobs must score within ±0.02 of the snapshot.

Shape:
  Each entry has stable ``key`` (snake_case, used in URLs and DB),
  human ``label`` (used in UI), ``abbrevs`` (list of uppercase forms
  recognized in filenames), and ``skills_core`` (list of normalized
  skill tokens used by the relevance engine's "core skills" 40% bucket).

Sources cross-checked while building this list:
  * core/relevance.py CORE_SKILLS / SECONDARY_SKILLS dicts
  * storage/company_rules.py ROLE_ALIASES
  * config/profile.py legacy keyword lists
"""

from __future__ import annotations

from typing import TypedDict


class Role(TypedDict):
    key: str           # snake_case, stable identifier
    label: str         # display name
    abbrevs: list[str] # uppercase filename abbreviations
    skills_core: list[str]  # normalized skill tokens


ROLES: list[Role] = [
    {
        "key": "data_engineer",
        "label": "Data Engineer",
        "abbrevs": ["DE", "DATA"],
        "skills_core": [
            "python", "sql", "spark", "airflow", "kafka", "etl",
            "snowflake", "databricks", "delta lake",
        ],
    },
    {
        "key": "ml_engineer",
        "label": "ML Engineer",
        "abbrevs": ["ML", "MLE"],
        "skills_core": [
            "python", "pytorch", "tensorflow", "mlflow",
            "feature store", "kubeflow", "sagemaker",
        ],
    },
    {
        "key": "ai_engineer",
        "label": "AI Engineer",
        "abbrevs": ["AI"],
        "skills_core": [
            "python", "llm", "rag", "langchain", "openai", "anthropic",
            "vector database", "embeddings",
        ],
    },
    {
        "key": "analytics_engineer",
        "label": "Analytics Engineer",
        "abbrevs": ["AE"],
        "skills_core": [
            "sql", "dbt", "snowflake", "looker", "tableau",
            "dimensional modeling", "semantic layer",
        ],
    },
    {
        "key": "data_scientist",
        "label": "Data Scientist",
        "abbrevs": ["DS"],
        "skills_core": [
            "python", "sql", "pandas", "scikit-learn", "statistics",
            "ab testing", "jupyter",
        ],
    },
    {
        "key": "data_analyst",
        "label": "Data Analyst",
        "abbrevs": ["DA"],
        "skills_core": [
            "sql", "excel", "tableau", "looker", "powerbi",
        ],
    },
    {
        "key": "software_engineer",
        "label": "Software Engineer",
        "abbrevs": ["SWE", "SDE", "SE"],
        "skills_core": [
            "python", "javascript", "go", "rust", "system design",
            "rest", "docker", "kubernetes",
        ],
    },
    {
        "key": "backend_engineer",
        "label": "Backend Engineer",
        "abbrevs": ["BE"],
        "skills_core": [
            "python", "go", "java", "postgresql", "redis", "grpc",
            "fastapi", "rest",
        ],
    },
    {
        "key": "platform_engineer",
        "label": "Platform Engineer",
        "abbrevs": ["PE"],
        "skills_core": [
            "kubernetes", "terraform", "aws", "gcp", "azure",
            "ci cd", "observability",
        ],
    },
    {
        "key": "sre",
        "label": "Site Reliability Engineer",
        "abbrevs": ["SRE", "DEVOPS"],
        "skills_core": [
            "kubernetes", "terraform", "prometheus", "grafana",
            "incident response", "slo",
        ],
    },
    {
        "key": "quant_strategist",
        "label": "Quant Strategist",
        "abbrevs": ["QUANT"],
        "skills_core": [
            "python", "c++", "kdb", "time series", "statistics",
            "derivatives",
        ],
    },
    {
        "key": "product_manager",
        "label": "Product Manager",
        "abbrevs": ["PM"],
        "skills_core": [
            "product strategy", "roadmap", "user research",
            "stakeholder management",
        ],
    },
    {
        "key": "applied_scientist",
        "label": "Applied Scientist",
        "abbrevs": ["AS"],
        "skills_core": [
            "python", "pytorch", "research", "publications",
            "ml systems",
        ],
    },
]


def by_key(key: str) -> Role | None:
    """Return the role with the given key, or None if not found."""
    for role in ROLES:
        if role["key"] == key:
            return role
    return None


def all_abbrevs() -> dict[str, str]:
    """Reverse map: uppercase abbrev → canonical label.

    Drop-in replacement for ``company_rules.ROLE_ALIASES``. Used by
    the filename parser to resolve ``GS_DE`` → "Data Engineer", etc.
    """
    out: dict[str, str] = {}
    for role in ROLES:
        for ab in role["abbrevs"]:
            out[ab.upper()] = role["label"]
    return out
