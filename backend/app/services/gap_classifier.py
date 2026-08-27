"""Deterministic skill-gap classification shared by mock mode and validation."""

from __future__ import annotations

from app.schemas.analysis import (
    Importance,
    SkillClassification,
    SkillGapAnalysis,
    SkillGapItem,
    SkillStatus,
)
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.matching import find_match, find_partial, normalize_skill, skills_equal


def classify_skill_gaps(
    candidate: CandidateProfile, job: JobProfile
) -> SkillGapAnalysis:
    """Classify every job requirement against the candidate's actual skills.

    - MATCHED: exact or synonym match with a resume-derived skill.
    - PARTIAL: meaningful token overlap (related but not equivalent).
    - MISSING: no evidence anywhere in the resume.
    Importance: HIGH for required skills, MEDIUM for everything else.
    """
    candidate_skills = candidate.all_skills()
    project_techs = candidate.project_technologies()

    seen: set[str] = set()
    matched: list[str] = []
    partial: list[str] = []
    missing: list[str] = []
    items: list[SkillGapItem] = []

    requirements = job.all_requirements() + job.soft_skills
    for requirement in requirements:
        key = requirement.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        importance = (
            Importance.HIGH
            if any(skills_equal(requirement, r) for r in job.required_skills)
            else Importance.MEDIUM
        )

        if find_match(requirement, candidate_skills):
            matched.append(requirement)
            items.append(SkillGapItem(skill=requirement, status=SkillStatus.MATCHED,
                                      importance=importance))
            continue

        related = find_partial(requirement, candidate_skills) or find_partial(requirement, project_techs)
        if related:
            partial.append(requirement)
            items.append(
                SkillGapItem(
                    skill=requirement,
                    status=SkillStatus.PARTIAL,
                    importance=importance,
                    reason=f"Related skill '{related}' found on the resume, but '{requirement}' itself is not evidenced.",
                    recommended_action=f"Strengthen {requirement}: map existing {related} experience to it and build a concrete example.",
                )
            )
        else:
            missing.append(requirement)
            items.append(
                SkillGapItem(
                    skill=requirement,
                    status=SkillStatus.MISSING,
                    importance=importance,
                    reason=(
                        f"'{requirement}' is listed as a required skill in the target job "
                        if importance == Importance.HIGH
                        else f"'{requirement}' is a preferred skill in the target job"
                    ) + " and does not appear anywhere in the resume.",
                    recommended_action=(
                        f"Learn {requirement} fundamentals and complete a hands-on project using it."
                        if importance == Importance.HIGH
                        else f"Get familiar with {requirement} through tutorials and a small demo."
                    ),
                )
            )

    return SkillGapAnalysis(matched=matched, partial=partial, missing=missing, gaps=items)


def validate_llm_classification(
    classification: SkillClassification,
    candidate: CandidateProfile,
    job: JobProfile,
) -> SkillGapAnalysis:
    """Guard an LLM-produced classification against hallucination.

    Every classified item must reference either a real candidate skill or a real
    job requirement (normalized comparison); anything else is dropped. Items the
    LLM marked MATCHED must survive exact/synonym verification against the
    candidate's own skills.
    """
    candidate_skills = candidate.all_skills()
    allowed_norm = {
        normalize_skill(s)
        for s in candidate_skills + job.all_requirements() + job.soft_skills
        if s.strip()
    }

    def _known(value: str) -> bool:
        return normalize_skill(value) in allowed_norm

    matched, partial, missing, items = [], [], [], []
    for item in classification.items:
        if not item.skill.strip() or not _known(item.skill):
            continue
        if item.status == SkillStatus.MATCHED and not find_match(item.skill, candidate_skills):
            item = item.model_copy(update={"status": SkillStatus.PARTIAL})
        {"matched": matched, "partial": partial, "missing": missing}[
            item.status.value
        ].append(item.skill)
        items.append(item)

    return SkillGapAnalysis(matched=matched, partial=partial, missing=missing, gaps=items)
