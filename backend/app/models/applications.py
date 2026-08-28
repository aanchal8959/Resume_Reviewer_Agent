"""Phase 3 SQLAlchemy models: application copilot and tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.analysis import Base, _uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationRow(Base):
    """One candidate pursuing one job. Status is ALWAYS user-controlled."""

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id"), index=True)
    resume_session_id: Mapped[str] = mapped_column(String(32), index=True)

    status: Mapped[str] = mapped_column(String(24), default="PREPARING", index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    events: Mapped[list["ApplicationEventRow"]] = relationship(
        back_populates="application", cascade="all, delete-orphan",
        order_by="ApplicationEventRow.created_at",
    )
    resume_versions: Mapped[list["ResumeVersionRow"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    cover_letters: Mapped[list["CoverLetterRow"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    research: Mapped["CompanyResearchRow | None"] = relationship(
        back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    questions: Mapped[list["ApplicationQuestionRow"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    checklist: Mapped[list["ChecklistItemRow"]] = relationship(
        back_populates="application", cascade="all, delete-orphan",
        order_by="ChecklistItemRow.position",
    )


class ApplicationEventRow(Base):
    __tablename__ = "application_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id"), index=True
    )
    event: Mapped[str] = mapped_column(String(48))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[ApplicationRow] = relationship(back_populates="events")


class ResumeVersionRow(Base):
    """A job-specific version of the resume. The master is never modified."""

    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("application_id", "version", name="uq_resume_version"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id"), index=True
    )
    base_resume_session_id: Mapped[str] = mapped_column(String(32))
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(256), default="Tailored Resume")
    content_markdown: Mapped[str] = mapped_column(Text)
    truthfulness_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    unsupported_claims_count: Mapped[int] = mapped_column(Integer, default=0)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[ApplicationRow] = relationship(back_populates="resume_versions")
    changes: Mapped[list["ResumeChangeRecordRow"]] = relationship(
        back_populates="resume_version", cascade="all, delete-orphan"
    )


class ResumeChangeRecordRow(Base):
    __tablename__ = "resume_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    resume_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("resume_versions.id"), index=True
    )
    section: Mapped[str] = mapped_column(String(64))
    original_text: Mapped[str] = mapped_column(Text)
    updated_text: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(String(24), default="clarity")
    supported: Mapped[bool] = mapped_column(Boolean, default=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    resume_version: Mapped[ResumeVersionRow] = relationship(back_populates="changes")


class CoverLetterRow(Base):
    __tablename__ = "cover_letters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id"), index=True
    )
    content_text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_with: Mapped[str] = mapped_column(String(16), default="mock")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[ApplicationRow] = relationship(back_populates="cover_letters")


class CompanyProfileRow(Base):
    """Cached company information (mock or external source)."""

    __tablename__ = "company_profiles"
    __table_args__ = (
        UniqueConstraint("company_name", "source", name="uq_company_source"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    company_name: Mapped[str] = mapped_column(String(256), index=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CompanyResearchRow(Base):
    __tablename__ = "company_research"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id"), unique=True, index=True
    )
    company_info: Mapped[dict] = mapped_column(JSON)
    insights: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[ApplicationRow] = relationship(back_populates="research")


class ApplicationQuestionRow(Base):
    __tablename__ = "application_questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    suggested_answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(24), default="behavioral")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    application: Mapped[ApplicationRow] = relationship(back_populates="questions")


class ChecklistItemRow(Base):
    __tablename__ = "application_checklist_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(256))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    auto: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    application: Mapped[ApplicationRow] = relationship(back_populates="checklist")
