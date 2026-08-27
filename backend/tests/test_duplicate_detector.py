"""Duplicate detection tests."""

from datetime import datetime, timedelta, timezone

from app.schemas.jobs import Job
from app.services.duplicate_detector import DuplicateDetector
from app.services.skill_normalizer import SkillNormalizer


def _job(title: str, company: str, source: str, index: int,
         description: str = "Great role", location: str | None = "Pune",
         url: str | None = None) -> Job:
    return Job(
        title=title,
        company=company,
        description=description,
        location=location,
        application_url=url or f"https://jobs.example.com/{index}",
        posted_at=datetime.now(timezone.utc) - timedelta(days=index),
        required_skills=["Python"],
    ).model_copy(update={"source": source, "source_job_id": f"{source}-{index}"})


def test_spec_example_duplicates_merged():
    detector = DuplicateDetector(SkillNormalizer())
    jobs = [
        _job("GenAI Engineer", "Company X", "board-a", 1),
        _job("Generative AI Engineer", "Company X", "board-b", 2),
        _job("AI Engineer", "Company X", "board-c", 3),
    ]
    canonical = detector.deduplicate(jobs)
    assert len(canonical) == 1
    merged = canonical[0]
    sources = {rec.source for rec in merged.duplicate_of} | {merged.source}
    assert sources == {"board-a", "board-b", "board-c"}


def test_identical_jobs_two_sources_one_canonical():
    detector = DuplicateDetector(SkillNormalizer())
    desc = "Identical posting body with Python and Kubernetes requirements."
    jobs = [
        _job("Backend Engineer", "Acme", "s1", 5, description=desc),
        _job("Backend Engineer", "Acme", "s2", 6, description=desc),
    ]
    canonical = detector.deduplicate(jobs)
    assert len(canonical) == 1


def test_different_roles_not_merged():
    detector = DuplicateDetector(SkillNormalizer())
    jobs = [
        _job("ML Engineer", "Acme", "s1", 7),
        _job("Data Engineer", "Acme", "s2", 8),
    ]
    assert len(detector.deduplicate(jobs)) == 2


def test_same_role_different_companies_not_merged():
    detector = DuplicateDetector(SkillNormalizer())
    jobs = [
        _job("GenAI Engineer", "Alpha", "s1", 9),
        _job("GenAI Engineer", "Beta Corp", "s2", 10),
    ]
    assert len(detector.deduplicate(jobs)) == 2


def test_merge_keeps_richest_fields():
    detector = DuplicateDetector(SkillNormalizer())
    thin = _job("GenAI Engineer", "Gamma", "s1", 11, description="short")
    rich = _job("GenAI Engineer", "Gamma", "s2", 12,
                description="Much longer description with salary 20-30 LPA and details",
                location="Bangalore")
    canonical = detector.deduplicate([thin, rich])
    assert len(canonical) == 1
    merged = canonical[0]
    assert merged.location == "Bangalore"
    assert "salary" in merged.description
