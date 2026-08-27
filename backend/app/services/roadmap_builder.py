"""Deterministic 30-day roadmap construction from prioritized skill gaps.

Used directly in mock mode and as a validated fallback/template source when an
LLM produces an unrealistic plan.
"""

from __future__ import annotations

from app.config import get_settings
from app.schemas.analysis import (
    Importance,
    Roadmap,
    RoadmapTask,
    SkillGapAnalysis,
    SkillStatus,
)

_LEARNING_TEMPLATES: list[tuple[str, str]] = [
    ("{skill} fundamentals", "Understand the core concepts and terminology of {skill}."),
    ("{skill} hands-on practice", "Complete guided tutorials or exercises covering {skill}."),
    ("{skill} mini project", "Build a small, focused project that applies {skill} end to end."),
    ("{skill} advanced topics", "Study advanced patterns, pitfalls and best practices for {skill}."),
    ("{skill} interview drills", "Solve common interview questions and explain {skill} design trade-offs."),
]

_REVISION_TEMPLATES: list[tuple[str, str]] = [
    ("Revision", "Review notes for all high-priority gaps covered this month."),
    ("Mock interview practice", "Run a timed mock interview focused on the target role's key skills."),
    ("System design walkthrough", "Sketch the end-to-end architecture implied by the job description."),
    ("Final gap review", "Re-test yourself on every remaining partial/missing skill."),
]

_UNIT_DAYS = {Importance.HIGH: 4, Importance.MEDIUM: 2, Importance.LOW: 1}


def _allocate_days(gaps: list, learning_days: int) -> list[int]:
    """Proportional day allocation; high-importance gaps get more days, min 1 day each."""
    if not gaps:
        return []
    units = [_UNIT_DAYS[gap.importance] for gap in gaps]
    total_units = sum(units)
    raw = [max(1, round(learning_days * unit / total_units)) for unit in units]
    while sum(raw) > learning_days and max(raw) > 1:
        raw[raw.index(max(raw))] -= 1
    while sum(raw) < learning_days:
        raw[raw.index(max(raw))] += 1
    return raw


def build_roadmap(
    skill_gap: SkillGapAnalysis,
    total_days: int | None = None,
    daily_hours: float | None = None,
) -> Roadmap:
    settings = get_settings()
    total_days = total_days or settings.roadmap_days
    daily_hours = daily_hours or settings.daily_study_hours

    priority_order = {Importance.HIGH: 0, Importance.MEDIUM: 1, Importance.LOW: 2}
    gaps = sorted(
        (g for g in skill_gap.gaps if g.status != SkillStatus.MATCHED),
        key=lambda g: priority_order[g.importance],
    )

    revision_days = max(3, total_days // 8)
    learning_days = total_days - revision_days
    allocations = _allocate_days(gaps, learning_days)

    tasks: list[RoadmapTask] = []
    day = 1
    for gap, allocated in zip(gaps, allocations):
        template_index = 0
        for offset in range(allocated):
            topic_tpl, goal_tpl = _LEARNING_TEMPLATES[template_index % len(_LEARNING_TEMPLATES)]
            is_last_day_of_gap = offset == allocated - 1
            hours = daily_hours if not is_last_day_of_gap else max(1.0, daily_hours / 2)
            tasks.append(
                RoadmapTask(
                    day=day,
                    topic=topic_tpl.format(skill=gap.skill),
                    goal=goal_tpl.format(skill=gap.skill),
                    estimated_hours=float(hours),
                    priority=gap.importance,
                )
            )
            day += 1
            template_index += 1

    for topic_tpl, goal_tpl in _REVISION_TEMPLATES[:revision_days]:
        tasks.append(
            RoadmapTask(
                day=day,
                topic=topic_tpl,
                goal=goal_tpl,
                estimated_hours=min(daily_hours, 2.0),
                priority=Importance.MEDIUM,
            )
        )
        day += 1

    weeks: list[list[RoadmapTask]] = [tasks[i : i + 7] for i in range(0, len(tasks), 7)]
    return Roadmap(total_days=total_days, daily_hours_target=daily_hours, weeks=weeks)
