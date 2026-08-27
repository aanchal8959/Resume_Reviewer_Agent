"""Job Normalization: raw source records -> validated `Job` models.

Deterministic regex/heuristic extraction first (skills, experience, salary,
work mode, employment type). The LLM is only consulted when the configured
provider can actually help (not mock mode) AND required fields are missing.
"""

from __future__ import annotations

import re

from app.config import get_settings
from app.schemas.jobs import RawJob, WorkMode
from app.services.llm_service import LLMError, LLMProvider
from app.services.skill_vocabulary import find_known_skills
from app.services.skill_normalizer import SkillNormalizer

_EXP_YEARS = r"(?:years?|yrs?\.?)"
_EXP_RANGE_RE = re.compile(
    rf"(\d+(?:\.\d+)?)\s*(?:to|–|—|-)\s*(\d+(?:\.\d+)?)\s*\+?\s*{_EXP_YEARS}",
    re.IGNORECASE,
)
_EXP_MIN_PLUS_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*\+\s*{_EXP_YEARS}", re.IGNORECASE)
_EXP_MIN_WORDS_RE = re.compile(
    rf"(?:minimum|min\.?|at least|over)\s+(\d+(?:\.\d+)?)\s*\+?\s*{_EXP_YEARS}",
    re.IGNORECASE,
)
_FRESHER_RE = re.compile(r"\b(?:fresher|entry[- ]level|graduate)\b", re.IGNORECASE)

_SALARY_LPA_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:-|–|to)\s*(?:₹|rs\.?|inr)?\s*"
    r"(\d{1,3}(?:\.\d+)?)\s*l(?:pa|akhs?)?\b",
    re.IGNORECASE,
)
_SALARY_LPA_SINGLE_RE = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d{1,2}(?:\.\d+)?)\s*lpa\b", re.IGNORECASE)

_WORK_MODE_PATTERNS: tuple[tuple[WorkMode, re.Pattern[str]], ...] = (
    ("remote", re.compile(r"\b(?:remote|work from home|wfh)\b", re.IGNORECASE)),
    ("hybrid", re.compile(r"\bhybrid\b", re.IGNORECASE)),
    ("onsite", re.compile(r"\b(?:on[- ]?site|in[- ]office|work from office)\b", re.IGNORECASE)),
)

_EMPLOYMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internship", re.compile(r"\binternship\b|\bintern\b", re.IGNORECASE)),
    ("contract", re.compile(r"\bcontract(or)?\b|\bc2h\b", re.IGNORECASE)),
    ("part-time", re.compile(r"\bpart[- ]time\b", re.IGNORECASE)),
    ("full-time", re.compile(r"\bfull[- ]time\b", re.IGNORECASE)),
)


def extract_experience(text: str) -> tuple[float | None, float | None]:
    range_match = _EXP_RANGE_RE.search(text)
    if range_match:
        low, high = float(range_match.group(1)), float(range_match.group(2))
        return (min(low, high), max(low, high))
    for pattern in (_EXP_MIN_PLUS_RE, _EXP_MIN_WORDS_RE):
        match = pattern.search(text)
        if match:
            value = float(match.group(1))
            return (value, None)
    if _FRESHER_RE.search(text):
        return (0.0, None)
    return (None, None)


def extract_salary_lpa(text: str) -> tuple[float | None, float | None]:
    match = _SALARY_LPA_RE.search(text)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return (min(low, high), max(low, high))
    match = _SALARY_LPA_SINGLE_RE.search(text)
    if match:
        value = float(match.group(1))
        return (value, value)
    return (None, None)


def extract_work_mode(text: str) -> WorkMode:
    title_and_body = text
    for mode, pattern in _WORK_MODE_PATTERNS:
        if pattern.search(title_and_body):
            return mode
    return "unknown"


def extract_employment_type(text: str) -> str | None:
    for label, pattern in _EMPLOYMENT_PATTERNS:
        if pattern.search(text):
            return label
    return None


class JobNormalizer:
    """Converts heterogeneous raw jobs into the canonical Job schema."""

    def __init__(self, provider: LLMProvider, skill_normalizer: SkillNormalizer) -> None:
        self._provider = provider
        self._skills = skill_normalizer

    def normalize(self, raw: RawJob) -> "Job":
        from app.schemas.jobs import Job

        text = "\n".join(part for part in (raw.title, raw.description) if part)
        exp_min, exp_max = extract_experience(text)
        salary_min, salary_max = extract_salary_lpa(text)
        work_mode = raw.work_mode or extract_work_mode(text)
        employment_type = raw.employment_type or extract_employment_type(text)

        known = find_known_skills(text)
        required, preferred = self._split_required(raw, known, text)
        preferred = [
            skill for skill in self._skills.normalize_list(preferred)
            if skill not in required
        ]

        job = Job(
            id=None,
            source=raw.source,
            source_job_id=raw.source_job_id,
            title=raw.title.strip(),
            company=raw.company.strip(),
            description=(raw.description or "").strip(),
            location=(raw.location or None),
            work_mode=work_mode,
            employment_type=employment_type,
            experience_min=exp_min,
            experience_max=exp_max,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="INR" if salary_min is not None else None,
            required_skills=required,
            preferred_skills=preferred,
            posted_at=raw.posted_at,
            application_url=raw.url,
        )
        if self._needs_llm_assist(job):
            job = self._llm_assist(job, raw)
        return job

    # -- internals -----------------------------------------------------------
    @staticmethod
    def _split_required(raw: RawJob, known: list[str], text: str) -> tuple[list[str], list[str]]:
        """Skills before a preferred-skills marker are required; after it, preferred."""
        del raw
        lowered = text.lower()
        boundary = len(text)
        for marker in ("nice to have", "preferred", "bonus points", "good to have"):
            position = lowered.find(marker)
            if position != -1:
                boundary = min(boundary, position)

        required: list[str] = []
        preferred: list[str] = []
        for skill in dict.fromkeys(known):
            position = lowered.find(skill.lower())
            if position == -1:
                continue
            target = required if position < boundary else preferred
            target.append(skill)
        if not required:
            required = list(preferred)
            preferred = []
        return required, preferred

    def _needs_llm_assist(self, job: "Job") -> bool:
        return (
            self._provider.name != "mock"
            and (not job.required_skills or job.experience_min is None)
        )

    def _llm_assist(self, job: "Job", raw: RawJob) -> "Job":
        from app.agents.job_agent import build_user_prompt
        from app.schemas.job import JobProfile

        try:
            profile = self._provider.generate_structured(
                system_prompt=(
                    "You are a precise technical recruiter extracting structured "
                    "requirements from job descriptions. Never invent skills."
                ),
                user_prompt=build_user_prompt(raw.description),
                response_model=JobProfile,
                context={"job_description_text": raw.description},
            )
        except LLMError:
            return job
        updates: dict = {}
        if not job.required_skills and profile.required_skills:
            updates["required_skills"] = self._skills.normalize_list(profile.required_skills)
        if not job.preferred_skills and profile.preferred_skills:
            updates["preferred_skills"] = self._skills.normalize_list(profile.preferred_skills)
        if job.experience_min is None and profile.required_experience_years is not None:
            updates["experience_min"] = profile.required_experience_years
        if not updates:
            return job
        return job.model_copy(update=updates)


__all__ = [
    "JobNormalizer",
    "extract_employment_type",
    "extract_experience",
    "extract_salary_lpa",
    "extract_work_mode",
]

