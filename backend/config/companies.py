"""
Company registry — 120+ companies with verified ATS slugs.

ATS URL patterns (all PUBLIC, no auth needed):
  Greenhouse:      boards-api.greenhouse.io/v1/boards/{SLUG}/jobs
  Lever:           api.lever.co/v0/postings/{SLUG}
  Ashby:           api.ashbyhq.com/posting-api/job-board/{SLUG}
  SmartRecruiters: api.smartrecruiters.com/v1/companies/{SLUG}/postings
  BambooHR:        {SLUG}.bamboohr.com/careers/list
  Workday:         POST {slug}.{wd_instance}.myworkdayjobs.com/wday/cxs/{slug}/{wd_board}/jobs

Priority tiers:
  1 = Check every cycle (top targets)
  2 = Check every 2nd cycle
  3 = Check every 4th cycle
"""

COMPANIES = [
    # ═══════════════════════════════════════
    #  TIER 1 — Dream targets (every cycle)
    #  These are your highest-priority companies.
    #  Scraped most frequently — new roles appear here first.
    # ═══════════════════════════════════════

    # ── Greenhouse — Dream companies (Tier 1) ──
    {"name": "Anthropic",          "ats": "greenhouse", "slug": "anthropic",             "tier": 1},
    {"name": "OpenAI",             "ats": "greenhouse", "slug": "openai",                "tier": 1},
    {"name": "Stripe",             "ats": "greenhouse", "slug": "stripe",                "tier": 1},
    {"name": "Databricks",         "ats": "greenhouse", "slug": "databricks",            "tier": 1},
    {"name": "Snowflake",          "ats": "greenhouse", "slug": "snowflakecomputing",    "tier": 1},
    {"name": "Palantir",           "ats": "greenhouse", "slug": "palantir",              "tier": 1},
    {"name": "Scale AI",           "ats": "greenhouse", "slug": "scaleai",               "tier": 1},
    {"name": "Coinbase",           "ats": "greenhouse", "slug": "coinbase",              "tier": 1},
    {"name": "Datadog",            "ats": "greenhouse", "slug": "datadog",               "tier": 1},
    {"name": "Reddit",             "ats": "greenhouse", "slug": "reddit",                "tier": 1},
    {"name": "Ramp",               "ats": "greenhouse", "slug": "ramp",                  "tier": 1},
    {"name": "Plaid",              "ats": "greenhouse", "slug": "plaid",                 "tier": 1},
    {"name": "Anduril",            "ats": "greenhouse", "slug": "andurilindustries",     "tier": 1},
    {"name": "Wiz",                "ats": "greenhouse", "slug": "wiz",                   "tier": 1},
    {"name": "Rippling",           "ats": "greenhouse", "slug": "rippling",              "tier": 1},
    {"name": "dbt Labs",           "ats": "greenhouse", "slug": "daboratoriesdbtlabsinc","tier": 1},
    {"name": "Fivetran",           "ats": "greenhouse", "slug": "fivetran",              "tier": 1},
    {"name": "Confluent",          "ats": "greenhouse", "slug": "confluent",             "tier": 1},
    {"name": "Discord",            "ats": "greenhouse", "slug": "discord",               "tier": 1},

    # ── Lever — Dream companies (Tier 1) ──
    {"name": "Netflix",            "ats": "lever",      "slug": "netflix",               "tier": 1},
    {"name": "Spotify",            "ats": "lever",      "slug": "spotify",               "tier": 1},

    # ── Ashby — Dream companies (Tier 1) ──
    {"name": "Vercel",             "ats": "ashby",      "slug": "vercel",                "tier": 1},
    {"name": "Linear",             "ats": "ashby",      "slug": "linear",                "tier": 1},
    {"name": "Supabase",           "ats": "ashby",      "slug": "supabase",              "tier": 1},

    # ── Big Tech Dream companies — use Greenhouse slugs ──
    {"name": "Salesforce",         "ats": "greenhouse", "slug": "salesforce",            "tier": 1},
    {"name": "Uber",               "ats": "greenhouse", "slug": "uber",                  "tier": 1},
    {"name": "DoorDash",           "ats": "greenhouse", "slug": "doordash",              "tier": 1},
    {"name": "Grubhub",            "ats": "greenhouse", "slug": "grubhub",               "tier": 1},

    # ═══════════════════════════════════════
    #  TIER 2 — Strong targets (every 2nd)
    # ═══════════════════════════════════════

    # ── Greenhouse ──
    {"name": "Figma",              "ats": "greenhouse", "slug": "figma",                 "tier": 2},
    {"name": "Notion",             "ats": "greenhouse", "slug": "notion",                "tier": 2},
    {"name": "Brex",               "ats": "greenhouse", "slug": "brex",                  "tier": 2},
    {"name": "Airtable",           "ats": "greenhouse", "slug": "airtable",              "tier": 2},
    {"name": "MongoDB",            "ats": "greenhouse", "slug": "mongodb",               "tier": 2},
    {"name": "Elastic",            "ats": "greenhouse", "slug": "elastic",               "tier": 2},
    {"name": "Cloudflare",         "ats": "greenhouse", "slug": "cloudflare",            "tier": 2},
    {"name": "GitLab",             "ats": "greenhouse", "slug": "gitlab",                "tier": 2},
    {"name": "HashiCorp",          "ats": "greenhouse", "slug": "hashicorp",             "tier": 2},
    {"name": "CrowdStrike",        "ats": "greenhouse", "slug": "crowdstrike",           "tier": 2},
    {"name": "Block (Square)",     "ats": "greenhouse", "slug": "block",                 "tier": 2},
    {"name": "Twilio",             "ats": "greenhouse", "slug": "twilio",                "tier": 2},
    {"name": "Affirm",             "ats": "greenhouse", "slug": "affirm",                "tier": 2},
    {"name": "Gusto",              "ats": "greenhouse", "slug": "gusto",                 "tier": 2},
    {"name": "Toast",              "ats": "greenhouse", "slug": "toast",                 "tier": 2},
    {"name": "Samsara",            "ats": "greenhouse", "slug": "samsara",               "tier": 2},
    {"name": "Miro",               "ats": "greenhouse", "slug": "miro",                  "tier": 2},
    {"name": "Navan",              "ats": "greenhouse", "slug": "navan",                 "tier": 2},
    {"name": "Grammarly",          "ats": "greenhouse", "slug": "grammarly",             "tier": 2},
    {"name": "Canva",              "ats": "greenhouse", "slug": "canva",                 "tier": 2},
    {"name": "Zapier",             "ats": "greenhouse", "slug": "zapier",                "tier": 2},
    {"name": "Webflow",            "ats": "greenhouse", "slug": "webflow",               "tier": 2},
    {"name": "Grafana Labs",       "ats": "greenhouse", "slug": "grafanalabs",           "tier": 2},
    {"name": "Temporal",           "ats": "greenhouse", "slug": "temporal",              "tier": 2},
    {"name": "Cockroach Labs",     "ats": "greenhouse", "slug": "cockroachlabs",         "tier": 2},
    {"name": "PlanetScale",        "ats": "greenhouse", "slug": "planetscale",           "tier": 2},
    {"name": "Vanta",              "ats": "greenhouse", "slug": "vanta",                 "tier": 2},
    {"name": "Weights & Biases",   "ats": "greenhouse", "slug": "wandb",                 "tier": 2},
    {"name": "Cohere",             "ats": "greenhouse", "slug": "cohere",                "tier": 2},
    {"name": "Mistral AI",         "ats": "greenhouse", "slug": "mistral",               "tier": 2},
    {"name": "Hugging Face",       "ats": "greenhouse", "slug": "huggingface",           "tier": 2},
    {"name": "Perplexity",         "ats": "greenhouse", "slug": "perplexityai",          "tier": 2},
    {"name": "Instacart",          "ats": "greenhouse", "slug": "instacart",             "tier": 2},
    {"name": "DoorDash",           "ats": "greenhouse", "slug": "doordash",              "tier": 2},
    {"name": "Lyft",               "ats": "greenhouse", "slug": "lyft",                  "tier": 2},
    {"name": "Airbnb",             "ats": "greenhouse", "slug": "airbnb",                "tier": 2},
    {"name": "Pinterest",          "ats": "greenhouse", "slug": "pinterest",             "tier": 2},
    {"name": "Snap",               "ats": "greenhouse", "slug": "snap",                  "tier": 2},
    {"name": "Robinhood",          "ats": "greenhouse", "slug": "robinhood",             "tier": 2},
    {"name": "Chime",              "ats": "greenhouse", "slug": "chime",                 "tier": 2},
    {"name": "Faire",              "ats": "greenhouse", "slug": "faire",                 "tier": 2},
    {"name": "Flexport",           "ats": "greenhouse", "slug": "flexport",              "tier": 2},
    {"name": "Pagerduty",          "ats": "greenhouse", "slug": "pagerduty",             "tier": 2},
    {"name": "Okta",               "ats": "greenhouse", "slug": "okta",                  "tier": 2},
    {"name": "SentinelOne",        "ats": "greenhouse", "slug": "sentinelone",           "tier": 2},

    # ── Ashby Tier 2 ──
    {"name": "Retool",             "ats": "ashby",      "slug": "retool",                "tier": 2},
    {"name": "Neon",               "ats": "ashby",      "slug": "neondatabase",          "tier": 2},
    {"name": "PostHog",            "ats": "ashby",      "slug": "posthog",               "tier": 2},
    {"name": "Railway",            "ats": "ashby",      "slug": "railway",               "tier": 2},
    {"name": "Resend",             "ats": "ashby",      "slug": "resend",                "tier": 2},
    {"name": "Tinybird",           "ats": "ashby",      "slug": "tinybird",              "tier": 2},
    {"name": "MotherDuck",         "ats": "ashby",      "slug": "motherduck",            "tier": 2},
    {"name": "Hex",                "ats": "ashby",      "slug": "hex",                   "tier": 2},

    # ═══════════════════════════════════════
    #  TIER 3 — Extended pipeline (every 4th)
    # ═══════════════════════════════════════

    # ── SmartRecruiters ──
    {"name": "Visa",               "ats": "smartrecruiters", "slug": "Visa",             "tier": 3},
    {"name": "KPMG",               "ats": "smartrecruiters", "slug": "KPMG",             "tier": 3},
    {"name": "Bosch",              "ats": "smartrecruiters", "slug": "BoschGroup",        "tier": 3},
    {"name": "McDonald's",         "ats": "smartrecruiters", "slug": "McDonalds",         "tier": 3},

    # ── Greenhouse Tier 3 ──
    {"name": "Loom",               "ats": "greenhouse", "slug": "loom",                  "tier": 3},
    {"name": "CircleCI",           "ats": "greenhouse", "slug": "circleci",              "tier": 3},
    {"name": "LaunchDarkly",       "ats": "greenhouse", "slug": "launchdarkly",          "tier": 3},
    {"name": "Amplitude",          "ats": "greenhouse", "slug": "amplitude",             "tier": 3},
    {"name": "Segment (Twilio)",   "ats": "greenhouse", "slug": "twilio",                "tier": 3},
    {"name": "Calendly",           "ats": "greenhouse", "slug": "calendly",              "tier": 3},
    {"name": "ClickUp",            "ats": "greenhouse", "slug": "clickup",               "tier": 3},
    {"name": "HubSpot",            "ats": "greenhouse", "slug": "hubspot",               "tier": 3},
    {"name": "Asana",              "ats": "greenhouse", "slug": "asana",                 "tier": 3},
    {"name": "Dropbox",            "ats": "greenhouse", "slug": "dropbox",               "tier": 3},
    {"name": "Atlassian",          "ats": "greenhouse", "slug": "atlassian",             "tier": 3},
    {"name": "Zoom",               "ats": "greenhouse", "slug": "zoomvideocommunications","tier": 3},
    {"name": "Uber",               "ats": "greenhouse", "slug": "uber",                  "tier": 3},
    {"name": "Rubrik",             "ats": "greenhouse", "slug": "rubrik",                "tier": 3},
    {"name": "Zscaler",            "ats": "greenhouse", "slug": "zscaler",               "tier": 3},
    {"name": "Verkada",            "ats": "greenhouse", "slug": "verkada",               "tier": 3},
    {"name": "Nutanix",            "ats": "greenhouse", "slug": "nutanix",               "tier": 3},
    {"name": "Pure Storage",       "ats": "greenhouse", "slug": "purestorage",           "tier": 3},
    {"name": "Starburst",          "ats": "greenhouse", "slug": "starburst",             "tier": 3},
    {"name": "Materialize",        "ats": "greenhouse", "slug": "materialize",           "tier": 3},
    {"name": "StarTree",           "ats": "greenhouse", "slug": "startree",              "tier": 3},
    {"name": "ClickHouse",         "ats": "greenhouse", "slug": "clickhouse",            "tier": 3},
    {"name": "Cribl",              "ats": "greenhouse", "slug": "criaboratories",        "tier": 3},

    # ── Lever Tier 3 ──
    {"name": "Handshake",          "ats": "lever",      "slug": "joinhandshake",         "tier": 3},
    {"name": "Calm",               "ats": "lever",      "slug": "calm",                  "tier": 3},

    # ── BambooHR ──
    {"name": "Prefect",            "ats": "bamboohr",   "slug": "prefect",               "tier": 2},
    {"name": "Dagster",            "ats": "bamboohr",   "slug": "elementl",              "tier": 2},
    {"name": "Great Expectations", "ats": "bamboohr",   "slug": "greatexpectations",     "tier": 3},

    # ═══════════════════════════════════════
    #  WORKDAY — Finance & Enterprise (Tier 1/2 if dream, Tier 3 otherwise)
    #  These companies post less frequently but are high-priority targets.
    #  Verify/update board names at: company.wd1.myworkdayjobs.com
    # ═══════════════════════════════════════

    # ── Dream finance/enterprise companies on Workday (Tier 1 — check every cycle) ──
    {"name": "Goldman Sachs",   "ats": "workday", "slug": "goldmansachs",  "wd_instance": "wd1", "wd_board": "GS",              "tier": 1},
    {"name": "JP Morgan Chase", "ats": "workday", "slug": "jpmc",          "wd_instance": "wd1", "wd_board": "JPMCCareerSite",  "tier": 1},
    {"name": "Fidelity",        "ats": "workday", "slug": "fidelity",      "wd_instance": "wd1", "wd_board": "fidelity-careers","tier": 1},
    {"name": "Citadel",         "ats": "workday", "slug": "citadel",       "wd_instance": "wd5", "wd_board": "Careers",         "tier": 1},
    {"name": "Bloomberg",       "ats": "workday", "slug": "bloomberg",     "wd_instance": "wd5", "wd_board": "BloombergLP",     "tier": 1},

    # ── Big Tech on Workday (Tier 1) ──
    {"name": "Apple",           "ats": "workday", "slug": "apple",         "wd_instance": "wd5", "wd_board": "US",              "tier": 1},
    {"name": "NVIDIA",          "ats": "workday", "slug": "nvidia",        "wd_instance": "wd5", "wd_board": "NVIDIAExternalCareerSite","tier": 1},
    {"name": "Microsoft",       "ats": "workday", "slug": "microsoft",     "wd_instance": "wd5", "wd_board": "MicrosoftExternalCareerSite","tier": 1},
    {"name": "Amazon",          "ats": "workday", "slug": "amazon",        "wd_instance": "wd5", "wd_board": "External",        "tier": 1},
    {"name": "Walmart",         "ats": "workday", "slug": "walmart",       "wd_instance": "wd5", "wd_board": "WalmartExternal", "tier": 1},
    {"name": "Meta",            "ats": "workday", "slug": "meta",          "wd_instance": "wd5", "wd_board": "FBExternalCareerSite","tier": 1},
    {"name": "Google",          "ats": "workday", "slug": "google",        "wd_instance": "wd5", "wd_board": "jobs",            "tier": 1},

    # ── Other dream companies on Workday (Tier 2) ──
    {"name": "Disney",          "ats": "workday", "slug": "disney",        "wd_instance": "wd5", "wd_board": "disneycareer",    "tier": 2},
    {"name": "Capital One",     "ats": "workday", "slug": "capitalone",    "wd_instance": "wd1", "wd_board": "Capital_One",     "tier": 2},
    {"name": "Amex",            "ats": "workday", "slug": "aexp",          "wd_instance": "wd5", "wd_board": "amex-careers",    "tier": 2},
    {"name": "Target",          "ats": "workday", "slug": "target",        "wd_instance": "wd1", "wd_board": "TGT_External",    "tier": 3},
    {"name": "Deloitte",        "ats": "workday", "slug": "deloitte",      "wd_instance": "wd5", "wd_board": "DeloitteCareers", "tier": 3},

    # ── Quant firms (AQR, HRT use custom job boards — listed for reference) ──
    # AQR:  https://careers.aqr.com  — no standard public API, apply directly
    # HRT:  https://www.hudsonrivertrading.com/careers/ — no public ATS API
    # Two Sigma: https://careers.twosigma.com — no standard public API
    # NOTE: Monitor these manually or check LinkedIn for new postings
]

# Total companies
TOTAL_COMPANIES = len(COMPANIES)

# ── Title filters ──
RELEVANT_TITLE_KEYWORDS = [
    "data engineer", "data platform", "data infrastructure",
    "ml engineer", "machine learning engineer", "mlops",
    "analytics engineer", "ai engineer", "ai platform",
    "etl", "data pipeline", "data scientist",
    "software engineer, data", "backend engineer, data",
    "platform engineer", "infrastructure engineer",
    "devops", "sre", "site reliability",
    "big data", "data architect", "data ops",
]

EXCLUDE_TITLE_KEYWORDS = [
    "recruiter", "sales", "marketing", "legal", "counsel",
    "talent acquisition", "account executive", "customer success",
    "designer", "ux", "product manager", "content writer",
    "office manager", "executive assistant", "receptionist",
]


def get_batch(cycle_number: int, batch_size: int = 0) -> list[dict]:
    """
    Smart batching: returns companies to scrape THIS cycle.

    - Tier 1: every cycle
    - Tier 2: every 2nd cycle
    - Tier 3: every 4th cycle

    If batch_size > 0, also splits within tiers for round-robin.
    """
    eligible = []
    for co in COMPANIES:
        tier = co.get("tier", 3)
        if tier == 1:
            eligible.append(co)
        elif tier == 2 and cycle_number % 2 == 0:
            eligible.append(co)
        elif tier == 3 and cycle_number % 4 == 0:
            eligible.append(co)

    if batch_size > 0 and len(eligible) > batch_size:
        # Round-robin within eligible companies
        start = (cycle_number * batch_size) % len(eligible)
        return eligible[start:start + batch_size] + eligible[:max(0, start + batch_size - len(eligible))]

    return eligible
