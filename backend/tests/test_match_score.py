"""Deterministic match-score tests."""

from app.schemas.candidate import CandidateProfile, EducationEntry, Project
from app.schemas.job import JobProfile
from app.services.match_scorer import compute_match_score


def _job() -> JobProfile:
    return JobProfile(
        role="GenAI Engineer",
        required_experience_years=2,
        required_skills=["Python", "RAG", "LLM", "GCP"],
        preferred_skills=["Kubernetes", "LangGraph"],
    )


def test_perfect_candidate_scores_100():
    candidate = CandidateProfile(
        name="Jane",
        total_experience_years=4,
        technical_skills=["Python", "RAG", "LLM", "GCP", "Kubernetes", "LangGraph"],
        ai_ml_skills=["RAG", "LLM"],
        cloud_platforms=["GCP"],
        projects=[Project(name="GenAI platform",
                          technologies=["Python", "LangGraph", "Vertex AI"])],
        education=[EducationEntry(degree="B.Tech Computer Science")],
    )
    job = _job()
    job.education_requirements = ["Bachelor"]
    score = compute_match_score(candidate, job)
    assert score.overall_score == 100.0
    assert score.breakdown.required_skills == 100.0
    assert score.breakdown.preferred_skills == 100.0
    assert score.breakdown.experience == 100.0
    assert score.breakdown.project_relevance == 100.0
    assert score.breakdown.education == 100.0


def test_deterministic_scoring_known_case():
    candidate = CandidateProfile(
        total_experience_years=2,
        technical_skills=["Python", "RAG"],
        education=[EducationEntry(degree="B.Tech Computer Science")],
    )
    job = _job()
    first = compute_match_score(candidate, job)
    second = compute_match_score(candidate, job)
    assert first.model_dump() == second.model_dump()

    # required: Python+RAG matched of 4 -> 50; preferred: none of 2 -> 0;
    # experience: 2/2 -> 100; focus coverage: Python,RAG of 4 areas -> 50;
    # education: no requirement -> 100.
    expected_overall = (
        50 * 0.5 + 0 * 0.2 + 100 * 0.15 + 50 * 0.10 + 100 * 0.05
    )
    assert first.breakdown.required_skills == 50.0
    assert first.breakdown.preferred_skills == 0.0
    assert first.breakdown.experience == 100.0
    assert first.breakdown.project_relevance == 50.0
    assert first.breakdown.education == 100.0
    assert abs(first.overall_score - expected_overall) < 0.01


def test_experience_under_requirement_partial_credit():
    candidate = CandidateProfile(total_experience_years=1, technical_skills=["Python"])
    job = JobProfile(required_experience_years=3)
    score = compute_match_score(candidate, job)
    assert score.breakdown.experience == pytest_approx(33.3)


def pytest_approx(value: float) -> float:
    return round(value, 1)


def test_unknown_job_experience_is_full_credit():
    candidate = CandidateProfile(total_experience_years=None)
    job = JobProfile()
    score = compute_match_score(candidate, job)
    assert score.breakdown.experience == 100.0


def test_custom_weights_change_result():
    candidate = CandidateProfile(total_experience_years=None, technical_skills=[])
    job = JobProfile(required_skills=["Python"])
    weights = {
        "required_skills": 1.0, "preferred_skills": 0.0, "experience": 0.0,
        "project_relevance": 0.0, "education": 0.0,
    }
    score = compute_match_score(candidate, job, weights=weights)
    assert score.overall_score == score.breakdown.required_skills * 1.0
