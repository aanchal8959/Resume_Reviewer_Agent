"""Shared agent plumbing: typed error + prompt formatting helpers."""

from __future__ import annotations

import json

from pydantic import BaseModel


class AgentError(Exception):
    """Raised when an agent cannot produce validated structured output."""


def format_model(model: BaseModel | dict | list | None) -> str:
    """Compact JSON rendering used inside prompts."""
    if model is None:
        return "null"
    payload = model.model_dump() if isinstance(model, BaseModel) else model

    def _default(value: object) -> object:
        if isinstance(value, BaseModel):
            return value.model_dump()
        raise TypeError(f"Unserializable prompt object: {type(value).__name__}")

    return json.dumps(payload, indent=2, default=_default)


EXTRACTION_RULES = (
    "STRICT EXTRACTION RULES:\n"
    "1. Use ONLY information explicitly present in the text. NEVER invent skills, "
    "experience, projects or requirements.\n"
    "2. If a value is not found, return null (or an empty list for list fields).\n"
    "3. Do not infer technologies that are merely implied by project names.\n"
    "4. Preserve the original spelling of skills.\n"
)
