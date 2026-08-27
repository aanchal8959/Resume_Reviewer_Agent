"""Job normalization tests: messy source text -> canonical Job fields."""

import pytest

from app.schemas.jobs import RawJob
from app.services.job_normalizer import (
    JobNormalizer,
    extract_experience,
    extract_salary_lpa,
    extract_work_mode,
)
from app.services.llm_service import LLMError
from app.services.skill_normalizer import SkillNormalizer


def test_spec_example_2plus_years():
    low, high = extract_experience("Looking for 2+ yrs Python, GenAI engineers")
    assert low == 2
    assert high is None


def test_range_parsing():
    low, high = extract_experience("Python / LLM Engineer - 2 to 4 years")
    assert (low, high) == (2.0, 4.0)


def test_fresher_and_minimum_forms():
    assert extract_experience("fresher friendly role") == (0.0, None)
    assert extract_experience("minimum 3 years of experience")[0] == 3


def test_salary_extraction():
    assert extract_salary_lpa("Package: 20-30 LPA") == (20.0, 30.0)
    assert extract_salary_lpa("Rs. 12-18 lakhs") == (12.0, 18.0)
    assert extract_salary_lpa("no salary info") == (None, None)


def test_work_mode_detection():
    assert extract_work_mode("remote first company") == "remote"
    assert extract_work_mode("hybrid working model") == "hybrid"
    assert extract_work_mode("work from office in Pune") == "onsite"
    assert extract_work_mode("nothing here") == "unknown"


class _NoLLM:
    name = "gemini-test"

    def generate_structured(self, *args, **kwargs):
        raise LLMError("provider unavailable in unit test")


def _normalize(raw_title: str, description: str):
    normalizer = JobNormalizer(_NoLLM(), SkillNormalizer())
    return normalizer.normalize(
        RawJob(source="t", title=raw_title, company="C", description=description)
    )


def test_full_normalization_extracts_skills_without_llm():
    job = _normalize(
        "GenAI Engineer",
        "We need a GenAI Engineer.\nREQUIREMENTS:\n"
        "- Strong Python\n- Hands on RAG and LLM\n"
        "PREFERRED / NICE TO HAVE:\n- Kubernetes exposure",
    )
    lowered_required = [s.lower() for s in job.required_skills]
    assert {"python", "rag", "llm", "genai"} <= set(lowered_required)
    assert any("kubernetes" in s.lower() for s in job.preferred_skills)


def test_normalization_is_deterministic():
    description = "Hiring 2+ years Python developers with FastAPI knowledge."
    first = _normalize("Backend Engineer", description)
    second = _normalize("Backend Engineer", description)
    # created_at/posted_at excluded: they are set by persistence layers.
    first_dump = first.model_dump(mode="json", exclude={"created_at"})
    second_dump = second.model_dump(mode="json", exclude={"created_at"})
    assert first_dump == second_dump


def test_llm_assist_failure_degrades_gracefully():
    """When deterministic extraction finds nothing and the provider fails,
    the normalizer returns the partially-filled job instead of crashing."""
    normalizer = JobNormalizer(_NoLLM(), SkillNormalizer())
    job = normalizer.normalize(RawJob(source="t", title="Mystery Role",
                                      company="C",
                                      description="Unclear posting"))
    assert job.title == "Mystery Role"
