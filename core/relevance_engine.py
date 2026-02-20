"""
Job Relevance Engine.
Scores job listings against the user profile using weighted
multi-signal matching across title, skills, location, company, and salary.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from config.profile import UserProfile

logger = logging.getLogger(__name__)


@dataclass
class RelevanceResult:
    total_score: float
    title_score: float
    skills_score: float
    location_score: float
    company_score: float
    salary_score: float
    remote_bonus: float
    exclusion_penalty: float
    matched_skills: list[str]
    matched_title: Optional[str]
    signals: list[str] = field(default_factory=list)


class RelevanceEngine:
    """
    Scores jobs against a candidate profile.

    Weights (sum to 1.0):
        Title:    0.30 | Skills:   0.35 | Location: 0.15
        Company:  0.10 | Salary:   0.10
    """

    WEIGHTS = {"title": 0.30, "skills": 0.35, "location": 0.15, "company": 0.10, "salary": 0.10}

    def __init__(self, profile: Optional[UserProfile] = None):
        self.profile = profile or UserProfile()
        self._skill_patterns: dict[str, re.Pattern] = {}
        for skill in self.profile.skills:
            self._skill_patterns[skill] = re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE)

    def score(self, job: dict) -> RelevanceResult:
        title = (job.get("title") or "").lower().strip()
        description = (job.get("description") or "").lower()
        location = (job.get("location") or "").lower()
        company = (job.get("company") or "").lower()
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        is_remote = job.get("is_remote", False)
        full_text = f"{title} {description}"
        signals = []

        # 1. Title Match
        title_score, matched_title = 0.0, None
        for target, weight in self.profile.target_titles.items():
            if self._fuzzy_title_match(title, target) and weight > title_score:
                title_score, matched_title = weight, target
        if matched_title:
            signals.append(f"title:{matched_title}")

        # 2. Skills Match
        matched_skills, skills_weighted = [], 0.0
        max_possible = sum(self.profile.skills.values())
        for skill, prof in self.profile.skills.items():
            if self._skill_patterns[skill].search(full_text):
                matched_skills.append(skill)
                skills_weighted += prof
        skills_score = min(skills_weighted / (max_possible * 0.3), 1.0)

        # 3. Location
        location_score = 0.0
        if is_remote:
            location_score = self.profile.remote_preference
        else:
            for pref in self.profile.preferred_locations:
                if pref in location:
                    location_score = 0.85 if pref in ("dallas","dfw","plano","irving","frisco","richardson") else 0.65
                    break

        # 4. Company
        company_score = 0.3
        for target in self.profile.target_companies:
            if target in company:
                company_score = 1.0
                signals.append(f"company:{target}")
                break

        # 5. Salary
        salary_score = 0.5
        if salary_max and salary_max > 0:
            if salary_max >= self.profile.min_salary_usd:
                salary_score = min(0.7 + (salary_max / self.profile.min_salary_usd - 1.0) * 0.3, 1.0)
            else:
                salary_score = max(salary_max / self.profile.min_salary_usd * 0.5, 0.0)

        # 6. Bonuses & Penalties
        remote_bonus = 0.05 if is_remote else 0.0
        exclusion_penalty = 0.0
        for kw in self.profile.exclude_keywords:
            if kw in full_text:
                exclusion_penalty = 0.8
                signals.append(f"excluded:{kw}")
                break

        weighted = (
            title_score * self.WEIGHTS["title"] + skills_score * self.WEIGHTS["skills"]
            + location_score * self.WEIGHTS["location"] + company_score * self.WEIGHTS["company"]
            + salary_score * self.WEIGHTS["salary"]
        )
        total = max(0.0, min((weighted + remote_bonus) * (1.0 - exclusion_penalty), 1.0))

        return RelevanceResult(
            total_score=round(total, 4), title_score=round(title_score, 4),
            skills_score=round(skills_score, 4), location_score=round(location_score, 4),
            company_score=round(company_score, 4), salary_score=round(salary_score, 4),
            remote_bonus=round(remote_bonus, 4), exclusion_penalty=round(exclusion_penalty, 4),
            matched_skills=matched_skills, matched_title=matched_title, signals=signals,
        )

    def _fuzzy_title_match(self, actual: str, target: str) -> bool:
        norms = {"sr.": "senior", "sr ": "senior ", "jr.": "junior", "ml ": "machine learning ", "engg": "engineer"}
        normalized = actual
        for abbr, full in norms.items():
            normalized = normalized.replace(abbr, full)
        target_words = set(target.split())
        actual_words = set(normalized.split())
        if target_words.issubset(actual_words):
            return True
        overlap = len(target_words & actual_words)
        return len(target_words) > 0 and overlap / len(target_words) >= 0.7

    def enrich_job(self, job: dict) -> dict:
        result = self.score(job)
        job["relevance_score"] = result.total_score
        job["matched_skills"] = result.matched_skills
        job["matched_title"] = result.matched_title
        return job
