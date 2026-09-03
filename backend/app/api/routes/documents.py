"""Document upload endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth.dependencies import get_current_user_optional
from app.config import get_settings
from app.database.database import get_database
from app.database.repository import NotFoundError, SessionRepository
from app.models.user import User
from app.schemas.analysis import DocumentUploadResponse
from app.services.pdf_parser import DocumentParseError, parse_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _validate_upload(file: UploadFile, field_label: str, max_bytes: int) -> bytes:
    filename = file.filename or ""
    if not filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type for {field_label}: '{filename}'. "
                "Upload a PDF or TXT file."
            ),
        )
    data = file.file.read(max_bytes + 1)
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded {field_label} file is empty.",
        )
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{field_label} exceeds the {max_bytes // (1024 * 1024)} MB limit.",
        )
    return data


@router.post("/upload", response_model=DocumentUploadResponse)
def upload_documents(
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    current_user: User | None = Depends(get_current_user_optional),
) -> DocumentUploadResponse:
    """Create an analysis session with a resume and a job description."""
    settings = get_settings()
    resume_bytes = _validate_upload(resume, "resume", settings.max_upload_bytes)
    jd_bytes = _validate_upload(job_description, "job description", settings.max_upload_bytes)

    try:
        resume_text = parse_document(
            resume.filename or "resume.pdf", resume.content_type or "", resume_bytes
        )
        job_text = parse_document(
            job_description.filename or "job_description.pdf",
            job_description.content_type or "",
            jd_bytes,
        )
    except DocumentParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    database = get_database()
    with database.session() as db:
        repo = SessionRepository(db)
        session_row = repo.create_session(user_id=current_user.id if current_user else None)
        resume_doc = repo.add_document(
            session_row.id,
            "resume",
            resume.filename or "resume.pdf",
            resume.content_type or "application/pdf",
            resume_text,
        )
        jd_doc = repo.add_document(
            session_row.id,
            "job_description",
            job_description.filename or "job_description.pdf",
            job_description.content_type or "application/pdf",
            job_text,
        )
        return DocumentUploadResponse(
            session_id=session_row.id,
            resume_document_id=resume_doc.id,
            job_description_document_id=jd_doc.id,
        )


@router.get("/{session_id}")
def list_documents(session_id: str) -> dict:
    database = get_database()
    with database.session() as db:
        repo = SessionRepository(db)
        try:
            session_row = repo.get_session(session_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return {
            "session_id": session_row.id,
            "documents": [
                {"id": doc.id, "kind": doc.kind, "filename": doc.filename}
                for doc in session_row.documents
            ],
        }
