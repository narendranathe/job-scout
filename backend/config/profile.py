"""
Your profile — the relevance engine scores every scraped job against this.
Edit these to match your skills and preferences.
"""

PROFILE = {
    # Core skills (weighted highest)
    "core_skills": [
        "python", "sql", "spark", "kafka", "airflow",
        "etl", "data pipeline", "data lake", "data warehouse",
        "azure", "aws", "databricks", "microsoft fabric",
    ],

    # Secondary skills (weighted medium)
    "secondary_skills": [
        "docker", "kubernetes", "terraform", "ci/cd",
        "delta lake", "dbt", "snowflake", "redshift",
        "postgresql", "sql server", "mongodb",
        "fastapi", "flask", "rest api",
        "git", "linux", "bash",
        "mlflow", "mlops", "machine learning",
        "pytorch", "tensorflow", "scikit-learn",
    ],

    # Preferred locations (boost score)
    "preferred_locations": [
        "remote", "dallas", "tx", "texas", "austin",
    ],

    # Experience level keywords (boost score)
    "experience_keywords": [
        "senior", "staff", "lead", "principal",
        "4+ years", "5+ years", "6+ years", "7+ years",
    ],

    # H1B / visa sponsorship matters
    "needs_sponsorship": True,

    # Minimum relevance score to keep (0.0 - 1.0)
    # Jobs below this score are still stored but marked low-priority
    "min_score_threshold": 0.3,
}
