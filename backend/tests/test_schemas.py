"""Schema validation tests: malformed LLM output must never pass silently."""

import pytest
from pydantic import ValidationError

from app.schemas.analysis import SkillClassification, SkillGapAnalysis, SkillGapItem, SkillStatus
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile


def test_candidate_rejects_wrong_types():
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"total_experience_years": "three years"})


def test_candidate_rejects_non_list_skills():
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"technical_skills": "Python"})


def test_candidate_ignores_extra_fields():
    profile = CandidateProfile.model_validate(
        {"name": "John Doe", "hallucinated_field": 42}
    )
    assert profile.name == "John Doe"
    assert not hasattr(profile, "hallucinated_field")


def test_candidate_defaults_are_empty_not_invented():
    profile = CandidateProfile()
    assert profile.name is None
    assert profile.total_experience_years is None
    assert profile.technical_skills == []


def test_job_profile_required_preferred_distinct():
    job = JobProfile(
        required_skills=["Python"], preferred_skills=["Kubernetes"]
    )
    assert set(job.required_skills).isdisjoint(job.preferred_skills)


def test_duplicate_gap_entries_rejected():
    gap = SkillGapItem(skill="Kubernetes", status=SkillStatus.MISSING)
    with pytest.raises(ValidationError):
        SkillGapAnalysis(gaps=[gap, gap])


def test_skill_classification_accepts_llm_shape():
    classification = SkillClassification.model_validate(
        {
            "items": [
                {"skill": "Python", "status": "matched"},
                {"skill": "MLOps", "status": "missing", "importance": "high",
                 "reason": "required", "recommended_action": "learn it"},
            ]
        }
    )
    assert len(classification.items) == 2


def test_invalid_status_string_rejected():
    with pytest.raises(ValidationError):
        SkillGapItem(skill="X", status="maybe")
