"""Application Copilot service: the Phase 3 business-logic core."""

from __future__ import annotations

from sqlalchemy import desc, select

from app.agents.company_research_agent import (
    CompanyResearchAgent,
    UnknownCompanyError,
)
from app.agents.copilot_agents import ApplicationQuestionsAgent, CoverLetterAgent
from app.config import get_settings
from app.database.application_repository import (
    ApplicationNotFoundError,
    ApplicationRepository,
    TerminalStateError,
)
from app.database.database import get_database
from app.database.job_repository import JobRepository
from app.database.repository import NotFoundError, SessionRepository
from app.models.jobs import JobMatchRow
from app.schemas.applications import (
    TERMINAL_STATUSES,
    ApplicationAnalytics,
    ApplicationDetail,
    ApplicationEventType,
    ApplicationOut,
    ApplicationQuestionItem,
    ApplicationStatus,
    ChecklistItem,
    CompanyInfo,
    CompanyInsights,
    CoverLetterDraft,
    EventOut,
    JobSummary,
    ResumeChange,
    SmartInsights,
    TailoredResume,
)
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.analysis_runner import _build_provider
from app.services.company_research.base import CompanyResearchError, get_company_source
from app.services.gap_classifier import classify_skill_gaps
from app.services.resume_tailor import ResumeTailoringService
from app.services.skill_normalizer import get_skill_normalizer


def _latest_match_overall(db, job_id: str) -> float | None:
    payload = db.scalars(
        select(JobMatchRow.payload)
        .where(JobMatchRow.job_id == job_id)
        .order_by(desc(JobMatchRow.created_at))
        .limit(1)
    ).first()
    return float(payload["overall_match"]) if payload else None


class ApplicationService:
    """High-level API used by routes and the copilot LangGraph pipeline."""

    # ------------------------------------------------------------- create/read
    def create_application(
        self, job_id: str, resume_session_id: str | None = None, user_id: str | None = None
    ) -> str:
        database = get_database()
        with database.session() as db:
            try:
                JobRepository(db).get_job_row(job_id)
            except NotFoundError as exc:
                raise ApplicationNotFoundError(f"Job '{job_id}' not found") from exc
            session_id = self._resolve_resume_session(db, resume_session_id)
            repo = ApplicationRepository(db)
            application = repo.create_application(job_id, session_id, user_id=user_id)
            repo.ensure_checklist(application.id)
            return application.id

    @staticmethod
    def _resolve_resume_session(db, resume_session_id: str | None) -> str:
        if resume_session_id:
            try:
                SessionRepository(db).get_document(resume_session_id, "resume")
            except NotFoundError as exc:
                raise ApplicationNotFoundError(
                    f"No resume found in session '{resume_session_id}'."
                ) from exc
            return resume_session_id
        latest = ApplicationRepository(db).latest_completed_resume_session()
        if latest is None:
            raise ApplicationNotFoundError(
                "No analyzed resume available. Run a Phase 1 analysis first."
            )
        return latest.id

    def _load_job_and_candidate(self, application_id: str):
        database = get_database()
        with database.session() as db:
            repo = ApplicationRepository(db)
            app_row = repo.get_application(application_id)
            job_row = JobRepository(db).get_job_row(app_row.job_id)
        candidate = self._candidate_profile(app_row.resume_session_id)
        job_profile = self._job_to_profile(job_row)
        return app_row, job_row, candidate, job_profile

    @staticmethod
    def _job_to_profile(job_row) -> JobProfile:
        return JobProfile(
            role=job_row.title,
            required_experience_years=job_row.experience_min,
            required_skills=list(job_row.required_skills or []),
            preferred_skills=list(job_row.preferred_skills or []),
        )

    def get_detail(self, application_id: str) -> ApplicationDetail:
        database = get_database()
        with database.session() as db:
            repo = ApplicationRepository(db)
            app_row = repo.get_application(application_id)
            job_row = JobRepository(db).get_job_row(app_row.job_id)

            detail = ApplicationDetail(
                id=app_row.id,
                job=JobSummary(
                    id=job_row.id, title=job_row.title, company=job_row.company,
                    location=job_row.location, work_mode=job_row.work_mode,
                    application_url=job_row.application_url,
                ),
                status=ApplicationStatus(app_row.status),
                overall_match=_latest_match_overall(db, app_row.job_id),
                applied_at=app_row.applied_at,
                notes=app_row.notes or "",
                next_action=self._NEXT_ACTION.get(app_row.status, "-"),
                created_at=app_row.created_at,
                updated_at=app_row.updated_at,
                timeline=[
                    EventOut(id=e.id, event=e.event, notes=e.notes,
                             created_at=e.created_at)
                    for e in app_row.events
                ],
                checklist=[
                    ChecklistItem(key=i.key, label=i.label, done=i.done, auto=i.auto)
                    for i in repo.checklist_items(application_id)
                ],
            )
            version = repo.latest_resume_version(application_id)
            if version is not None:
                change_rows = sorted(version.changes, key=lambda c: c.position)
                detail.tailored_resume = TailoredResume(
                    content_markdown=version.content_markdown,
                    changes=[
                        ResumeChange(
                            section=c.section, original=c.original_text,
                            updated=c.updated_text, reason=c.reason,
                            type=c.change_type, supported=c.supported,
                            warning=c.warning,
                        )
                        for c in change_rows
                    ],
                    summary=f"Version {version.version} - tailored for this role.",
                    truthfulness_checked=version.truthfulness_checked,
                    unsupported_claims_count=version.unsupported_claims_count,
                )
            letter = repo.latest_cover_letter(application_id)
            if letter is not None:
                detail.cover_letter = CoverLetterDraft(
                    content_text=letter.content_text,
                    word_count=letter.word_count,
                    generated_with=letter.generated_with,
                    approved=letter.approved,
                )
            research = repo.get_research(application_id)
            if research is not None:
                detail.company_info = CompanyInfo(**research.company_info)
                detail.company_insights = CompanyInsights(**research.insights)
            detail.questions = [
                ApplicationQuestionItem(
                    question=q.question, suggested_answer=q.suggested_answer,
                    category=q.category, order_index=q.order_index,
                )
                for q in sorted(app_row.questions, key=lambda x: x.order_index)
            ]
            return detail

    def list_applications(self, status=None, company=None,
                          role=None) -> list[ApplicationOut]:
        database = get_database()
        with database.session() as db:
            pairs = ApplicationRepository(db).list_applications(
                status=status, company=company, role=role
            )
            out: list[ApplicationOut] = []
            for app_row, job_row in pairs:
                out.append(ApplicationOut(
                    id=app_row.id,
                    job=JobSummary(
                        id=job_row.id, title=job_row.title,
                        company=job_row.company, location=job_row.location,
                        work_mode=job_row.work_mode,
                        application_url=job_row.application_url,
                    ),
                    status=ApplicationStatus(app_row.status),
                    overall_match=_latest_match_overall(db, app_row.job_id),
                    applied_at=app_row.applied_at,
                    notes=app_row.notes or "",
                    next_action=self._NEXT_ACTION.get(app_row.status, "-"),
                    created_at=app_row.created_at,
                    updated_at=app_row.updated_at,
                ))
            return out

    # ------------------------------------------------------------------ mutate
    def set_status(self, application_id: str, status: ApplicationStatus,
                   notes: str | None = None) -> ApplicationDetail:
        current = self._current_status(application_id)
        if current in TERMINAL_STATUSES and current != status:
            raise TerminalStateError(
                f"Application is {current.value} (terminal); status can no "
                "longer change. Create a new application instead."
            )
        with get_database().session() as db:
            ApplicationRepository(db).set_status(application_id, status.value, notes)
        if status == ApplicationStatus.READY_TO_APPLY:
            self._toggle_item(application_id, "ready_marked", True)
        if status == ApplicationStatus.APPLIED:
            self._toggle_item(application_id, "applied_externally", True)
        return self.get_detail(application_id)

    def set_notes(self, application_id: str, notes: str) -> ApplicationDetail:
        with get_database().session() as db:
            ApplicationRepository(db).set_notes(application_id, notes)
        return self.get_detail(application_id)

    # ------------------------------------------------------------ copilot steps
    def tailor_resume(self, application_id: str,
                      regenerate: bool = False) -> ApplicationDetail:
        database = get_database()
        with database.session() as db:
            repo = ApplicationRepository(db)
            app_row = repo.get_application(application_id)
            existing = repo.latest_resume_version(application_id)
            if existing is not None and not regenerate:
                return self.get_detail(application_id)
            resume_doc = SessionRepository(db).get_document(
                app_row.resume_session_id, "resume"
            )
            resume_text = resume_doc.text_content
        _, job_row, candidate, job_profile = \
            self._load_job_and_candidate(application_id)

        gap = classify_skill_gaps(candidate, job_profile)
        tailored = ResumeTailoringService(
            _build_provider(get_settings()), get_skill_normalizer()
        ).tailor(resume_text, candidate, job_profile, missing_skills=gap.missing[:3])

        with database.session() as db:
            repo = ApplicationRepository(db)
            repo.save_resume_version(
                application_id,
                base_resume_session_id=app_row.resume_session_id,
                job_id=app_row.job_id,
                content_markdown=tailored.content_markdown,
                truthfulness_checked=tailored.truthfulness_checked,
                unsupported_count=tailored.unsupported_claims_count,
                changes=[c.model_dump(mode="json") for c in tailored.changes],
            )
            repo.add_event(
                application_id, ApplicationEventType.RESUME_TAILORED,
                notes=(f"{len(tailored.changes)} edits; "
                       f"{tailored.unsupported_claims_count} flagged claim(s)"),
            )
            repo.toggle_checklist_item(application_id, "resume_tailored", True)
        return self.get_detail(application_id)

    def approve_resume(self, application_id: str) -> ApplicationDetail:
        with get_database().session() as db:
            repo = ApplicationRepository(db)
            repo.approve_resume_version(application_id)
            repo.toggle_checklist_item(application_id, "changes_reviewed", True)
            repo.add_event(application_id, "RESUME_APPROVED",
                           notes="User approved tailored resume")
        return self.get_detail(application_id)

    def generate_cover_letter(self, application_id: str,
                              regenerate: bool = False) -> ApplicationDetail:
        database = get_database()
        with database.session() as db:
            repo = ApplicationRepository(db)
            if repo.latest_cover_letter(application_id) is not None and not regenerate:
                return self.get_detail(application_id)
        app_row, job_row, candidate, job_profile = \
            self._load_job_and_candidate(application_id)
        detail = self.get_detail(application_id)
        gap = classify_skill_gaps(candidate, job_profile)
        draft = CoverLetterAgent(_build_provider(get_settings())).generate(
            candidate=candidate,
            job_title=job_row.title,
            company=job_row.company,
            matched_skills=gap.matched,
            company_info=detail.company_info,
            tailored_context=(detail.tailored_resume.summary
                              if detail.tailored_resume else None),
        )
        with database.session() as db:
            repo = ApplicationRepository(db)
            repo.save_cover_letter(application_id, draft.content_text,
                                   draft.word_count, draft.generated_with)
            repo.add_event(application_id, ApplicationEventType.COVER_LETTER,
                           notes=f"{draft.generated_with}, {draft.word_count} words")
            repo.toggle_checklist_item(application_id, "cover_letter", True)
        return self.get_detail(application_id)

    def update_cover_letter(self, application_id: str,
                            content_text: str) -> ApplicationDetail:
        with get_database().session() as db:
            repo = ApplicationRepository(db)
            existing = repo.latest_cover_letter(application_id)
            repo.save_cover_letter(
                application_id, content_text, len(content_text.split()),
                generated_with=(existing.generated_with if existing else "user-edited"),
            )
            repo.add_event(application_id, "COVER_LETTER_EDITED",
                           notes="User edited cover letter")
        return self.get_detail(application_id)

    def approve_cover_letter(self, application_id: str) -> ApplicationDetail:
        with get_database().session() as db:
            repo = ApplicationRepository(db)
            repo.approve_cover_letter(application_id)
            repo.add_event(application_id, "COVER_LETTER_APPROVED",
                           notes="User approved cover letter")
        return self.get_detail(application_id)

    def research_company(self, application_id: str) -> ApplicationDetail:
        database = get_database()
        with database.session() as db:
            app_row = ApplicationRepository(db).get_application(application_id)
            job_row = JobRepository(db).get_job_row(app_row.job_id)
        agent = CompanyResearchAgent(get_company_source())
        job_skills = [str(s) for s in (job_row.required_skills or [])]
        prep_areas = list(dict.fromkeys(job_skills))[:4] or \
            [f"the {job_row.title} core stack"]
        try:
            info, insights = agent.research(job_row.company, job_row.title,
                                            job_skills, prep_areas)
        except UnknownCompanyError:
            info = CompanyInfo(name=job_row.company, source="none", is_mock=False)
            from app.services.copilot_templates import build_company_insights

            insights = CompanyInsights(**build_company_insights(
                info, job_row.title, job_skills, prep_areas
            ))
        except CompanyResearchError:
            raise
        with database.session() as db:
            repo = ApplicationRepository(db)
            repo.cache_company_profile(info.name, info.source,
                                       info.model_dump(mode="json"))
            repo.save_research(application_id, info.model_dump(mode="json"),
                               insights.model_dump())
            repo.toggle_checklist_item(application_id, "company_researched", True)
        return self.get_detail(application_id)

    def generate_questions(self, application_id: str,
                           regenerate: bool = False) -> ApplicationDetail:
        detail = self.get_detail(application_id)
        if detail.questions and not regenerate:
            return detail
        app_row, job_row, candidate, job_profile = \
            self._load_job_and_candidate(application_id)
        gap = classify_skill_gaps(candidate, job_profile)
        salary_min, salary_max = job_row.salary_min, job_row.salary_max
        items = ApplicationQuestionsAgent(_build_provider(get_settings())).generate(
            candidate=candidate,
            job_title=job_row.title,
            required_skills=[str(s) for s in (job_row.required_skills or [])],
            missing_skills=gap.missing[:4],
            salary_text=(
                f"{salary_min:g}-{salary_max:g} LPA"
                if salary_min is not None and salary_max is not None else None
            ),
            skill_evidence=self._skill_evidence(candidate, gap.matched),
        )
        database = get_database()
        with database.session() as db:
            repo = ApplicationRepository(db)
            repo.replace_questions(application_id, [i.model_dump() for i in items])
            repo.toggle_checklist_item(application_id, "questions_reviewed", True)
        return self.get_detail(application_id)

    def toggle_checklist(self, application_id: str, key: str,
                         done: bool) -> ApplicationDetail:
        with get_database().session() as db:
            ApplicationRepository(db).toggle_checklist_item(application_id, key, done)
        return self.get_detail(application_id)

    def prepare_all(self, application_id: str) -> ApplicationDetail:
        """Full copilot run used by POST /applications/{id}/prepare."""
        self.tailor_resume(application_id)
        try:
            self.research_company(application_id)
        except CompanyResearchError:
            pass  # degraded research must not block preparation
        self.generate_cover_letter(application_id)
        self.generate_questions(application_id)
        return self.get_detail(application_id)

    # ---------------------------------------------------------------- analytics
    def analytics(self) -> ApplicationAnalytics:
        database = get_database()
        with database.session() as db:
            rows = ApplicationRepository(db).all_applications_with_matches()
        counts = {status.value: 0 for status in ApplicationStatus}
        matches: list[float] = []
        for app_row, overall in rows:
            if app_row.status in counts:
                counts[app_row.status] += 1
            if overall is not None:
                matches.append(overall)
        total = len(rows)
        reached_applied = sum(
            counts[s] for s in ("APPLIED", "OA_RECEIVED", "INTERVIEW",
                                "OFFER", "REJECTED")
        )
        reached_interview = counts["INTERVIEW"] + counts["OFFER"]

        def pct(part: int, whole: int) -> float:
            return round(part / whole * 100, 1) if whole else 0.0

        return ApplicationAnalytics(
            total_applications=total,
            saved=counts["SAVED"], preparing=counts["PREPARING"],
            ready_to_apply=counts["READY_TO_APPLY"], applied=counts["APPLIED"],
            oa_received=counts["OA_RECEIVED"], interviews=reached_interview,
            offers=counts["OFFER"], rejected=counts["REJECTED"],
            withdrawn=counts["WITHDRAWN"],
            interview_rate=pct(reached_interview, reached_applied),
            offer_rate=pct(counts["OFFER"], reached_applied),
            rejection_rate=pct(counts["REJECTED"], total),
            average_match_score=(
                round(sum(matches) / len(matches), 1) if matches else None
            ),
        )

    def smart_insights(self) -> SmartInsights:
        database = get_database()
        with database.session() as db:
            rows = ApplicationRepository(db).all_applications_with_matches()
        applied_statuses = {"APPLIED", "OA_RECEIVED", "INTERVIEW", "OFFER", "REJECTED"}
        high = [0, 0]  # applied, interviews
        low = [0, 0]
        for app_row, overall in rows:
            if app_row.status not in applied_statuses:
                continue
            bucket = high if (overall is not None and overall >= 85) else low
            bucket[0] += 1
            bucket[1] += int(app_row.status in {"INTERVIEW", "OFFER"})
        if len(rows) < 3 or high[0] + low[0] < 3:
            return SmartInsights(insights=[], sufficient_data=False)

        def rate(bucket: list[int]) -> float:
            return bucket[1] / bucket[0] * 100 if bucket[0] else 0.0

        insights: list[str] = []
        high_rate, low_rate = rate(high), rate(low)
        if high[0]:
            insights.append(
                f"Applications with an 85%+ match reach interviews at "
                f"{high_rate:.0f}% vs {low_rate:.0f}% for weaker matches."
            )
            insights.append(
                "Prioritize jobs where match > 80%, experience fits the band, "
                "and required-skill coverage > 75%."
            )
        else:
            insights.append(
                "Interview conversion is not yet correlated with match score."
            )
        offers = sum(1 for app_row, _ in rows if app_row.status == "OFFER")
        if offers:
            insights.append(f"{offers} offer(s) received so far.")
        return SmartInsights(insights=insights, sufficient_data=True)

    def export_resume_version(self, application_id: str):
        database = get_database()
        with database.session() as db:
            version = ApplicationRepository(db).latest_resume_version(application_id)
            if version is None:
                raise ApplicationNotFoundError("No tailored resume yet.")
            content = version.content_markdown
            title = f"{version.title}"
        return content, title

    def export_cover_letter(self, application_id: str):
        database = get_database()
        with database.session() as db:
            letter = ApplicationRepository(db).latest_cover_letter(application_id)
            if letter is None:
                raise ApplicationNotFoundError("No cover letter yet.")
            return letter.content_text

    # --------------------------------------------------------------- internals
    _NEXT_ACTION = {
        "SAVED": "Start preparing the application",
        "PREPARING": "Complete resume, cover letter and research",
        "READY_TO_APPLY": "Open the application URL and submit externally",
        "APPLIED": "Prepare for assessments and interviews",
        "OA_RECEIVED": "Complete the online assessment",
        "INTERVIEW": "Prepare with the roadmap and question bank",
        "OFFER": "Evaluate the offer",
        "REJECTED": "Review gaps and apply to better-matched roles",
        "WITHDRAWN": "-",
    }

    def _current_status(self, application_id: str) -> ApplicationStatus:
        with get_database().session() as db:
            row = ApplicationRepository(db).get_application(application_id)
            return ApplicationStatus(row.status)

    def _toggle_item(self, application_id: str, key: str, done: bool) -> None:
        with get_database().session() as db:
            ApplicationRepository(db).toggle_checklist_item(application_id, key, done)

    def _candidate_profile(self, resume_session_id: str) -> CandidateProfile:
        database = get_database()
        with database.session() as db:
            result = SessionRepository(db).get_result(resume_session_id)
            cached = result.candidate_profile if result else None
            try:
                resume_text = SessionRepository(db).get_document(
                    resume_session_id, "resume"
                ).text_content
            except NotFoundError:
                resume_text = None
        if cached:
            return CandidateProfile.model_validate(cached)
        if resume_text is None:
            raise ApplicationNotFoundError(
                "Candidate profile unavailable: no resume document for this session."
            )
        from app.agents.candidate_agent import CandidateProfileAgent
        from app.services.llm_service import get_llm_provider

        provider = get_llm_provider(get_settings())
        profile = CandidateProfileAgent(provider).run(resume_text)
        with database.session() as db:
            SessionRepository(db).save_result(
                resume_session_id, candidate_profile=profile.model_dump(),
                job_profile=None, skill_gap=None, match_score=None,
                roadmap=None, errors=[],
            )
        return profile

    @staticmethod
    def _skill_evidence(candidate: CandidateProfile,
                        matched: list[str]) -> dict[str, str]:
        evidence: dict[str, str] = {}
        for project in candidate.projects:
            for tech in project.technologies:
                evidence.setdefault(
                    tech.lower(),
                    f"project '{project.name}' using "
                    f"{', '.join(project.technologies[:4])}",
                )
        for skill in matched:
            evidence.setdefault(skill.lower(), f"listed skills ({skill})")
        return evidence


def _company_source():
    return get_company_source()


__all__ = [
    "ApplicationNotFoundError",
    "ApplicationService",
    "TerminalStateError",
]

