"""Arize Phoenix tracing setup (local, opt-in).

Standard practice:
- Local collector at http://localhost:6006/v1/traces (run: docker run -p 6006:6006 -p 4317:4317 arizephoenix/phoenix)
- OTEL SDK + openinference instrumentation for LangChain/LangGraph.

Set PHOENIX_TRACING=true in backend/.env to enable. Disabled by default and in tests.
Phoenix and LangSmith are independent — both can be enabled together.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Track whether instrumentation was already applied.
_configured: bool = False


def configure_phoenix(settings) -> bool:
    """Configure Arize Phoenix OTEL tracing if enabled.

    Returns True if tracing was enabled (or already enabled), False otherwise.
    Never raises — all errors are logged and tracing is disabled gracefully.
    """
    global _configured

    # Avoid double-registration.
    if _configured:
        return True

    tracing = bool(getattr(settings, "phoenix_tracing", False))
    # Also honour raw env for manual override.
    if not tracing:
        raw = os.getenv("PHOENIX_TRACING", "").lower().strip()
        tracing = raw in {"1", "true", "yes", "on"}

    if not tracing:
        # Ensure explicit off (some OTEL libs auto-enable if PHOENIX env set).
        os.environ.setdefault("PHOENIX_TRACING", "false")
        return False

    endpoint = getattr(settings, "phoenix_endpoint", "http://localhost:6006/v1/traces") or "http://localhost:6006/v1/traces"
    project = getattr(settings, "phoenix_project", "job-switch-agent") or "job-switch-agent"

    # Standard OTEL env vars — downstream libs read these.
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = endpoint
    os.environ["PHOENIX_PROJECT_NAME"] = project

    try:
        # arize-phoenix-otel provides a one-call helper.
        from phoenix.otel import register  # type: ignore

        tracer_provider = register(
            project_name=project,
            endpoint=endpoint,
            auto_instrument=True,
        )
        logger.info("Phoenix tracing enabled: project=%s endpoint=%s", project, endpoint)
        _configured = True
        return True
    except ImportError as exc:
        # Fallback to manual OTEL setup if arize-phoenix-otel not installed.
        logger.debug("arize-phoenix-otel not available (%s), trying manual OTEL setup", exc)

    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
        from openinference.instrumentation.langchain import LangChainInstrumentor  # type: ignore

        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        LangChainInstrumentor().instrument(tracer_provider=provider)
        # LangGraph is built on LangChain — instrumenting LangChain covers it.

        logger.info("Phoenix tracing enabled (manual OTEL): project=%s endpoint=%s", project, endpoint)
        _configured = True
        return True
    except ImportError as exc:
        logger.warning(
            "Phoenix tracing requested but dependencies missing: %s. "
            "Install with: pip install arize-phoenix-otel openinference-instrumentation-langchain "
            "opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp",
            exc,
        )
        return False
    except Exception as exc:  # pragma: no cover - unexpected setup failure
        logger.warning("Phoenix tracing setup failed: %s", exc)
        return False


def reset_phoenix_state() -> None:
    """Test helper — reset configured flag."""
    global _configured
    _configured = False
