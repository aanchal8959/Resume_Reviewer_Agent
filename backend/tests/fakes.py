"""Test doubles.

These exist ONLY for the test suite: they keep integration tests hermetic
(no network, no API keys) without shipping any mock provider inside the
application itself.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.schemas.jobs import JobSearchPreferences, RawJob


# ---------------------------------------------------------------------------
# Fake job source (hermetic stand-in for live providers)
# ---------------------------------------------------------------------------

_FAKE_JOB_SPECS: list[tuple[str, str, str, str | None, str]] = [
    # title, company, description, location, source
    ("GenAI Engineer", "Nimbus AI Labs",
     "Build GenAI products. REQUIREMENTS:\n- Hands-on experience with Python\n"
     "- Hands-on experience with RAG\n- Hands-on experience with LLM\n"
     "- Experience with GCP\nPREFERRED / NICE TO HAVE:\n- Kubernetes exposure\n"
     "- MLOps is a plus", "Bangalore", "remotive"),
    ("Generative AI Engineer", "VertexWorks",
     "GenAI platform role.\nREQUIREMENTS:\n- 2+ years of professional experience\n"
     "- Strong Python\n- Hands-on RAG and GenAI\n- Experience with GCP\n"
     "PREFERRED / NICE TO HAVE:\n- Terraform", "Remote", "greenhouse"),
    ("Java Developer", "Orbit Commerce",
     "Backend Java services.\nREQUIREMENTS:\n- 3+ years of professional experience\n"
     "- Hands-on experience with Java\n- Experience with Microservices\n"
     "PREFERRED / NICE TO HAVE:\n- Kubernetes", "Pune", "remotive"),
    ("Senior Backend Engineer", "Ledgerline Fintech",
     "Payments platform.\nREQUIREMENTS:\n- 5+ years of professional experience\n"
     "- Hands-on experience with Java\n- Experience with PostgreSQL\n"
     "PREFERRED / NICE TO HAVE:\n- Kafka", "Bangalore", "greenhouse"),
    ("ML Engineer", "Quantly",
     "Model training role.\nREQUIREMENTS:\n- 2+ years of professional experience\n"
     "- Hands-on experience with Python\n- Hands-on experience with PyTorch\n"
     "PREFERRED / NICE TO HAVE:\n- MLflow", "Remote", "remotive"),
    ("Data Scientist", "Insightmint",
     "Analytics role.\nREQUIREMENTS:\n- 2+ years of professional experience\n"
     "- Hands-on experience with Python\n- Hands-on experience with Pandas\n"
     "PREFERRED / NICE TO HAVE:\n- Tableau", "Mumbai", "greenhouse"),
    ("Marketing Manager", "Brandboost Agency",
     "Campaigns and SEO.\nREQUIREMENTS:\n- 4+ years of professional experience\n"
     "- Digital Marketing\n- SEO", "Delhi NCR", "remotive"),
]


def _fake_raw(index: int, title: str, company: str, description: str,
              location: str | None, source: str) -> RawJob:
    salary = None
    match = re.search(r"(\d+)\+", description)
    del match  # salaries intentionally omitted; normalization handles absence
    return RawJob(
        source=source,
        source_type="REAL",
        source_job_id=f"{source}-{index:03d}",
        title=title,
        company=company,
        description=description,
        location=location,
        work_mode="remote" if location == "Remote" else "onsite",
        url=f"https://jobs.example.com/{index:03d}",
    )


def build_fake_jobs() -> list[RawJob]:
    return [
        _fake_raw(i, *spec) for i, spec in enumerate(_FAKE_JOB_SPECS)
    ]


def _matches(job: RawJob, keywords: list[str]) -> bool:
    from app.services.matching import tokenize

    if not keywords:
        return True
    haystack = f"{job.title} {job.company} {job.description}".lower()
    token_lists = [tokenize(k) for k in keywords]
    for tokens in token_lists:
        if tokens and all(t in haystack for t in tokens):
            return True
    for tokens in token_lists:
        if tokens and any(t in haystack for t in tokens):
            return True
    return False


class FakeSourceAdapter:
    """Drop-in adapter for JobSourceManager with deterministic results."""

    name = "fake"
    display_name = "Test Source"

    def __init__(self, jobs: list[RawJob] | None = None) -> None:
        self.jobs = jobs if jobs is not None else build_fake_jobs()

    def search_jobs(self, query: JobSearchPreferences,
                    strategy_queries: list[str]) -> list[RawJob]:
        keywords = strategy_queries or query.keywords
        return [job for job in self.jobs if _matches(job, keywords)]


def fake_adapter_fn(jobs: list[RawJob] | None = None):
    adapter = FakeSourceAdapter(jobs)
    return adapter.search_jobs


# ---------------------------------------------------------------------------
# Stub Gemini provider (structured-output script per response model)
# ---------------------------------------------------------------------------


class StubGeminiProvider:
    """Returns deterministic valid payloads per response_model."""

    name = "gemini-stub"

    def generate_structured(self, system_prompt: str, user_prompt: str,
                            response_model: type[BaseModel],
                            context: dict | None = None) -> BaseModel:
        payload = self._payload(response_model, user_prompt, context or {})
        return response_model.model_validate(payload)

    @staticmethod
    def _payload(model: type[BaseModel], user_prompt: str,
                 context: dict) -> dict:
        name = model.__name__
        if name == "CandidateProfile":
            return {"name": "John Doe", "total_experience_years": 2,
                    "current_role": "AI Engineer",
                    "programming_languages": ["Python"],
                    "technical_skills": ["Python"]}
        if name == "JobProfile":
            return {"role": "GenAI Engineer",
                    "required_skills": ["Python", "RAG"],
                    "preferred_skills": ["Kubernetes"]}
        if name == "TailoredResume":
            return {
                "content_markdown": (
                    "# John Doe\n\n## Summary\nAligned with the role.\n\n"
                    "## Experience\n- Developed a RAG chatbot using Python "
                    "and FastAPI for retrieval\n- Deployed production "
                    "Kubernetes clusters across regions\n"
                ),
                "changes": [{
                    "section": "Experience",
                    "original": "Worked on chatbots",
                    "updated": "Developed a RAG chatbot using Python and FastAPI",
                    "reason": "clarity",
                    "type": "clarity",
                }],
                "summary": "Stub tailored resume.",
                "recommendations": [],
            }
        if name == "CoverLetterDraft":
            letter = (
                "Dear Hiring Team,\n\nI am excited to apply for the GenAI "
                "Engineer position at Acme AI Technologies. My background "
                "covers Python, RAG and production LLM applications, which "
                "maps directly to your requirements.\n\nAt my current role I "
                "built retrieval pipelines end to end, from data ingestion to "
                "evaluation, always with a focus on reliability.\n\nI would "
                "welcome the chance to discuss how I can contribute.\n\n"
                "Sincerely,\nJohn Doe"
            )
            return {"content_text": letter, "word_count": len(letter.split()),
                    "generated_with": "stub"}
        if name == "QuestionSet":
            return {"items": [
                {"question": "Why this role?",
                 "suggested_answer": "It matches my skills.", "category": "behavioral"},
                {"question": "Describe your Python experience.",
                 "suggested_answer": "See resume projects.", "category": "technical"},
                {"question": "Expected salary?",
                 "suggested_answer": "[fill in]", "category": "practical"},
            ]}
        if name == "SkillClassification":
            return {"items": [
                {"skill": "Python", "status": "matched"},
                {"skill": "Kubernetes", "status": "missing"},
            ]}
        if name == "Roadmap":
            tasks = [{"day": d, "topic": "Study", "goal": "Learn",
                      "estimated_hours": 2, "priority": "high"}
                     for d in range(1, 31)]
            return {"total_days": 30, "daily_hours_target": 2,
                    "weeks": [tasks[i:i + 7] for i in range(0, 30, 7)]}
        raise AssertionError(f"Stub has no payload for {name}")
