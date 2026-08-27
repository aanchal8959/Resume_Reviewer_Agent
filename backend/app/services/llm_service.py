"""LLM provider abstraction (Gemini-only).

Agents depend only on ``LLMProvider.generate_structured``; the concrete
provider talks to the Gemini public REST API using ``x-goog-api-key``
(required for modern ``AQ.``-style AI Studio keys). Structured output is
always validated with Pydantic before it leaves this layer.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.schemas.jobs import ProviderStatus

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


def get_llm_provider(settings=None) -> LLMProvider:
    """Factory building the configured Gemini provider."""
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise LLMUnavailableError(
            "GEMINI_API_KEY is not set. Add it to backend/.env "
            "(get a key at https://aistudio.google.com/api/key)."
        )
    return GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.model_name,
        timeout_seconds=settings.llm_timeout_seconds,
    )
