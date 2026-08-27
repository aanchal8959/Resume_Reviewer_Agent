"""Roadmap generation tests: priority ordering, coverage and realism."""

from app.schemas.analysis import (
    Importance,
    Roadmap,
    SkillGapAnalysis,
    SkillGapItem,
    SkillStatus,
)
from app.services.roadmap_builder import build_roadmap


def _gap(skill: str, importance: Importance) -> SkillGapItem:
    return SkillGapItem(skill=skill, status=SkillStatus.MISSING, importance=importance)


def _analysis(*gaps: SkillGapItem) -> SkillGapAnalysis:
    analysis = SkillGapAnalysis(
        gaps=list(gaps),
        missing=[g.skill for g in gaps if g.status == SkillStatus.MISSING],
    )
    return analysis


def test_high_priority_gaps_come_first():
    analysis = _analysis(
        _gap("Terraform", Importance.LOW),
        _gap("System Design", Importance.MEDIUM),
        _gap("Kubernetes", Importance.HIGH),
        _gap("MLOps", Importance.HIGH),
    )
    roadmap = build_roadmap(analysis, total_days=30, daily_hours=2)

    first_day_per_skill = {}
    for task in roadmap.all_tasks():
        for skill in ("Kubernetes", "MLOps", "System Design", "Terraform"):
            if task.topic.startswith(skill):
                first_day_per_skill.setdefault(skill, task.day)

    assert first_day_per_skill["Kubernetes"] < first_day_per_skill["MLOps"]
    assert first_day_per_skill["MLOps"] < first_day_per_skill["System Design"]
    assert first_day_per_skill["System Design"] < first_day_per_skill["Terraform"]


def test_plan_covers_exactly_30_days():
    analysis = _analysis(_gap("Kubernetes", Importance.HIGH))
    roadmap = build_roadmap(analysis, total_days=30, daily_hours=2)
    days = sorted(task.day for task in roadmap.all_tasks())
    assert days == list(range(1, 31))
    assert len(roadmap.weeks) == 5


def test_daily_hours_never_exceeded():
    analysis = _analysis(
        _gap("Kubernetes", Importance.HIGH),
        _gap("MLOps", Importance.MEDIUM),
    )
    roadmap = build_roadmap(analysis, total_days=30, daily_hours=2)
    assert all(task.estimated_hours <= 2.0 for task in roadmap.all_tasks())
    assert all(task.estimated_hours > 0 for task in roadmap.all_tasks())


def test_revision_included_at_end():
    analysis = _analysis(_gap("Kubernetes", Importance.HIGH))
    roadmap = build_roadmap(analysis, total_days=30, daily_hours=2)
    last_week = roadmap.weeks[-1]
    assert any("revision" in task.topic.lower() or "mock interview" in task.topic.lower()
               for task in last_week)


def test_empty_gaps_still_produces_valid_shape():
    roadmap = build_roadmap(_analysis(), total_days=30, daily_hours=2)
    assert isinstance(roadmap, Roadmap)
