"""Shared runner for the Phase 1 analysis workflow.

Used by POST /api/analysis/{session_id}/start and by the Phase 2
"Analyze This Job" flow so the multi-agent pipeline exists in exactly one place.
Failures (bad key, quota, timeouts) are persisted and surfaced to the client.
"""

from __future__ import annotations

from app.agents.orchestrator import Orchestrator
from app.config import get_settings
from app.database.database import get_database
from app.database.repository import SessionRepository


class AnalysisRunError(Exception):
    """Raised when the analysis pipeline cannot even be attempted."""


def run_and_store_analysis(
    session_id: str,
    resume_text: str,
    job_description_text: str,
) -> tuple[str, str | None]:
    """Run the LangGraph pipeline and persist results.

    Returns (status, error_message) with status in {"completed", "failed"}.
    """
    settings = get_settings()
    database = get_database()

    try:
        orchestrator = Orchestrator(
            provider=_build_provider(settings), weights=settings.match_weights
        )
    except Exception as exc:  # noqa: BLE001 - config errors surface as 503 upstream
        raise AnalysisRunError(str(exc)) from exc

    try:
        final_state = orchestrator.run(resume_text, job_description_text, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 - every failure must be persisted
        message = f"Analysis failed: {exc}"
        with database.session() as db:
            SessionRepository(db).set_status(session_id, "failed", error=message)
        return "failed", message

    errors = list(final_state.get("errors") or [])
    failed = bool(errors) or final_state.get("match_score") is None
    overall = (final_state.get("match_score") or {}).get("overall_score")

    with database.session() as db:
        repo = SessionRepository(db)
        repo.save_result(
            session_id,
            candidate_profile=final_state.get("candidate_profile"),
            job_profile=final_state.get("job_profile"),
            skill_gap=final_state.get("skill_gap"),
            match_score=final_state.get("match_score"),
            roadmap=final_state.get("roadmap"),
            errors=errors,
        )
        repo.set_status(
            session_id,
            "failed" if failed else "completed",
            error="; ".join(errors) if errors else None,
            overall_score=float(overall) if isinstance(overall, (int, float)) else None,
        )
    return ("failed", "; ".join(errors) or "Analysis produced no match score.") if failed \
        else ("completed", None)


def _build_provider(settings):
    from app.services.llm_service import get_llm_provider

    return get_llm_provider(settings)
