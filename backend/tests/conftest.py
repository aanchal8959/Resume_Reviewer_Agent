"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("GEMINI_API_KEY", "test-key-for-suite")
# Force hermetic provider for tests regardless of local backend/.env
os.environ["LLM_PROVIDER"] = "gemini"
# Disable tracing in tests — never emit hermetic runs.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["PHOENIX_TRACING"] = "false"
os.environ["PHOENIX_ENDPOINT"] = "http://localhost:6006/v1/traces"
# Clear cached settings so tests read the hermetic env, not local .env
try:
    from app.config import get_settings as _get_settings  # noqa: E402
    _get_settings.cache_clear()  # type: ignore[attr-defined]
except Exception:
    pass
# Tests must be hermetic: never call real job providers or company research.
from app.services.job_sources import manager as _manager_module  # noqa: E402
from tests.fakes import FakeSourceAdapter, build_fake_jobs  # noqa: E402


def _hermetic_adapters(cls, settings):  # noqa: ANN001
    adapter = FakeSourceAdapter()
    from app.services.job_sources.base import ProviderAdapter

    return [ProviderAdapter(
        "fake", "Test Source", "REAL", True, adapter.search_jobs,
    )]


_manager_module.JobSourceManager._build_adapters = classmethod(_hermetic_adapters)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.config import get_settings

    get_settings.cache_clear()
    # Reset Phoenix tracer state so tests stay hermetic
    try:
        from app.services.phoenix_setup import reset_phoenix_state

        reset_phoenix_state()
    except Exception:
        pass
    yield
    get_settings.cache_clear()
    try:
        from app.services.phoenix_setup import reset_phoenix_state

        reset_phoenix_state()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def stub_gemini_provider(monkeypatch):
    """All product LLM calls resolve to the deterministic stub in tests."""
    from tests.fakes import StubGeminiProvider

    monkeypatch.setattr(
        "app.services.llm_service.get_llm_provider",
        lambda settings=None: StubGeminiProvider(),
    )
    from app.services import analysis_runner as _runner

    monkeypatch.setattr(_runner, "_build_provider",
                        lambda settings=None: StubGeminiProvider())


@pytest.fixture(autouse=True)
def hermetic_company_source(monkeypatch):
    """Company research stub returning honest minimal info for any name."""
    from app.schemas.applications import CompanyInfo

    def fake_source():
        class _Stub:
            name = "stub"

            def get_company_info(self, company_name: str) -> CompanyInfo:
                return CompanyInfo(
                    name=company_name,
                    description=f"Public information for {company_name}.",
                    source="stub",
                    is_mock=False,
                    verified_fields=["description"],
                )

        return _Stub()

    monkeypatch.setattr(
        "app.services.application_service.get_company_source", fake_source
    )

from fastapi.testclient import TestClient  # noqa: E402

from app.database import database as db_module  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.pdf_parser import build_fake_pdf  # noqa: E402

SAMPLE_RESUME_TEXT = """John Doe
Bengaluru, India | john.doe@example.com

SUMMARY
AI Engineer with 3 years of experience building GenAI applications.

EXPERIENCE
Current role: AI Engineer
- Built an enterprise RAG chatbot using Python, FastAPI, LangChain and GCP Vertex AI
- Deployed services with Docker and Cloud Run
- Strong communication and teamwork across teams

EDUCATION
B.Tech Computer Science, 2020

SKILLS
Python, FastAPI, LangChain, RAG, LLM, GCP, Docker, SQL, PostgreSQL

PROJECTS
Enterprise RAG System: retrieval augmented generation chatbot for support teams
Technologies: Python, Vertex AI, FAISS, FastAPI
"""

SAMPLE_JOB_TEXT = """Company: Acme AI
Role: GenAI Engineer

We are looking for a GenAI Engineer to build production LLM applications.

RESPONSIBILITIES:
- Design and ship RAG pipelines
- Build APIs with Python and FastAPI
- Deploy services on GCP and Kubernetes

REQUIREMENTS:
- 2+ years experience with Python
- Strong RAG and LLM knowledge
- Experience with GCP
- Kubernetes fundamentals
- System design for distributed systems

PREFERRED / NICE TO HAVE:
- MLOps
- LangGraph
- Terraform

EDUCATION:
Bachelor degree in Computer Science
"""


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the singleton database at a per-test SQLite file."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    db = db_module.init_database(url)
    yield db
    db.engine.dispose()
    db_module.reset_database()


@pytest.fixture()
def client(temp_db):
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def uploaded_files():
    return {
        "resume": ("resume.pdf", build_fake_pdf(SAMPLE_RESUME_TEXT.splitlines()),
                   "application/pdf"),
        "job_description": ("job_description.pdf",
                            build_fake_pdf(SAMPLE_JOB_TEXT.splitlines()),
                            "application/pdf"),
    }


# ---------------------------------------------------------------------------
# Phase 2/3 shared helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def analyzed_session(client, uploaded_files):
    """Upload resume + JD and complete the Phase 1 analysis."""
    response = client.post("/api/documents/upload", files=uploaded_files)
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    started = client.post(f"/api/analysis/{session_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "completed"
    return session_id


@pytest.fixture()
def recommended_job(client, analyzed_session):
    """Run a mock discovery search and return the top recommended job."""
    search = client.post(
        "/api/jobs/search",
        json={
            "session_id": analyzed_session,
            "keywords": ["GenAI Engineer"],
            "locations": ["Bangalore", "Pune", "Remote"],
            "remote": True,
            "min_match_percent": 50,
        },
    )
    assert search.status_code == 200
    body = search.json()
    assert body["status"] == "completed", body
    recs = client.get(f"/api/jobs/recommendations/{body['search_id']}").json()
    assert recs["recommendations"]
    return recs["recommendations"][0]["job"]
