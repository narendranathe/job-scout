"""Canonical role taxonomy — single source of truth for the dashboard.

Consolidates role definitions that were previously scattered across:

* ``backend/storage/company_rules.py::ROLE_ALIASES`` — short→canonical
  for resume filename parsing
* ``backend/core/relevance.py`` — title heuristics for the scoring engine
* Ad-hoc strings in the wizard / frontend

The wizard picker (``GET /api/role-taxonomy``) returns this list verbatim.
``company_rules.ROLE_ALIASES`` is derived from it so filename parsing
stays bit-exact identical (snapshot pinned by
``tests/test_role_taxonomy_regression.py``).

Schema for each entry (flat per PRD Q5):

    {
      "key": str,           # snake_case stable identifier
      "label": str,         # human-readable display name
      "abbrevs": list[str], # short codes used in resume filenames (UPPER)
      "skills_core": list[str],  # canonical core skills for this role
    }

Adding a role: append an entry; flow through to ``ROLE_ALIASES`` is
automatic. Each abbrev must be unique across roles (a duplicate would
make the filename parser ambiguous). Test guards this.
"""
from __future__ import annotations


ROLES: list[dict] = [
    {
        "key": "data_engineer",
        "label": "Data Engineer",
        "abbrevs": ["DE", "DATA"],
        "skills_core": ["python", "sql", "spark", "airflow", "kafka", "etl"],
    },
    {
        "key": "ml_engineer",
        "label": "ML Engineer",
        "abbrevs": ["ML", "MLE"],
        "skills_core": ["python", "pytorch", "tensorflow", "mlflow", "scikit-learn", "machine learning"],
    },
    {
        "key": "ai_engineer",
        "label": "AI Engineer",
        "abbrevs": ["AI"],
        "skills_core": ["python", "llm", "langchain", "transformers", "openai", "anthropic"],
    },
    {
        "key": "analytics_engineer",
        "label": "Analytics Engineer",
        "abbrevs": ["AE"],
        "skills_core": ["sql", "dbt", "snowflake", "bigquery", "looker", "tableau"],
    },
    {
        "key": "data_scientist",
        "label": "Data Scientist",
        "abbrevs": ["DS"],
        "skills_core": ["python", "sql", "pandas", "numpy", "scikit-learn", "statistics"],
    },
    {
        "key": "data_analyst",
        "label": "Data Analyst",
        "abbrevs": ["DA"],
        "skills_core": ["sql", "excel", "tableau", "powerbi", "python"],
    },
    {
        "key": "data_quality",
        "label": "Data Quality",
        "abbrevs": ["DQ"],
        "skills_core": ["sql", "python", "great expectations", "soda", "monte carlo"],
    },
    {
        "key": "software_engineer",
        "label": "Software Engineer",
        "abbrevs": ["SWE", "SDE", "SE"],
        "skills_core": ["python", "java", "go", "typescript", "rest api", "distributed systems"],
    },
    {
        "key": "backend_engineer",
        "label": "Backend Engineer",
        "abbrevs": ["BE"],
        "skills_core": ["python", "go", "rust", "postgresql", "rest api", "microservices"],
    },
    {
        "key": "platform_engineer",
        "label": "Platform Engineer",
        "abbrevs": ["PE"],
        "skills_core": ["kubernetes", "terraform", "aws", "ci/cd", "docker"],
    },
    {
        "key": "sre",
        "label": "Site Reliability Engineer",
        "abbrevs": ["SRE"],
        "skills_core": ["kubernetes", "prometheus", "grafana", "terraform", "linux", "incident response"],
    },
    {
        "key": "applied_scientist",
        "label": "Applied Scientist",
        "abbrevs": ["AS"],
        "skills_core": ["python", "pytorch", "research", "experimentation", "statistics"],
    },
    {
        "key": "quant_strategist",
        "label": "Quant Strategist",
        "abbrevs": ["QUANT"],
        "skills_core": ["python", "c++", "statistics", "backtesting", "systematic", "time series"],
    },
    {
        "key": "ai_quant",
        "label": "AI Quant",
        "abbrevs": ["AIQ"],
        "skills_core": ["python", "pytorch", "alpha research", "ml", "statistics"],
    },
    {
        "key": "solutions_architect",
        "label": "Solutions Architect",
        "abbrevs": ["SA"],
        "skills_core": ["aws", "azure", "system design", "rest api", "kubernetes"],
    },
    {
        "key": "product_manager",
        "label": "Product Manager",
        "abbrevs": ["PM"],
        "skills_core": ["roadmap", "user research", "analytics", "sql"],
    },
]


def role_by_key(key: str) -> dict | None:
    """Return the role entry matching ``key``, or None."""
    for r in ROLES:
        if r["key"] == key:
            return r
    return None


def all_labels() -> list[str]:
    """Return display labels in registration order."""
    return [r["label"] for r in ROLES]


def all_abbrevs() -> list[str]:
    """Return every abbreviation across all roles (UPPER)."""
    out = []
    for r in ROLES:
        out.extend(r["abbrevs"])
    return out


def alias_map() -> dict[str, str]:
    """Lowercase abbrev → canonical label dict.

    Drop-in equivalent of the legacy ``ROLE_ALIASES`` dict. The
    ``"data"`` legacy alias for Data Engineer is preserved here because
    it was a JobScout-specific long-form alias, not an upper-case abbrev.
    """
    out: dict[str, str] = {}
    for r in ROLES:
        for a in r["abbrevs"]:
            out[a.lower()] = r["label"]
    # Legacy long-form aliases that pre-date the formal taxonomy. These
    # appeared as lowercase tokens inside resume filenames before the
    # abbrev system existed; the parser still needs to resolve them.
    out["data"] = "Data Engineer"
    return out
