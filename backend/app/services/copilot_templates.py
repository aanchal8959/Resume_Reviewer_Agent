"""Deterministic insight derivation shared by the Company Research Agent.

These are business-logic rules connecting structured inputs (job requirements,
company info, skill gaps) — not mock data and not an LLM replacement.
"""

from __future__ import annotations

from app.schemas.applications import CompanyInfo


def build_company_insights(
    info: CompanyInfo,
    job_title: str,
    job_skills: list[str],
    prep_areas: list[str],
) -> dict:
    overlap = [
        area for area in info.technology_areas
        if any(area.lower() in s.lower() or s.lower() in area.lower()
               for s in job_skills)
    ]
    why_role_matters = (
        f"The {job_title} role connects directly to {info.name}'s work on "
        f"{', '.join(overlap[:3])}."
        if overlap else
        f"Public information connecting the {job_title} role to {info.name}'s "
        "priorities is limited; review their products and ask about team focus "
        "in early conversations."
    ) if info.name else "Not available."
    tech_environment = sorted(set(info.technology_areas + job_skills[:4]))
    return {
        "what_they_do": info.description or "Not available.",
        "why_role_matters": why_role_matters,
        "technology_environment": tech_environment,
        "interview_prep_areas": [
            f"Given the role requirements, {area} is likely an important "
            "preparation area." for area in prep_areas[:4]
        ] or ["Review the job description's core requirements before interviews."],
    }


__all__ = ["build_company_insights"]
