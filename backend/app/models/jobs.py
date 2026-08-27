"""Phase 2 SQLAlchemy models: job discovery, normalization and matching."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.analysis import Base, _uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobSearchSession(Base):
    """One discovery run for one candidate resume session."""

    __tablename__ = "job_search_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source_session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | searching | processing | completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    query_json: Mapped[dict] = mapped_column(JSON)
    strategy_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    discovered_count: Mapped[int] = mapped_column(default=0)
    unique_count: Mapped[int] = mapped_column(default=0)
    top_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRow(Base):
    """Canonical normalized job (deduplicated across sources)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)

    title: Mapped[str] = mapped_column(String(256))
    company: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")

    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    work_mode: Mapped[str] = mapped_column(String(16), default="unknown")
    employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    experience_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(32), nullable=True)

    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_source: Mapped[str] = mapped_column(String(64), default="unknown")
    source_type: Mapped[str] = mapped_column(String(8), default="REAL")
    source_job_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # --- Phase 4: lifecycle / freshness ---
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url_status: Mapped[str] = mapped_column(String(12), default="UNKNOWN")

    source_records: Mapped[list["JobSourceRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobSourceRecord(Base):
    """Provenance: where each copy of a job was seen."""

    __tablename__ = "job_source_records"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_source_job_id"),
        Index("ix_source_records_job", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id"))
    source: Mapped[str] = mapped_column(String(64))
    source_job_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    job: Mapped[JobRow] = relationship(back_populates="source_records")


class JobMatchRow(Base):
    """Cached candidate-vs-job match for a given search session."""

    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("search_id", "job_id", name="uq_match_search_job"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    search_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("job_search_sessions.id"), index=True
    )
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id"), index=True)
    candidate_session_id: Mapped[str] = mapped_column(String(32), index=True)
    overall_match: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
