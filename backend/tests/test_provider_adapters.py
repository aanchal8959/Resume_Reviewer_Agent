"""Provider payload -> RawJob mapping tests (no network involved)."""

from app.services.job_sources.adzuna_source import AdzunaJobSource
from app.services.job_sources.arbeitnow_source import ArbeitnowJobSource
from app.services.job_sources.greenhouse_source import GreenhouseCompanySource
from app.services.job_sources.jobicy_source import JobicyJobSource
from app.services.job_sources.remotive_source import RemotiveJobSource


def test_arbeitnow_payload_normalized():
    raw = ArbeitnowJobSource._to_raw({
        "slug": "java-dev-123",
        "title": "Java Developer",
        "company_name": "Example GmbH",
        "description": "<p>Great Java role</p>",
        "remote": True,
        "url": "https://arbeitnow.com/jobs/java-dev-123",
        "job_types": ["full-time"],
        "location": "Berlin",
        "created_at": 1750000000,
    })
    assert raw is not None
    assert raw.title == "Java Developer"
    assert raw.company == "Example GmbH"          # company_name -> company
    assert raw.location == "Berlin"
    assert raw.work_mode == "remote"
    assert raw.source_type == "REAL"
    assert raw.posted_at is not None


def test_arbeitnow_missing_fields_rejected():
    assert ArbeitnowJobSource._to_raw({"title": "No company"}) is None


def test_jobicy_payload_normalized():
    raw = JobicyJobSource._to_raw({
        "id": 42,
        "jobTitle": "Backend Developer",
        "companyName": "Acme",
        "jobGeo": "Remote",
        "jobLevel": "Senior",
        "jobType": "Full Time",
        "jobDescription": "<b>Build</b> APIs",
        "pubDate": "2026-08-01T00:00:00Z",
        "annualSalaryMin": 80000, "annualSalaryMax": 100000,
        "annualSalaryCurrency": "USD",
        "url": "https://jobicy.com/jobs/42",
    })
    assert raw.company == "Acme"
    assert raw.experience_level == "Senior"
    assert raw.salary_text and "80000" in raw.salary_text
    assert raw.url.endswith("/42")


def test_adzuna_payload_normalized():
    source = AdzunaJobSource(app_id="x", api_key="y")
    raw = source._to_raw({
        "id": "777",
        "title": "Data Scientist",
        "company": {"display_name": "Insightmint"},
        "location": {"display_name": "Mumbai"},
        "description": "Analytics role",
        "redirect_url": "https://adzuna.in/r/777",
        "created": "2026-08-10T00:00:00Z",
        "contract_time": "permanent",
        "salary_min": 1200000, "salary_max": 1800000,
    })
    assert raw.company == "Insightmint"
    assert raw.location == "Mumbai"
    assert raw.employment_type == "permanent"


def test_greenhouse_payload_normalized():
    raw = GreenhouseCompanySource._to_raw(
        {
            "id": 99,
            "title": "ML Engineer",
            "content": "<p>Build models</p>",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/99",
            "updated_at": "2026-08-12T00:00:00Z",
            "location": {"name": "Remote"},
        },
        company_name="Acme Inc",
    )
    assert raw.source == "greenhouse"
    assert raw.source_type == "REAL"
    assert raw.source_job_id == "99"
    assert raw.company == "Acme Inc"


def test_remotive_payload_normalized():
    raw = RemotiveJobSource._to_raw({
        "id": 5,
        "title": "GenAI Engineer",
        "company_name": "VertexWorks",
        "description": "<p>RAG</p>",
        "candidate_required_location": "Remote",
        "url": "https://remotive.com/5",
        "publication_date": "2026-08-05T00:00:00Z",
    })
    assert raw.source == "remotive"
    assert raw.title == "GenAI Engineer"
    assert raw.work_mode is None or raw.location == "Remote"
