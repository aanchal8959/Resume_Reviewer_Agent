"""Phase 2 schemas: job search, normalization, matching, ranking."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
SourceType = Literal["REAL", "MOCK"]
JobStatus = Literal["ACTIVE", "EXPIRED", "REMOVED", "UNKNOWN"]
UrlStatus = Literal["VALID", "INVALID", "UNKNOWN"]


# ---------------------------------------------------------------------------
# Discovery inputs
# ---------------------------------------------------------------------------


class JobSearchPreferences(BaseModel):
    """User-provided preferences that steer discovery and ranking."""

    model_config = ConfigDict(extra="ignore")

    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote: bool | None = None
    work_modes: list[WorkMode] = Field(default_factory=list)
    experience_min: float | None = Field(default=None, ge=0)
    experience_max: float | None = Field(default=None, ge=0)
    salary_min: float | None = Field(default=None, ge=0)  # LPA when INR
    employment_types: list[str] = Field(default_factory=list)
    min_match_percent: float | None = Field(default=None, ge=0, le=100)


class SearchStrategy(BaseModel):
    """The concrete queries the discovery agent will run per source."""

    model_config = ConfigDict(extra="ignore")

    queries: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    rationale: str | None = None


class JobSearchRequest(JobSearchPreferences):
    """POST /api/jobs/search body. `session_id` links the Phase 1 resume."""

    session_id: str
    refresh: bool = False  # bypass the TTL cache and query providers again


# ---------------------------------------------------------------------------
# Raw source record -> normalized job
# ---------------------------------------------------------------------------


class RawJob(BaseModel):
    """Loose representation returned by any JobSource before normalization."""

    model_config = ConfigDict(extra="allow")

    source: str
    source_type: SourceType = "REAL"
    source_job_id: str | None = None
    title: str
    company: str
    description: str = ""
    location: str | None = None
    work_mode: WorkMode | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    salary_text: str | None = None
    url: str | None = None
    posted_at: datetime | None = None


class Job(BaseModel):
    """Normalized job stored and matched against candidates."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    source: str = "unknown"
    source_type: SourceType = "REAL"
    source_job_id: str | None = None

    title: str
    company: str
    description: str = ""

    location: str | None = None
    work_mode: WorkMode = "unknown"
    employment_type: str | None = None

    experience_min: float | None = None
    experience_max: float | None = None
    experience_level: str | None = None

    salary_min: float | None = None  # LPA when INR
    salary_max: float | None = None
    salary_currency: str | None = None

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)

    posted_at: datetime | None = None
    application_url: str | None = None

    created_at: datetime | None = None
    duplicate_of: list["SourceRecord"] = Field(default_factory=list)

    # --- Phase 4: lifecycle / freshness metadata ---
    status: JobStatus = "ACTIVE"
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None
    url_status: UrlStatus = "UNKNOWN"


class SourceRecord(BaseModel):
    """One occurrence of a job on one source (dedup provenance)."""

    model_config = ConfigDict(extra="ignore")

    source: str
    source_job_id: str | None = None
    title: str | None = None
    url: str | None = None


# ---------------------------------------------------------------------------
# Matching / ranking output
# ---------------------------------------------------------------------------


class JobMatchBreakdown(BaseModel):
    """Component scores; None = not applicable (its weight was redistributed)."""

    required_skill_match: float | None = None
    preferred_skill_match: float | None = None
    role_match: float | None = None
    experience_match: float | None = None
    location_match: float | None = None
    salary_match: float | None = None


class JobMatch(BaseModel):
    job_id: str
    overall_match: float
    breakdown: JobMatchBreakdown
    weights_used: dict[str, float]

    matched_skills: list[str] = Field(default_factory=list)
    partial_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)

    filtered_out: bool = False
    filter_reasons: list[str] = Field(default_factory=list)


class JobExplanation(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    rank: int
    job: Job
    match: JobMatch
    explanation: JobExplanation
    freshness_bonus: float = 0.0
    adjusted_score: float = 0.0


class RankedRecommendations(BaseModel):
    search_id: str
    status: str
    total_jobs: int
    recommendations: list[Recommendation]


class JobSearchSummary(BaseModel):
    search_id: str
    status: str
    created_at: datetime | None = None
    query: JobSearchPreferences
    strategy: SearchStrategy | None = None
    discovered_count: int = 0
    unique_count: int = 0
    error: str | None = None


class StartAnalysisForJobResponse(BaseModel):
    session_id: str
    status: str
    message: str | None = None


# ---------------------------------------------------------------------------
# Phase 4: provider aggregation metadata
# ---------------------------------------------------------------------------


class ProviderStatus(BaseModel):
    """Per-provider outcome for one search; never exposes raw errors/secrets."""

    model_config = ConfigDict(extra="ignore")

    name: str
    source_type: SourceType = "REAL"
    status: Literal["success", "empty", "error", "skipped"] = "success"
    count: int = 0
    enabled: bool = True
    healthy: bool | None = None
    message: str | None = None  # sanitized, user-safe

    @classmethod
    def sanitize_error(cls, error: str) -> str:
        """Strip anything that smells like a key/URL query string."""
        cleaned = " ".join(str(error).split())
        for token in ("api_key", "apikey", "app_id", "token", "password"):
            cleaned = cleaned.replace(token, "***")
        return cleaned[:200]


class SearchMetadata(BaseModel):
    live_results: bool = False
    cached_results: bool = False
    discovered: int = 0
    unique: int = 0
    duplicates_removed: int = 0
    duration_ms: int | None = None


class Pagination(BaseModel):
    page: int = 1
    limit: int = 20
    total: int = 0
    has_next: bool = False


Job.update_forward_refs()
