"""ORM models. Import all model modules so create_all sees every table."""

from app.models.analysis import (  # noqa: F401
    AnalysisResultRow,
    AnalysisSession,
    Base,
    Document,
)
from app.models.jobs import (  # noqa: F401
    JobMatchRow,
    JobRow,
    JobSearchSession,
    JobSourceRecord,
)
from app.models.applications import (  # noqa: F401
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

__all__ = [
    "Base",
    "Document",
    "AnalysisSession",
    "AnalysisResultRow",
    "JobSearchSession",
    "JobRow",
    "JobSourceRecord",
    "JobMatchRow",
    "ApplicationRow",
    "ApplicationEventRow",
    "ResumeVersionRow",
    "ResumeChangeRecordRow",
    "CoverLetterRow",
    "CompanyProfileRow",
    "CompanyResearchRow",
    "ApplicationQuestionRow",
    "ChecklistItemRow",
]
