"""Skill matching + gap classification tests (spec example included)."""

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.gap_classifier import classify_skill_gaps, validate_llm_classification
from app.services.matching import skills_equal
from app.schemas.analysis import SkillClassification, SkillGapItem, SkillStatus


def _candidate(skills: list[str]) -> CandidateProfile:
    return CandidateProfile(technical_skills=skills)


def _job(required: list[str], preferred: list[str] | None = None) -> JobProfile:
    return JobProfile(required_skills=required, preferred_skills=preferred or [])


def test_spec_example_matched_and_missing():
    candidate = _candidate(["Python", "GCP", "RAG"])
    job = _job(["Python", "GCP", "RAG", "Kubernetes"])
    analysis = classify_skill_gaps(candidate, job)

    assert sorted(s.lower() for s in analysis.matched) == ["gcp", "python", "rag"]
    assert [s.lower() for s in analysis.missing] == ["kubernetes"]


def test_synonym_match_k8s_kubernetes():
    assert skills_equal("Kubernetes", "k8s")
    assert skills_equal("LLM", "Large Language Model")
    assert not skills_equal("Python", "Java")


def test_partial_detection_related_skill():
    candidate = _candidate(["Docker"])
    job = _job(["Kubernetes"])
    analysis = classify_skill_gaps(candidate, job)
    assert analysis.partial == ["Kubernetes"]
    assert analysis.matched == []
    gap_item = analysis.gaps[0]
    assert "Docker" in (gap_item.reason or "")


def test_required_gaps_are_high_importance():
    candidate = _candidate([])
    job = _job(["Terraform"], preferred=["MLOps"])
    analysis = classify_skill_gaps(candidate, job)
    by_skill = {item.skill: item for item in analysis.gaps}
    assert by_skill["Terraform"].importance.value == "high"
    assert by_skill["MLOps"].importance.value == "medium"


def test_no_hallucinated_skills_in_output():
    candidate = _candidate(["Python"])
    job = _job(["Python"])
    classification = SkillClassification(
        items=[
            SkillGapItem(skill="Quantum Computing", status=SkillStatus.MISSING),
            SkillGapItem(skill="Python", status=SkillStatus.MATCHED),
        ]
    )
    analysis = validate_llm_classification(classification, candidate, job)
    assert all(item.skill != "Quantum Computing" for item in analysis.gaps)


def test_llm_cannot_claim_unsupported_matched_skill():
    candidate = _candidate(["Docker"])
    job = _job(["Kubernetes"])
    classification = SkillClassification(
        items=[SkillGapItem(skill="Kubernetes", status=SkillStatus.MATCHED)]
    )
    analysis = validate_llm_classification(classification, candidate, job)
    k8s_item = next(item for item in analysis.gaps if item.skill == "Kubernetes")
    assert k8s_item.status == SkillStatus.PARTIAL
