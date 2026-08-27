"""Analysis endpoints: start the LangGraph workflow and fetch results."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.database.database import get_database
from app.database.repository import NotFoundError, SessionRepository
from app.schemas.analysis import StartAnalysisResponse
from app.services.analysis_runner import AnalysisRunError, run_and_store_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/{session_id}/start", response_model=StartAnalysisResponse)
def start_analysis(session_id: str) -> StartAnalysisResponse:
    """Run the multi-agent analysis synchronously for an uploaded session."""
    database = get_database()

    with database.session() as db:
        repo = SessionRepository(db)
        try:
            resume_doc = repo.get_document(session_id, "resume")
            jd_doc = repo.get_document(session_id, "job_description")
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        resume_text, job_text = resume_doc.text_content, jd_doc.text_content
        repo.set_status(session_id, "processing")

    try:
        result_status, error_message = run_and_store_analysis(
            session_id, resume_text, job_text
        )
    except AnalysisRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    if result_status != "completed":
        return StartAnalysisResponse(
            session_id=session_id, status="failed", message=error_message
        )
    return StartAnalysisResponse(
        session_id=session_id, status="completed", message="Analysis completed."
    )


@router.get("/{session_id}")
def get_analysis(session_id: str) -> dict:
    """Return the stored analysis result for a session."""
    database = get_database()
    with database.session() as db:
        repo = SessionRepository(db)
        try:
            session_row = repo.get_session(session_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        result = repo.get_result(session_id)
    payload: dict = {
        "session_id": session_row.id,
        "status": session_row.status,
        "error": session_row.error,
        "candidate_profile": None,
        "job_profile": None,
        "skill_gap": None,
        "match_score": None,
        "roadmap": None,
        "errors": [],
    }
    if result is not None:
        payload.update(
            {
                "candidate_profile": result.candidate_profile,
                "job_profile": result.job_profile,
                "skill_gap": result.skill_gap,
                "match_score": result.match_score,
                "roadmap": result.roadmap,
                "errors": result.errors or [],
            }
        )
    return payload

