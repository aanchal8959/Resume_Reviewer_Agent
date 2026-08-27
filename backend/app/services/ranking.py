"""Deterministic ranking: filter impossible jobs, freshness bonus, order."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings
from app.schemas.jobs import Job, JobMatch, Recommendation


def freshness_bonus(posted_at: datetime | None) -> float:
    if posted_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    reference = posted_at
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - reference).total_seconds() / 86400)
    if age_days <= 7:
        return 2.0
    if age_days <= 14:
        return 1.0
    return 0.0


class RankingService:
    """Filters clearly-impossible matches and orders the rest."""

    def __init__(self, matcher) -> None:
        self._settings = get_settings()
        self._matcher = matcher

    def rank(
        self,
        jobs_with_matches: list[tuple[Job, JobMatch]],
        preferences=None,
    ) -> list[Recommendation]:
        min_match = getattr(preferences, "min_match_percent", None)
        results: list[Recommendation] = []
        rank = 1
        entries: list[tuple[float, float, float, int, Job, JobMatch]] = []
        for job, match in jobs_with_matches:
            if match.filtered_out or match.filter_reasons:
                continue
            if min_match is not None and match.overall_match < min_match:
                continue
            bonus = freshness_bonus(job.posted_at)
            adjusted = round(min(100.0, match.overall_match + bonus), 1)
            entries.append((adjusted, match.breakdown.experience_match,
                            job.salary_max or 0.0, len(entries), job, match))
        # Best score first; ties broken by experience fit, then salary, then stable.
        entries.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
        for adjusted, _exp, _salary, _idx, job, match in entries[: self._settings.ranking_top_n]:
            results.append(
                Recommendation(
                    rank=rank,
                    job=job,
                    match=match,
                    explanation=self._matcher.explain(job, match),
                    freshness_bonus=freshness_bonus(job.posted_at),
                    adjusted_score=adjusted,
                )
            )
            rank += 1
        return results

    @staticmethod
    def apply_filters(match: JobMatch) -> JobMatch:
        """Mark matches that should not be recommended at all."""
        settings = get_settings()
        reasons: list[str] = []
        experience = match.breakdown.experience_match
        if experience is not None and experience < settings.ranking_min_experience_ratio * 100:
            reasons.append("Experience requirement far exceeds candidate profile")
        critical_risk = any("critically low" in risk for risk in match.risk_factors)
        if critical_risk:
            reasons.append("Critical experience mismatch")
        if reasons:
            return match.model_copy(update={"filtered_out": True,
                                            "filter_reasons": reasons})
        return match

