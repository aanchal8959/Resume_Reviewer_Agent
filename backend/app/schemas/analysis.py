"""Pydantic models for skill-gap analysis, match score and the roadmap."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillStatus(str, Enum):
    MATCHED = "matched"
    PARTIAL = "partial"
    MISSING = "missing"


class Importance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SkillGapItem(BaseModel):
    """A single gap with actionable guidance."""

    model_config = ConfigDict(extra="ignore")

    skill: str
    status: SkillStatus
    importance: Importance = Importance.MEDIUM
    reason: str | None = None
    recommended_action: str | None = None


class SkillGapAnalysis(BaseModel):
    matched: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    gaps: list[SkillGapItem] = Field(default_factory=list)

    @field_validator("gaps")
    @classmethod
    def _validate_gaps(cls, value: list[SkillGapItem]) -> list[SkillGapItem]:
        seen: set[str] = set()
        for item in value:
            key = item.skill.strip().lower()
            if key in seen:
                raise ValueError(f"Duplicate gap entry for skill '{item.skill}'")
            seen.add(key)
        return value

    def priority_gaps(self) -> list[SkillGapItem]:
        """Missing/partial gaps ordered high -> medium -> low importance."""
        order = {Importance.HIGH: 0, Importance.MEDIUM: 1, Importance.LOW: 2}
        relevant = [gap for gap in self.gaps if gap.status != SkillStatus.MATCHED]
        return sorted(relevant, key=lambda gap: order[gap.importance])


class ScoreBreakdown(BaseModel):
    required_skills: float
    preferred_skills: float
    experience: float
    project_relevance: float
    education: float


class MatchScore(BaseModel):
    overall_score: float = Field(ge=0.0, le=100.0)
    breakdown: ScoreBreakdown
    weights_used: dict[str, float]


class RoadmapTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    day: int = Field(ge=1)
    topic: str
    goal: str
    estimated_hours: float = Field(gt=0)
    priority: Importance = Importance.MEDIUM


class Roadmap(BaseModel):
    total_days: int = Field(gt=0)
    daily_hours_target: float = Field(gt=0)
    weeks: list[list[RoadmapTask]] = Field(default_factory=list)

    @field_validator("weeks")
    @classmethod
    def _max_seven_days_per_week(
        cls, value: list[list[RoadmapTask]]
    ) -> list[list[RoadmapTask]]:
        for week in value:
            if len(week) > 7:
                raise ValueError("A roadmap week cannot contain more than 7 tasks")
        return value

    def all_tasks(self) -> list[RoadmapTask]:
        return [task for week in self.weeks for task in week]


class SkillClassification(BaseModel):
    """Raw structured LLM output before grouping into a SkillGapAnalysis."""

    model_config = ConfigDict(extra="ignore")

    items: list[SkillGapItem] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Full pipeline output persisted per session."""

    candidate_profile: dict | None = None
    job_profile: dict | None = None
    skill_gap: dict | None = None
    match_score: dict | None = None
    roadmap: dict | None = None
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request/response schemas
# ---------------------------------------------------------------------------


class DocumentUploadResponse(BaseModel):
    session_id: str
    resume_document_id: str
    job_description_document_id: str


class StartAnalysisResponse(BaseModel):
    session_id: str
    status: str
    message: str | None = None


class ErrorResponse(BaseModel):
    detail: str
