"""Render a normalized JobRow as plain text (for Phase 1 pipeline reuse)."""

from __future__ import annotations

from typing import Any


def render_job_as_text(row: Any) -> str:
    lines = [
        f"{row.title}",
        f"Company: {row.company}",
    ]
    if row.location:
        lines.append(f"Location: {row.location} ({row.work_mode})")
    if row.experience_min is not None or row.experience_max is not None:
        low = row.experience_min if row.experience_min is not None else "?"
        high = row.experience_max if row.experience_max is not None else low
        lines.append(f"Required experience: {low} to {high} years")
    if row.salary_min is not None:
        currency = row.salary_currency or "INR"
        lines.append(f"Salary: {row.salary_min:g} - {row.salary_max:g} LPA ({currency})")
    if row.required_skills:
        lines.append("REQUIREMENTS:")
        lines.extend(f"- Hands-on experience with {skill}" for skill in row.required_skills)
    if row.preferred_skills:
        lines.append("PREFERRED / NICE TO HAVE:")
        lines.extend(f"- Exposure to {skill}" for skill in row.preferred_skills)
    if row.description:
        lines.append("")
        lines.append(row.description)
    if row.application_url:
        lines.append("")
        lines.append(f"Apply at: {row.application_url}")
    return "\n".join(lines)
