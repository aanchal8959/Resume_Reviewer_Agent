"""Deterministic job matching + ranking tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import Job, JobMatch, JobSearchPreferences
from app.services.job_matcher import JobMatchingService
from app.services.ranking import RankingService, freshness_bonus
from app.services.skill_normalizer import SkillNormalizer


def _candidate(years: float | None = 2) -> CandidateProfile:
    return CandidateProfile(
        name="Test Candidate",
        total_experience_years=years,
        current_role="GenAI Engineer",
        technical_skills=["Python", "GCP", "RAG", "GenAI"],
    )


def _job(title: str = "GenAI Engineer", company: str = "Acme",
         required: list[str] | None = None,
         preferred: list[str] | None = None,
         exp_min: float | None = None, exp_max: float | None = None,
         location: str | None = "Pune",
         salary_min: float | None = None, salary_max: float | None = None,
         days_ago: int = 3) -> Job:
    return Job(
        id=f"job-{title}-{company}".replace(" ", "-").lower(),
        title=title, company=company,
        description="Build GenAI products with modern tooling.",
        location=location,
        work_mode="hybrid" if location and location != "Remote" else "remote",
        experience_min=exp_min, experience_max=exp_max,
        salary_min=salary_min, salary_max=salary_max, salary_currency="INR" if salary_max else None,
        required_skills=required or [],
        preferred_skills=preferred or [],
        posted_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


@pytest.fixture()
def matcher():
    return JobMatchingService(SkillNormalizer())


def test_spec_example_high_match_missing_kubernetes(matcher):
    job = _job(required=["Python", "GCP", "RAG", "GenAI"], preferred=["Kubernetes"])
    match = matcher.match(_candidate(), job)
    assert match.overall_match >= 70
    lowered = {s.lower() for s in match.matched_skills}
    assert {"python", "gcp", "rag"} <= lowered
    assert any("kubernetes" in s.lower() for s in match.missing_skills)


def test_experience_mismatch_is_penalized_and_filtered(matcher):
    job = _job(required=["Python"], exp_min=8)
    match = RankingService.apply_filters(
        matcher.match(_candidate(years=2), job)
    )
    assert match.breakdown.experience_match < 40
    assert match.filtered_out
    assert match.filter_reasons


def test_experience_inside_band_full_credit(matcher):
    job = _job(exp_min=1, exp_max=4)
    match = matcher.match(_candidate(years=2), job)
    assert match.breakdown.experience_match == 100.0


def test_location_match_and_mismatch(matcher):
    prefs = JobSearchPreferences(locations=["Pune"])
    good = matcher.match(_candidate(), _job(location="Pune"), prefs)
    bad = matcher.match(_candidate(), _job(location="New York"), prefs)
    assert good.breakdown.location_match == 100.0
    assert bad.breakdown.location_match == 0.0


def test_unknown_salary_redistributes_not_punishes(matcher):
    weights = {
        "required_skill_match": 0.5, "preferred_skill_match": 0.0,
        "role_match": 0.0, "experience_match": 0.5,
        "location_match": 0.0, "salary_match": 0.0,
    }
    no_salary = _job(required=[], salary_max=None)
    match = matcher.match(_candidate(), no_salary, weights=weights)
    assert match.breakdown.salary_match is None  # redistributed, not zeroed
    assert match.breakdown.required_skill_match == 100.0


def test_ranking_orders_best_job_first(matcher):
    great = _job(title="Perfect Fit", required=["Python", "RAG"], days_ago=1)
    decent = _job(title="Decent Fit", required=["Python"], days_ago=20)
    poor = _job(title="Poor Fit", required=["Kubernetes", "Terraform", "Go"], days_ago=30)

    pairs = []
    for job in (great, decent, poor):
        match = RankingService.apply_filters(
            matcher.match(_candidate(), job)
        )
        pairs.append((job, match))

    ranker = RankingService(matcher)
    ranked = ranker.rank(pairs)
    titles = [rec.job.title for rec in ranked]
    assert titles[0] == "Perfect Fit"
    assert titles.index("Perfect Fit") < titles.index("Poor Fit")
    assert all(rec.rank == i + 1 for i, rec in enumerate(ranked))


def test_freshness_bonus_tiers():
    now = datetime.now(timezone.utc)
    assert freshness_bonus(now - timedelta(days=2)) == 2.0
    assert freshness_bonus(now - timedelta(days=10)) == 1.0
    assert freshness_bonus(now - timedelta(days=40)) == 0.0
