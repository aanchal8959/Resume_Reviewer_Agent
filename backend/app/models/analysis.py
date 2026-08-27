"""SQLAlchemy ORM models. Agents never import this module directly."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    """An uploaded resume or job description (text already extracted)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "resume" | "job_description"
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    text_content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped["AnalysisSession"] = relationship(back_populates="documents")


class AnalysisSession(Base):
    """One resume + one job description and the analysis produced for them."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | processing | completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    documents: Mapped[list[Document]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    result: Mapped["AnalysisResultRow | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class AnalysisResultRow(Base):
    """JSON snapshots of each agent's structured output."""

    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id"), unique=True, index=True
    )
    candidate_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    job_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    skill_gap: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    match_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    roadmap: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)

    session: Mapped[AnalysisSession] = relationship(back_populates="result")
