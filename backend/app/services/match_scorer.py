"""Transparent, deterministic match-score calculation (never LLM-generated)."""

from __future__ import annotations

from app.schemas.analysis import MatchScore, ScoreBreakdown
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.matching import find_match, find_partial, normalize_skill, tokenize

DEFAULT_WEIGHTS: dict[str, float] = {
    "required_skills": 0.50,
    "preferred_skills": 0.20,
    "experience": 0.15,
    "project_relevance": 0.10,
    "education": 0.05,
}


def _ratio(hit: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return hit / total


def _required_skills_score(candidate_skills: list[str], job: JobProfile) -> float:
    required = job.required_skills or (
        job.programming_languages + job.frameworks + job.ai_ml_technologies
        if not job.preferred_skills
        else []
    )
    if not required:
        return 1.0
    hits = sum(1 for skill in required if find_match(skill, candidate_skills))
    return _ratio(hits, len(required))


def _preferred_skills_score(candidate_skills: list[str], job: JobProfile) -> float:
    if not job.preferred_skills:
        return 1.0
    hits = sum(1 for skill in job.preferred_skills if find_match(skill, candidate_skills))
    return _ratio(hits, len(job.preferred_skills))


def _experience_score(candidate_years: float | None, job_years: float | None) -> float:
    """No requirement stated -> nothing to miss (full credit).

    Requirement known but candidate years unknown -> conservative partial credit.
    """
    if job_years is None:
        return 1.0
    if candidate_years is None:
        return 0.5
    return min(candidate_years / job_years, 1.0)


def _project_relevance_score(candidate: CandidateProfile, job: JobProfile) -> float:
    """Coverage of the job's technical focus areas by the candidate's evidence
    pool (declared skills + project technologies)."""
    evidence = candidate.all_skills() + candidate.project_technologies()
    focus_areas = {
        normalize_skill(s)
        for s in (
            job.required_skills
            + job.frameworks
            + job.cloud_technologies
            + job.ai_ml_technologies
        )
        if s.strip()
    }
    if not focus_areas:
        return 1.0
    if not evidence:
        return 0.0
    relevant = sum(
        1
        for area in focus_areas
        if find_match(area, evidence) or find_partial(area, evidence)
    )
    return _ratio(relevant, len(focus_areas))


_GENERIC_EDU_TOKENS = {"degree", "bachelor", "bachelors", "master", "masters", "phd",
                       "engineering", "certification", "certified"}


def _education_score(candidate: CandidateProfile, job: JobProfile) -> float:
    """Generic degree-level requirements are satisfied by any listed education;
    specific requirements need meaningful word overlap."""
    requirements = [r for r in (job.education_requirements + job.certifications) if r.strip()]
    owned_items = [e.lower() for e in candidate.education_text() if e.strip()]
    if not requirements:
        return 1.0
    if not owned_items:
        return 0.0

    def satisfied(req: str) -> bool:
        req_tokens = tokenize(req)
        if not req_tokens:
            return False
        if req_tokens & _GENERIC_EDU_TOKENS:
            return True
        for item in owned_items:
            item_tokens = tokenize(item)
            overlap = req_tokens & item_tokens
            if overlap and len(overlap) >= max(1, len(req_tokens) // 2):
                return True
        return False

    hits = sum(1 for req in requirements if satisfied(req))
    return _ratio(hits, len(requirements))


def compute_match_score(
    candidate: CandidateProfile,
    job: JobProfile,
    weights: dict[str, float] | None = None,
) -> MatchScore:
    """Weighted breakdown; every component is a plain ratio in [0, 100]."""
    weights = weights or DEFAULT_WEIGHTS
    candidate_skills = candidate.all_skills()

    breakdown = ScoreBreakdown(
        required_skills=round(_required_skills_score(candidate_skills, job) * 100, 1),
        preferred_skills=round(_preferred_skills_score(candidate_skills, job) * 100, 1),
        experience=round(_experience_score(candidate.total_experience_years,
                                           job.required_experience_years) * 100, 1),
        project_relevance=round(_project_relevance_score(candidate, job) * 100, 1),
        education=round(_education_score(candidate, job) * 100, 1),
    )

    overall = (
        breakdown.required_skills * weights["required_skills"]
        + breakdown.preferred_skills * weights["preferred_skills"]
        + breakdown.experience * weights["experience"]
        + breakdown.project_relevance * weights["project_relevance"]
        + breakdown.education * weights["education"]
    )
    return MatchScore(
        overall_score=round(overall, 1),
        breakdown=breakdown,
        weights_used=dict(weights),
    )
