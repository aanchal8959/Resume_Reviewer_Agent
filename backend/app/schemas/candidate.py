"""Pydantic models describing the candidate, extracted strictly from the resume.

Hallucination policy: every field is Optional or defaulted; agents must set
None / "unknown" instead of guessing values that are not present in the resume.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RoleEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    company: str | None = None
    duration: str | None = None


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    degree: str
    institution: str | None = None
    year: str | None = None


class Certification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    issuer: str | None = None
    year: str | None = None


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """Structured candidate profile extracted from a resume."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    total_experience_years: float | None = None
    current_role: str | None = None
    previous_roles: list[RoleEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    cloud_platforms: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    ai_ml_skills: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    domain_experience: list[str] = Field(default_factory=list)

    def all_skills(self) -> list[str]:
        """Aggregated skill vocabulary used by the skill-gap matcher."""
        return (
            self.technical_skills
            + self.programming_languages
            + self.frameworks
            + self.cloud_platforms
            + self.databases
            + self.ai_ml_skills
        )

    def project_technologies(self) -> list[str]:
        """Technologies evidenced by projects (used for project-relevance scoring)."""
        techs: list[str] = []
        for project in self.projects:
            techs.extend(project.technologies)
        return techs

    def education_text(self) -> list[str]:
        """Degree/certification strings used for education scoring."""
        entries = [entry.degree for entry in self.education]
        entries.extend(cert.name for cert in self.certifications)
        return entries
