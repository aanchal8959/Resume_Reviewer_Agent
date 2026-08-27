"""Resume tailoring tests (stubbed Gemini + truthfulness integration)."""

import pytest

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.llm_service import LLMResponseError
from app.services.resume_tailor import ResumeTailoringService
from app.services.skill_normalizer import SkillNormalizer
from app.services.truthfulness import ResumeTruthfulnessValidator

ORIGINAL_RESUME = """John Doe
john@example.com

SUMMARY
AI Engineer with 2 years of experience.

EXPERIENCE
- Worked on a RAG chatbot using Python and FAISS
- Helped with FastAPI service development

EDUCATION
B.Tech Computer Science, 2021

SKILLS
Python, FastAPI, RAG, FAISS

PROJECTS
Enterprise RAG System: internal document search
Technologies: Python, FAISS, FastAPI
"""

JOB = JobProfile(
    role="GenAI Engineer",
    required_skills=["Python", "RAG", "LLM", "GCP"],
    preferred_skills=["Kubernetes"],
)


class _StubTailor:
    """Returns a fixed tailored resume including one unsupported claim."""

    name = "gemini-stub"
    output = {
        "content_markdown": (
            "# John Doe\n\n## Summary\nAligned with GenAI Engineer.\n\n"
            "## Experience\n- Developed a retrieval augmented generation "
            "chatbot using Python and FAISS for enterprise document search\n"
            "- Built production Kubernetes clusters across three regions\n"
        ),
        "changes": [
            {"section": "Experience",
             "original": "Worked on a RAG chatbot using Python and FAISS",
             "updated": "Developed a retrieval augmented generation chatbot "
                        "using Python and FAISS for enterprise document search",
             "reason": "clarity + keyword alignment", "type": "clarity"},
            {"section": "Experience",
             "original": "Helped with FastAPI service development",
             "updated": "Built production Kubernetes clusters across regions",
             "reason": "alignment attempt", "type": "relevance"},
        ],
        "summary": "Stub tailored resume.",
        "recommendations": [],
    }

    def generate_structured(self, *args, **kwargs):
        from app.schemas.applications import TailoredResume

        return TailoredResume.model_validate(self.output)


def _tailor_with(provider):
    candidate = CandidateProfile.model_validate({
        "name": "John Doe", "total_experience_years": 2,
        "current_role": "AI Engineer",
        "technical_skills": ["Python", "FastAPI", "RAG", "FAISS"],
        "projects": [{"name": "Enterprise RAG System",
                      "technologies": ["Python", "FAISS", "FastAPI"]}],
    })
    return ResumeTailoringService(provider, SkillNormalizer()).tailor(
        ORIGINAL_RESUME, candidate, JOB
    )


def test_unsupported_claim_is_flagged_not_hidden():
    tailored = _tailor_with(_StubTailor())
    assert tailored.unsupported_claims_count >= 1
    flagged = [c for c in tailored.changes if not c.supported]
    assert flagged, "the Kubernetes claim must be flagged"
    assert any("not be supported" in (c.warning or "") for c in flagged)
    # The supported rephrase passes.
    clean = [c for c in tailored.changes if c.supported]
    assert clean and all(c.warning is None for c in clean)


def test_changes_log_original_and_updated():
    tailored = _tailor_with(_StubTailor())
    for change in tailored.changes:
        assert change.section == "Experience"
        assert change.original and change.updated


def test_llm_failure_raises_agent_error():
    class Broken:
        name = "gemini"

        def generate_structured(self, *args, **kwargs):
            raise LLMResponseError("Gemini request failed with 429: quota")

    with pytest.raises(Exception) as exc_info:
        _tailor_with(Broken())
    assert "Resume tailoring failed" in str(exc_info.value)


def test_master_resume_untouched():
    tailored = _tailor_with(_StubTailor())
    assert ORIGINAL_RESUME.startswith("John Doe")
    assert "B.Tech Computer Science" in ORIGINAL_RESUME
