"""Repository for Phase 2 job discovery persistence."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models.jobs import JobMatchRow, JobRow, JobSearchSession, JobSourceRecord
from app.schemas.jobs import Job


def fingerprint_for(job: Job) -> str:
    """Stable identity for a normalized job (company + title + location)."""
    def clean(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    raw = "|".join((clean(job.company), clean(job.title), clean(job.location or "")))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class JobRepository:
    def __init__(self, db: OrmSession) -> None:
        self._db = db

    # -- search sessions -----------------------------------------------------
    def create_search_session(self, source_session_id: str, query: dict) -> JobSearchSession:
        row = JobSearchSession(source_session_id=source_session_id, query_json=query)
        self._db.add(row)
        self._db.flush()
        return row

    def get_search_session(self, search_id: str) -> JobSearchSession:
        row = self._db.get(JobSearchSession, search_id)
        if row is None:
            from app.database.repository import NotFoundError

            raise NotFoundError(f"Job search '{search_id}' not found")
        return row

    def set_search_status(
        self,
        search_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        row = self.get_search_session(search_id)
        row.status = status
        row.error = error
        if status in {"completed", "failed"}:
            row.completed_at = datetime.now(timezone.utc)

    def save_strategy(self, search_id: str, strategy: dict) -> None:
        self.get_search_session(search_id).strategy_json = strategy

    def save_recommendations(self, search_id: str, ordered_job_ids: list[dict],
                             discovered: int, unique: int, top_score: float | None) -> None:
        row = self.get_search_session(search_id)
        row.recommendations_json = ordered_job_ids
        row.discovered_count = discovered
        row.unique_count = unique
        row.top_score = top_score

    # -- jobs ------------------------------------------------------------------
    def upsert_canonical_jobs(self, jobs: list[Job]) -> dict[str, JobRow]:
        """Persist canonical jobs; returns fingerprint -> row mapping."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mapping: dict[str, JobRow] = {}
        for job in jobs:
            fingerprint = fingerprint_for(job)
            row = self._db.scalars(
                select(JobRow).where(JobRow.fingerprint == fingerprint)
            ).first()
            if row is None:
                row = JobRow(
                    fingerprint=fingerprint,
                    title=job.title,
                    company=job.company,
                    description=job.description,
                    location=job.location,
                    work_mode=job.work_mode or "unknown",
                    employment_type=job.employment_type,
                    experience_min=job.experience_min,
                    experience_max=job.experience_max,
                    experience_level=job.experience_level,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    salary_currency=job.salary_currency,
                    required_skills=job.required_skills,
                    preferred_skills=job.preferred_skills,
                    posted_at=job.posted_at,
                    application_url=job.application_url,
                    first_source=job.source,
                    source_type=job.source_type or "REAL",
                    source_job_id=job.source_job_id,
                    status="ACTIVE",
                    last_seen_at=now,
                )
                self._db.add(row)
                self._db.flush()
            else:
                # Re-encountered on a source: it is alive again and freshened.
                row.last_seen_at = now
                if row.status in {"UNKNOWN", "EXPIRED"}:
                    row.status = "ACTIVE"
                self._merge_into_row(row, job)
            for record in [SourceRecordLite(job.source, job.source_job_id, job.title,
                                            job.application_url)] + [
                SourceRecordLite(rec.source, rec.source_job_id, rec.title, rec.url)
                for rec in job.duplicate_of
            ]:
                self.add_source_record(row.id, record.source, record.source_job_id,
                                       record.raw_title, record.url)
            mapping[fingerprint] = row
        return mapping

    @staticmethod
    def _merge_into_row(row: JobRow, job: Job) -> None:
        if len(job.description) > len(row.description or ""):
            row.description = job.description
        if not row.salary_min and job.salary_min:
            row.salary_min = job.salary_min
            row.salary_max = job.salary_max
            row.salary_currency = job.salary_currency
        if row.work_mode == "unknown" and job.work_mode != "unknown":
            row.work_mode = job.work_mode
        row.required_skills = list(dict.fromkeys(
            list(row.required_skills or []) + list(job.required_skills)
        ))
        row.preferred_skills = list(dict.fromkeys(
            list(row.preferred_skills or []) + list(job.preferred_skills)
        ))

    def add_source_record(self, job_id: str, source: str, source_job_id: str | None,
                          raw_title: str | None, url: str | None) -> None:
        # The UNIQUE constraint is on (source, source_job_id) globally: if this
        # occurrence is already attached to any canonical job, leave it there.
        exists = self._db.scalars(
            select(JobSourceRecord).where(
                JobSourceRecord.source == source,
                JobSourceRecord.source_job_id == source_job_id,
            )
        ).first()
        if exists is not None:
            return
        self._db.add(
            JobSourceRecord(
                job_id=job_id,
                source=source,
                source_job_id=source_job_id,
                raw_title=raw_title,
                url=url,
            )
        )
        self._db.flush()

    def get_job_row(self, job_id: str) -> JobRow:
        row = self._db.get(JobRow, job_id)
        if row is None:
            from app.database.repository import NotFoundError

            raise NotFoundError(f"Job '{job_id}' not found")
        return row

    # -- matches ---------------------------------------------------------------
    def find_cached_match(self, candidate_session_id: str, fingerprint: str) -> dict | None:
        stmt = (
            select(JobMatchRow)
            .join(JobRow, JobMatchRow.job_id == JobRow.id)
            .where(
                JobMatchRow.candidate_session_id == candidate_session_id,
                JobRow.fingerprint == fingerprint,
            )
            .order_by(JobMatchRow.created_at.desc())
        )
        row = self._db.scalars(stmt).first()
        return row.payload if row is not None else None

    def save_match(self, search_id: str, candidate_session_id: str,
                   job_id: str, payload: dict, overall: float) -> JobMatchRow:
        existing = self._db.scalars(
            select(JobMatchRow).where(
                JobMatchRow.search_id == search_id,
                JobMatchRow.job_id == job_id,
            )
        ).first()
        if existing is not None:
            existing.payload = payload
            existing.overall_match = overall
            self._db.flush()
            return existing
        row = JobMatchRow(
            search_id=search_id,
            job_id=job_id,
            candidate_session_id=candidate_session_id,
            overall_match=overall,
            payload=payload,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def get_matches(self, search_id: str) -> list[JobMatchRow]:
        return list(self._db.scalars(
            select(JobMatchRow).where(JobMatchRow.search_id == search_id)
        ))


class SourceRecordLite:
    __slots__ = ("source", "source_job_id", "raw_title", "url")

    def __init__(self, source: str, source_job_id: str | None,
                 raw_title: str | None, url: str | None) -> None:
        self.source = source
        self.source_job_id = source_job_id
        self.raw_title = raw_title
        self.url = url
