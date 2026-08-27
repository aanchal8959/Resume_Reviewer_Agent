"""Cover letter + application questions agent tests (stubbed Gemini)."""

from tests.fakes import StubGeminiProvider
from app.agents.copilot_agents import (
    ApplicationQuestionsAgent,
    CoverLetterAgent,
)
from app.schemas.candidate import CandidateProfile


def _candidate() -> CandidateProfile:
    return CandidateProfile.model_validate({
        "name": "John Doe", "total_experience_years": 2,
        "current_role": "AI Engineer",
        "technical_skills": ["Python", "RAG", "FastAPI"],
        "projects": [{"name": "Enterprise RAG System",
                      "technologies": ["Python", "FAISS"]}],
    })


def test_cover_letter_contains_job_and_candidate_context():
    draft = CoverLetterAgent(StubGeminiProvider()).generate(
        candidate=_candidate(), job_title="GenAI Engineer",
        company="Acme AI Technologies",
        matched_skills=["Python", "RAG"],
    )
    assert "GenAI Engineer" in draft.content_text
    assert "Acme AI Technologies" in draft.content_text
    assert "Dear Hiring Team" in draft.content_text
    assert draft.word_count == len(draft.content_text.split())
    assert draft.word_count > 0


def test_questions_cover_behavioral_technical_practical():
    items = ApplicationQuestionsAgent(StubGeminiProvider()).generate(
        candidate=_candidate(), job_title="GenAI Engineer",
        required_skills=["Python", "RAG", "GCP"],
        missing_skills=["Kubernetes"],
        salary_text="22-32 LPA",
    )
    categories = {item.category for item in items}
    assert {"behavioral", "technical", "practical"} <= categories
