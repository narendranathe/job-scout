"""
Company Registry — Maps 100+ target companies to their ATS platforms.

ATS platforms with FREE public APIs (no auth needed):
  - Greenhouse:      boards-api.greenhouse.io/v1/boards/{slug}/jobs
  - Lever:           api.lever.co/v0/postings/{slug}
  - Ashby:           api.ashbyhq.com/posting-api/job-board/{slug}
  - SmartRecruiters: api.smartrecruiters.com/v1/companies/{id}/postings

Platforms requiring scraping:
  - Workday:         {company}.wd5.myworkdayjobs.com/en-US/{board}
  - iCIMS:           careers-{company}.icims.com/jobs/search
  - Custom:          Company-specific career pages
"""

from dataclasses import dataclass
from enum import Enum


class ATSPlatform(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    WORKDAY = "workday"
    ICIMS = "icims"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Company:
    name: str
    ats: ATSPlatform
    board_slug: str  # ATS-specific identifier
    career_url: str  # Fallback career page
    priority: int = 1  # 1=high, 2=medium, 3=low
    notes: str = ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 100+ COMPANIES — organized by ATS platform
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMPANY_REGISTRY: list[Company] = [

    # ══════════════════════════════════════════
    # GREENHOUSE (Public API — no auth needed)
    # API: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
    # ══════════════════════════════════════════

    Company("Uber", ATSPlatform.GREENHOUSE, "uber", "https://www.uber.com/us/en/careers/", 1),
    Company("Stripe", ATSPlatform.GREENHOUSE, "stripe", "https://stripe.com/jobs", 1),
    Company("Datadog", ATSPlatform.GREENHOUSE, "datadog", "https://careers.datadoghq.com/", 1),
    Company("Snowflake", ATSPlatform.GREENHOUSE, "snowflake", "https://careers.snowflake.com/", 1),
    Company("Databricks", ATSPlatform.GREENHOUSE, "databricks", "https://www.databricks.com/company/careers", 1),
    Company("Cloudflare", ATSPlatform.GREENHOUSE, "cloudflare", "https://www.cloudflare.com/careers/", 1),
    Company("Discord", ATSPlatform.GREENHOUSE, "discord", "https://discord.com/careers", 1),
    Company("Figma", ATSPlatform.GREENHOUSE, "figma", "https://www.figma.com/careers/", 2),
    Company("Notion", ATSPlatform.GREENHOUSE, "notion", "https://www.notion.so/careers", 2),
    Company("Coinbase", ATSPlatform.GREENHOUSE, "coinbase", "https://www.coinbase.com/careers", 1),
    Company("Airbnb", ATSPlatform.GREENHOUSE, "airbnb", "https://careers.airbnb.com/", 1),
    Company("DoorDash", ATSPlatform.GREENHOUSE, "doordash", "https://careers.doordash.com/", 2),
    Company("Instacart", ATSPlatform.GREENHOUSE, "instacart", "https://instacart.careers/", 2),
    Company("Twitch", ATSPlatform.GREENHOUSE, "twitch", "https://www.twitch.tv/jobs", 2),
    Company("HashiCorp", ATSPlatform.GREENHOUSE, "hashicorp", "https://www.hashicorp.com/careers", 2),
    Company("MongoDB", ATSPlatform.GREENHOUSE, "mongodb", "https://www.mongodb.com/careers", 1),
    Company("Elastic", ATSPlatform.GREENHOUSE, "elastic", "https://www.elastic.co/careers/", 2),
    Company("Confluent", ATSPlatform.GREENHOUSE, "confluent", "https://www.confluent.io/careers/", 1),
    Company("dbt Labs", ATSPlatform.GREENHOUSE, "dbtlabs", "https://www.getdbt.com/careers/", 1),
    Company("Fivetran", ATSPlatform.GREENHOUSE, "fivetran", "https://www.fivetran.com/careers", 1),
    Company("Starburst", ATSPlatform.GREENHOUSE, "starburst", "https://www.starburst.io/careers/", 2),
    Company("Plaid", ATSPlatform.GREENHOUSE, "plaid", "https://plaid.com/careers/", 2),
    Company("Airtable", ATSPlatform.GREENHOUSE, "airtable", "https://airtable.com/careers", 2),
    Company("GitLab", ATSPlatform.GREENHOUSE, "gitlab", "https://about.gitlab.com/jobs/", 2),
    Company("Ramp", ATSPlatform.GREENHOUSE, "ramp", "https://ramp.com/careers", 1),
    Company("Brex", ATSPlatform.GREENHOUSE, "brex", "https://www.brex.com/careers", 2),
    Company("Scale AI", ATSPlatform.GREENHOUSE, "scaleai", "https://scale.com/careers", 1),
    Company("Anduril", ATSPlatform.GREENHOUSE, "anduril", "https://www.anduril.com/careers/", 2),
    Company("Palantir", ATSPlatform.GREENHOUSE, "palantir", "https://www.palantir.com/careers/", 1),
    Company("Block (Square)", ATSPlatform.GREENHOUSE, "block", "https://block.xyz/careers", 1),
    Company("Robinhood", ATSPlatform.GREENHOUSE, "robinhood", "https://robinhood.com/careers/", 2),
    Company("Reddit", ATSPlatform.GREENHOUSE, "reddit", "https://www.redditinc.com/careers", 2),
    Company("Okta", ATSPlatform.GREENHOUSE, "okta", "https://www.okta.com/company/careers/", 2),
    Company("Grammarly", ATSPlatform.GREENHOUSE, "grammarly", "https://www.grammarly.com/careers", 3),
    Company("HubSpot", ATSPlatform.GREENHOUSE, "hubspot", "https://www.hubspot.com/careers", 2),
    Company("Toast", ATSPlatform.GREENHOUSE, "toast", "https://careers.toasttab.com/", 3),
    Company("Verkada", ATSPlatform.GREENHOUSE, "verkada", "https://www.verkada.com/careers/", 3),
    Company("Rippling", ATSPlatform.GREENHOUSE, "rippling", "https://www.rippling.com/careers", 2),
    Company("Navan", ATSPlatform.GREENHOUSE, "navan", "https://navan.com/careers", 3),
    Company("Anthropic", ATSPlatform.GREENHOUSE, "anthropic", "https://www.anthropic.com/careers", 1),
    Company("OpenAI", ATSPlatform.GREENHOUSE, "openai", "https://openai.com/careers", 1),
    Company("Cohere", ATSPlatform.GREENHOUSE, "cohere", "https://cohere.com/careers", 2),

    # ══════════════════════════════════════════
    # LEVER (Public API — no auth needed)
    # API: GET https://api.lever.co/v0/postings/{slug}
    # ══════════════════════════════════════════

    Company("Netflix", ATSPlatform.LEVER, "netflix", "https://jobs.netflix.com/", 1),
    Company("Spotify", ATSPlatform.LEVER, "spotify", "https://www.lifeatspotify.com/jobs", 1),
    Company("Twilio", ATSPlatform.LEVER, "twilio", "https://www.twilio.com/en-us/company/jobs", 2),
    Company("GitHub", ATSPlatform.LEVER, "github", "https://github.com/about/careers", 1),
    Company("Lyft", ATSPlatform.LEVER, "lyft", "https://www.lyft.com/careers", 2),
    Company("Two Sigma", ATSPlatform.LEVER, "twosigma", "https://www.twosigma.com/careers/", 1),
    Company("Citadel", ATSPlatform.LEVER, "citadel", "https://www.citadel.com/careers/", 1),
    Company("Jane Street", ATSPlatform.LEVER, "janestreet", "https://www.janestreet.com/join-jane-street/", 1),
    Company("Point72", ATSPlatform.LEVER, "point72", "https://point72.com/careers/", 1),
    Company("D.E. Shaw", ATSPlatform.LEVER, "deshaw", "https://www.deshaw.com/careers", 1),
    Company("Cockroach Labs", ATSPlatform.LEVER, "cockroachlabs", "https://www.cockroachlabs.com/careers/", 2),
    Company("PlanetScale", ATSPlatform.LEVER, "planetscale", "https://planetscale.com/careers", 2),
    Company("Temporal", ATSPlatform.LEVER, "temporal", "https://temporal.io/careers", 2),
    Company("Vercel", ATSPlatform.LEVER, "vercel", "https://vercel.com/careers", 3),
    Company("Supabase", ATSPlatform.LEVER, "supabase", "https://supabase.com/careers", 3),

    # ══════════════════════════════════════════
    # ASHBY (Public API — no auth needed)
    # API: POST https://api.ashbyhq.com/posting-api/job-board/{slug}
    # ══════════════════════════════════════════

    Company("Whatnot", ATSPlatform.ASHBY, "whatnot", "https://www.whatnot.com/careers", 3),
    Company("Linear", ATSPlatform.ASHBY, "linear", "https://linear.app/careers", 3),
    Company("Hightouch", ATSPlatform.ASHBY, "hightouch", "https://hightouch.com/careers", 2),
    Company("Census", ATSPlatform.ASHBY, "census", "https://www.getcensus.com/careers", 3),
    Company("Prefect", ATSPlatform.ASHBY, "prefect", "https://www.prefect.io/careers", 2),

    # ══════════════════════════════════════════
    # SMARTRECRUITERS (Public API — no auth needed)
    # API: GET https://api.smartrecruiters.com/v1/companies/{id}/postings
    # ══════════════════════════════════════════

    Company("Visa", ATSPlatform.SMARTRECRUITERS, "visa", "https://usa.visa.com/careers.html", 2),
    Company("KPMG", ATSPlatform.SMARTRECRUITERS, "KPMG", "https://kpmg.com/us/en/careers.html", 3),

    # ══════════════════════════════════════════
    # WORKDAY (Requires HTML parsing)
    # Pattern: https://{company}.wd5.myworkdayjobs.com/en-US/{board}
    # ══════════════════════════════════════════

    Company("Disney", ATSPlatform.WORKDAY, "disneycareer/wdj/search", "https://jobs.disneycareers.com/", 1,
            notes="https://disney.wd5.myworkdayjobs.com/en-US/disneycareer"),
    Company("Capital One", ATSPlatform.WORKDAY, "capitalone/search", "https://www.capitalonecareers.com/", 1,
            notes="https://capitalone.wd12.myworkdayjobs.com/en-US/capitalone"),
    Company("American Airlines", ATSPlatform.WORKDAY, "aa_jobs/search", "https://jobs.aa.com/", 1,
            notes="https://americanairlines.wd1.myworkdayjobs.com/en-US/aa_jobs"),
    Company("AT&T", ATSPlatform.WORKDAY, "att/search", "https://www.att.jobs/", 1,
            notes="https://att.wd1.myworkdayjobs.com/en-US/att"),
    Company("JPMorgan Chase", ATSPlatform.WORKDAY, "jpmc/search", "https://careers.jpmorgan.com/", 1,
            notes="https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/requisitions"),
    Company("Goldman Sachs", ATSPlatform.WORKDAY, "goldmansachs/search", "https://www.goldmansachs.com/careers/", 1,
            notes="https://goldmansachs.wd1.myworkdayjobs.com/en-US/goldmansachs"),
    Company("Morgan Stanley", ATSPlatform.WORKDAY, "morganstanley/search", "https://www.morganstanley.com/careers", 1,
            notes="https://morganstanley.wd1.myworkdayjobs.com/en-US/morganstanley"),
    Company("Bank of America", ATSPlatform.WORKDAY, "bofa/search", "https://careers.bankofamerica.com/", 2,
            notes="https://bankcampuscareers.wd1.myworkdayjobs.com/en-US/bofa"),
    Company("Walmart", ATSPlatform.WORKDAY, "walmart/search", "https://careers.walmart.com/", 2,
            notes="https://walmart.wd5.myworkdayjobs.com/en-US/WalmartExternal"),
    Company("Target", ATSPlatform.WORKDAY, "target/search", "https://corporate.target.com/careers", 3,
            notes="https://target.wd5.myworkdayjobs.com/en-US/targetCareers"),
    Company("Deloitte", ATSPlatform.WORKDAY, "deloitte/search", "https://apply.deloitte.com/", 3),
    Company("Accenture", ATSPlatform.WORKDAY, "accenture/search", "https://www.accenture.com/careers", 3),
    Company("Lockheed Martin", ATSPlatform.WORKDAY, "lockheed/search", "https://www.lockheedmartinjobs.com/", 3),

    # ══════════════════════════════════════════
    # CUSTOM CAREER PAGES (direct scraping)
    # ══════════════════════════════════════════

    Company("Google", ATSPlatform.CUSTOM, "google", "https://www.google.com/about/careers/applications/jobs/results/", 1,
            notes="Google Careers API: careers.google.com/api/v3/search/"),
    Company("Meta", ATSPlatform.CUSTOM, "meta", "https://www.metacareers.com/jobs/", 1,
            notes="Meta Careers: metacareers.com/jobs with JSON endpoint"),
    Company("Apple", ATSPlatform.CUSTOM, "apple", "https://jobs.apple.com/en-us/search", 1,
            notes="Apple Jobs API: jobs.apple.com/api/role/search"),
    Company("Amazon", ATSPlatform.CUSTOM, "amazon", "https://www.amazon.jobs/en/", 1,
            notes="Amazon Jobs API: amazon.jobs/en/search.json"),
    Company("Microsoft", ATSPlatform.CUSTOM, "microsoft", "https://careers.microsoft.com/", 1,
            notes="MSFT Careers API: careers.microsoft.com/us/en/search-results"),
    Company("Bloomberg", ATSPlatform.CUSTOM, "bloomberg", "https://careers.bloomberg.com/", 1,
            notes="Bloomberg Careers with JSON search endpoint"),
    Company("Tesla", ATSPlatform.CUSTOM, "tesla", "https://www.tesla.com/careers/search/", 2),
    Company("NVIDIA", ATSPlatform.CUSTOM, "nvidia", "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", 1),
    Company("AMD", ATSPlatform.CUSTOM, "amd", "https://careers.amd.com/careers-home/jobs", 3),
    Company("Intel", ATSPlatform.CUSTOM, "intel", "https://jobs.intel.com/en/search-jobs", 2),
    Company("Salesforce", ATSPlatform.CUSTOM, "salesforce", "https://careers.salesforce.com/en/jobs/", 2),
    Company("Adobe", ATSPlatform.CUSTOM, "adobe", "https://careers.adobe.com/us/en/search-results", 2),
    Company("Oracle", ATSPlatform.CUSTOM, "oracle", "https://careers.oracle.com/jobs/", 3),
    Company("IBM", ATSPlatform.CUSTOM, "ibm", "https://www.ibm.com/careers", 3),
    Company("Cisco", ATSPlatform.CUSTOM, "cisco", "https://jobs.cisco.com/", 3),
    Company("VMware", ATSPlatform.CUSTOM, "vmware", "https://careers.vmware.com/", 3),
    Company("LinkedIn", ATSPlatform.CUSTOM, "linkedin", "https://careers.linkedin.com/", 2),
    Company("Twitter/X", ATSPlatform.CUSTOM, "x", "https://careers.x.com/", 2),
    Company("Snap", ATSPlatform.GREENHOUSE, "snap", "https://snap.com/en-US/jobs", 3),
    Company("Pinterest", ATSPlatform.GREENHOUSE, "pinterest", "https://www.pinterestcareers.com/", 3),
    Company("Zillow", ATSPlatform.GREENHOUSE, "zillow", "https://www.zillow.com/careers/", 3),
    Company("Expedia", ATSPlatform.GREENHOUSE, "expedia", "https://lifeatexpediagroup.com/jobs", 3),
    Company("Booking.com", ATSPlatform.GREENHOUSE, "booking", "https://jobs.booking.com/", 3),
    Company("Galaxy Digital", ATSPlatform.GREENHOUSE, "galaxydigital", "https://www.galaxy.com/careers/", 1,
            notes="FP&A / digital assets focus — applied recently"),
]


def get_companies_by_ats(ats: ATSPlatform) -> list[Company]:
    """Get all companies using a specific ATS platform."""
    return [c for c in COMPANY_REGISTRY if c.ats == ats]


def get_companies_by_priority(priority: int = 1) -> list[Company]:
    """Get companies at or above a priority level (1=highest)."""
    return [c for c in COMPANY_REGISTRY if c.priority <= priority]


def get_all_ats_types() -> set[ATSPlatform]:
    """Get all ATS platforms in the registry."""
    return {c.ats for c in COMPANY_REGISTRY}


# Quick stats
if __name__ == "__main__":
    from collections import Counter
    by_ats = Counter(c.ats.value for c in COMPANY_REGISTRY)
    by_priority = Counter(c.priority for c in COMPANY_REGISTRY)
    print(f"Total companies: {len(COMPANY_REGISTRY)}")
    print(f"By ATS: {dict(by_ats)}")
    print(f"By priority: {dict(by_priority)}")
