"""Deterministic cross-source duplicate detection.

Signals (no LLM involved):
  1. identical application URL (normalized)
  2. identical (source, source_job_id) within the same batch is impossible by
     construction; across sources source ids differ, so URL/title signals apply
  3. same company AND title equivalence via synonym-expanded token subset or
     SequenceMatcher ratio >= threshold
  4. same company AND description similarity >= threshold

Records are grouped (union-find) and merged into one canonical job that keeps
the richest field values plus full provenance.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.config import get_settings
from app.schemas.jobs import Job, SourceRecord
from app.services.skill_normalizer import SkillNormalizer

# Title abbreviations expanded before comparison so "GenAI Engineer" and
# "Generative AI Engineer" compare equal-ish.
_TITLE_EXPANSIONS: tuple[tuple[str, str], ...] = (
    ("generative ai", "genai"),
    ("gen ai", "genai"),
    ("artificial intelligence", "ai"),
    ("machine learning", "ml"),
    ("large language model", "llm"),
    ("k8s", "kubernetes"),
    ("sre", "site reliability engineer"),
    ("sde", "software development engineer"),
)


def normalize_title(title: str, normalizer: SkillNormalizer) -> str:
    lowered = normalizer.display_name(title).lower()
    for long_form, short_form in _TITLE_EXPANSIONS:
        lowered = re.sub(rf"\b{re.escape(long_form)}\b", short_form, lowered)
    return re.sub(r"[^a-z0-9+ ]+", " ", lowered).strip()


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.strip().lower()
    cleaned = re.sub(r"[?&]utm_[^&]*", "", cleaned)
    return cleaned.rstrip("/")


def _tokens(text: str) -> set[str]:
    return {token for token in text.split() if token}


def titles_equivalent(a: str, b: str, normalizer: SkillNormalizer,
                      threshold: float) -> bool:
    na, nb = normalize_title(a, normalizer), normalize_title(b, normalizer)
    if na == nb:
        return True
    ta, tb = _tokens(na), _tokens(nb)
    if ta == tb:
        return True
    # Subset direction catches "AI Engineer" ⊂ "GenAI Engineer" at one company.
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    if abs(len(na) - len(nb)) > 25:
        return False
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def description_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sample_a = a[:4000].strip().lower()
    sample_b = b[:4000].strip().lower()
    if sample_a == sample_b:
        return 1.0
    return SequenceMatcher(None, sample_a, sample_b).ratio()


class DuplicateDetector:
    _MAX_TIME = datetime.max.replace(tzinfo=timezone.utc)

    def __init__(self, skill_normalizer: SkillNormalizer) -> None:
        self._skills = skill_normalizer
        self._skills = skill_normalizer

    def deduplicate(self, jobs: list[Job]) -> list[Job]:
        """Merge duplicates into canonical jobs with provenance attached."""
        settings = get_settings()
        parent = list(range(len(jobs)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            root_i, root_j = find(i), find(j)
            if root_i != root_j:
                parent[max(root_i, root_j)] = min(root_i, root_j)

        url_keys = [normalize_url(job.application_url) for job in jobs]

        for i in range(len(jobs)):
            for j in range(i + 1, len(jobs)):
                a, b = jobs[i], jobs[j]
                if not self._same_company(a.company, b.company):
                    continue
                same_url = (
                    url_keys[i] is not None and url_keys[i] == url_keys[j]
                )
                same_desc = (
                    min(len(a.description), len(b.description)) >= 120
                    and description_similarity(a.description, b.description)
                    >= settings.dedupe_description_threshold
                )
                same_title = titles_equivalent(
                    a.title, b.title, self._skills, settings.dedupe_title_threshold
                )
                exact_title = normalize_title(a.title, self._skills) == \
                    normalize_title(b.title, self._skills)
                same_location = (a.location or "").lower() == (b.location or "").lower()
                if (
                    same_url
                    or (same_desc and same_title)
                    or exact_title
                    or (same_title and same_location)
                ):
                    union(i, j)

        groups: dict[int, list[int]] = {}
        for index in range(len(jobs)):
            groups.setdefault(find(index), []).append(index)

        canonical: list[Job] = []
        for members in groups.values():
            records = [jobs[m] for m in members]
            canonical.append(self._merge(records))
        return canonical

    # -- internals -----------------------------------------------------------
    @staticmethod
    def _same_company(a: str, b: str) -> bool:
        def clean(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", value.lower())

        ca, cb = clean(a), clean(b)
        if not ca or not cb:
            return False
        if ca == cb:
            return True
        # Substring matches only count for meaningful company names.
        return (len(ca) >= 5 and ca in cb) or (len(cb) >= 5 and cb in ca)

    def _merge(self, records: list[Job]) -> Job:
        ordered = sorted(
            records,
            key=lambda job: (
                -self._completeness(job),
                job.posted_at or job.created_at or self._MAX_TIME,
            ),
        )
        canonical = ordered[0].model_copy(deep=True)
        canonical.duplicate_of = []
        for other in ordered[1:]:
            canonical.duplicate_of.append(
                SourceRecord(
                    source=other.source,
                    source_job_id=other.source_job_id,
                    title=other.title,
                    url=other.application_url,
                )
            )
            self._fill_missing_fields(canonical, other)
        return canonical

    @staticmethod
    def _fill_missing_fields(canonical: Job, other: Job) -> None:
        """Keep the richest value per field without overwriting better data."""
        for name in (
            "description", "location", "work_mode", "employment_type",
            "experience_min", "experience_max", "salary_min", "salary_max",
            "salary_currency", "application_url", "posted_at", "source_job_id",
        ):
            current = getattr(canonical, name)
            candidate = getattr(other, name)
            if (current is None or current == "" or current == "unknown") and candidate:
                setattr(canonical, name, candidate)
        if len(other.description or "") > len(canonical.description or ""):
            setattr(canonical, "description", other.description)
        for name in ("required_skills", "preferred_skills"):
            merged = list(dict.fromkeys(getattr(canonical, name) + getattr(other, name)))
            setattr(canonical, name, merged)

    @staticmethod
    def _completeness(job: Job) -> int:
        score = 0
        for value in (
            job.description, job.location, job.salary_min, job.salary_max,
            job.application_url, job.posted_at, job.experience_min,
        ):
            if value not in (None, "", "unknown"):
                score += 1
        score += min(len(job.required_skills), 5)
        return score
