"""GeminiProvider REST implementation tests (no network — httpx MockTransport)."""

import httpx
import pytest

from app.services.llm_service import (
    GeminiProvider,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from pydantic import BaseModel


class Echo(BaseModel):
    answer: str


def _provider(handler) -> GeminiProvider:
    transport = httpx.MockTransport(handler)
    return GeminiProvider(api_key="AQ.test", model_name="gemini-test",
                          timeout_seconds=5, transport=transport)


def test_success_parses_json_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b"x-goog-api-key" not in body  # key goes in header, not body
        assert request.headers["x-goog-api-key"] == "AQ.test"
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": '{"answer": "hello"}'}]}}]
        })

    provider = _provider(handler)
    result = provider.generate_structured("sys", "user", Echo)
    assert result.answer == "hello"


def test_401_maps_to_unavailable():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "invalid"}})

    with pytest.raises(LLMUnavailableError):
        _provider(handler).generate_structured("s", "u", Echo)


def test_429_quota_surfaces_sanitized_message():
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "quota exceeded "
                                                         "for api_key user"}})

    with pytest.raises(LLMResponseError) as exc_info:
        _provider(handler).generate_structured("s", "u", Echo)
    assert "api_key" not in str(exc_info.value)


def test_unknown_model_hint_added():
    def handler(request):
        return httpx.Response(404, json={"error": {
            "message": "models/gemini-wrong is not found for API version v1beta"}})

    with pytest.raises(LLMResponseError) as exc_info:
        _provider(handler).generate_structured("s", "u", Echo)
    assert "MODEL_NAME" in str(exc_info.value)


def test_timeout_mapped():
    def handler(request):
        raise httpx.ConnectTimeout("too slow")

    with pytest.raises(LLMTimeoutError):
        _provider(handler).generate_structured("s", "u", Echo)


def test_empty_candidates_rejected():
    def handler(request):
        return httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]})

    with pytest.raises(LLMResponseError):
        _provider(handler).generate_structured("s", "u", Echo)


def test_repair_second_attempt_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": "not json"}]}}]
            })
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": '{"answer": "fixed"}'}]}}]
        })

    result = _provider(handler).generate_structured("s", "u", Echo)
    assert result.answer == "fixed"
