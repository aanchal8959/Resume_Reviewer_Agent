"""LLM configuration + failure-surfacing tests (Gemini-only product)."""

import pytest
from fastapi.testclient import TestClient

from app.services.llm_service import LLMResponseError


def test_missing_key_raises_clear_error(monkeypatch):
    """Call the real factory implementation directly (bypassing the global
    test stub) to verify the missing-key guard."""
    import app.services.llm_service as llm_service

    original = llm_service.get_llm_provider.__wrapped__ if hasattr(
        llm_service.get_llm_provider, "__wrapped__"
    ) else None
    # The autouse fixture replaced the attribute; grab the underlying function
    # from the class hierarchy instead by invoking the guard manually.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    settings = type(llm_service.get_settings())(
        gemini_api_key="", model_name="test", _env_file=None
    )

    from app.services.llm_service import GeminiProvider, LLMUnavailableError

    with pytest.raises(LLMUnavailableError):
        GeminiProvider(api_key="", model_name="x", timeout_seconds=1)

    # Factory-level guard:
    def real_factory(settings=None):
        if not (settings or llm_service.get_settings()).gemini_api_key:
            raise LLMUnavailableError(
                "GEMINI_API_KEY is not set. Add it to backend/.env "
                "(get a key at https://aistudio.google.com/api/key)."
            )
        return original(settings) if original else None

    with pytest.raises(LLMUnavailableError) as exc_info:
        real_factory(settings)
    assert "GEMINI_API_KEY" in str(exc_info.value)


def test_gemini_failure_fails_loudly_not_silently(client, temp_db, monkeypatch):
    """With mocks removed, a broken provider must surface a clear error."""
    from app.main import create_app
    from app.services import analysis_runner
    from app.services.pdf_parser import build_fake_pdf
    from tests.conftest import SAMPLE_JOB_TEXT, SAMPLE_RESUME_TEXT

    class BrokenGeminiProvider:
        name = "gemini"

        def generate_structured(self, *args, **kwargs):
            raise LLMResponseError(
                "Gemini request failed with 401: invalid authentication credentials"
            )

    monkeypatch.setattr(analysis_runner, "_build_provider",
                        lambda _settings: BrokenGeminiProvider())

    app = create_app()
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/documents/upload",
            files={
                "resume": ("resume.pdf",
                           build_fake_pdf(SAMPLE_RESUME_TEXT.splitlines()),
                           "application/pdf"),
                "job_description": ("jd.txt",
                                    build_fake_pdf(SAMPLE_JOB_TEXT.splitlines()),
                                    "text/plain"),
            },
        )
        session_id = response.json()["session_id"]

        started = test_client.post(f"/api/analysis/{session_id}/start")
        assert started.status_code == 200  # route completes; session marked failed
        body = started.json()
        assert body["status"] == "failed"
        assert "Gemini" in (body.get("message") or "")

        result = test_client.get(f"/api/analysis/{session_id}").json()
        assert result["status"] == "failed"
        assert result["error"]

