"""LLM provider abstraction (Gemini + OpenRouter).

Agents depend only on ``LLMProvider.generate_structured``. Two independent
backends are available:

- ``GeminiProvider`` — Google Generative Language API (``x-goog-api-key``).
- ``OpenRouterProvider`` — OpenAI-compatible ``/chat/completions`` via
  https://openrouter.ai (any ``openai/*`` or other model). Providers are
  fully independent; selection is via ``LLM_PROVIDER`` (``gemini`` |
  ``openrouter``).

Structured output is always validated with Pydantic before it leaves this layer.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.schemas.jobs import ProviderStatus

# Optional LangSmith decorator — no-op if langsmith not installed or tracing off.
try:
    from langsmith import traceable as _traceable  # type: ignore

    def _maybe_traceable(*args, **kwargs):  # type: ignore
        return _traceable(*args, **kwargs)

except Exception:  # pragma: no cover - missing optional dep

    def _maybe_traceable(*_args, **_kwargs):  # type: ignore
        def _decorator(fn):  # type: ignore
            return fn

        return _decorator

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for LLM-layer failures."""


class LLMUnavailableError(LLMError):
    """Provider not usable (missing key, bad credentials, bad config)."""


class LLMTimeoutError(LLMError):
    """Provider did not respond within the configured timeout."""


class LLMResponseError(LLMError):
    """Provider returned empty/malformed output that failed validation."""


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        context: dict | None = None,
    ) -> T:
        """Return a validated instance of ``response_model`` or raise LLMError."""


class GeminiProvider(LLMProvider):
    """Google Gemini provider calling the public REST API directly.

    Uses the ``x-goog-api-key`` header, which is required for newer
    ``AQ.``-style AI Studio keys (the legacy SDK sends them incorrectly and
    fails with 401 ACCESS_TOKEN_TYPE_UNSUPPORTED). Structured output uses
    JSON response mode; every reply is validated with Pydantic by the caller.
    """

    name = "gemini"

    API_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

    def __init__(
        self,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMUnavailableError("GeminiProvider requires an API key.")
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @_maybe_traceable(name="gemini.generate_structured", run_type="llm")
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        context: dict | None = None,
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        base_prompt = (
            f"{user_prompt}\n\nRespond with ONLY a single valid JSON object "
            f"that conforms to this JSON Schema:\n{schema_json}"
        )
        last_error: Exception | None = None
        for attempt in range(2):
            prompt = base_prompt
            if attempt == 1 and last_error is not None:
                prompt = (
                    f"{user_prompt}\n\nYour previous reply failed validation:\n"
                    f"{last_error}\n\nReturn ONLY corrected JSON conforming to:\n"
                    f"{schema_json}"
                )
            raw_text = self._invoke(system_prompt, prompt)
            try:
                payload = json.loads(raw_text)
                return response_model.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
        raise LLMResponseError(
            f"Gemini returned output that failed {response_model.__name__} "
            f"validation after 2 attempts: {last_error}"
        )

    # -- internals ---------------------------------------------------------------
    @_maybe_traceable(name="gemini._invoke", run_type="llm")
    def _invoke(self, system_prompt: str, prompt: str) -> str:
        try:
            with httpx.Client(timeout=self._timeout_seconds,
                              transport=self._transport) as client:
                response = client.post(
                    self.API_URL.format(model=self._model_name),
                    headers={"x-goog-api-key": self._api_key},
                    json={
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.1,
                        },
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Gemini request timed out after {self._timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMResponseError(f"Gemini request failed: {exc}") from exc

        if response.status_code == 200:
            return self._extract_text(response)

        detail = self._error_detail(response)
        if response.status_code in (401, 403):
            raise LLMUnavailableError(
                f"Gemini rejected the credentials ({response.status_code}): {detail}"
            )
        raise LLMResponseError(
            f"Gemini request failed with {response.status_code}: {detail}"
        )

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text", "")) for part in parts)
        except Exception as exc:  # noqa: BLE001 - malformed success payloads
            raise LLMResponseError(
                f"Gemini returned an unexpected payload: {exc}"
            ) from exc
        if not text.strip():
            reason = ""
            try:
                reason = str(data["candidates"][0].get("finishReason", ""))
            except Exception:  # noqa: BLE001
                pass
            raise LLMResponseError(
                f"Gemini returned an empty response (finishReason={reason or 'unknown'})."
            )
        return text.strip()

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        message = ""
        try:
            message = str(response.json().get("error", {}).get("message", ""))
        except Exception:  # noqa: BLE001
            pass
        if response.status_code == 404 and "model" in message.lower():
            message += (
                " - check MODEL_NAME in your .env (use a model available to "
                "your account, e.g. gemini-3-flash-preview)."
            )
        return ProviderStatus.sanitize_error(message or response.text[:200])


class OpenRouterProvider(LLMProvider):
    """OpenRouter (OpenAI-compatible) provider via ``/chat/completions``.

    Independent from ``GeminiProvider`` — own base URL, API key, model and
    timeout. Uses ``Authorization: Bearer <key>`` and requests JSON object
    output; all replies are validated with Pydantic exactly like Gemini.
    """

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str = "https://openrouter.ai/api/v1",
        site_url: str | None = None,
        app_name: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMUnavailableError("OpenRouterProvider requires an API key.")
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._site_url = site_url
        self._app_name = app_name
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @_maybe_traceable(name="openrouter.generate_structured", run_type="llm")
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        context: dict | None = None,
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        base_prompt = (
            f"{user_prompt}\n\nRespond with ONLY a single valid JSON object "
            f"that conforms to this JSON Schema:\n{schema_json}"
        )
        last_error: Exception | None = None
        for attempt in range(2):
            prompt = base_prompt
            if attempt == 1 and last_error is not None:
                prompt = (
                    f"{user_prompt}\n\nYour previous reply failed validation:\n"
                    f"{last_error}\n\nReturn ONLY corrected JSON conforming to:\n"
                    f"{schema_json}"
                )
            raw_text = self._invoke(system_prompt, prompt)
            try:
                payload = json.loads(raw_text)
                return response_model.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
        raise LLMResponseError(
            f"OpenRouter returned output that failed {response_model.__name__} "
            f"validation after 2 attempts: {last_error}"
        )

    @_maybe_traceable(name="openrouter._invoke", run_type="llm")
    def _invoke(self, system_prompt: str, prompt: str) -> str:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._app_name:
            headers["X-Title"] = self._app_name
        body = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"OpenRouter request timed out after {self._timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMResponseError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code == 200:
            return self._extract_text(response)

        detail = self._error_detail(response)
        if response.status_code in (401, 403):
            raise LLMUnavailableError(
                f"OpenRouter rejected the credentials ({response.status_code}): {detail}"
            )
        raise LLMResponseError(
            f"OpenRouter request failed with {response.status_code}: {detail}"
        )

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        try:
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("missing choices")
            message = choices[0].get("message", {})
            text = message.get("content", "")
            if isinstance(text, list):
                # Some models return content as parts
                text = "".join(str(p.get("text", "") if isinstance(p, dict) else str(p)) for p in text)
            text = str(text)
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseError(
                f"OpenRouter returned an unexpected payload: {exc}"
            ) from exc
        if not text.strip():
            reason = ""
            try:
                reason = str(data["choices"][0].get("finish_reason", "") or data["choices"][0].get("finishReason", ""))
            except Exception:  # noqa: BLE001
                pass
            raise LLMResponseError(
                f"OpenRouter returned an empty response (finish_reason={reason or 'unknown'})."
            )
        return text.strip()

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        message = ""
        try:
            payload = response.json()
            err = payload.get("error", {})
            if isinstance(err, dict):
                message = str(err.get("message", "") or err.get("msg", ""))
            elif isinstance(err, str):
                message = err
            if not message:
                message = str(payload.get("message", ""))
        except Exception:  # noqa: BLE001
            pass
        if response.status_code == 404 and "model" in message.lower():
            message += (
                " - check OPENROUTER_MODEL in your .env "
                "(e.g. openai/gpt-4o-mini)."
            )
        return ProviderStatus.sanitize_error(message or response.text[:300])


def get_llm_provider(settings=None) -> LLMProvider:
    """Factory building the configured provider (gemini | openrouter)."""
    settings = settings or get_settings()
    provider = str(getattr(settings, "llm_provider", "gemini") or "gemini").lower()
    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise LLMUnavailableError(
                "OPENROUTER_API_KEY is not set. Add it to backend/.env "
                "(LLM_PROVIDER=openrouter, get a key at https://openrouter.ai/keys)."
            )
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model_name=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            site_url=settings.openrouter_site_url,
            app_name=settings.openrouter_app_name,
            timeout_seconds=settings.openrouter_timeout_seconds,
        )
    # default: gemini
    if not settings.gemini_api_key:
        raise LLMUnavailableError(
            "GEMINI_API_KEY is not set. Add it to backend/.env "
            "(get a key at https://aistudio.google.com/api/key) or set LLM_PROVIDER=openrouter."
        )
    return GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.model_name,
        timeout_seconds=settings.llm_timeout_seconds,
    )
