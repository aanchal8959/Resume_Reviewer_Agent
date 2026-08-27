"""Pydantic models describing the target job, extracted strictly from the JD text."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JobProfile(BaseModel):
    """Structured job description analysis. Required vs preferred is explicit."""

    model_config = ConfigDict(extra="ignore")

    company: str | None = None
    role: str | None = None
    required_experience_years: float | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    cloud_technologies: list[str] = Field(default_factory=list)
    ai_ml_technologies: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    system_design_requirements: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    def all_requirements(self) -> list[str]:
        """Every skill-like requirement (required first). Used by the gap agent."""
        return (
            self.required_skills
            + self.preferred_skills
            + self.programming_languages
            + self.frameworks
            + self.cloud_technologies
            + self.ai_ml_technologies
            + self.databases
            + self.system_design_requirements
        )
