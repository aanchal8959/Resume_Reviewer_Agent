"""Phase 3 schemas: applications, tailoring, cover letters, research, analytics."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ApplicationStatus(str, Enum):
    SAVED = "SAVED"
    PREPARING = "PREPARING"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLIED = "APPLIED"
    OA_RECEIVED = "OA_RECEIVED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


TERMINAL_STATUSES = {ApplicationStatus.OFFER, ApplicationStatus.REJECTED,
                     ApplicationStatus.WITHDRAWN}


class ApplicationEventType(str, Enum):
    CREATED = "JOB_SAVED"
    RESUME_TAILORED = "RESUME_TAILORED"
    COVER_LETTER = "COVER_LETTER_GENERATED"
    COMPANY_RESEARCH = "COMPANY_RESEARCHED"
    QUESTIONS_GENERATED = "QUESTIONS_GENERATED"
    PREPARED = "APPLICATION_PREPARED"
    STATUS_CHANGED = "STATUS_CHANGED"
    NOTE_ADDED = "NOTE_ADDED"
    APPLIED = "APPLIED"
    OA_RECEIVED = "OA_RECEIVED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    OFFER = "OFFER_RECEIVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


# ---------------------------------------------------------------------------
# Resume tailoring
# ---------------------------------------------------------------------------


class ChangeType(str, Enum):
    CLARITY = "clarity"
    KEYWORD = "keyword"
    RELEVANCE = "relevance"
    STRUCTURE = "structure"


class ResumeChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section: str
    original: str
    updated: str
    reason: str
    type: ChangeType = ChangeType.CLARITY
    supported: bool = True
    warning: str | None = None


class TailoredResume(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content_markdown: str
    changes: list[ResumeChange] = Field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    truthfulness_checked: bool = False
    unsupported_claims_count: int = 0


class UnsupportedClaim(BaseModel):
    claim: str
    kind: str  # technology | company | title | education | experience | certification
    reason: str


class TruthfulnessReport(BaseModel):
    checked_claims: int = 0
    unsupported: list[UnsupportedClaim] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.unsupported


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------


class CompanyInfo(BaseModel):
    """Structured public information; None means genuinely unavailable."""

    model_config = ConfigDict(extra="ignore")

    name: str
    industry: str | None = None
    description: str | None = None
    products_services: list[str] = Field(default_factory=list)
    company_size: str | None = None
    headquarters: str | None = None
    technology_areas: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    website: str | None = None
    source: str = "unknown"
    is_mock: bool = False
    verified_fields: list[str] = Field(default_factory=list)
    inferred_fields: list[str] = Field(default_factory=list)


class CompanyInsights(BaseModel):
    what_they_do: str
    why_role_matters: str
    technology_environment: list[str]
    interview_prep_areas: list[str]


# ---------------------------------------------------------------------------
# Cover letter & questions
# ---------------------------------------------------------------------------


class CoverLetterDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content_text: str
    word_count: int = 0
    generated_with: str = "mock"  # mock | gemini
    approved: bool = False


class ApplicationQuestionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    suggested_answer: str
    category: str = "behavioral"  # behavioral | technical | practical
    order_index: int = 0


class QuestionSet(BaseModel):
    """Structured LLM output wrapping generated application questions."""

    model_config = ConfigDict(extra="ignore")

    items: list[ApplicationQuestionItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Checklist / applications API
# ---------------------------------------------------------------------------


class ChecklistItem(BaseModel):
    key: str
    label: str
    done: bool = False
    auto: bool = True  # auto-computed vs user-toggled


class CreateApplicationRequest(BaseModel):
    job_id: str
    resume_session_id: str | None = None


class StatusUpdateRequest(BaseModel):
    status: ApplicationStatus
    notes: str | None = None


class NotesUpdateRequest(BaseModel):
    notes: str = Field(min_length=1, max_length=8000)


class TailorResumeRequest(BaseModel):
    regenerate: bool = False


class CoverLetterGenerateRequest(BaseModel):
    regenerate: bool = False


class CoverLetterEditRequest(BaseModel):
    content_text: str = Field(min_length=1, max_length=20000)


class EventOut(BaseModel):
    id: str | None = None
    event: str
    notes: str | None = None
    created_at: datetime | None = None


class JobSummary(BaseModel):
    id: str | None = None
    title: str
    company: str
    location: str | None = None
    work_mode: str | None = None
    application_url: str | None = None


class ApplicationOut(BaseModel):
    id: str
    job: JobSummary
    status: ApplicationStatus
    overall_match: float | None = None
    applied_at: datetime | None = None
    notes: str = ""
    next_action: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationDetail(ApplicationOut):
    timeline: list[EventOut] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    tailored_resume: TailoredResume | None = None
    cover_letter: CoverLetterDraft | None = None
    company_info: CompanyInfo | None = None
    company_insights: CompanyInsights | None = None
    questions: list[ApplicationQuestionItem] = Field(default_factory=list)


class ApplicationAnalytics(BaseModel):
    total_applications: int
    saved: int
    preparing: int
    ready_to_apply: int
    applied: int
    oa_received: int
    interviews: int
    offers: int
    rejected: int
    withdrawn: int
    interview_rate: float
    offer_rate: float
    rejection_rate: float
    average_match_score: float | None = None


class SmartInsights(BaseModel):
    insights: list[str] = Field(default_factory=list)
    sufficient_data: bool = False
