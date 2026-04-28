"""
Relevance engine — scores every scraped job against your profile.
No ML dependencies. Pure keyword + heuristic scoring.
"""

import re
import logging
from config.profile import PROFILE
from config.companies import RELEVANT_TITLE_KEYWORDS, EXCLUDE_TITLE_KEYWORDS

log = logging.getLogger(__name__)

PLATINUM_BOOST = 0.08


class RelevanceEngine:
    def __init__(self):
        self.core = [s.lower() for s in PROFILE["core_skills"]]
        self.secondary = [s.lower() for s in PROFILE["secondary_skills"]]
        self.locations = [s.lower() for s in PROFILE["preferred_locations"]]
        self.exp_kw = [s.lower() for s in PROFILE["experience_keywords"]]
        self.needs_sponsor = PROFILE.get("needs_sponsorship", False)

    def is_relevant_title(self, title: str) -> bool:
        """
        Pre-filter: only keep titles relevant to data/ML/AI/analytics engineering.

        Three-gate logic:
          1. Hard-exclude — immediately reject irrelevant roles (field operator,
             HR, medical, data entry, etc.)
          2. Hard-include — immediately accept known target roles
          3. Context filter — broad terms (data, AI) only pass if paired with an
             engineering/technical context word, preventing "Field Data Collector"
             or "Data Entry Specialist" from leaking through.
        """
        t = title.lower()

        # Gate 1: hard exclude — rejects before anything else
        if any(kw in t for kw in EXCLUDE_TITLE_KEYWORDS):
            return False

        # Gate 2: hard include — explicit target role match
        if any(kw in t for kw in RELEVANT_TITLE_KEYWORDS):
            return True

        # Gate 3: contextual match — broad signal must pair with engineering context
        has_data_ctx = any(w in t for w in [
            "data", "database", "dba", "dataops",
        ])
        has_ml_ai = any(w in t for w in [
            "ml ", " ml", "machine learning", "artificial intelligence",
            "ai ", " ai", "llm", "nlp", "deep learning", "neural",
            "computer vision", "generative",
        ])
        has_eng_ctx = any(w in t for w in [
            "engineer", "engineering", "developer", "dev ", "architect",
            "scientist", "analyst", "specialist",
        ])
        has_infra_ctx = any(w in t for w in [
            "pipeline", "etl", "warehouse", "lakehouse", "dbt",
            "kafka", "spark", "airflow", "streaming",
        ])

        technical = has_eng_ctx or has_infra_ctx
        return (has_data_ctx or has_ml_ai) and technical

    def score(self, job: dict) -> tuple[float, list[str]]:
        """
        Score a job 0.0 → 1.0 and return matched skills.

        Scoring breakdown:
          - Core skill matches:     40% (each core skill = 40/len(core))
          - Secondary skill matches: 20%
          - Title relevance:        15%
          - Location preference:    10%
          - Experience level match: 10%
          - Sponsorship signal:      5%
        """
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        location = (job.get("location") or "").lower()
        text = f"{title} {desc}"

        matched_skills = []
        score = 0.0

        # ── Core skills (40%) ──
        core_weight = 0.40 / max(len(self.core), 1)
        for skill in self.core:
            if _skill_match(skill, text):
                score += core_weight
                matched_skills.append(skill)

        # ── Secondary skills (20%) ──
        sec_weight = 0.20 / max(len(self.secondary), 1)
        for skill in self.secondary:
            if _skill_match(skill, text):
                score += sec_weight
                matched_skills.append(skill)

        # ── Title relevance (15%) ──
        title_score = 0.0
        if any(kw in title for kw in ["data engineer", "data platform", "data infrastructure"]):
            title_score = 0.15
        elif any(kw in title for kw in ["ml engineer", "machine learning", "mlops", "ai engineer"]):
            title_score = 0.14
        elif any(kw in title for kw in ["analytics engineer", "data scientist"]):
            title_score = 0.12
        elif any(kw in title for kw in [
            "quantitative researcher", "quant researcher", "quant developer",
            "quant analyst", "quant engineer", "quant strat", "trading engineer",
            "systematic researcher", "research engineer", "financial engineer",
        ]):
            title_score = 0.13  # quant research/engineering — highly relevant
        elif any(kw in title for kw in ["platform engineer", "backend engineer"]):
            title_score = 0.08
        elif any(kw in title for kw in ["quantitative", "quant", "algorithmic", "systematic"]):
            title_score = 0.07  # broad quant signal
        elif "data" in title or "engineer" in title:
            title_score = 0.05
        score += title_score

        # ── Location (10%) ──
        if any(loc in location for loc in self.locations):
            score += 0.10
        elif job.get("is_remote"):
            score += 0.10  # Remote is always a match

        # ── Experience level (10%) ──
        if any(kw in text for kw in self.exp_kw):
            score += 0.10

        # ── Sponsorship (5%) ──
        if self.needs_sponsor:
            if _detects_sponsorship(text):
                score += 0.05
            elif _detects_no_sponsorship(text):
                score -= 0.05  # Penalty

        # Clamp to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        # ── Platinum company boost (8%) ──
        if job.get("tier") == "platinum":
            score = min(1.0, score + PLATINUM_BOOST)

        # Deduplicate while preserving insertion order (a skill could appear in both
        # core and secondary lists if profile.py was misconfigured)
        return round(score, 4), list(dict.fromkeys(matched_skills))


def _skill_match(skill: str, text: str) -> bool:
    """Match skill accounting for word boundaries and common variants."""
    # Direct match
    if skill in text:
        return True
    # Handle multi-word skills
    if " " in skill:
        return skill in text
    # Word boundary match to avoid false positives (e.g. 'r' matching 'programmer')
    pattern = rf'\b{re.escape(skill)}\b'
    return bool(re.search(pattern, text))


def _detects_sponsorship(text: str) -> bool:
    return any(kw in text for kw in [
        "visa sponsor", "h1b", "h-1b", "sponsorship available",
        "immigration support", "work visa",
    ])


def _detects_no_sponsorship(text: str) -> bool:
    return any(kw in text for kw in [
        "no sponsorship", "not sponsor", "unable to sponsor",
        "without sponsorship", "citizen only", "clearance required",
        "permanent resident", "us citizen",
    ])
