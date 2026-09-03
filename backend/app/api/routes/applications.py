"""Phase 3 endpoints: application copilot and tracking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.agents.application_copilot_orchestrator import ApplicationCopilotPipeline
from app.auth.dependencies import get_current_user_optional
from app.config import get_settings
from app.database.application_repository import (
    ApplicationNotFoundError,
    TerminalStateError,
)
from app.models.user import User
from app.schemas.applications import (
    ApplicationAnalytics,
    CreateApplicationRequest,
    CoverLetterEditRequest,
    CoverLetterGenerateRequest,
    NotesUpdateRequest,
    SmartInsights,
    StatusUpdateRequest,
    TailorResumeRequest,
)
from app.services.analysis_runner import _build_provider
from app.services.application_service import ApplicationService
from app.services.document_export import to_markdown, to_pdf, to_txt
from app.services.llm_service import LLMUnavailableError

router = APIRouter(prefix="/api/applications", tags=["applications"])

_service = ApplicationService


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    body: CreateApplicationRequest, current_user: User | None = Depends(get_current_user_optional)
) -> dict:
    try:
        application_id = _service().create_application(
            body.job_id, body.resume_session_id, user_id=current_user.id if current_user else None
        )
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"application_id": application_id, "status": "PREPARING"}


@router.get("")
def list_applications(
    app_status: str | None = Query(None, alias="status"),
    company: str | None = None,
    role: str | None = None,
) -> dict:
    applications = _service().list_applications(app_status, company, role)
    return {"total": len(applications), "applications": [
        a.model_dump(mode="json") for a in applications
    ]}


@router.get("/analytics")
def get_analytics() -> dict:
    analytics: ApplicationAnalytics = _service().analytics()
    insights: SmartInsights = _service().smart_insights()
    return {
        "analytics": analytics.model_dump(),
        "insights": insights.model_dump(),
    }


@router.get("/{application_id}")
def get_application(application_id: str) -> dict:
    try:
        detail = _service().get_detail(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.patch("/{application_id}/status")
def update_status(application_id: str, body: StatusUpdateRequest) -> dict:
    try:
        detail = _service().set_status(application_id, body.status, body.notes)
    except TerminalStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.post("/{application_id}/notes")
def add_notes(application_id: str, body: NotesUpdateRequest) -> dict:
    try:
        detail = _service().set_notes(application_id, body.notes)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.post("/{application_id}/prepare")
def prepare_application(application_id: str) -> dict:
    """Full copilot LangGraph run: tailor + research + letter + questions."""
    service = _service()
    try:
        service.get_detail(application_id)  # 404 fast
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    try:
        _build_provider(get_settings())
    except LLMUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    pipeline = ApplicationCopilotPipeline(service)
    _detail, errors = pipeline.run(application_id)
    result = service.get_detail(application_id).model_dump(mode="json")
    result["warnings"] = errors
    return result


@router.post("/{application_id}/resume/tailor")
def tailor_resume(application_id: str, body: TailorResumeRequest | None = None) -> dict:
    regenerate = bool(body.regenerate) if body else False
    try:
        detail = _service().tailor_resume(application_id, regenerate)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.post("/{application_id}/resume/approve")
def approve_resume(application_id: str) -> dict:
    try:
        detail = _service().approve_resume(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.get("/{application_id}/resume/versions")
def resume_versions(application_id: str) -> dict:
    from app.database.database import get_database

    with get_database().session() as db:
        repo = _application_repository(db)
        try:
            repo.get_application(application_id)
        except ApplicationNotFoundError as exc:
            raise _not_found(exc) from exc
        versions = [
            {
                "version": v.version,
                "title": v.title,
                "created_at": v.created_at,
                "approved": v.approved,
                "unsupported_claims_count": v.unsupported_claims_count,
                "changes": [
                    {
                        "section": c.section, "original": c.original_text,
                        "updated": c.updated_text, "reason": c.reason,
                        "type": c.change_type, "supported": c.supported,
                        "warning": c.warning,
                    }
                    for c in sorted(v.changes, key=lambda x: x.position)
                ],
            }
            for v in repo.all_resume_versions(application_id)
        ]
    return {"versions": versions,
            "master_note": "The master resume is never modified; each job gets "
                           "its own version."}


@router.get("/{application_id}/resume/export")
def export_resume(application_id: str, fmt: str = "md") -> Response:
    try:
        content, title = _service().export_resume_version(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    fmt = fmt.lower()
    if fmt == "txt":
        return Response(to_txt(content), media_type="text/plain",
                        headers=_attachment(f"{title}.txt"))
    if fmt == "pdf":
        return Response(to_pdf(content), media_type="application/pdf",
                        headers=_attachment(f"{title}.pdf"))
    if fmt in {"md", "markdown"}:
        return Response(to_markdown(content), media_type="text/markdown",
                        headers=_attachment(f"{title}.md"))
    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"Unsupported export format '{fmt}'. Use txt|md|pdf.")


@router.post("/{application_id}/cover-letter")
def generate_cover_letter(application_id: str,
                          body: CoverLetterGenerateRequest | None = None) -> dict:
    regenerate = bool(body.regenerate) if body else False
    try:
        detail = _service().generate_cover_letter(application_id, regenerate)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.put("/{application_id}/cover-letter")
def edit_cover_letter(application_id: str, body: CoverLetterEditRequest) -> dict:
    try:
        detail = _service().update_cover_letter(application_id, body.content_text)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.post("/{application_id}/cover-letter/approve")
def approve_cover_letter(application_id: str) -> dict:
    try:
        detail = _service().approve_cover_letter(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.get("/{application_id}/cover-letter/export")
def export_cover_letter(application_id: str, fmt: str = "txt") -> Response:
    try:
        content = _service().export_cover_letter(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    fmt = fmt.lower()
    if fmt == "pdf":
        return Response(to_pdf(content), media_type="application/pdf",
                        headers=_attachment("cover_letter.pdf"))
    if fmt in {"txt", "text"}:
        return Response(to_txt(content), media_type="text/plain",
                        headers=_attachment("cover_letter.txt"))
    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"Unsupported export format '{fmt}'. Use txt|pdf.")


@router.post("/{application_id}/company/research")
def research_company(application_id: str) -> dict:
    try:
        detail = _service().get_detail(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    try:
        detail = _service().research_company(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    except Exception as exc:  # noqa: BLE001 - explicit degraded-research response
        return {
            "research_available": False,
            "message": (
                "Company research unavailable. You can still prepare your "
                "application using the job description and candidate profile."
            ),
            "error": str(exc),
        }
    payload = detail.model_dump(mode="json")
    payload["research_available"] = True
    return payload


@router.post("/{application_id}/questions")
def generate_questions(application_id: str) -> dict:
    try:
        detail = _service().generate_questions(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return detail.model_dump(mode="json")


@router.get("/{application_id}/checklist")
def get_checklist(application_id: str) -> dict:
    try:
        detail = _service().get_detail(application_id)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"checklist": [c.model_dump() for c in detail.checklist]}


@router.patch("/{application_id}/checklist/{key}")
def toggle_checklist(application_id: str, key: str,
                     done: bool = Query(...)) -> dict:
    try:
        detail = _service().toggle_checklist(application_id, key, done)
    except ApplicationNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"checklist": [c.model_dump() for c in detail.checklist]}


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _application_repository(db):
    from app.database.application_repository import ApplicationRepository

    return ApplicationRepository(db)
