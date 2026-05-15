"""
Relevance engine — scores every scraped job against your profile.
No ML dependencies. Pure keyword + heuristic scoring, with an optional
TF-IDF refinement when a resume is loaded (uses helpers from
storage.resume_vault).
"""

import re
import logging
from config.profile import PROFILE
from config.companies import RELEVANT_TITLE_KEYWORDS, EXCLUDE_TITLE_KEYWORDS

log = logging.getLogger(__name__)

# ── Component weights (sum to 1.00) ─────────────────────────────────
# Rebalanced in the v2 scoring overhaul:
#   - core 40 → 36, secondary 20 → 17 to free 7 points
#   - sponsorship 5 → 8 (issue #11: needs_sponsorship users now lose more
#     ground on explicit no-sponsor signals and gain more on positive ones)
#   - salary 0 → 4 (issue #10: posted salary tier nudges the score)
CORE_WEIGHT = 0.36
SECONDARY_WEIGHT = 0.17
TITLE_WEIGHT = 0.15
LOCATION_WEIGHT = 0.10
EXPERIENCE_WEIGHT = 0.10
SPONSORSHIP_WEIGHT = 0.08
SALARY_WEIGHT = 0.04

PLATINUM_BOOST = 0.08

# Salary tier rubric (USD/yr). Reads salary_max if present, else salary_min.
# Aligned with the dashboard's $220K+ filter (commit 9198112).
SALARY_TIERS = (
    (300_000, 1.00),
    (220_000, 0.75),
    (160_000, 0.50),
    (100_000, 0.25),
)

# TF-IDF booster bounds: cosine sim ∈ [0,1] maps to a multiplier on the core
# component. A loaded resume can shave up to 15% off core when the job
# description has no contextual overlap, but never adds above the budget.
TFIDF_MIN_FACTOR = 0.85
TFIDF_MAX_FACTOR = 1.00


def salary_score(job: dict) -> float:
    """
    Return a fraction in [0.0, 1.0] reflecting how high the posted salary is.
    Uses salary_max if available, otherwise salary_min. Missing → 0.0 (no
    boost, no penalty — many ATSes don't publish salary).
    """
    sal = job.get("salary_max") or job.get("salary_min") or 0
    try:
        sal = int(sal)
    except (TypeError, ValueError):
        return 0.0
    if sal <= 0:
        return 0.0
    for threshold, fraction in SALARY_TIERS:
        if sal >= threshold:
            return fraction
    return 0.0


class RelevanceEngine:
    def __init__(self, resume_text: str | None = None):
        self.core = [s.lower() for s in PROFILE["core_skills"]]
        self.secondary = [s.lower() for s in PROFILE["secondary_skills"]]
        self.locations = [s.lower() for s in PROFILE["preferred_locations"]]
        self.exp_kw = [s.lower() for s in PROFILE["experience_keywords"]]
        self.needs_sponsor = PROFILE.get("needs_sponsorship", False)

        # When a resume is supplied, pre-tokenize once. Each scored job then
        # runs a 2-doc TF-IDF + cosine against this cached token list to
        # refine the core component (see score()).
        self._resume_tokens: list[str] | None = None
        if resume_text:
            try:
                from storage.resume_vault import _tokenize
                self._resume_tokens = _tokenize(resume_text)
            except Exception as e:
                log.warning("TF-IDF booster disabled — resume tokenize failed: %s", e)

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

        Component weights (sum = 1.00):
          - Core skill matches:     36%   (modulated by TF-IDF if resume loaded)
          - Secondary skill matches: 17%
          - Title relevance:        15%
          - Location preference:    10%
          - Experience level match: 10%
          - Sponsorship signal:      8%   (issue #11)
          - Salary tier:             4%   (issue #10)

        Plus an additive +8% boost for jobs at Platinum-tier companies
        (capped at 1.0). When the engine is constructed with resume text,
        the core component is multiplied by a TF-IDF cosine factor in
        [0.85, 1.0] (issue #7) — a contextual quality check on top of
        the keyword-only core match.
        """
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        location = (job.get("location") or "").lower()
        text = f"{title} {desc}"

        matched_skills = []
        score = 0.0

        # ── Core skills (36%) ──
        core_weight = CORE_WEIGHT / max(len(self.core), 1)
        core_hits = 0
        for skill in self.core:
            if _skill_match(skill, text):
                core_hits += 1
                matched_skills.append(skill)
        core_component = core_hits * core_weight

        # TF-IDF resume refinement: only meaningful when both the resume and
        # a non-trivial job description are present.
        if self._resume_tokens and desc:
            core_component *= _tfidf_factor(self._resume_tokens, text)

        score += core_component

        # ── Secondary skills (17%) ──
        sec_weight = SECONDARY_WEIGHT / max(len(self.secondary), 1)
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
            score += LOCATION_WEIGHT
        elif job.get("is_remote"):
            score += LOCATION_WEIGHT  # Remote is always a match

        # ── Experience level (10%) ──
        if any(kw in text for kw in self.exp_kw):
            score += EXPERIENCE_WEIGHT

        # ── Sponsorship (8%) — symmetric reward / penalty per issue #11 ──
        if self.needs_sponsor:
            if _detects_sponsorship(text):
                score += SPONSORSHIP_WEIGHT
            elif _detects_no_sponsorship(text):
                score -= SPONSORSHIP_WEIGHT

        # ── Salary tier (4%) — issue #10 ──
        score += salary_score(job) * SALARY_WEIGHT

        # Clamp to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        # ── Platinum company boost (+8% additive) ──
        if job.get("tier") == "platinum":
            score = min(1.0, score + PLATINUM_BOOST)

        # Deduplicate while preserving insertion order (a skill could appear in both
        # core and secondary lists if profile.py was misconfigured)
        return round(score, 4), list(dict.fromkeys(matched_skills))


def _tfidf_factor(resume_tokens: list[str], job_text: str) -> float:
    """
    Cosine similarity between a cached resume token list and a fresh job
    description, mapped into the [TFIDF_MIN_FACTOR, TFIDF_MAX_FACTOR] band.
    Falls back to TFIDF_MAX_FACTOR (no-op) if the TF-IDF helpers can't be
    imported, so scoring never breaks on a vault import error.
    """
    try:
        from storage.resume_vault import _tokenize, _build_tfidf, _cosine_sim
    except Exception:
        return TFIDF_MAX_FACTOR

    job_tokens = _tokenize(job_text)
    if not job_tokens:
        return TFIDF_MAX_FACTOR
    vecs = _build_tfidf([resume_tokens, job_tokens])
    sim = _cosine_sim(vecs[0], vecs[1])
    return TFIDF_MIN_FACTOR + (TFIDF_MAX_FACTOR - TFIDF_MIN_FACTOR) * sim


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
