"""Repository pattern: the only module allowed to touch ORM internals."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models.analysis import AnalysisResultRow, AnalysisSession, Document


class NotFoundError(Exception):
    """Raised when a session or document does not exist."""


class SessionRepository:
    def __init__(self, db: OrmSession) -> None:
        self._db = db

    # -- sessions -----------------------------------------------------------
    def create_session(self, user_id: str | None = None) -> AnalysisSession:
        session = AnalysisSession(user_id=user_id)
        self._db.add(session)
        self._db.flush()
        return session

    def get_session(self, session_id: str) -> AnalysisSession:
        obj = self._db.get(AnalysisSession, session_id)
        if obj is None:
            raise NotFoundError(f"Analysis session '{session_id}' not found")
        return obj

    def set_status(
        self,
        session_id: str,
        status: str,
        error: str | None = None,
        overall_score: float | None = None,
    ) -> None:
        from datetime import datetime, timezone

        session = self.get_session(session_id)
        session.status = status
        session.error = error
        if overall_score is not None:
            session.overall_score = overall_score
        if status in {"completed", "failed"}:
            session.completed_at = datetime.now(timezone.utc)

    # -- documents ----------------------------------------------------------
    def add_document(
        self,
        session_id: str,
        kind: str,
        filename: str,
        content_type: str,
        text_content: str,
    ) -> Document:
        doc = Document(
            session_id=session_id,
            kind=kind,
            filename=filename,
            content_type=content_type,
            text_content=text_content,
        )
        self._db.add(doc)
        self._db.flush()
        return doc

    def get_document(self, session_id: str, kind: str) -> Document:
        stmt = select(Document).where(
            Document.session_id == session_id, Document.kind == kind
        )
        doc = self._db.scalars(stmt).first()
        if doc is None:
            raise NotFoundError(f"No '{kind}' document in session '{session_id}'")
        return doc

    # -- results ------------------------------------------------------------
    def save_result(
        self,
        session_id: str,
        *,
        candidate_profile: dict | None,
        job_profile: dict | None,
        skill_gap: dict | None,
        match_score: dict | None,
        roadmap: dict | None,
        errors: list[str],
    ) -> AnalysisResultRow:
        row = self._db.scalars(
            select(AnalysisResultRow).where(AnalysisResultRow.session_id == session_id)
        ).first()
        if row is None:
            row = AnalysisResultRow(session_id=session_id)
            self._db.add(row)
        row.candidate_profile = candidate_profile
        row.job_profile = job_profile
        row.skill_gap = skill_gap
        row.match_score = match_score
        row.roadmap = roadmap
        row.errors = errors
        self._db.flush()
        return row

    def get_result(self, session_id: str) -> AnalysisResultRow | None:
        session = self.get_session(session_id)
        return session.result
