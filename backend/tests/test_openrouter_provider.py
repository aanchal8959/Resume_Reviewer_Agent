"""OpenRouterProvider REST implementation tests (no network — httpx MockTransport)."""

import httpx
import pytest
from pydantic import BaseModel

from app.services.llm_service import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    OpenRouterProvider,
    get_llm_provider as _real_get_llm_provider,
)


class Echo(BaseModel):
    answer: str


def _provider(handler, **kwargs) -> OpenRouterProvider:
    transport = httpx.MockTransport(handler)
    base_url = kwargs.pop("base_url", "https://openrouter.ai/api/v1")
    return OpenRouterProvider(
        api_key="sk-or-test",
        model_name="openai/gpt-4o-mini",
        base_url=base_url,
        timeout_seconds=5,
        transport=transport,
        **kwargs,
    )


def test_success_parses_json_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-or-test"
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        body = request.read()
        # key must not leak in body
        assert b"sk-or-test" not in body
        # model and response_format check
        import json as _json
        payload = _json.loads(body)
        assert payload["model"] == "openai/gpt-4o-mini"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"answer": "hello"}'}, "finish_reason": "stop"}]
        })

    provider = _provider(handler)
    result = provider.generate_structured("sys", "user", Echo)
    assert result.answer == "hello"


def test_custom_base_url_used():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.custom.ai/v1/chat/completions"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"answer": "ok"}'}}]
        })

    provider = _provider(handler, base_url="https://api.custom.ai/v1")
    result = provider.generate_structured("s", "u", Echo)
    assert result.answer == "ok"


def test_headers_optional_forwarded():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["http-referer"] == "http://localhost:3000"
        assert request.headers["x-title"] == "Job Switch Agent"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"answer": "hi"}'}}]
        })

    provider = _provider(
        handler, site_url="http://localhost:3000", app_name="Job Switch Agent"
    )
    result = provider.generate_structured("s", "u", Echo)
    assert result.answer == "hi"


def test_401_maps_to_unavailable():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    with pytest.raises(LLMUnavailableError):
        _provider(handler).generate_structured("s", "u", Echo)


def test_429_quota_surfaces_sanitized_message():
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "quota exceeded for api_key user"}})

    with pytest.raises(LLMResponseError) as exc_info:
        _provider(handler).generate_structured("s", "u", Echo)
    assert "api_key" not in str(exc_info.value)


def test_unknown_model_hint_added():
    def handler(request):
        return httpx.Response(404, json={"error": {"message": "model openai/gpt-wrong is not found"}})

    with pytest.raises(LLMResponseError) as exc_info:
        _provider(handler).generate_structured("s", "u", Echo)
    assert "OPENROUTER_MODEL" in str(exc_info.value)


def test_timeout_mapped():
    def handler(request):
        raise httpx.ConnectTimeout("too slow")

    with pytest.raises(LLMTimeoutError):
        _provider(handler).generate_structured("s", "u", Echo)


def test_empty_choices_rejected():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length"}]})

    with pytest.raises(LLMResponseError):
        _provider(handler).generate_structured("s", "u", Echo)


def test_repair_second_attempt_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "not json"}}]
            })
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"answer": "fixed"}'}}]
        })

    result = _provider(handler).generate_structured("s", "u", Echo)
    assert result.answer == "fixed"


def test_factory_selects_provider():
    from app.config import Settings

    # openrouter without key -> unavailable
    s = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key=None)
    with pytest.raises(LLMUnavailableError) as ei:
        _real_get_llm_provider(s)
    assert "OPENROUTER_API_KEY" in str(ei.value)

    # openrouter with key -> correct type
    s2 = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="sk-or-test")
    provider = _real_get_llm_provider(s2)
    assert provider.name == "openrouter"

    # gemini without key -> unavailable
    s3 = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=None)
    with pytest.raises(LLMUnavailableError):
        _real_get_llm_provider(s3)

    # gemini with key
    s4 = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="AQ.test")
    provider2 = _real_get_llm_provider(s4)
    assert provider2.name == "gemini"
