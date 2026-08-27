"""Deterministic candidate-vs-job matching (Phase 2).

No LLM involvement: every component is a transparent ratio, weights are
configurable, and missing data (salary/location unknown on the job side,
preferences not provided by the user) causes weight redistribution rather than
an unfair penalty.
"""

from __future__ import annotations

from app.config import get_settings
from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import Job, JobExplanation, JobMatch, JobMatchBreakdown
from app.services.gap_classifier import classify_skill_gaps
from app.services.matching import find_match, find_partial, tokenize
from app.services.skill_normalizer import SkillNormalizer

ALL_WEIGHT_KEYS = (
    "required_skill_match", "preferred_skill_match", "role_match",
    "experience_match", "location_match", "salary_match",
)


def _skill_coverage(required: list[str], evidence: list[str]) -> tuple[float, int, int]:
    if not required:
        return 1.0, 0, 0
    full = sum(1 for skill in required if find_match(skill, evidence))
    partial = sum(1 for skill in required if not find_match(skill, evidence)
                  and find_partial(skill, evidence))
    score = (full + 0.5 * partial) / len(required)
    return min(score, 1.0), full, len(required)


def _role_similarity(candidate_role: str | None, title: str) -> float:
    if not candidate_role:
        return 1.0
    a = " ".join(sorted(tokenize(candidate_role)))
    b = " ".join(sorted(tokenize(title)))
    if not a or not b:
        return 0.5
    from difflib import SequenceMatcher

    ratio = SequenceMatcher(None, a, b).ratio()
    tokens_a, tokens_b = set(tokenize(candidate_role)), set(tokenize(title))
    jaccard = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
    return max(ratio, jaccard)


def _experience_score(cand_years: float | None, job_min: float | None,
                      job_max: float | None) -> float:
    """All return values are on a 0-100 scale."""
    if job_min is None and job_max is None:
        return 100.0
    if cand_years is None:
        return 0.5
    low = job_min if job_min is not None else 0.0
    high = job_max if job_max is not None else low
    if cand_years < low:
        # Shortfall ratio; large shortfalls collapse toward zero quickly.
        return max(0.0, cand_years / low) ** 2 * 100
    if high > 0 and cand_years > high * 2:
        return 85.0  # significantly overqualified: mild penalty, not disqualifying
    return 100.0


def _location_score(job: Job, preferences) -> float | None:
    """None => component not applicable (weight redistributed)."""
    wanted = [loc.strip().lower() for loc in (preferences.locations or []) if loc.strip()]
    modes = list(preferences.work_modes or [])
    remote_ok = preferences.remote is True or "remote" in modes
    any_pref_given = bool(wanted) or remote_ok or bool(modes)
    if not any_pref_given:
        return None
    job_location = (job.location or "").strip().lower()
    job_mode = getattr(job, "work_mode", "unknown") or "unknown"

    if job_mode == "remote" and (remote_ok or not wanted):
        return 100.0
    if wanted:
        for city in wanted:
            if city in job_location or job_location in city:
                return 100.0
        if job_location == "":
            return 50.0  # unknown location with stated preference: neutral credit
        return 0.0
    if modes and job_mode in modes:
        return 100.0
    return 40.0  # only a work-mode was requested and the job does not match


def _salary_score(job: Job, salary_min_pref: float | None) -> float | None:
    if salary_min_pref is None:
        return None  # user gave no expectation -> redistribute
    if job.salary_max is None:
        return None  # job hides salary -> redistribute, never punish
    if job.salary_max >= salary_min_pref:
        return 100.0
    if job.salary_max <= 0:
        return 0.0
    return round(job.salary_max / salary_min_pref * 100, 1)


class JobMatchingService:
    def __init__(self, skill_normalizer: SkillNormalizer) -> None:
        self._skills = skill_normalizer

    def match(
        self,
        candidate: CandidateProfile,
        job: Job,
        preferences=None,
        weights: dict[str, float] | None = None,
    ) -> JobMatch:
        settings = get_settings()
        if preferences is None:
            from app.schemas.jobs import JobSearchPreferences

            preferences = JobSearchPreferences()
        weights = dict(weights or settings.job_match_weights)

        evidence = candidate.all_skills() + candidate.project_technologies()
        req_score, _full_req, _total_req = _skill_coverage(
            job.required_skills, evidence
        )
        pref_score, _full_pref, _total_pref = _skill_coverage(
            job.preferred_skills, evidence
        )
        role_score = _role_similarity(candidate.current_role, job.title)
        exp_score = _experience_score(
            candidate.total_experience_years, job.experience_min, job.experience_max
        )

        components: dict[str, float | None] = {
            "required_skill_match": req_score * 100,
            "preferred_skill_match": pref_score * 100,
            "role_match": role_score * 100,
            "experience_match": exp_score,
            "location_match": _location_score(job, preferences),
            "salary_match": _salary_score(
                job, getattr(preferences, "salary_min", None)
            ),
        }

        active_weight_total = sum(
            w for key, w in weights.items() if components.get(key) is not None
        )
        breakdown_values: dict[str, float] = {}
        overall = 0.0
        for key in ALL_WEIGHT_KEYS:
            value = components[key]
            if value is None:
                continue
            share = weights[key] / active_weight_total if active_weight_total else 0.0
            breakdown_values[key] = round(value, 1)
            overall += value * share

        gap_analysis = classify_skill_gaps(
            candidate,
            self._job_to_profile(job),
        )
        matched_display = self._skills.normalize_list(gap_analysis.matched)
        partial_display = self._skills.normalize_list(gap_analysis.partial)
        missing_display = self._skills.normalize_list(gap_analysis.missing)

        risk_factors = self._risk_factors(candidate, job, req_score, exp_score)

        return JobMatch(
            job_id=job.id or "",
            overall_match=round(overall, 1),
            breakdown=JobMatchBreakdown(**breakdown_values),
            weights_used=dict(weights),
            matched_skills=matched_display,
            partial_skills=partial_display,
            missing_skills=missing_display,
            risk_factors=risk_factors,
        )

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _job_to_profile(job: Job):
        from app.schemas.job import JobProfile

        return JobProfile(
            role=job.title,
            required_experience_years=job.experience_min,
            required_skills=job.required_skills,
            preferred_skills=job.preferred_skills,
        )

    @staticmethod
    def _risk_factors(candidate: CandidateProfile, job: Job,
                      req_ratio: float, exp_score: float) -> list[str]:
        risks: list[str] = []
        cand_years = candidate.total_experience_years
        if job.experience_min is not None and cand_years is not None \
                and cand_years < job.experience_min:
            shortfall = job.experience_min - cand_years
            risks.append(
                f"Requires {job.experience_min:g}+ years experience "
                f"(candidate has {cand_years:g})"
                if shortfall >= 1 else
                f"Slightly under the {job.experience_min:g}-year bar"
            )
        if job.required_skills and req_ratio < 0.5:
            risks.append("More than half of the required skills are unproven")
        if job.experience_min is not None and cand_years is not None \
                and job.experience_max is not None \
                and cand_years > job.experience_max * 2:
            risks.append("Candidate may be overqualified for this band")
        if exp_score < 40:
            risks.append("Experience fit is critically low")
        return risks

    def explain(self, job: Job, match: JobMatch) -> JobExplanation:
        """Fact-based explanation derived ONLY from structured match results."""
        strengths: list[str] = []
        gaps: list[str] = []

        strong_matched = [
            skill for skill in match.matched_skills
            if skill.lower() in {s.lower() for s in job.required_skills}
        ]
        if strong_matched[:4]:
            strengths.append(
                "Strong match: " + ", ".join(strong_matched[:4])
            )
        preferred_hits = [
            skill for skill in match.matched_skills
            if skill.lower() not in {s.lower() for s in strong_matched}
            and skill.lower() in {s.lower() for s in job.preferred_skills}
        ]
        if preferred_hits:
            strengths.append("Preferred skills covered: " + ", ".join(preferred_hits[:3]))
        if match.breakdown.experience_match >= 99:
            strengths.append("Experience fits the advertised band")
        elif match.breakdown.experience_match < 50:
            gaps.append(f"Experience fit is low ({match.breakdown.experience_match:.0f}%)")
        if match.breakdown.role_match >= 80:
            strengths.append("Role aligns with your current profile")
        elif match.breakdown.role_match < 40:
            gaps.append("Role differs from your current experience")

        for skill in match.partial_skills[:3]:
            gaps.append(f"{skill}: related experience, needs strengthening")
        for skill in match.missing_skills[:3]:
            gaps.append(f"{skill} experience is missing")
        for risk in match.risk_factors:
            gaps.append(risk)

        return JobExplanation(strengths=strengths, gaps=gaps)

