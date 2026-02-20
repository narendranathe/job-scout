"""
User profile definition for job relevance scoring.
"""

from dataclasses import dataclass, field


@dataclass
class UserProfile:
    target_titles: dict[str, float] = field(default_factory=lambda: {
        "senior data engineer": 1.0, "staff data engineer": 1.0,
        "lead data engineer": 0.95, "principal data engineer": 0.95,
        "ml engineer": 0.90, "machine learning engineer": 0.90,
        "senior ml engineer": 0.95, "data platform engineer": 0.90,
        "analytics engineer": 0.80, "senior analytics engineer": 0.85,
        "data architect": 0.85, "mlops engineer": 0.85,
        "senior software engineer data": 0.80, "ai engineer": 0.80,
    })

    skills: dict[str, float] = field(default_factory=lambda: {
        "python": 1.0, "sql": 1.0, "pyspark": 0.95, "t-sql": 0.90,
        "apache spark": 0.95, "kafka": 0.90, "apache kafka": 0.90,
        "spark streaming": 0.85, "flink": 0.60,
        "azure": 0.90, "aws": 0.85, "databricks": 0.90,
        "microsoft fabric": 0.90, "azure data factory": 0.85,
        "azure synapse": 0.80, "s3": 0.75, "redshift": 0.70,
        "snowflake": 0.70, "bigquery": 0.65, "gcp": 0.60,
        "etl": 0.95, "elt": 0.90, "data pipeline": 0.95,
        "data warehouse": 0.90, "data lake": 0.85,
        "data modeling": 0.85, "dimensional modeling": 0.80,
        "data quality": 0.85, "data governance": 0.75,
        "mlops": 0.80, "mlflow": 0.75, "feature store": 0.70,
        "machine learning": 0.75, "scikit-learn": 0.70,
        "tensorflow": 0.60, "pytorch": 0.60,
        "airflow": 0.80, "docker": 0.80, "kubernetes": 0.70,
        "ci/cd": 0.80, "terraform": 0.65, "git": 0.90,
        "sql server": 0.90, "postgresql": 0.80, "mongodb": 0.65,
        "delta lake": 0.85, "iceberg": 0.70,
        "agile": 0.80, "scrum": 0.85,
    })

    years_experience: int = 4
    education: str = "masters"
    preferred_locations: list[str] = field(default_factory=lambda: [
        "dallas", "dfw", "plano", "irving", "frisco", "richardson",
        "fort worth", "austin", "houston",
        "remote", "hybrid",
        "new york", "san francisco", "seattle", "chicago",
    ])
    remote_preference: float = 0.95
    target_companies: list[str] = field(default_factory=lambda: [
        "disney", "uber", "bloomberg", "google", "meta", "capital one",
        "at&t", "american airlines", "amazon", "apple", "netflix",
        "stripe", "datadog", "snowflake", "databricks", "microsoft",
        "galaxy", "coinbase", "two sigma", "citadel", "jane street",
        "anthropic", "openai", "palantir", "nvidia",
    ])
    exclude_keywords: list[str] = field(default_factory=lambda: [
        "intern", "internship", "junior", "entry level", "entry-level",
        "associate", "clearance required", "ts/sci", "polygraph",
    ])
    min_salary_usd: int = 130_000

    # Keywords to search for across all boards
    search_keywords: list[str] = field(default_factory=lambda: [
        "data engineer", "ml engineer", "machine learning engineer",
        "data platform", "mlops", "analytics engineer",
    ])
