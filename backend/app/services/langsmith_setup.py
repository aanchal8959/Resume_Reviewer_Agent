"""LangSmith setup helper.

Centralizes the env-var wiring so tracing is opt-in and never breaks startup.
Set LANGSMITH_TRACING=true (or LANGCHAIN_TRACING_V2=true) + LANGCHAIN_API_KEY
in backend/.env to enable. All graphs and LLM calls emit traces when enabled.
"""

from __future__ import annotations

import os


def configure_langsmith(settings) -> None:
    """Populate the env vars that the langsmith SDK auto-reads.

    Does not import langsmith itself so the app still boots if the package
    is absent; langsmith is an optional dependency in requirements.txt.
    """
    # Normalize aliases: support both LANGSMITH_* and LANGCHAIN_* forms.
    tracing = bool(getattr(settings, "langsmith_tracing", False))
    # also honour raw env if Settings wasn't given LANGSMITH_TRACING but caller
    # exported LANGCHAIN_TRACING_V2=true
    if not tracing:
        raw = os.getenv("LANGCHAIN_TRACING_V2", "").lower().strip()
        tracing = raw in {"1", "true", "yes", "on"}

    if not tracing:
        # Ensure SDK is explicitly off (tests rely on this).
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        return

    # Resolve API key: Settings.langsmith_api_key > langchain_api_key > env
    api_key = (
        getattr(settings, "langsmith_api_key", None)
        or getattr(settings, "langchain_api_key", None)
        or os.getenv("LANGCHAIN_API_KEY")
        or os.getenv("LANGSMITH_API_KEY")
    )
    if not api_key:
        # Tracing requested but no key — disable gracefully rather than crash.
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        return

    project = getattr(settings, "langsmith_project", "job-switch-agent") or "job-switch-agent"
    endpoint = getattr(settings, "langsmith_endpoint", "https://api.smith.langchain.com")

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    # langsmith SDK checks both names.
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    os.environ["LANGSMITH_ENDPOINT"] = endpoint
