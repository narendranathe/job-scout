"""
Your personal profile — the relevance engine scores every scraped job against this.

Edit these to match your actual skills and preferences.
Skills are extracted from your resume automatically when you POST to /api/resume,
but the values here act as permanent defaults that always apply.
"""

# Niche AI/LLM-tooling terms. Surfaced as a separate UI lane (not a score boost)
# so the signal stays interpretable on a small job corpus where IDF is unstable.
RARE_SKILLS_WATCH = [
    "llamaindex",
    "model context protocol",
    "mcp",
    "vllm",
    "agentic eval",
    "rag eval",
    "langgraph",
    "anthropic sdk",
    "claude api",
    "fine-tuning",
    "prompt caching",
]

PROFILE = {
    # ── Core skills (40% of score) ─────────────────────────────────────
    # Your strongest, most used skills — weight these the highest
    "core_skills": [
        "python", "sql", "spark", "pyspark", "kafka",
        "airflow", "etl", "data pipeline", "data lake", "data warehouse",
        "azure", "aws", "databricks", "delta lake", "microsoft fabric",
    ],

    # ── Secondary skills (20% of score) ────────────────────────────────
    # Skills you know well but aren't your primary focus
    "secondary_skills": [
        "docker", "kubernetes", "terraform", "ci/cd",
        "dbt", "snowflake", "redshift", "bigquery",
        "postgresql", "sql server", "mongodb",
        "fastapi", "flask", "rest api",
        "git", "linux", "bash",
        "mlflow", "mlops", "machine learning",
        "pytorch", "tensorflow", "scikit-learn",
        "tableau", "powerbi", "looker",
        "flink", "kinesis", "data mesh",
        # Quant/HFT skills — relevant for Jane Street, Two Sigma, Citadel etc.
        "numpy", "pandas", "scipy", "quantitative", "statistical modeling",
        "backtesting", "systematic", "low latency", "c++", "java",
        "distributed systems", "high performance", "real-time",
        "financial modeling", "time series", "algorithm",
    ],

    # ── Preferred locations (10% of score) ─────────────────────────────
    # Remote + TX cities are primary. NYC/Chicago added for quant firms.
    "preferred_locations": [
        "remote", "dallas", "tx", "texas", "austin", "plano",
        "new york", "nyc", "new york city", "chicago",
    ],

    # ── Experience level keywords (10% of score) ────────────────────────
    # You're targeting senior+ roles — these boost the score
    "experience_keywords": [
        "senior", "sr.", "staff", "lead", "principal", "distinguished",
        "4+ years", "5+ years", "6+ years", "7+ years", "8+ years",
    ],

    # ── H1B / visa sponsorship ──────────────────────────────────────────
    # True = sponsorship signal boosts score; "no sponsorship" penalizes
    "needs_sponsorship": True,

    # ── Minimum relevance score to store ────────────────────────────────
    # Jobs below this are filtered out entirely (saves DB space)
    "min_score_threshold": 0.30,

    # ── Dream job alert threshold ────────────────────────────────────────
    # Only send notifications when score >= this AND company + role match
    # Set in env var ALERT_MIN_SCORE (default 0.65) or change here
    "alert_min_score": 0.65,

    # ── Dream companies ──────────────────────────────────────────────────
    # These are set via DREAM_COMPANIES env var on Render.
    # Kept here as documentation of intent — the notifier reads env var.
    "_dream_companies_reference": [
        "Anthropic", "OpenAI", "Stripe", "Databricks", "Snowflake",
        "Goldman Sachs", "Walmart", "Apple", "NVIDIA", "Google",
        "Microsoft", "Disney", "Citadel", "Citadel Securities", "AQR Capital",
        "Hudson River Trading", "Jane Street", "Two Sigma", "Jump Trading",
        "SIG", "IMC Trading", "Bridgewater Associates", "Flow Traders",
        "Tower Research Capital", "Millennium Management",
        "Point72", "Optiver", "Virtu Financial", "PIMCO",
        "Netflix", "Meta", "Spotify", "Fidelity", "Uber",
        "Bloomberg", "Morgan Stanley", "BlackRock", "DoorDash", "Amazon",
        "Salesforce", "JP Morgan Chase",
    ],

    # ── Dream role keywords ──────────────────────────────────────────────
    # Kept here as documentation — notifier reads DREAM_ROLE_KEYWORDS env var
    "_dream_roles_reference": [
        "data engineer", "senior data engineer", "sr data engineer",
        "ml engineer", "ai engineer", "analytics engineer", "analytical engineer",
        "data platform engineer", "staff data engineer", "principal data engineer",
        "lead data engineer",
        # Quant/HFT roles
        "quantitative researcher", "quant researcher", "quant developer",
        "quant analyst", "trading engineer", "quant engineer",
        "research engineer", "systematic researcher",
    ],
}
