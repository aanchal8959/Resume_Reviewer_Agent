"""Skill Gap Agent: candidate profile vs job profile -> classified gaps.

The LLM proposes a classification, but every item is re-verified against the
actual structured profiles; hallucinated skills are dropped and unclassified
requirements fall back to deterministic classification.
"""

from __future__ import annotations

from app.agents.base import AgentError, format_model
from app.schemas.analysis import SkillClassification, SkillGapAnalysis
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.gap_classifier import classify_skill_gaps, validate_llm_classification
from app.services.llm_service import LLMError, LLMProvider
from app.services.matching import normalize_skill

_SYSTEM_PROMPT = (
    "You are a skill-gap analyst. You compare a candidate's verified skills with "
    "a job's requirements and classify every requirement as matched, partial or "
    "missing.\n"
    "RULES:\n"
    "1. 'matched' ONLY if the resume clearly evidences that exact skill (or an "
    "obvious synonym).\n"
    "2. 'partial' when the candidate has a closely related skill but not the "
    "requirement itself.\n"
    "3. 'missing' when there is no evidence in the resume.\n"
    "4. Never introduce skills that are absent from both inputs.\n"
    "5. Importance: high for required skills, medium otherwise.\n"
    "6. For every non-matched skill give a reason and one concrete recommended_action."
)


def build_user_prompt(candidate: CandidateProfile, job: JobProfile) -> str:
    return (
        "Compare this candidate against the target job requirements.\n\n"
        f"<candidate_profile>\n{format_model(candidate)}\n</candidate_profile>\n\n"
        f"<job_profile>\n{format_model(job)}\n</job_profile>"
    )


class SkillGapAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def run(self, candidate: CandidateProfile, job: JobProfile) -> SkillGapAnalysis:
        try:
            classification = self._provider.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=build_user_prompt(candidate, job),
                response_model=SkillClassification,
                context={"candidate_profile": candidate, "job_profile": job},
            )
            analysis = validate_llm_classification(classification, candidate, job)
        except LLMError as exc:
            raise AgentError(f"Skill gap analysis failed: {exc}") from exc
        return self._fill_uncovered_requirements(analysis, candidate, job)

    @staticmethod
    def _fill_uncovered_requirements(
        analysis: SkillGapAnalysis, candidate: CandidateProfile, job: JobProfile
    ) -> SkillGapAnalysis:
        """Ensure every requirement appears exactly once in the final output."""
        covered = {normalize_skill(item.skill) for item in analysis.gaps}
        fallback = classify_skill_gaps(candidate, job)
        extra = [
            item
            for item in fallback.gaps
            if normalize_skill(item.skill) not in covered
        ]
        if not extra:
            return analysis
        gaps = list(analysis.gaps) + extra
        by_status: dict[str, list[str]] = {
            "matched": list(analysis.matched),
            "partial": list(analysis.partial),
            "missing": list(analysis.missing),
        }
        for item in extra:
            by_status[item.status.value].append(item.skill)
        return SkillGapAnalysis(
            matched=by_status["matched"],
            partial=by_status["partial"],
            missing=by_status["missing"],
            gaps=gaps,
        )
