"""Roadmap Agent: gaps + score -> realistic 30-day preparation plan.

An LLM-generated plan is accepted only if it passes realism validation;
otherwise the deterministic builder takes over.
"""

from __future__ import annotations

from app.agents.base import AgentError, format_model
from app.config import get_settings
from app.schemas.analysis import MatchScore, Roadmap, ScoreBreakdown, SkillGapAnalysis
from app.services.llm_service import LLMError, LLMProvider
from app.services.match_scorer import DEFAULT_WEIGHTS
from app.services.roadmap_builder import build_roadmap

_SYSTEM_PROMPT = (
    "You are a career coach that builds realistic day-by-day preparation "
    "roadmaps for candidates switching jobs.\n"
    "RULES:\n"
    "1. Cover exactly the requested number of days (day numbers 1..N, no gaps).\n"
    "2. Prioritize high-importance missing skills before medium/low ones.\n"
    "3. Never exceed the daily hours target; keep every estimated_hours > 0.\n"
    "4. Reserve roughly the last quarter for revision and mock interviews.\n"
    "5. Base topics ONLY on the provided skill gaps and job requirements.\n"
)


def build_user_prompt(
    skill_gap: SkillGapAnalysis,
    match_score: MatchScore,
    total_days: int,
    daily_hours: float,
) -> str:
    return (
        f"Create a {total_days}-day preparation roadmap with a maximum of "
        f"{daily_hours} study hours per day.\n\n"
        f"<match_score>\n{format_model(match_score)}\n</match_score>\n\n"
        f"<prioritized_gaps>\n{format_model(skill_gap.priority_gaps())}\n</prioritized_gaps>"
    )


def validate_plan(roadmap: Roadmap, total_days: int, daily_hours: float) -> list[str]:
    """Returns a list of realism violations (empty list = plan accepted)."""
    tasks = roadmap.all_tasks()
    days = [task.day for task in tasks]
    problems: list[str] = []
    if sorted(days) != list(range(1, total_days + 1)):
        problems.append(f"Plan must cover days 1..{total_days} exactly once")
    if any(task.estimated_hours <= 0 or task.estimated_hours > daily_hours + 0.51 for task in tasks):
        problems.append("Every task must be within the daily hours target")
    return problems


class RoadmapAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def run(
        self,
        skill_gap: SkillGapAnalysis,
        match_score: MatchScore | None = None,
    ) -> Roadmap:
        settings = get_settings()
        score = match_score if match_score is not None else self._neutral_score()
        try:
            roadmap = self._provider.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=build_user_prompt(
                    skill_gap, score, settings.roadmap_days, settings.daily_study_hours
                ),
                response_model=Roadmap,
                context={
                    "skill_gap": skill_gap,
                    "total_days": settings.roadmap_days,
                    "daily_hours": settings.daily_study_hours,
                },
            )
            if not validate_plan(roadmap, settings.roadmap_days, settings.daily_study_hours):
                return roadmap
        except (LLMError, AgentError):
            pass
        # Deterministic fallback keeps the product functional even when the LLM
        # fails or returns an unrealistic/malformed plan.
        return build_roadmap(
            skill_gap, total_days=settings.roadmap_days, daily_hours=settings.daily_study_hours
        )

    @staticmethod
    def _neutral_score() -> MatchScore:
        return MatchScore(
            overall_score=0,
            breakdown=ScoreBreakdown(
                required_skills=0,
                preferred_skills=0,
                experience=0,
                project_relevance=0,
                education=0,
            ),
            weights_used=dict(DEFAULT_WEIGHTS),
        )
