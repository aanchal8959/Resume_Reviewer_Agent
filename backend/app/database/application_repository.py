"""Repository for Phase 3 application tracking and copilot artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session as OrmSession

from app.models.analysis import AnalysisResultRow, AnalysisSession
from app.models.applications import (
    ApplicationEventRow,
    ApplicationQuestionRow,
    ApplicationRow,
    ChecklistItemRow,
    CompanyProfileRow,
    CompanyResearchRow,
    CoverLetterRow,
    ResumeChangeRecordRow,
    ResumeVersionRow,
)
from app.models.jobs import JobMatchRow, JobRow
from app.schemas.applications import ApplicationEventType


class ApplicationNotFoundError(Exception):
    pass


class TerminalStateError(Exception):
    """Status change attempted on a terminal-state application."""


class ApplicationRepository:
    def __init__(self, db: OrmSession) -> None:
        self._db = db

    # -- applications ----------------------------------------------------------
    def create_application(self, job_id: str, resume_session_id: str) -> ApplicationRow:
        row = ApplicationRow(job_id=job_id, resume_session_id=resume_session_id)
        self._db.add(row)
        self._db.flush()
        self.add_event(row.id, ApplicationEventType.CREATED,
                       notes="Application created")
        return row

    def get_application(self, application_id: str) -> ApplicationRow:
        row = self._db.get(ApplicationRow, application_id)
        if row is None:
            raise ApplicationNotFoundError(
                f"Application '{application_id}' not found"
            )
        return row

    def list_applications(
        self,
        status: str | None = None,
        company: str | None = None,
        role: str | None = None,
    ) -> list[tuple[ApplicationRow, JobRow]]:
        stmt = select(ApplicationRow, JobRow).join(
            JobRow, ApplicationRow.job_id == JobRow.id
        ).order_by(desc(ApplicationRow.updated_at))
        if status:
            stmt = stmt.where(ApplicationRow.status == status.upper())
        if company:
            stmt = stmt.where(JobRow.company.ilike(f"%{company}%"))
        if role:
            stmt = stmt.where(JobRow.title.ilike(f"%{role}%"))
        return [(app, job) for app, job in self._db.execute(stmt)]

    def set_status(self, application_id: str, status: str,
                   notes: str | None = None) -> ApplicationRow:
        row = self.get_application(application_id)
        previous = row.status
        row.status = status
        if status == "APPLIED" and row.applied_at is None:
            row.applied_at = datetime.now(timezone.utc)
        event_type = {
            "APPLIED": ApplicationEventType.APPLIED,
            "OA_RECEIVED": ApplicationEventType.OA_RECEIVED,
            "INTERVIEW": ApplicationEventType.INTERVIEW_SCHEDULED,
            "OFFER": ApplicationEventType.OFFER,
            "REJECTED": ApplicationEventType.REJECTED,
            "WITHDRAWN": ApplicationEventType.WITHDRAWN,
        }.get(status)
        if event_type is not None:
            self.add_event(application_id, event_type, notes=notes or status)
        else:
            self.add_event(
                application_id, ApplicationEventType.STATUS_CHANGED,
                notes=notes or f"{previous} → {status}",
            )
        return row

    def set_notes(self, application_id: str, notes: str) -> ApplicationRow:
        row = self.get_application(application_id)
        row.notes = notes
        self.add_event(application_id, ApplicationEventType.NOTE_ADDED,
                       notes="Notes updated")
        return row

    # -- events ------------------------------------------------------------------
    def add_event(self, application_id: str, event: ApplicationEventType | str,
                  notes: str | None = None) -> None:
        self._db.add(ApplicationEventRow(
            application_id=application_id,
            event=event.value if isinstance(event, ApplicationEventType) else str(event),
            notes=notes,
        ))
        self._db.flush()

    # -- resume versions -------------------------------------------------------
    def latest_resume_version(self, application_id: str) -> ResumeVersionRow | None:
        return self._db.scalars(
            select(ResumeVersionRow)
            .where(ResumeVersionRow.application_id == application_id)
            .order_by(desc(ResumeVersionRow.version))
        ).first()

    def all_resume_versions(self, application_id: str) -> list[ResumeVersionRow]:
        return list(self._db.scalars(
            select(ResumeVersionRow)
            .where(ResumeVersionRow.application_id == application_id)
            .order_by(desc(ResumeVersionRow.version))
        ))

    def save_resume_version(
        self,
        application_id: str,
        base_resume_session_id: str,
        job_id: str,
        content_markdown: str,
        truthfulness_checked: bool,
        unsupported_count: int,
        changes: list[dict],
    ) -> ResumeVersionRow:
        last_version = self._db.scalar(
            select(ResumeVersionRow.version)
            .where(ResumeVersionRow.application_id == application_id)
            .order_by(desc(ResumeVersionRow.version))
            .limit(1)
        ) or 0
        version_row = ResumeVersionRow(
            application_id=application_id,
            base_resume_session_id=base_resume_session_id,
            job_id=job_id,
            version=last_version + 1,
            title=f"Tailored v{last_version + 1}",
            content_markdown=content_markdown,
            truthfulness_checked=truthfulness_checked,
            unsupported_claims_count=unsupported_count,
        )
        self._db.add(version_row)
        self._db.flush()
        for position, change in enumerate(changes):
            self._db.add(ResumeChangeRecordRow(
                resume_version_id=version_row.id,
                section=change["section"],
                original_text=change["original"],
                updated_text=change["updated"],
                reason=change.get("reason"),
                change_type=str(change.get("type", "clarity")),
                supported=bool(change.get("supported", True)),
                warning=change.get("warning"),
                position=position,
            ))
        self._db.flush()
        return version_row

    def approve_resume_version(self, application_id: str) -> ResumeVersionRow | None:
        version = self.latest_resume_version(application_id)
        if version is not None:
            version.approved = True
        return version

    # -- cover letters -----------------------------------------------------------
    def latest_cover_letter(self, application_id: str) -> CoverLetterRow | None:
        return self._db.scalars(
            select(CoverLetterRow)
            .where(CoverLetterRow.application_id == application_id)
            .order_by(desc(CoverLetterRow.created_at))
        ).first()

    def save_cover_letter(self, application_id: str, content_text: str,
                          word_count: int, generated_with: str) -> CoverLetterRow:
        self._db.execute(
            delete(CoverLetterRow).where(
                CoverLetterRow.application_id == application_id
            )
        )
        row = CoverLetterRow(
            application_id=application_id,
            content_text=content_text,
            word_count=word_count,
            generated_with=generated_with,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def approve_cover_letter(self, application_id: str) -> CoverLetterRow | None:
        letter = self.latest_cover_letter(application_id)
        if letter is not None:
            letter.approved = True
        return letter

    # -- company research ---------------------------------------------------------
    def cached_company_profile(self, company_name: str, source: str) -> dict | None:
        row = self._db.scalars(
            select(CompanyProfileRow).where(
                CompanyProfileRow.company_name == company_name.strip().lower(),
                CompanyProfileRow.source == source,
            )
        ).first()
        return row.payload if row else None

    def cache_company_profile(self, company_name: str, source: str,
                              payload: dict) -> None:
        exists = self.cached_company_profile(company_name, source) is not None
        if not exists:
            self._db.add(CompanyProfileRow(
                company_name=company_name.strip().lower(),
                source=source,
                payload=payload,
            ))
            self._db.flush()

    def get_research(self, application_id: str) -> CompanyResearchRow | None:
        return self._db.scalars(
            select(CompanyResearchRow).where(
                CompanyResearchRow.application_id == application_id
            )
        ).first()

    def save_research(self, application_id: str, company_info: dict,
                      insights: dict) -> CompanyResearchRow:
        row = self.get_research(application_id)
        if row is None:
            row = CompanyResearchRow(application_id=application_id,
                                     company_info=company_info, insights=insights)
            self._db.add(row)
        else:
            row.company_info = company_info
            row.insights = insights
        self._db.flush()
        self.add_event(application_id, ApplicationEventType.COMPANY_RESEARCH)
        return row

    # -- questions ------------------------------------------------------------------
    def replace_questions(self, application_id: str,
                          items: list[dict]) -> list[ApplicationQuestionRow]:
        self._db.execute(delete(ApplicationQuestionRow).where(
            ApplicationQuestionRow.application_id == application_id
        ))
        rows = [
            ApplicationQuestionRow(
                application_id=application_id,
                question=item["question"],
                suggested_answer=item["suggested_answer"],
                category=item.get("category", "behavioral"),
                order_index=index,
            )
            for index, item in enumerate(items)
        ]
        self._db.add_all(rows)
        self._db.flush()
        self.add_event(application_id, ApplicationEventType.QUESTIONS_GENERATED)
        return rows

    # -- checklist --------------------------------------------------------------
    def ensure_checklist(self, application_id: str) -> None:
        existing = self._db.scalars(select(ChecklistItemRow).where(
            ChecklistItemRow.application_id == application_id
        )).all()
        if existing:
            return
        defaults = [
            ("review_job", "Review job description", True, True),
            ("resume_tailored", "Resume tailored", False, True),
            ("changes_reviewed", "Review resume changes & warnings", False, True),
            ("cover_letter", "Cover letter prepared", False, True),
            ("company_researched", "Company researched", False, True),
            ("questions_reviewed", "Application questions reviewed", False, True),
            ("ready_marked", "Marked as ready to apply", False, True),
            ("applied_externally", "Applied on the company website (you submit!)", False, False),
        ]
        for position, (key, label, done, auto) in enumerate(defaults):
            self._db.add(ChecklistItemRow(
                application_id=application_id,
                key=key,
                label=label,
                done=done,
                auto=auto,
                position=position,
            ))
        self._db.flush()

    def checklist_items(self, application_id: str) -> list[ChecklistItemRow]:
        return list(self._db.scalars(
            select(ChecklistItemRow)
            .where(ChecklistItemRow.application_id == application_id)
            .order_by(ChecklistItemRow.position)
        ))

    def toggle_checklist_item(self, application_id: str, key: str, done: bool) -> ChecklistItemRow:
        row = self._db.scalars(select(ChecklistItemRow).where(
            ChecklistItemRow.application_id == application_id,
            ChecklistItemRow.key == key,
        )).first()
        if row is None:
            raise ApplicationNotFoundError(f"Checklist item '{key}' not found")
        row.done = done
        return row

    # -- helpers used by analytics -----------------------------------------------
    def all_applications_with_matches(self) -> list[tuple[ApplicationRow, float | None]]:
        results: list[tuple[ApplicationRow, float | None]] = []
        apps = list(self._db.scalars(select(ApplicationRow)))
        for app in apps:
            match_payload = self._db.scalars(
                select(JobMatchRow.payload)
                .where(JobMatchRow.job_id == app.job_id)
                .order_by(desc(JobMatchRow.created_at))
                .limit(1)
            ).first()
            overall = match_payload.get("overall_match") if match_payload else None
            results.append((app, overall))
        return results

    def latest_completed_resume_session(self) -> AnalysisSession | None:
        return self._db.scalars(
            select(AnalysisSession)
            .join(AnalysisResultRow, AnalysisResultRow.session_id == AnalysisSession.id)
            .where(AnalysisSession.status == "completed")
            .order_by(desc(AnalysisSession.completed_at))
        ).first()
